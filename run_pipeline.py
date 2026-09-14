"""
LinkedIn watch notifier.

Commands:
  python run_pipeline.py --watch-linkedin             Poll LinkedIn and notify on new matches
  python run_pipeline.py --watch-linkedin --keywords "Software Engineer Intern" --location Canada --interval 300
  python run_pipeline.py --watch-linkedin --once      Single check-and-notify pass (for cron/launchd)
"""
import sys
import time
from datetime import datetime, timezone

from rich.console import Console
from rich.rule import Rule

from app.config import settings
from app.db.database import init_db, SessionLocal, Posting
from app.pipeline import run_pipeline
from app.notify.notifier import notify

console = Console()


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


if __name__ == "__main__":
    args = sys.argv[1:]

    if "--watch-linkedin" in args:
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
