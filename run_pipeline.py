"""
Job pipeline CLI.

Commands:
  python run_pipeline.py                     Ingest + filter from all sources
  python run_pipeline.py --source hn         Ingest from one source only
  python run_pipeline.py --list              Show new postings
  python run_pipeline.py --list --status all Show all postings regardless of status
  python run_pipeline.py --draft <url>       Generate blurb + keywords for one posting
  python run_pipeline.py --draft-all         Generate blurbs for all new unreviewed postings
  python run_pipeline.py --tailor <url>      Full resume tailoring for one posting
  python run_pipeline.py --status <url> reviewed|sent|rejected   Update a posting's status
"""
import sys
import json
from datetime import datetime, timezone

from rich.console import Console
from rich.text import Text
from rich.rule import Rule
from rich.padding import Padding
from rich import print as rprint

from app.db.database import init_db, SessionLocal, Posting
from app.pipeline import run_pipeline
from app.drafting.drafter import draft as generate_draft, tailor as generate_tailor

console = Console()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def relative_time(dt: datetime | None) -> str:
    if dt is None:
        return "unknown"
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    delta = datetime.now(timezone.utc) - dt
    s = int(delta.total_seconds())
    if s < 60:
        return f"{s} second{'s' if s != 1 else ''} ago"
    if s < 3600:
        m = s // 60
        return f"{m} minute{'s' if m != 1 else ''} ago"
    if s < 86400:
        h = s // 3600
        return f"{h} hour{'s' if h != 1 else ''} ago"
    d = s // 86400
    return f"{d} day{'s' if d != 1 else ''} ago"


STATUS_COLOR = {
    "new":      "bright_cyan",
    "reviewed": "bright_yellow",
    "sent":     "bright_green",
    "rejected": "dim",
}

SOURCE_LABEL = {
    "hn_who_is_hiring": "HN",
    "remoteok":         "RemoteOK",
    "remotive":         "Remotive",
}


def print_posting(p: Posting, show_draft: bool = False, show_tailor: bool = False):
    status_color = STATUS_COLOR.get(p.status, "white")
    source_label = SOURCE_LABEL.get(p.source, p.source or "?")

    # Header line: company + title
    company = (p.company or "Unknown").strip()
    title   = (p.title   or "").strip()

    header = Text()
    header.append(f"  {company}", style=f"bold {status_color}")
    if title and title != company:
        # Trim title to avoid repetition if it starts with company name
        short_title = title[len(company):].lstrip(" |–-").strip() if title.lower().startswith(company.lower()) else title
        if short_title:
            header.append(f"  ·  {short_title[:90]}", style="white")

    console.print(header)

    # Meta line: source, time, url
    meta = Text()
    meta.append(f"    [{source_label}]", style="dim cyan")
    meta.append(f"  {relative_time(p.posted_at)}", style="dim")
    meta.append(f"  {p.url}", style="dim blue underline")
    console.print(meta)

    # Keywords (if available)
    if p.keywords:
        try:
            kws = json.loads(p.keywords)
            if kws:
                kw_text = Text("    ")
                kw_text.append("keywords: ", style="dim")
                kw_text.append("  ".join(f"#{k}" for k in kws), style="bright_magenta")
                console.print(kw_text)
        except (json.JSONDecodeError, TypeError):
            pass

    # Blurb (if requested and available)
    if show_draft and p.draft:
        console.print()
        console.print(Padding(Text(p.draft, style="italic"), (0, 0, 0, 4)))

    # Tailoring (if requested and available)
    if show_tailor and p.tailoring:
        try:
            t = json.loads(p.tailoring)
            console.print()
            console.print(Text("    ── TAILORING ──", style="bold yellow"))

            if t.get("bullets_to_emphasize"):
                console.print(Text("    Emphasize these bullets:", style="yellow"))
                for b in t["bullets_to_emphasize"]:
                    console.print(Text(f"      • {b}", style="white"))

            if t.get("rewrites"):
                console.print()
                console.print(Text("    Suggested rewrites:", style="yellow"))
                for r in t["rewrites"]:
                    console.print(Text(f"      Before: {r.get('original','')}", style="dim"))
                    console.print(Text(f"      After:  {r.get('suggested','')}", style="bright_white"))

            if t.get("blurb"):
                console.print()
                console.print(Text("    Blurb:", style="yellow"))
                console.print(Padding(Text(t["blurb"], style="italic"), (0, 0, 0, 6)))
        except (json.JSONDecodeError, TypeError):
            pass

    console.print(Rule(style="dim"))


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

def cmd_run(source: str):
    console.print(Rule(f"[bold cyan]Ingesting from: {source}[/]"))
    init_db()
    db = SessionLocal()
    try:
        result = run_pipeline(source=source, db=db)
        if "error" in result:
            console.print(f"[red]Error:[/] {result['error']}")
            return

        console.print(f"  [dim]Fetched[/]        {result.get('ingested', 0)}")
        console.print(f"  [bright_cyan]New postings[/]   {result.get('new', 0)}")
        console.print(f"  [dim]Rejected[/]       {result.get('rejected', 0)}")
        console.print(f"  [bright_green]Ready to review[/] {result.get('ready_to_review', 0)}")
        console.print()
        console.print("[dim]Run[/] [bold]--list[/] [dim]to see new postings.[/]")
    finally:
        db.close()


def cmd_list(status_filter: str | None, show_draft: bool):
    init_db()
    db = SessionLocal()
    try:
        q = db.query(Posting)
        if status_filter == "all":
            pass
        elif status_filter:
            q = q.filter(Posting.status == status_filter)
        else:
            q = q.filter(Posting.status == "new")

        postings = q.order_by(Posting.posted_at.desc().nullslast()).all()

        if not postings:
            console.print("[dim]No postings found.[/]")
            return

        label = status_filter or "new"
        console.print(Rule(f"[bold cyan]{len(postings)} posting(s) — {label}[/]"))
        console.print()

        for p in postings:
            print_posting(p, show_draft=show_draft)
    finally:
        db.close()


