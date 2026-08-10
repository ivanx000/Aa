"""Tests for the per-source fetch functions in app/ingestion/fetcher.py.

httpx.get is monkeypatched so these never make real network calls.
"""
import httpx
import pytest

from app.ingestion import fetcher


class _FakeResponse:
    def __init__(self, json_data, status_code=200):
        self._json_data = json_data
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("error", request=None, response=self)

    def json(self):
        return self._json_data


# ---------------------------------------------------------------------------
# HN Who Is Hiring
# ---------------------------------------------------------------------------

def test_fetch_hn_who_is_hiring_parses_comments(monkeypatch):
    story_search_response = _FakeResponse(
        {"hits": [{"objectID": "111", "author": "whoishiring", "created_at_i": 1000, "title": "Ask HN: Who is hiring? (Aug 2026)"}]}
    )
    comments_response = _FakeResponse(
        {
            "hits": [
                {
                    "objectID": "222",
                    "comment_text": "Acme Corp | Remote | Full-time<p>"
                    + "We are looking for a software engineering intern to join our team. "
                    + "You'll build features and ship code weekly with mentorship.",
                    "created_at_i": 1690000000,
                },
                {
                    # junk comment — should be filtered out
                    "objectID": "333",
                    "comment_text": "Still hiring? " + "x" * 160,
                    "created_at_i": 1690000001,
                },
            ],
            "nbPages": 1,
        }
    )

    calls = []

    def fake_get(url, params=None, timeout=None):
        calls.append(params)
        if "tags" in params and params["tags"] == "story,ask_hn":
            return story_search_response
        return comments_response

    monkeypatch.setattr(fetcher.httpx, "get", fake_get)

    postings = fetcher._fetch_hn_who_is_hiring()

    assert len(postings) == 1
    p = postings[0]
    assert p["url"] == "https://news.ycombinator.com/item?id=222"
    assert p["company"] == "Acme Corp"
    assert p["source"] == "hn_who_is_hiring"
    assert p["posted_at"] is not None
    assert "<p>" not in p["description"]  # HTML tags stripped


def test_fetch_hn_who_is_hiring_returns_empty_when_no_thread_found(monkeypatch):
    monkeypatch.setattr(
        fetcher.httpx, "get", lambda url, params=None, timeout=None: _FakeResponse({"hits": []})
    )
    assert fetcher._fetch_hn_who_is_hiring() == []


# ---------------------------------------------------------------------------
# RemoteOK
# ---------------------------------------------------------------------------

def test_fetch_remoteok_skips_legal_notice_and_parses_jobs(monkeypatch):
    data = [
        {"legal": "This is a legal notice, not a job"},  # first element, no "id"
        {
            "id": "123",
            "url": "https://remoteok.com/remote-jobs/123",
            "position": "Machine Learning Intern",
            "company": "Acme",
            "description": "Remote internship building ML models.",
            "tags": ["python", "ml"],
            "epoch": 1690000000,
        },
    ]

    monkeypatch.setattr(
        fetcher.httpx,
        "get",
        lambda url, headers=None, timeout=None, follow_redirects=None: _FakeResponse(data),
    )

    postings = fetcher._fetch_remoteok()

    assert len(postings) == 1
    p = postings[0]
    assert p["url"] == "https://remoteok.com/remote-jobs/123"
    assert p["title"] == "Machine Learning Intern"
    assert p["source"] == "remoteok"
    assert "python" in p["description"]
    assert p["posted_at"] is not None


def test_fetch_remoteok_builds_fallback_url_when_missing(monkeypatch):
    data = [{"id": "456", "position": "Intern", "company": "Acme"}]
    monkeypatch.setattr(
        fetcher.httpx,
        "get",
        lambda url, headers=None, timeout=None, follow_redirects=None: _FakeResponse(data),
    )

    postings = fetcher._fetch_remoteok()
    assert postings[0]["url"] == "https://remoteok.com/remote-jobs/456"


# ---------------------------------------------------------------------------
# Remotive
# ---------------------------------------------------------------------------

def test_fetch_remotive_parses_jobs(monkeypatch):
    data = {
        "jobs": [
            {
                "url": "https://remotive.com/job/1",
                "title": "Full Stack Intern",
                "company_name": "Acme",
                "description": "Remote internship on our full-stack team.",
                "publication_date": "2026-08-01T12:00:00",
            }
        ]
    }
    monkeypatch.setattr(fetcher.httpx, "get", lambda url, timeout=None: _FakeResponse(data))

    postings = fetcher._fetch_remotive()

    assert len(postings) == 1
    p = postings[0]
    assert p["url"] == "https://remotive.com/job/1"
    assert p["source"] == "remotive"
    assert p["posted_at"].year == 2026


