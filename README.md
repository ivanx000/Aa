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
```

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
