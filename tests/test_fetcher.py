from datetime import datetime, timezone

from app.db.database import Posting
from app.ingestion.fetcher import MIN_POSTING_LENGTH, _is_real_posting, _store


# ---------------------------------------------------------------------------
# _is_real_posting
# ---------------------------------------------------------------------------

GOOD_POSTING = (
    "Acme Corp | Toronto, ON | Full-time | Remote OK\n\n"
    "We are looking for a software engineering intern to join our growing "
    "platform team. You'll work on our core API, ship features weekly, and "
    "pair with senior engineers."
)


def test_is_real_posting_accepts_normal_posting():
    assert _is_real_posting(GOOD_POSTING)


def test_is_real_posting_rejects_too_short_text():
    short_text = "Acme Corp | Toronto | hiring an intern"
    assert len(short_text) < MIN_POSTING_LENGTH
    assert not _is_real_posting(short_text)


def test_is_real_posting_rejects_junk_first_lines():
    junk_first_lines = [
        "Is anyone still looking for engineers? " + "x" * 150,
        "Hi, thanks for reading my comment. " + "x" * 150,
        "I'm a CS student looking for opportunities. " + "x" * 150,
        "Still hiring? " + "x" * 150,
        "Any update on this thread? " + "x" * 150,
        "Applied for this two weeks ago. " + "x" * 150,
        "Formatting error, please ignore. " + "x" * 150,
    ]
    for text in junk_first_lines:
        assert not _is_real_posting(text), text


def test_is_real_posting_only_checks_first_line_for_junk():
    # Junk phrase appears in the body, not the first line — should still pass
    text = GOOD_POSTING + "\nAny update? We are still reviewing applications."
    assert _is_real_posting(text)


# ---------------------------------------------------------------------------
# _store (dedup logic)
# ---------------------------------------------------------------------------

def _raw_posting(url="https://example.com/job/1", **overrides):
    posting = {
        "url": url,
        "title": "Software Engineering Intern",
        "company": "Acme",
        "description": "Remote internship.",
        "source": "hn_who_is_hiring",
        "posted_at": datetime.now(timezone.utc),
    }
    posting.update(overrides)
    return posting


def test_store_inserts_new_postings(db_session):
    raw = [_raw_posting(url="https://example.com/job/1")]
    result = _store(raw, db_session)

    assert result == {"fetched": 1, "new": 1, "skipped": 0}
    assert db_session.query(Posting).count() == 1


def test_store_skips_duplicate_urls(db_session):
    existing = Posting(**_raw_posting(url="https://example.com/job/1"))
    db_session.add(existing)
    db_session.commit()

    raw = [_raw_posting(url="https://example.com/job/1")]
    result = _store(raw, db_session)

    assert result == {"fetched": 1, "new": 0, "skipped": 1}
    assert db_session.query(Posting).count() == 1


def test_store_mixed_new_and_duplicate(db_session):
    db_session.add(Posting(**_raw_posting(url="https://example.com/job/1")))
    db_session.commit()

    raw = [
        _raw_posting(url="https://example.com/job/1"),  # duplicate
        _raw_posting(url="https://example.com/job/2"),  # new
    ]
    result = _store(raw, db_session)

    assert result == {"fetched": 2, "new": 1, "skipped": 1}
    assert db_session.query(Posting).count() == 2


def test_store_empty_list(db_session):
    result = _store([], db_session)
    assert result == {"fetched": 0, "new": 0, "skipped": 0}