def test_fetch_remotive_skips_jobs_without_url(monkeypatch):
    data = {"jobs": [{"title": "No URL job"}]}
    monkeypatch.setattr(fetcher.httpx, "get", lambda url, timeout=None: _FakeResponse(data))
    assert fetcher._fetch_remotive() == []


def test_fetch_remotive_handles_bad_publication_date(monkeypatch):
    data = {
        "jobs": [
            {
                "url": "https://remotive.com/job/2",
                "title": "Intern",
                "company_name": "Acme",
                "description": "desc",
                "publication_date": "not-a-date",
            }
        ]
    }
    monkeypatch.setattr(fetcher.httpx, "get", lambda url, timeout=None: _FakeResponse(data))

    postings = fetcher._fetch_remotive()
    assert postings[0]["posted_at"] is None


# ---------------------------------------------------------------------------
# Adzuna
# ---------------------------------------------------------------------------

def test_fetch_adzuna_skipped_without_credentials(monkeypatch):
    monkeypatch.setattr(fetcher.settings, "adzuna_app_id", "")
    monkeypatch.setattr(fetcher.settings, "adzuna_app_key", "")

    assert fetcher._fetch_adzuna() == []


def test_fetch_adzuna_parses_results_and_stops_on_empty_page(monkeypatch):
    monkeypatch.setattr(fetcher.settings, "adzuna_app_id", "id123")
    monkeypatch.setattr(fetcher.settings, "adzuna_app_key", "key123")

    page_1 = _FakeResponse(
        {
            "results": [
                {
                    "redirect_url": "https://adzuna.com/job/1",
                    "title": "Software Intern",
                    "company": {"display_name": "Acme"},
                    "location": {"display_name": "Toronto, ON"},
                    "description": "Great internship.",
                    "created": "2026-08-01T12:00:00Z",
                }
            ]
        }
    )
    page_2 = _FakeResponse({"results": []})
    responses = {"1": page_1, "2": page_2}

    def fake_get(url, params=None, timeout=None):
        return responses[url.split("/")[-1]]

    monkeypatch.setattr(fetcher.httpx, "get", fake_get)

    postings = fetcher._fetch_adzuna()

    assert len(postings) == 1
    p = postings[0]
    assert p["url"] == "https://adzuna.com/job/1"
    assert p["source"] == "adzuna"
    assert "Toronto" in p["description"]
    assert p["posted_at"].tzinfo is not None


def test_fetch_adzuna_skips_results_without_redirect_url(monkeypatch):
    monkeypatch.setattr(fetcher.settings, "adzuna_app_id", "id123")
    monkeypatch.setattr(fetcher.settings, "adzuna_app_key", "key123")

    page_1 = _FakeResponse({"results": [{"title": "No URL"}]})
    page_2 = _FakeResponse({"results": []})
    responses = {"1": page_1, "2": page_2}

    def fake_get(url, params=None, timeout=None):
        return responses[url.split("/")[-1]]

    monkeypatch.setattr(fetcher.httpx, "get", fake_get)

    assert fetcher._fetch_adzuna() == []


# ---------------------------------------------------------------------------
# fetch_and_store / SOURCES registry
# ---------------------------------------------------------------------------

def test_fetch_and_store_unknown_source(db_session):
    result = fetcher.fetch_and_store("bogus_source", db_session)
    assert "error" in result


def test_fetch_and_store_dispatches_to_source_fn(monkeypatch, db_session):
    monkeypatch.setitem(
        fetcher.SOURCES,
        "remoteok",
        lambda: [
            {
                "url": "https://example.com/1",
                "title": "Intern",
                "company": "Acme",
                "description": "desc",
                "source": "remoteok",
                "posted_at": None,
            }
        ],
    )

    result = fetcher.fetch_and_store("remoteok", db_session)
    assert result == {"fetched": 1, "new": 1, "skipped": 0}


def test_fetch_and_store_all_aggregates_sources(monkeypatch, db_session):
    def make_fn(url):
        return lambda: [
            {
                "url": url,
                "title": "Intern",
                "company": "Acme",
                "description": "desc",
                "source": "src",
                "posted_at": None,
            }
        ]

    monkeypatch.setitem(fetcher.SOURCES, "hn_who_is_hiring", make_fn("https://example.com/hn"))
    monkeypatch.setitem(fetcher.SOURCES, "remoteok", make_fn("https://example.com/remoteok"))
    monkeypatch.setitem(fetcher.SOURCES, "remotive", make_fn("https://example.com/remotive"))
    monkeypatch.setitem(fetcher.SOURCES, "adzuna", lambda: [])

    result = fetcher.fetch_and_store("all", db_session)

    assert result["fetched"] == 3
    assert result["new"] == 3
    assert result["skipped"] == 0
    assert set(result["per_source"].keys()) == {
        "hn_who_is_hiring",
        "remoteok",
        "remotive",
        "adzuna",
    }
