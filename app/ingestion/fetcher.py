"""
Ingestion layer — fetches postings from job sources and stores new ones (deduped by URL).

Sources:
  - hn_who_is_hiring  (HN "Who is Hiring?" via Algolia — no scraping)
  - remoteok          (RemoteOK public JSON API)
  - remotive          (Remotive public JSON API)
"""
import re
from datetime import datetime, timezone, timedelta
import httpx
from sqlalchemy.orm import Session

from app.db.database import Posting


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

MIN_POSTING_LENGTH = 150

JUNK_PATTERNS = [
    r"^(is|are|do|does|can|could|would|will|have|has|what|when|where|why|how)\b",
    r"^(hi|hello|thanks|thank you|congrats|congratulations|fyi)\b",
    r"^i('m| am) (a |an )?(cs|software|developer|engineer|looking|an ex)",
    r"^i have \d+",
    r"^formatting error",
    r"^any (chance|update|word|news)",
    r"^still hiring",
    r"^applied for",
    r"^opportunity looking for",
    r"^(senior |junior |mid |founding )?(software |full.?stack |backend |frontend |ai )?engineer looking",
    r"resume\s*:\s*https?://",
    r"^looking for (a |an )?(new )?opportunit",
    r"^job not found",
    r"^'.*'\s*->\s*job not found",
    r"^an account \d+",
]
_junk_re = re.compile("|".join(JUNK_PATTERNS), re.IGNORECASE)


def _is_real_posting(text: str) -> bool:
    if len(text.strip()) < MIN_POSTING_LENGTH:
        return False
    first_line = text.split("\n")[0].strip()
    if _junk_re.search(first_line):
        return False
    return True


# ---------------------------------------------------------------------------
# HN Who Is Hiring
# ---------------------------------------------------------------------------

HN_ALGOLIA = "https://hn.algolia.com/api/v1/search"


def _fetch_hn_who_is_hiring() -> list[dict]:
    now = datetime.now(timezone.utc)
    cutoff = int((now - timedelta(days=60)).timestamp())

    resp = httpx.get(
        HN_ALGOLIA,
        params={
            "query": "Ask HN: Who is hiring?",
            "tags": "story,ask_hn",
            "hitsPerPage": 5,
            "numericFilters": f"created_at_i>{cutoff}",
        },
        timeout=15,
    )
    resp.raise_for_status()
    hits = resp.json().get("hits", [])

    wih_hits = [h for h in hits if h.get("author") == "whoishiring"] or hits
    if not wih_hits:
        return []

    # Algolia /search ranks by relevance, not recency — pick the newest thread explicitly.
    newest = max(wih_hits, key=lambda h: h.get("created_at_i", 0))
    story_id = newest["objectID"]
    story_title = newest.get("title", "")
    print(f"  HN thread: {story_title} (id={story_id})")

    postings = []
    page = 0
    while True:
        resp = httpx.get(
            HN_ALGOLIA,
            params={
                "tags": f"comment,story_{story_id}",
                "hitsPerPage": 200,
                "page": page,
            },
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
        comments = data.get("hits", [])
        if not comments:
            break

        for c in comments:
            text = re.sub(r"<[^>]+>", " ", c.get("comment_text", "") or "").strip()
            if not _is_real_posting(text):
                continue

            obj_id = c.get("objectID", "")
            url = f"https://news.ycombinator.com/item?id={obj_id}"
            first_line = text.split("\n")[0].strip()
            company = first_line.split("|")[0].strip() if "|" in first_line else ""

            # Parse posted_at from unix timestamp
            created_ts = c.get("created_at_i")
            posted_at = (
                datetime.fromtimestamp(created_ts, tz=timezone.utc)
                if created_ts else None
            )

            postings.append({
                "url": url,
                "title": first_line[:200],
                "company": company[:200],
                "description": text,
                "source": "hn_who_is_hiring",
                "posted_at": posted_at,
            })

        if page >= data.get("nbPages", 1) - 1:
            break
        page += 1

    return postings


# ---------------------------------------------------------------------------
# RemoteOK
# ---------------------------------------------------------------------------

REMOTEOK_URL = "https://remoteok.com/api"


def _fetch_remoteok() -> list[dict]:
    resp = httpx.get(
        REMOTEOK_URL,
        headers={"User-Agent": "job-pipeline/0.1 (personal project)"},
        timeout=20,
        follow_redirects=True,
    )
    resp.raise_for_status()
    data = resp.json()

    # First element is a legal notice dict, skip it
    jobs = [j for j in data if isinstance(j, dict) and j.get("id")]

    postings = []
    for j in jobs:
        url = j.get("url", "") or f"https://remoteok.com/remote-jobs/{j.get('id')}"
        title = j.get("position", "") or ""
        company = j.get("company", "") or ""
        description = f"{title}\n{company}\n\n{j.get('description', '') or ''}"
        tags = " ".join(j.get("tags", []) or [])
        full_text = f"{description} {tags}"

        epoch = j.get("epoch")
        posted_at = (
            datetime.fromtimestamp(epoch, tz=timezone.utc) if epoch else None
        )

        postings.append({
            "url": url,
            "title": title[:200],
            "company": company[:200],
            "description": full_text,
            "source": "remoteok",
            "posted_at": posted_at,
        })

    return postings


# ---------------------------------------------------------------------------
# Remotive
# ---------------------------------------------------------------------------

REMOTIVE_URL = "https://remotive.com/api/remote-jobs"


def _fetch_remotive() -> list[dict]:
    resp = httpx.get(REMOTIVE_URL, timeout=20)
    resp.raise_for_status()
    jobs = resp.json().get("jobs", [])

    postings = []
    for j in jobs:
        url = j.get("url", "")
        if not url:
            continue
        title = j.get("title", "") or ""
        company = j.get("company_name", "") or ""
        description = f"{title}\n{company}\n\n{j.get('description', '') or ''}"

        pub_date = j.get("publication_date")  # "2024-03-15T12:00:00"
        posted_at = None
        if pub_date:
            try:
                posted_at = datetime.fromisoformat(pub_date.replace("Z", "+00:00"))
            except ValueError:
                pass

        postings.append({
            "url": url,
            "title": title[:200],
            "company": company[:200],
            "description": description,
            "source": "remotive",
            "posted_at": posted_at,
        })

    return postings


# ---------------------------------------------------------------------------
# Source registry + main entry point
# ---------------------------------------------------------------------------

SOURCES: dict[str, callable] = {
    "hn_who_is_hiring": _fetch_hn_who_is_hiring,
    "remoteok": _fetch_remoteok,
    "remotive": _fetch_remotive,
    "all": None,  # special: runs all sources
}


def fetch_and_store(source: str, db: Session) -> dict:
    if source == "all":
        results = {}
        for s in ("hn_who_is_hiring", "remoteok", "remotive"):
            results[s] = _store(SOURCES[s](), db)
        total = {k: sum(r[k] for r in results.values()) for k in ("fetched", "new", "skipped")}
        total["per_source"] = results
        return total

    if source not in SOURCES:
        return {"error": f"Unknown source '{source}'. Available: {list(SOURCES.keys())}"}

    raw = SOURCES[source]()
    return _store(raw, db)


def _store(raw: list[dict], db: Session) -> dict:
    new_count = skipped = 0
    for p in raw:
        if db.query(Posting).filter(Posting.url == p["url"]).first():
            skipped += 1
            continue
        db.add(Posting(**p))
        new_count += 1
    db.commit()
    return {"fetched": len(raw), "new": new_count, "skipped": skipped}
