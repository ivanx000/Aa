from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.ingestion.fetcher import fetch_and_store
from app.pipeline import run_pipeline

router = APIRouter()


@router.post("/run")
def run_ingestion(source: str = "hn_who_is_hiring", db: Session = Depends(get_db)):
    """Ingest only — no filtering or drafting."""
    return fetch_and_store(source=source, db=db)


@router.post("/pipeline")
def run_full_pipeline(source: str = "hn_who_is_hiring", db: Session = Depends(get_db)):
    """Full pass: ingest → filter → draft → save."""
    return run_pipeline(source=source, db=db)
