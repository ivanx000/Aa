# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A personal terminal tool for surfacing intern/co-op/new grad job postings and generating tailored resume materials on demand. No auto-submission — everything is manual. The primary interface is `run_pipeline.py`; the FastAPI app (`app/main.py`) exists as a secondary REST interface but is not the day-to-day entrypoint.

## Commands

```bash
# Run the pipeline (ingest + filter, no drafting)
python run_pipeline.py

# Ingest from a specific source
python run_pipeline.py --source hn_who_is_hiring   # or remoteok, remotive, adzuna, all

# List new postings in the terminal
python run_pipeline.py --list
python run_pipeline.py --list --status all          # show all statuses

# Generate blurb + resume keywords on demand
python run_pipeline.py --draft <url>
python run_pipeline.py --draft-all                  # batch draft all new postings

# Full resume tailoring for one posting
python run_pipeline.py --tailor <url>

# Update a posting's status
python run_pipeline.py --status <url> reviewed|sent|rejected

# Top skills/tools/languages across all scraped postings (not just intern-filtered ones)
python run_pipeline.py --trends
python run_pipeline.py --trends --days 30 --top 20   # custom window / list size

# Poll LinkedIn and send a macOS notification (with a link) on each new match
python run_pipeline.py --watch-linkedin
python run_pipeline.py --watch-linkedin --keywords "Software Engineer Intern" --location Canada --interval 300
python run_pipeline.py --watch-linkedin --once       # single pass, for cron/launchd

# Run the FastAPI server (not needed for normal use)
uvicorn app.main:app --reload

# Manual draft test (single posting, prints to stdout)
python test_draft.py

# Migrate an existing DB to add new columns (run once after schema changes)
python -c "
import sqlite3; conn = sqlite3.connect('pipeline.db')
conn.execute('ALTER TABLE postings ADD COLUMN posted_at DATETIME')
conn.execute('ALTER TABLE postings ADD COLUMN tailoring TEXT')
conn.execute('ALTER TABLE postings ADD COLUMN notified_at DATETIME')
conn.commit()
"
```

## Architecture

The pipeline has three stages that run sequentially. Drafting is intentionally **not** part of the pipeline run — it's on-demand only.

```
run_pipeline.py  ←── primary CLI entrypoint (rich terminal UI)
      │
      ▼
app/pipeline.py  ←── orchestrates ingest → filter (no drafting)
      │
      ├── app/ingestion/fetcher.py   fetch_and_store(source, db, **kwargs)
      │     Sources: hn_who_is_hiring (Algolia API), remoteok (JSON API), remotive (JSON API),
      │              adzuna (JSON API, requires free ADZUNA_APP_ID/ADZUNA_APP_KEY in .env),
      │              linkedin (public guest job-search HTML, no login — see below)
      │     Dedupes by URL. Stores posted_at from each source's timestamp field.
      │     Filters junk with MIN_POSTING_LENGTH=150 + JUNK_PATTERNS regex.
      │     "linkedin" is excluded from the "all" source and driven only by
      │     --watch-linkedin — it's polled frequently with a 1h f_TPR window,
      │     unlike the other sources which are pulled broadly on each run.
      │
      └── app/filtering/filter.py    is_relevant(title, description)
            Three required checks (all must pass):
            1. _keyword_match   — target role keywords (ML, full-stack, robotics, SaaS, etc.)
            2. _intern_match    — must be intern/co-op/student/new-grad/junior/entry-level
            3. _location_ok     — remote OK anywhere; onsite/hybrid must be in Canada

On-demand drafting (called directly from run_pipeline.py, never from pipeline.py):

app/drafting/drafter.py
  draft(title, description)  → DraftResult(blurb, keywords)
  tailor(title, description) → TailoringResult(blurb, keywords, bullets_to_emphasize, rewrites)
  Both call Ollama (llama3.2 by default) with temperature=0.3.
  _parse_response() strips markdown fences and extracts first {...} JSON block.

On-demand trend analysis (called directly from run_pipeline.py, never from pipeline.py):

app/analytics/trends.py
  compute_trends(postings, top_n) → list[SkillCount]
  Regex-matches title+description against SKILL_TAXONOMY (languages, frameworks,
  ML, cloud, databases, tools), counting each skill once per posting. Scans ALL
  stored postings within the window (including status="rejected"), not just the
  intern-filtered subset — this is a market-wide signal, not a search result.
  Bare "C" and "go" are deliberately excluded from the taxonomy — too noisy as
  common English words/abbreviations ("C-suite", "go-to-market") in free text.

LinkedIn watch (--watch-linkedin, called directly from run_pipeline.py, never from pipeline.py):

  Loops (or, with --once, runs a single pass — for cron/launchd) calling
  run_pipeline(source="linkedin", ...) on an interval, then queries for
  postings with status="new" and notified_at IS NULL and fires a notification
  (app/notify/notifier.py) for each, marking notified_at so it isn't repeated.
  Uses the same is_relevant() filter as the rest of the pipeline, so a
  "Software Engineer Intern" search still gets the intern/location screen.
  app/notify/notifier.py shells out to `terminal-notifier` (click opens the
  job URL) if installed, else `osascript` (no click-to-open). Values are
  always passed as separate argv entries, never interpolated into a shell or
  AppleScript string, since posting titles/companies are untrusted scraped text.
```

## Data model

Single table `postings` in `pipeline.db` (SQLite):

| Column | Notes |
|---|---|
| `url` | Primary key / dedup key |
| `title`, `company`, `description`, `source` | Raw from fetcher |
| `posted_at` | When the job was originally posted (nullable for old rows) |
| `fetched_at` | When we stored it |
| `draft` | Blurb text — NULL until `--draft` is run |
| `keywords` | JSON list — NULL until `--draft` is run |
| `tailoring` | JSON `{blurb, keywords, bullets_to_emphasize, rewrites}` — NULL until `--tailor` |
| `status` | `new` → `reviewed` → `sent` / `rejected` |
| `notified_at` | Set once `--watch-linkedin` has sent a notification for this posting — NULL until then |

SQLAlchemy does not auto-migrate. Add columns manually with `ALTER TABLE` when the schema changes.

## Key files

- `facts.yaml` — single source of truth for all LLM drafting (profile, experience, projects, talking points). Edit this when the resume changes.
- `app/config.py` — `Settings` via pydantic-settings; `target_keywords` list controls role keyword filter. Override via `.env`.
- `run_pipeline.py` — all CLI logic; `print_posting()` controls terminal rendering.

## LLM behavior notes

- Model is llama3.2 (3B params) by default — output quality is limited. Blurbs tend to be short and sometimes repetitive across postings. Switching to a larger model via `OLLAMA_MODEL=llama3.1:8b` in `.env` improves quality significantly.
- Prompts expect JSON output. `_parse_response()` in `drafter.py` handles malformed responses gracefully with a fallback to raw text.
- The tailor prompt passes all resume bullets to the LLM and asks it to select which to emphasize and suggest rewrites — do not fabricate bullets not in `facts.yaml`.