def cmd_draft(url: str):
    init_db()
    db = SessionLocal()
    try:
        posting = db.query(Posting).filter(Posting.url == url).first()
        if not posting:
            console.print(f"[red]Posting not found:[/] {url}")
            return

        console.print(Rule(f"[bold cyan]Drafting blurb for: {posting.company or url}[/]"))
        console.print("[dim]Generating...[/]")

        result = generate_draft(posting.title or "", posting.description or "")
        posting.draft = result.blurb
        posting.keywords = json.dumps(result.keywords)
        db.commit()

        console.print()
        console.print(Text("BLURB", style="bold bright_cyan"))
        console.print(Padding(result.blurb, (1, 0, 1, 2)))
        console.print(Text("RESUME KEYWORDS", style="bold bright_magenta"))
        for kw in result.keywords:
            console.print(f"  • {kw}")
    finally:
        db.close()


def cmd_draft_all():
    init_db()
    db = SessionLocal()
    try:
        postings = (
            db.query(Posting)
            .filter(Posting.status == "new", Posting.draft.is_(None))
            .all()
        )

        if not postings:
            console.print("[dim]No new unreviewed postings without a draft.[/]")
            return

        console.print(Rule(f"[bold cyan]Drafting {len(postings)} posting(s)[/]"))

        for i, p in enumerate(postings, 1):
            console.print(f"  [{i}/{len(postings)}] {p.company or p.url[:60]}...", end=" ")
            try:
                result = generate_draft(p.title or "", p.description or "")
                p.draft = result.blurb
                p.keywords = json.dumps(result.keywords)
                db.commit()
                console.print("[green]✓[/]")
            except Exception as e:
                console.print(f"[red]✗ {e}[/]")

        console.print()
        console.print("[dim]Run[/] [bold]--list[/] [dim]to review with blurbs.[/]")
    finally:
        db.close()


def cmd_tailor(url: str):
    init_db()
    db = SessionLocal()
    try:
        posting = db.query(Posting).filter(Posting.url == url).first()
        if not posting:
            console.print(f"[red]Posting not found:[/] {url}")
            return

        console.print(Rule(f"[bold yellow]Tailoring resume for: {posting.company or url}[/]"))
        console.print("[dim]Generating...[/]")

        result = generate_tailor(posting.title or "", posting.description or "")
        posting.tailoring = json.dumps({
            "blurb": result.blurb,
            "keywords": result.keywords,
            "bullets_to_emphasize": result.bullets_to_emphasize,
            "rewrites": result.rewrites,
        })
        if not posting.draft:
            posting.draft = result.blurb
            posting.keywords = json.dumps(result.keywords)
        db.commit()

        console.print()
        if result.bullets_to_emphasize:
            console.print(Text("BULLETS TO EMPHASIZE", style="bold yellow"))
            for b in result.bullets_to_emphasize:
                console.print(f"  • {b}")
            console.print()

        if result.rewrites:
            console.print(Text("SUGGESTED REWRITES", style="bold yellow"))
            for r in result.rewrites:
                console.print(Text(f"  Before: {r.get('original','')}", style="dim"))
                console.print(Text(f"  After:  {r.get('suggested','')}", style="bright_white"))
                console.print()

        console.print(Text("BLURB", style="bold bright_cyan"))
        console.print(Padding(result.blurb, (1, 0, 1, 2)))

        console.print(Text("RESUME KEYWORDS", style="bold bright_magenta"))
        for kw in result.keywords:
            console.print(f"  • {kw}")
    finally:
        db.close()


def cmd_set_status(url: str, status: str):
    valid = {"new", "reviewed", "sent", "rejected"}
    if status not in valid:
        console.print(f"[red]Invalid status.[/] Must be one of: {', '.join(valid)}")
        return
    init_db()
    db = SessionLocal()
    try:
        posting = db.query(Posting).filter(Posting.url == url).first()
        if not posting:
            console.print(f"[red]Posting not found:[/] {url}")
            return
        posting.status = status
        db.commit()
        console.print(f"[green]✓[/] {posting.company or url} → {status}")
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    args = sys.argv[1:]

    if not args:
        cmd_run(source="all")

    elif "--list" in args:
        status = None
        for i, a in enumerate(args):
            if a == "--status" and i + 1 < len(args):
                status = args[i + 1]
        show_draft = "--draft" in args
        cmd_list(status_filter=status, show_draft=show_draft)

    elif "--draft-all" in args:
        cmd_draft_all()

    elif "--draft" in args:
        idx = args.index("--draft")
        if idx + 1 < len(args):
            cmd_draft(args[idx + 1])
        else:
            console.print("[red]Usage:[/] --draft <url>")

    elif "--tailor" in args:
        idx = args.index("--tailor")
        if idx + 1 < len(args):
            cmd_tailor(args[idx + 1])
        else:
            console.print("[red]Usage:[/] --tailor <url>")

    elif "--status" in args:
        idx = args.index("--status")
        if idx + 2 < len(args):
            cmd_set_status(args[idx + 1], args[idx + 2])
        else:
            console.print("[red]Usage:[/] --status <url> <new|reviewed|sent|rejected>")

    elif "--source" in args:
        idx = args.index("--source")
        if idx + 1 < len(args):
            cmd_run(source=args[idx + 1])
        else:
            console.print("[red]Usage:[/] --source <hn_who_is_hiring|remoteok|remotive|all>")

    else:
        console.print(__doc__)
