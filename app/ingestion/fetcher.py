"""
Ingestion layer — fetches postings from job sources and stores new ones (deduped by URL).

Sources:
  - hn_who_is_hiring  (HN "Who is Hiring?" via Algolia — no scraping)
  - remoteok          (RemoteOK public JSON API)
  - remotive          (Remotive public JSON API)
  - adzuna            (Adzuna public JSON API — job aggregator, requires free API key)
  - linkedin          (LinkedIn's public guest job-search endpoint — no login, HTML parsed
                       with BeautifulSoup. Driven by --watch-linkedin, polled at low frequency.)
"""
import re
from datetime import datetime, timezone, timedelta
import httpx
from bs4 import BeautifulSoup
from sqlalchemy.orm import Session

from app.config import settings
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
            raw = c.get("comment_text", "") or ""
            # HN wraps paragraphs in <p>/<br> with no literal newlines, so
            # convert those to "\n" *before* stripping tags — otherwise the
            # whole comment collapses into one line and "first line" ends up
            # being the entire post.
            raw = re.sub(r"<p>|<br\s*/?>", "\n", raw, flags=re.IGNORECASE)
            text = re.sub(r"<[^>]+>", " ", raw).strip()
            text = re.sub(r"[ \t]*\n[ \t]*", "\n", text).strip()
            if not _is_real_posting(text):
                continue

            obj_id = c.get("objectID", "")
            url = f"https://news.ycombinator.com/item?id={obj_id}"
            first_line = text.split("\n")[0].strip()

            # Convention is "Company | Role | Location | ...". When it's
            # followed, use the role field alone as the title so seniority/
            # intern signals aren't diluted by company name or the trailing
            # location/comp/tags fields. Freeform comments with no "|" fall
            # back to the whole first line, as before.
            parts = [p.strip() for p in first_line.split("|")] if "|" in first_line else []
            company = parts[0] if len(parts) >= 2 else ""
            role = parts[1] if len(parts) >= 2 else first_line

            # Parse posted_at from unix timestamp
            created_ts = c.get("created_at_i")
            posted_at = (
                datetime.fromtimestamp(created_ts, tz=timezone.utc)
                if created_ts else None
            )

            postings.append({
                "url": url,
                "title": role[:200],
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
# Adzuna
# ---------------------------------------------------------------------------

ADZUNA_URL = "https://api.adzuna.com/v1/api/jobs/ca/search/{page}"


def _fetch_adzuna() -> list[dict]:
    if not settings.adzuna_app_id or not settings.adzuna_app_key:
        print("  Adzuna: skipped (set ADZUNA_APP_ID / ADZUNA_APP_KEY in .env)")
        return []

    postings = []
    for page in (1, 2):
        resp = httpx.get(
            ADZUNA_URL.format(page=page),
            params={
                "app_id": settings.adzuna_app_id,
                "app_key": settings.adzuna_app_key,
                "results_per_page": 50,
                "category": "it-jobs",
                "sort_by": "date",
                "max_days_old": 14,
                "content-type": "application/json",
            },
            timeout=20,
        )
        resp.raise_for_status()
        results = resp.json().get("results", [])
        if not results:
            break

        for j in results:
            url = j.get("redirect_url", "")
            if not url:
                continue
            title = j.get("title", "") or ""
            company = (j.get("company") or {}).get("display_name", "") or ""
            location = (j.get("location") or {}).get("display_name", "") or ""
            description = f"{title}\n{company}\n{location}\n\n{j.get('description', '') or ''}"

            created = j.get("created")  # ISO string, e.g. "2024-03-15T12:00:00Z"
            posted_at = None
            if created:
                try:
                    posted_at = datetime.fromisoformat(created.replace("Z", "+00:00"))
                except ValueError:
                    pass

            postings.append({
                "url": url,
                "title": title[:200],
                "company": company[:200],
                "description": description,
                "source": "adzuna",
                "posted_at": posted_at,
            })

    return postings


# ---------------------------------------------------------------------------
# LinkedIn (public guest job-search endpoint — no login required)
# ---------------------------------------------------------------------------

LINKEDIN_GUEST_SEARCH_URL = "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"

# Kept short (last hour) since this source is meant to be polled repeatedly by
# --watch-linkedin rather than run once like the other sources — a wide window
# would just re-fetch postings already deduped out on every poll.
LINKEDIN_TIME_POSTED_FILTER = "r3600"


def _fetch_linkedin(keywords: str | None = None, location: str | None = None) -> list[dict]:
    keywords = keywords if keywords is not None else settings.linkedin_keywords
    location = location if location is not None else settings.linkedin_location

    params = {"keywords": keywords, "f_TPR": LINKEDIN_TIME_POSTED_FILTER, "start": 0}
    if location:
        params["location"] = location

    resp = httpx.get(
        LINKEDIN_GUEST_SEARCH_URL,
        params=params,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
            )
        },
        timeout=15,
        follow_redirects=True,
    )
    resp.raise_for_status()
    if not resp.text.strip():
        return []

    return _parse_linkedin_html(resp.text)


