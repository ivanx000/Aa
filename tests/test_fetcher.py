from datetime import datetime, timezone

from app.db.database import Posting
from app.ingestion.fetcher import _store


# ---------------------------------------------------------------------------
# _store (dedup logic)
# ---------------------------------------------------------------------------

def _raw_posting(url="https://example.com/job/1", **overrides):
    posting = {
        "url": url,
        "title": "Software Engineering Intern",
        "company": "Acme",
        "description": "Remote internship.",
        "source": "linkedin",
        "posted_at": datetime.now(timezone.utc),
    }
    posting.update(overrides)
    return posting


def test_store_inserts_new_postings(db_session):
    raw = [_raw_posting(url="https://example.com/job/1")]
    result = _store(raw, db_session)

    assert result["fetched"] == 1
    assert result["new"] == 1
    assert result["skipped"] == 0
    assert db_session.query(Posting).count() == 1


def test_store_skips_duplicate_urls(db_session):
    existing = Posting(**_raw_posting(url="https://example.com/job/1"))
    db_session.add(existing)
    db_session.commit()

    raw = [_raw_posting(url="https://example.com/job/1")]
    result = _store(raw, db_session)

    assert result["fetched"] == 1
    assert result["new"] == 0
    assert result["skipped"] == 1
    assert db_session.query(Posting).count() == 1


def test_store_mixed_new_and_duplicate(db_session):
    db_session.add(Posting(**_raw_posting(url="https://example.com/job/1")))
    db_session.commit()

    raw = [
        _raw_posting(url="https://example.com/job/1"),  # duplicate
        _raw_posting(url="https://example.com/job/2"),  # new
    ]
    result = _store(raw, db_session)

    assert result["fetched"] == 2
    assert result["new"] == 1
    assert result["skipped"] == 1
    assert db_session.query(Posting).count() == 2


def test_store_empty_list(db_session):
    result = _store([], db_session)
    assert result["fetched"] == 0
    assert result["new"] == 0
    assert result["skipped"] == 0
