# Job Application Pipeline

A personal terminal tool that ingests job postings, filters them to relevant intern/student roles, and helps tailor your resume and application materials — all on-demand, no auto-submission.

## What it does

- Pulls job postings from **HN Who Is Hiring**, **RemoteOK**, and **Remotive**
- Filters to intern/co-op/new grad roles in AI/ML, robotics, full-stack, or SaaS
- Location filter: remote (anywhere) or onsite/hybrid in Canada only
- Generates on-demand "why I'm a good fit" blurbs via local LLM (Ollama)
- Suggests resume keywords and bullet rewrites tailored to each posting
- Tracks status (new → reviewed → sent / rejected) in a local SQLite DB
- Reports the top skills/tools/languages showing up across all scraped postings (not just intern-filtered ones), so you can see what the market is asking for right now
- Watches LinkedIn for new postings matching a keyword search (e.g. "Software Engineer Intern") and sends a macOS notification with a link straight to the posting

Everything is manual and on-demand — you review and send, the tool just surfaces and drafts.

## Setup

**Prerequisites:** Python 3.10+, [Ollama](https://ollama.com) with `llama3.2` pulled

```bash
pip install -r requirements.txt
ollama pull llama3.2
```

Edit `facts.yaml` with your background, experience, and projects — this is the source of truth for all LLM drafting.

## Usage

```bash
# Ingest + filter new postings from all sources
python run_pipeline.py

# Ingest from a specific source
python run_pipeline.py --source hn_who_is_hiring
python run_pipeline.py --source remoteok
python run_pipeline.py --source remotive

# List new postings
python run_pipeline.py --list

# List all postings (any status)
python run_pipeline.py --list --status all

# Generate a blurb + resume keywords for one posting
python run_pipeline.py --draft <url>

# Generate blurbs for all new postings at once
python run_pipeline.py --draft-all

# Full resume tailoring for a specific posting
# (bullets to emphasize, suggested rewrites, blurb)
python run_pipeline.py --tailor <url>

# Mark a posting's status
python run_pipeline.py --status <url> reviewed
python run_pipeline.py --status <url> sent
python run_pipeline.py --status <url> rejected

# Top skills/tools/languages in demand this week (across all scraped postings)
python run_pipeline.py --trends

# Custom window and list size
python run_pipeline.py --trends --days 30 --top 20

# Watch LinkedIn and get a macOS notification (with a link) on each new match
python run_pipeline.py --watch-linkedin
python run_pipeline.py --watch-linkedin --keywords "Software Engineer Intern" --location Canada
python run_pipeline.py --watch-linkedin --interval 300   # poll every 5 minutes (default)

# Single check-and-notify pass, e.g. for cron/launchd instead of a long-running loop
python run_pipeline.py --watch-linkedin --once
```

### LinkedIn watch notifications

`--watch-linkedin` polls LinkedIn's public job-search page (no login) for postings
matching `--keywords`/`--location` (or `LINKEDIN_KEYWORDS`/`LINKEDIN_LOCATION` in
`.env`), stores new ones (reusing the same filter as the rest of the pipeline —
see `is_relevant` in `app/filtering/filter.py`), and fires a notification for each
one it hasn't notified about yet.

- Install [`terminal-notifier`](https://github.com/julienXX/terminal-notifier) (`brew install terminal-notifier`) so clicking the notification opens the job directly in your browser. Without it, notifications still appear (via `osascript`) but you'll need to copy the link from the terminal.
- Runs as a foreground loop by default — for it to fire while you're not watching a terminal, either leave it running in a background terminal tab, or run `--watch-linkedin --once` on a schedule via `cron`/`launchd`.
- LinkedIn markup and rate limiting can change without notice — this hits a public, unauthenticated endpoint, not an official API, so treat it as best-effort and keep polling infrequent (default: every 5 minutes).

## Stack

- **Python / FastAPI** — backend and CLI
- **SQLite / SQLAlchemy** — local storage (swap `DATABASE_URL` in `.env` for Postgres)
- **Ollama (llama3.2)** — free local LLM, no API key needed
- **rich** — terminal formatting

## Config

Override defaults via a `.env` file:

```
DATABASE_URL=sqlite:///./pipeline.db
OLLAMA_HOST=http://localhost:11434
OLLAMA_MODEL=llama3.2
```
