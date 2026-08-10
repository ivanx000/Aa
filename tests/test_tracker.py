import json
from datetime import datetime, timezone

from app.db.database import Posting
from app.tracker.tracker import list_postings, update_status


def _add_posting(db_session, url, status="new", **overrides):
    fields = {
        "url": url,
        "title": "Software Engineering Intern",
        "company": "Acme",
        "description": "Remote internship.",
        "source": "hn_who_is_hiring",
        "status": status,
        "fetched_at": datetime.now(timezone.utc),
    }
    fields.update(overrides)
    posting = Posting(**fields)
    db_session.add(posting)
    db_session.commit()
    return posting


# ---------------------------------------------------------------------------
# update_status
# ---------------------------------------------------------------------------

def test_update_status_success(db_session):
    _add_posting(db_session, "https://example.com/1")

    result = update_status("https://example.com/1", "reviewed", db_session)

    assert result == {"url": "https://example.com/1", "status": "reviewed"}
    posting = db_session.query(Posting).filter_by(url="https://example.com/1").one()
    assert posting.status == "reviewed"


def test_update_status_rejects_invalid_status(db_session):
    _add_posting(db_session, "https://example.com/1")

    result = update_status("https://example.com/1", "archived", db_session)

    assert "error" in result
    posting = db_session.query(Posting).filter_by(url="https://example.com/1").one()
    assert posting.status == "new"  # unchanged


def test_update_status_posting_not_found(db_session):
    result = update_status("https://example.com/missing", "sent", db_session)
    assert result == {"error": "Posting not found"}


# ---------------------------------------------------------------------------
# list_postings
# ---------------------------------------------------------------------------

def test_list_postings_no_filter_returns_all(db_session):
    _add_posting(db_session, "https://example.com/1", status="new")
    _add_posting(db_session, "https://example.com/2", status="rejected")

    results = list_postings(None, db_session)

    assert {r["url"] for r in results} == {
        "https://example.com/1",
        "https://example.com/2",
    }


def test_list_postings_filters_by_status(db_session):
    _add_posting(db_session, "https://example.com/1", status="new")
    _add_posting(db_session, "https://example.com/2", status="rejected")

    results = list_postings("rejected", db_session)

    assert len(results) == 1
    assert results[0]["url"] == "https://example.com/2"


def test_list_postings_decodes_keywords_json(db_session):
    _add_posting(
        db_session,
        "https://example.com/1",
        keywords=json.dumps(["python", "fastapi"]),
    )

    results = list_postings(None, db_session)

    assert results[0]["keywords"] == ["python", "fastapi"]


def test_list_postings_empty_keywords_defaults_to_empty_list(db_session):
    _add_posting(db_session, "https://example.com/1")

    results = list_postings(None, db_session)

    assert results[0]["keywords"] == []
