# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A personal terminal tool that polls LinkedIn's public job-search page for new intern/co-op postings and fires a macOS notification (with a link) the moment one matches. No auto-submission, no drafting — it only watches and notifies. The entrypoint is `run_pipeline.py --watch-linkedin`.

## Commands

```bash
# Poll LinkedIn and send a macOS notification (with a link) on each new match
python run_pipeline.py --watch-linkedin
python run_pipeline.py --watch-linkedin --keywords "Software Engineer Intern" --location Canada --interval 300
python run_pipeline.py --watch-linkedin --once       # single pass, for cron/launchd
```

## Architecture

```
run_pipeline.py  ←── CLI entrypoint; cmd_watch_linkedin() loops (or, with --once,
      │              runs a single pass) calling run_pipeline(source="linkedin", ...)
      │              on an interval, then queries for postings with status="new"
      │              and notified_at IS NULL and fires a notification for each,
      │              marking notified_at so it isn't repeated.
      ▼
app/pipeline.py  ←── orchestrates ingest → filter
      │
      ├── app/ingestion/fetcher.py   fetch_and_store(source="linkedin", db, **kwargs)
      │     Fetches LinkedIn's public guest job-search endpoint (no login),
      │     HTML parsed with BeautifulSoup. Dedupes by URL. Stores posted_at
      │     from the posting's <time> element.
      │     Polled with a 1h f_TPR window since --watch-linkedin runs frequently
      │     — a wider window would just re-fetch postings already deduped out.
      │
      └── app/filtering/filter.py    is_relevant(title, description)
            Three required checks (all must pass):
            1. _keyword_match   — target role keywords (ML, full-stack, robotics, SaaS, etc.)
            2. _intern_match    — must be intern/co-op/student/new-grad/junior/entry-level
            3. _location_ok     — remote OK anywhere; onsite/hybrid must be in Canada

app/notify/notifier.py
  notify(title, subtitle, message, url) shells out to `osascript` to show a
  native `display alert` dialog with an "Open" button (click opens the job
  URL). Values are always passed as separate argv entries, never interpolated
  into a shell or AppleScript string, since posting titles/companies are
  untrusted scraped text.
```

## Data model

Single table `postings` in `pipeline.db` (SQLite):

| Column | Notes |
|---|---|
| `url` | Primary key / dedup key |
| `title`, `company`, `description`, `source` | Raw from fetcher (`source` is always `"linkedin"`) |
| `posted_at` | When the job was originally posted (nullable) |
| `fetched_at` | When we stored it |
| `status` | `new` (passed the filter) or `rejected` (set by `is_relevant`) |
| `notified_at` | Set once a notification has fired for this posting — NULL until then |

SQLAlchemy does not auto-migrate. Add columns manually with `ALTER TABLE` when the schema changes.

## Key files

- `app/config.py` — `Settings` via pydantic-settings; `target_keywords` controls the role keyword filter, `linkedin_keywords`/`linkedin_location` control the default search. Override via `.env`.
- `run_pipeline.py` — all CLI logic.

## Running unattended

A `launchd` agent (`~/Library/LaunchAgents/com.ivanxie.linkedin-watch.plist`, outside this repo) runs `run_pipeline.py --watch-linkedin --once` from this project's directory every 5 minutes, so notifications keep arriving without a terminal open.
