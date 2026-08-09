"""
One-off backfill: populate posted_at for existing HN postings that predate
the posted_at column being wired up in the fetcher (they were inserted with
NULL and never re-touched since _store() dedupes by URL and skips existing rows).

Run once:
  python backfill_posted_at.py
"""
import re
import time
from datetime import datetime, timezone

import httpx

from app.db.database import init_db, SessionLocal, Posting

HN_ITEM_URL = "https://hn.algolia.com/api/v1/items/{id}"
HN_URL_RE = re.compile(r"id=(\d+)")


def main():
    init_db()
    db = SessionLocal()
    try:
        postings = (
            db.query(Posting)
            .filter(Posting.source == "hn_who_is_hiring", Posting.posted_at.is_(None))
            .all()
        )
        print(f"Backfilling {len(postings)} posting(s)...")

        updated = failed = 0
        for i, p in enumerate(postings, 1):
            m = HN_URL_RE.search(p.url or "")
            if not m:
                failed += 1
                continue
            item_id = m.group(1)
            try:
                resp = httpx.get(HN_ITEM_URL.format(id=item_id), timeout=15)
                resp.raise_for_status()
                created_at = resp.json().get("created_at")
                if created_at:
                    p.posted_at = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
                    updated += 1
                else:
                    failed += 1
            except Exception as e:
                print(f"  [{i}/{len(postings)}] failed for {item_id}: {e}")
                failed += 1

            if i % 20 == 0:
                db.commit()
                print(f"  [{i}/{len(postings)}] committed...")
            time.sleep(0.1)  # be polite to the Algolia API

        db.commit()
        print(f"Done. Updated {updated}, failed {failed}.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
