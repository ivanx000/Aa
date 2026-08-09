from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends
from sqlalchemy.orm import Session

from app.db.database import init_db, get_db
from app.ingestion.router import router as ingestion_router
from app.tracker.tracker import list_postings, update_status


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(title="Job Pipeline", version="0.1.0", lifespan=lifespan)

app.include_router(ingestion_router, prefix="/ingestion", tags=["ingestion"])


@app.get("/health")
def health():
    return {"status": "ok"}


# ── Tracker endpoints ────────────────────────────────────────────────────────

@app.get("/postings")
def get_postings(status: str | None = None, db: Session = Depends(get_db)):
    """List postings, optionally filtered by status (new/reviewed/sent/rejected)."""
    return list_postings(status=status, db=db)


@app.patch("/postings/{url:path}/status")
def set_status(url: str, status: str, db: Session = Depends(get_db)):
    """Update a posting's status."""
    return update_status(url=url, status=status, db=db)
