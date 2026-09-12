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
  python run_pipeline.py --trends                    Top skills/tools in demand this week
  python run_pipeline.py --trends --days 30 --top 20  Custom window and list size
  python run_pipeline.py --watch-linkedin             Poll LinkedIn and notify on new matches
  python run_pipeline.py --watch-linkedin --keywords "Software Engineer Intern" --location Canada --interval 300
  python run_pipeline.py --watch-linkedin --once      Single check-and-notify pass (for cron/launchd)
"""
import sys
import time
import json
from datetime import datetime, timezone, timedelta

from rich.console import Console
from rich.text import Text
from rich.rule import Rule
from rich.padding import Padding
from rich import print as rprint

from app.config import settings
from app.db.database import init_db, SessionLocal, Posting
from app.pipeline import run_pipeline
from app.drafting.drafter import draft as generate_draft, tailor as generate_tailor
from app.analytics.trends import compute_trends
from app.notify.notifier import notify

console = Console()

MAX_POSTING_AGE_DAYS = 3


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


def age_color(dt: datetime | None) -> str:
    """Green when fresh, sliding through yellow to red as a posting nears MAX_POSTING_AGE_DAYS."""
    if dt is None:
        return "grey58"
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    hours = max(0.0, (datetime.now(timezone.utc) - dt).total_seconds() / 3600)
    frac = min(1.0, hours / (MAX_POSTING_AGE_DAYS * 24))

    stops = [(0.0, (90, 230, 110)), (0.5, (240, 210, 60)), (1.0, (235, 70, 70))]
    (f0, c0), (f1, c1) = next(
        (a, b) for a, b in zip(stops, stops[1:]) if frac <= b[0]
    )
    t = 0.0 if f1 == f0 else (frac - f0) / (f1 - f0)
    r, g, b = (round(c0[i] + (c1[i] - c0[i]) * t) for i in range(3))
    return f"rgb({r},{g},{b})"


STATUS_COLOR = {
    "new":      "bright_cyan",
    "reviewed": "bright_yellow",
    "sent":     "bright_green",
    "rejected": "grey58",
}

SOURCE_LABEL = {
    "hn_who_is_hiring": "HN",
    "remoteok":         "RemoteOK",
    "remotive":         "Remotive",
    "adzuna":           "Adzuna",
    "linkedin":         "LinkedIn",
}


def print_posting(p: Posting, show_draft: bool = False, show_tailor: bool = False):
    status_color = STATUS_COLOR.get(p.status, "white")
    source_label = SOURCE_LABEL.get(p.source, p.source or "?")

    # Header line: company + title
    company = (p.company or "Unknown").strip()
    title   = (p.title   or "").strip()

    header = Text()
    if p.status != "new":
        header.append(f"  [{p.status.upper()}]", style=f"bold {status_color}")
    header.append(f"  {company}", style=f"bold {status_color}")
    if title and title != company:
        # Trim title to avoid repetition if it starts with company name
        short_title = title[len(company):].lstrip(" |–-").strip() if title.lower().startswith(company.lower()) else title
        if short_title:
            header.append(f"  ·  {short_title[:90]}", style="bright_white")

    console.print(header)

    # Meta line: source, time, url
    meta = Text()
    meta.append(f"    [{source_label}]", style="bold cyan")
    meta.append(f"  {relative_time(p.posted_at)}", style=f"bold {age_color(p.posted_at)}")
    meta.append(f"  {p.url}", style="bright_blue underline")
    console.print(meta)

    # Keywords (if available)
    if p.keywords:
        try:
            kws = json.loads(p.keywords)
            if kws:
                kw_text = Text("    ")
                kw_text.append("keywords: ", style="grey58")
                kw_text.append("  ".join(f"#{k}" for k in kws), style="bright_magenta")
                console.print(kw_text)
        except (json.JSONDecodeError, TypeError):
            pass

    # Blurb (if requested and available)
    if show_draft and p.draft:
        console.print()
        console.print(Padding(Text(p.draft, style="italic bright_white"), (0, 0, 0, 4)))

    # Tailoring (if requested and available)
    if show_tailor and p.tailoring:
        try:
            t = json.loads(p.tailoring)
            console.print()
            console.print(Text("    ── TAILORING ──", style="bold bright_yellow"))

            if t.get("bullets_to_emphasize"):
                console.print(Text("    Emphasize these bullets:", style="bright_yellow"))
                for b in t["bullets_to_emphasize"]:
                    console.print(Text(f"      • {b}", style="bright_white"))

            if t.get("rewrites"):
                console.print()
                console.print(Text("    Suggested rewrites:", style="bright_yellow"))
                for r in t["rewrites"]:
                    console.print(Text(f"      Before: {r.get('original','')}", style="grey58"))
                    console.print(Text(f"      After:  {r.get('suggested','')}", style="bright_white"))

            if t.get("blurb"):
                console.print()
                console.print(Text("    Blurb:", style="bright_yellow"))
                console.print(Padding(Text(t["blurb"], style="italic bright_white"), (0, 0, 0, 6)))
        except (json.JSONDecodeError, TypeError):
            pass

    console.print(Rule(style="grey35"))


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

        cutoff = datetime.now(timezone.utc) - timedelta(days=MAX_POSTING_AGE_DAYS)
        q = q.filter(Posting.posted_at.isnot(None), Posting.posted_at >= cutoff)

        postings = q.order_by(Posting.posted_at.desc().nullslast()).all()

        if not postings:
            console.print(f"[dim]No postings found within the last {MAX_POSTING_AGE_DAYS} days.[/]")
            return

        label = status_filter or "new"
        console.print(Rule(f"[bold cyan]{len(postings)} posting(s) — {label} — last {MAX_POSTING_AGE_DAYS}d[/]"))
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


CATEGORY_COLOR = {
    "language":  "bright_cyan",
    "framework": "bright_magenta",
    "ml":        "bright_green",
    "cloud":     "bright_yellow",
    "database":  "bright_blue",
    "tool":      "grey70",
}

BAR_WIDTH = 30


def cmd_trends(days: int, top_n: int):
    init_db()
    db = SessionLocal()
    try:
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        postings = (
            db.query(Posting)
            .filter(Posting.posted_at.isnot(None), Posting.posted_at >= cutoff)
            .all()
        )

        if not postings:
            console.print(f"[dim]No postings found within the last {days} day(s).[/]")
            return

        results = compute_trends(postings, top_n=top_n)
        if not results:
            console.print("[dim]No recognized skills/tools found in this window.[/]")
            return

        console.print(Rule(
            f"[bold cyan]Top {len(results)} skills — last {days}d "
            f"({len(postings)} posting(s) scanned)[/]"
        ))
        console.print()

        max_count = results[0].count
        for i, r in enumerate(results, 1):
            color = CATEGORY_COLOR.get(r.category, "white")
            filled = round((r.count / max_count) * BAR_WIDTH) if max_count else 0
            bar = "█" * filled + "░" * (BAR_WIDTH - filled)

            line = Text()
            line.append(f"  {i:>2}. ", style="grey58")
            line.append(f"{r.name:<14}", style=f"bold {color}")
            line.append(f" {bar} ", style=color)
            line.append(f"{r.count:>3}", style="bright_white")
            line.append(f"  ({r.pct:.0f}%)", style="grey58")
            console.print(line)

        console.print()
    finally:
        db.close()


def cmd_watch_linkedin(keywords: str, location: str, interval: int, once: bool):
    init_db()
    label = f'"{keywords}"' + (f" in {location}" if location else " (anywhere)")
    console.print(Rule(f"[bold cyan]Watching LinkedIn — {label}[/]"))
    if once:
        console.print("[dim]Single pass.[/]")
    else:
        console.print(f"[dim]Polling every {interval}s. Press Ctrl+C to stop.[/]")
    console.print()

    while True:
        db = SessionLocal()
        try:
            result = run_pipeline(source="linkedin", db=db, keywords=keywords, location=location)
            if "error" in result:
                console.print(f"[red]Error:[/] {result['error']}")
            else:
                to_notify = (
                    db.query(Posting)
                    .filter(
                        Posting.source == "linkedin",
                        Posting.status == "new",
                        Posting.notified_at.is_(None),
                    )
                    .all()
                )
                for p in to_notify:
                    console.print(f"[bold bright_green]NEW[/]  {p.company or 'Unknown'} — {p.title}")
                    console.print(f"      {p.url}")
                    notify(
                        title="New LinkedIn posting",
                        subtitle=p.company or "",
                        message=p.title or "",
                        url=p.url,
                    )
                    p.notified_at = datetime.now(timezone.utc)
                db.commit()
                if not to_notify:
                    console.print("[dim]No new matches this pass.[/]")
        except Exception as e:
            console.print(f"[red]Watch error:[/] {e}")
        finally:
            db.close()

        if once:
            break
        time.sleep(interval)


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

    elif "--trends" in args:
        days = 7
        top_n = 15
        for i, a in enumerate(args):
            if a == "--days" and i + 1 < len(args):
                days = int(args[i + 1])
            elif a == "--top" and i + 1 < len(args):
                top_n = int(args[i + 1])
        cmd_trends(days=days, top_n=top_n)

    elif "--source" in args:
        idx = args.index("--source")
        if idx + 1 < len(args):
            cmd_run(source=args[idx + 1])
        else:
            console.print("[red]Usage:[/] --source <hn_who_is_hiring|remoteok|remotive|adzuna|linkedin|all>")

    elif "--watch-linkedin" in args:
        keywords = settings.linkedin_keywords
        location = settings.linkedin_location
        interval = 300
        once = "--once" in args
        for i, a in enumerate(args):
            if a == "--keywords" and i + 1 < len(args):
                keywords = args[i + 1]
            elif a == "--location" and i + 1 < len(args):
                location = args[i + 1]
            elif a == "--interval" and i + 1 < len(args):
                interval = int(args[i + 1])
        cmd_watch_linkedin(keywords=keywords, location=location, interval=interval, once=once)

    else:
        console.print(__doc__)
