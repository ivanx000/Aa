import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.main as main_module
from app.db.database import Base, Posting, get_db


@pytest.fixture()
def client(monkeypatch):
    """TestClient wired to an isolated in-memory DB — never touches pipeline.db."""
    # StaticPool keeps a single connection alive across threads, otherwise each
    # new connection to sqlite:///:memory: gets its own throwaway database.
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    TestingSession = sessionmaker(bind=engine)

    def override_get_db():
        db = TestingSession()
        try:
            yield db
        finally:
            db.close()

    # Prevent the app's lifespan from calling init_db() against the real pipeline.db
    monkeypatch.setattr(main_module, "init_db", lambda: None)
    main_module.app.dependency_overrides[get_db] = override_get_db

    with TestClient(main_module.app) as test_client:
        yield test_client, TestingSession

    main_module.app.dependency_overrides.clear()
    engine.dispose()


def _add_posting(Session, url, status="new", **overrides):
    fields = {
        "url": url,
        "title": "Software Engineering Intern",
        "company": "Acme",
        "description": "Remote internship.",
        "source": "hn_who_is_hiring",
        "status": status,
    }
    fields.update(overrides)
    session = Session()
    session.add(Posting(**fields))
    session.commit()
    session.close()


# ---------------------------------------------------------------------------
# /health
# ---------------------------------------------------------------------------

def test_health(client):
    test_client, _ = client
    resp = test_client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


# ---------------------------------------------------------------------------
# GET /postings
# ---------------------------------------------------------------------------

def test_get_postings_empty(client):
    test_client, _ = client
    resp = test_client.get("/postings")
    assert resp.status_code == 200
    assert resp.json() == []


def test_get_postings_returns_all_by_default(client):
    test_client, Session = client
    _add_posting(Session, "https://example.com/1", status="new")
    _add_posting(Session, "https://example.com/2", status="rejected")

    resp = test_client.get("/postings")
    assert resp.status_code == 200
    urls = {p["url"] for p in resp.json()}
    assert urls == {"https://example.com/1", "https://example.com/2"}


def test_get_postings_filters_by_status(client):
    test_client, Session = client
    _add_posting(Session, "https://example.com/1", status="new")
    _add_posting(Session, "https://example.com/2", status="rejected")

    resp = test_client.get("/postings", params={"status": "rejected"})
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 1
    assert body[0]["url"] == "https://example.com/2"


# ---------------------------------------------------------------------------
# PATCH /postings/{url}/status
# ---------------------------------------------------------------------------

def test_patch_status_success(client):
    test_client, Session = client
    _add_posting(Session, "https://example.com/1")

    resp = test_client.patch(
        "/postings/https://example.com/1/status", params={"status": "reviewed"}
    )
    assert resp.status_code == 200
    assert resp.json() == {"url": "https://example.com/1", "status": "reviewed"}


def test_patch_status_invalid_status(client):
    test_client, Session = client
    _add_posting(Session, "https://example.com/1")

    resp = test_client.patch(
        "/postings/https://example.com/1/status", params={"status": "archived"}
    )
    assert resp.status_code == 200
    assert "error" in resp.json()


def test_patch_status_not_found(client):
    test_client, _ = client
    resp = test_client.patch(
        "/postings/https://example.com/missing/status", params={"status": "sent"}
    )
    assert resp.status_code == 200
    assert resp.json() == {"error": "Posting not found"}


# ---------------------------------------------------------------------------
# /ingestion routes — fetch_and_store / run_pipeline are mocked out so no
# real network calls happen
# ---------------------------------------------------------------------------

def test_ingestion_run_calls_fetch_and_store(client, monkeypatch):
    test_client, _ = client
    calls = {}

    def fake_fetch_and_store(source, db):
        calls["source"] = source
        return {"fetched": 3, "new": 2, "skipped": 1}

    monkeypatch.setattr("app.ingestion.router.fetch_and_store", fake_fetch_and_store)

    resp = test_client.post("/ingestion/run", params={"source": "remoteok"})

    assert resp.status_code == 200
    assert resp.json() == {"fetched": 3, "new": 2, "skipped": 1}
    assert calls["source"] == "remoteok"


def test_ingestion_pipeline_calls_run_pipeline(client, monkeypatch):
    test_client, _ = client
    calls = {}

    def fake_run_pipeline(source, db):
        calls["source"] = source
        return {"source": source, "ingested": 5, "new": 4, "rejected": 1, "ready_to_review": 3}

    monkeypatch.setattr("app.ingestion.router.run_pipeline", fake_run_pipeline)

    resp = test_client.post("/ingestion/pipeline", params={"source": "adzuna"})

    assert resp.status_code == 200
    assert resp.json()["ready_to_review"] == 3
    assert calls["source"] == "adzuna"


def test_ingestion_run_defaults_to_hn_source(client, monkeypatch):
    test_client, _ = client
    calls = {}

    monkeypatch.setattr(
        "app.ingestion.router.fetch_and_store",
        lambda source, db: calls.setdefault("source", source) or {"fetched": 0, "new": 0, "skipped": 0},
    )

    test_client.post("/ingestion/run")
    assert calls["source"] == "hn_who_is_hiring"
