from app.db.database import Posting
from app.analytics.trends import compute_trends


def _posting(title="", description="", **kwargs):
    return Posting(url=kwargs.pop("url", f"https://example.com/{title}"), title=title, description=description, **kwargs)


def test_compute_trends_counts_each_skill_once_per_posting():
    postings = [_posting(title="Python Intern", description="python python python, some pandas too")]
    results = compute_trends(postings)
    by_name = {r.name: r.count for r in results}
    assert by_name["Python"] == 1
    assert by_name["Pandas"] == 1


def test_compute_trends_counts_across_postings():
    postings = [
        _posting(url="a", title="Backend Intern", description="Golang and Docker experience"),
        _posting(url="b", title="Platform Intern", description="Golang, Kubernetes, Docker"),
    ]
    results = compute_trends(postings)
    by_name = {r.name: r.count for r in results}
    assert by_name["Go"] == 2
    assert by_name["Docker"] == 2
    assert by_name["Kubernetes"] == 1


def test_compute_trends_bare_go_and_c_are_not_tracked():
    # "go" and "C" are excluded from the taxonomy — too noisy as bare words
    # ("go-to-market", "C-suite", "C.V.") to be a reliable signal.
    postings = [_posting(title="Growth Intern", description="Let's go build a C-suite deck")]
    results = compute_trends(postings)
    assert results == []


def test_compute_trends_handles_symbol_suffixed_aliases():
    postings = [_posting(title="C++ Engineer", description="Strong C++ and some C# on the side")]
    results = compute_trends(postings)
    by_name = {r.name: r.count for r in results}
    assert by_name["C++"] == 1
    assert by_name["C#"] == 1


def test_compute_trends_respects_top_n():
    postings = [_posting(title="Full Stack Intern", description="Python, React, AWS, Docker, Postgres")]
    results = compute_trends(postings, top_n=2)
    assert len(results) == 2


def test_compute_trends_pct_reflects_fraction_of_postings():
    postings = [
        _posting(url="a", title="ML Intern", description="Python and PyTorch"),
        _posting(url="b", title="Backend Intern", description="Java only"),
    ]
    results = compute_trends(postings)
    by_name = {r.name: r for r in results}
    assert by_name["Python"].pct == 50.0


def test_compute_trends_empty_postings_returns_empty():
    assert compute_trends([]) == []


def test_compute_trends_no_matches_returns_empty():
    postings = [_posting(title="Barista Intern", description="serving coffee and pastries")]
    assert compute_trends(postings) == []