def _parse_linkedin_html(html: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")

    postings = []
    for card in soup.select("div.base-card"):
        try:
            urn = card.get("data-entity-urn", "")
            job_id = urn.rsplit(":", 1)[-1] if urn else None

            title_el = card.select_one("h3.base-search-card__title")
            company_el = card.select_one("h4.base-search-card__subtitle")
            location_el = card.select_one("span.job-search-card__location")
            time_el = card.select_one("time")

            if not job_id or not title_el:
                continue

            title = title_el.get_text(strip=True)
            company = company_el.get_text(strip=True) if company_el else ""
            location_text = location_el.get_text(strip=True) if location_el else ""
            url = f"https://www.linkedin.com/jobs/view/{job_id}/"

            posted_at = None
            if time_el and time_el.get("datetime"):
                try:
                    posted_at = datetime.fromisoformat(time_el["datetime"]).replace(tzinfo=timezone.utc)
                except ValueError:
                    pass

            postings.append({
                "url": url,
                "title": title[:200],
                "company": company[:200],
                "description": f"{title}\n{company}\n{location_text}",
                "source": "linkedin",
                "posted_at": posted_at,
            })
        except (AttributeError, KeyError):
            continue  # malformed card — LinkedIn markup shifts occasionally, skip rather than fail the whole batch

    return postings


# ---------------------------------------------------------------------------
# Source registry + main entry point
# ---------------------------------------------------------------------------

SOURCES: dict[str, callable] = {
    "hn_who_is_hiring": _fetch_hn_who_is_hiring,
    "remoteok": _fetch_remoteok,
    "remotive": _fetch_remotive,
    "adzuna": _fetch_adzuna,
    "linkedin": _fetch_linkedin,
    "all": None,  # special: runs all sources (excludes linkedin — see --watch-linkedin)
}


def fetch_and_store(source: str, db: Session, **kwargs) -> dict:
    if source == "all":
        results = {}
        for s in ("hn_who_is_hiring", "remoteok", "remotive", "adzuna"):
            results[s] = _store(SOURCES[s](), db)
        total = {k: sum(r[k] for r in results.values()) for k in ("fetched", "new", "skipped")}
        total["per_source"] = results
        return total

    if source not in SOURCES:
        return {"error": f"Unknown source '{source}'. Available: {list(SOURCES.keys())}"}

    fetch_fn = SOURCES[source]
    raw = fetch_fn(**kwargs) if kwargs else fetch_fn()
    return _store(raw, db)


def _store(raw: list[dict], db: Session) -> dict:
    new_count = skipped = 0
    new_postings = []
    for p in raw:
        if db.query(Posting).filter(Posting.url == p["url"]).first():
            skipped += 1
            continue
        db.add(Posting(**p))
        new_postings.append({"url": p["url"], "title": p["title"], "company": p["company"]})
        new_count += 1
    db.commit()
    return {
        "fetched": len(raw),
        "new": new_count,
        "skipped": skipped,
        "new_postings": new_postings,
    }
