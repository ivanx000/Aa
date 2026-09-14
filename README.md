# LinkedIn Watch Notifier

A personal terminal tool that polls LinkedIn's public job search for new intern/co-op postings and sends a macOS notification with a link to each one, the moment it appears.

## What it does

- Polls LinkedIn's public guest job-search page (no login) for postings matching a keyword search (default: "Software Engineer Intern")
- Filters to intern/co-op/student roles in target fields (ML, full-stack, robotics, SaaS, etc.), remote anywhere or onsite/hybrid in Canada
- Dedupes by URL and only notifies once per posting, tracked in a local SQLite DB
- Fires a native macOS alert (click "Open" to jump straight to the job) when a new match is found

## Setup

**Prerequisites:** Python 3.10+

```bash
pip install -r requirements.txt
```

## Usage

```bash
# Watch LinkedIn and get a macOS notification (with a link) on each new match
python run_pipeline.py --watch-linkedin

# Override the default keyword/location search
python run_pipeline.py --watch-linkedin --keywords "Software Engineer Intern" --location Canada

# Poll on a custom interval (default: every 5 minutes)
python run_pipeline.py --watch-linkedin --interval 300

# Single check-and-notify pass, e.g. for cron/launchd instead of a long-running loop
python run_pipeline.py --watch-linkedin --once
```

`--watch-linkedin` polls LinkedIn's public job-search page for postings matching `--keywords`/`--location` (or `LINKEDIN_KEYWORDS`/`LINKEDIN_LOCATION` in `.env`), stores new ones after running them through the relevance filter (`is_relevant` in `app/filtering/filter.py`), and fires a notification for each one it hasn't notified about yet.

- Runs as a foreground loop by default — for it to fire while you're not watching a terminal, either leave it running in a background terminal tab, or run `--watch-linkedin --once` on a schedule via `cron`/`launchd`.
- LinkedIn markup and rate limiting can change without notice — this hits a public, unauthenticated endpoint, not an official API, so treat it as best-effort and keep polling infrequent (default: every 5 minutes).

## Stack

- **Python** — CLI
- **SQLite / SQLAlchemy** — local storage of seen postings (swap `DATABASE_URL` in `.env` for Postgres)
- **httpx / BeautifulSoup** — fetches and parses LinkedIn's guest job-search HTML
- **rich** — terminal formatting

## Config

Override defaults via a `.env` file:

```
DATABASE_URL=sqlite:///./pipeline.db
LINKEDIN_KEYWORDS=Software Engineer Intern
LINKEDIN_LOCATION=Canada
```
