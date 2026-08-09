"""
Tracker — writes posting + draft + status to the DB.
The React dashboard (or Airtable/Notion) reads from here.
Status flow: new → reviewed → sent | rejected
"""
import json
from sqlalchemy.orm import Session
from app.db.database import Posting


def update_status(url: str, status: str, db: Session) -> dict:
    valid = {"new", "reviewed", "sent", "rejected"}
    if status not in valid:
        return {"error": f"Invalid status. Must be one of {valid}"}

    posting = db.query(Posting).filter(Posting.url == url).first()
    if not posting:
        return {"error": "Posting not found"}

    posting.status = status
    db.commit()
    return {"url": url, "status": status}


def list_postings(status: str | None, db: Session) -> list[dict]:
    q = db.query(Posting)
    if status:
        q = q.filter(Posting.status == status)
    return [
        {
            "url": p.url,
            "title": p.title,
            "company": p.company,
            "status": p.status,
            "fetched_at": p.fetched_at.isoformat() if p.fetched_at else None,
            "draft": p.draft,
            "keywords": json.loads(p.keywords) if p.keywords else [],
        }
        for p in q.order_by(Posting.fetched_at.desc()).all()
    ]
