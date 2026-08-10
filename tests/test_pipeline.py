from app.db.database import Posting
from app.pipeline import run_pipeline


def _add_posting(db_session, url, title, description, status="new", draft=None):
    posting = Posting(
        url=url,
        title=title,
        company="Acme",
        description=description,
        source="hn_who_is_hiring",
        status=status,
        draft=draft,
    )
    db_session.add(posting)
    return posting


def test_run_pipeline_rejects_non_matching_postings(monkeypatch, db_session):
    # A relevant posting and an irrelevant one already sitting in the DB as "new"
    _add_posting(
        db_session,
        "https://example.com/1",
        "Machine Learning Intern",
        "Remote internship on ML pipelines.",
    )
    _add_posting(
        db_session,
        "https://example.com/2",
        "Senior Software Engineer",
        "Onsite in New York, 10 years experience.",
    )
    db_session.commit()

    monkeypatch.setattr(
        "app.pipeline.fetch_and_store",
        lambda source, db: {"fetched": 0, "new": 0, "skipped": 0},
    )

    result = run_pipeline(source="hn_who_is_hiring", db=db_session)

    relevant = db_session.query(Posting).filter_by(url="https://example.com/1").one()
    irrelevant = db_session.query(Posting).filter_by(url="https://example.com/2").one()

    assert relevant.status == "new"
    assert irrelevant.status == "rejected"
    assert result["rejected"] == 1


def test_run_pipeline_reports_ready_to_review_count(monkeypatch, db_session):
    _add_posting(
        db_session,
        "https://example.com/1",
        "Machine Learning Intern",
        "Remote internship on ML pipelines.",
    )
    _add_posting(
        db_session,
        "https://example.com/2",
        "Barista",
        "Serving coffee, no tech involved.",
    )
    db_session.commit()

    monkeypatch.setattr(
        "app.pipeline.fetch_and_store",
        lambda source, db: {"fetched": 2, "new": 2, "skipped": 0},
    )

    result = run_pipeline(source="hn_who_is_hiring", db=db_session)

    assert result == {
        "source": "hn_who_is_hiring",
        "ingested": 2,
        "new": 2,
        "rejected": 1,
        "ready_to_review": 1,
    }


def test_run_pipeline_skips_postings_that_already_have_a_draft(monkeypatch, db_session):
    # Even if it wouldn't pass the filter, a posting with a draft shouldn't be re-evaluated
    _add_posting(
        db_session,
        "https://example.com/1",
        "Senior Software Engineer",
        "Onsite in New York.",
        draft="already drafted",
    )
    db_session.commit()

    monkeypatch.setattr(
        "app.pipeline.fetch_and_store",
        lambda source, db: {"fetched": 0, "new": 0, "skipped": 0},
    )

    result = run_pipeline(source="hn_who_is_hiring", db=db_session)

    posting = db_session.query(Posting).filter_by(url="https://example.com/1").one()
    assert posting.status == "new"  # untouched — not part of the unfiltered query
    assert result["rejected"] == 0


def test_run_pipeline_propagates_ingest_error(monkeypatch, db_session):
    monkeypatch.setattr(
        "app.pipeline.fetch_and_store",
        lambda source, db: {"error": "Unknown source 'bogus'"},
    )

    result = run_pipeline(source="bogus", db=db_session)

    assert result == {"error": "Unknown source 'bogus'"}
