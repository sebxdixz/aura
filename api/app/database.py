"""
database.py – Engine / Session factory for AURA.

Usage (FastAPI dependency):

    from .database import get_db

    @app.get("/...")
    def my_route(db: Session = Depends(get_db)):
        ...
"""
from __future__ import annotations

import os
from typing import Generator

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

DATABASE_URL: str = os.environ["DATABASE_URL"]

engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,       # detect stale connections
    pool_size=5,
    max_overflow=10,
    connect_args={"connect_timeout": 10},
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


RUNTIME_MIGRATIONS = [
    "ALTER TABLE incidents ADD COLUMN IF NOT EXISTS attachment_type VARCHAR(40)",
    "ALTER TABLE incidents ADD COLUMN IF NOT EXISTS attachment_filename VARCHAR(255)",
    "ALTER TABLE incidents ADD COLUMN IF NOT EXISTS attachment_mime_type VARCHAR(120)",
    "ALTER TABLE incidents ADD COLUMN IF NOT EXISTS attachment_size_bytes INTEGER",
    "ALTER TABLE incidents ADD COLUMN IF NOT EXISTS attachment_storage_path TEXT",
    "ALTER TABLE incidents ADD COLUMN IF NOT EXISTS attachment_text_extracted TEXT",
    "ALTER TABLE incidents ADD COLUMN IF NOT EXISTS attachment_summary TEXT",
    "ALTER TABLE incidents ADD COLUMN IF NOT EXISTS evidence_from_attachment JSONB NOT NULL DEFAULT '[]'::jsonb",
    "ALTER TABLE incidents ADD COLUMN IF NOT EXISTS attachment_signals JSONB NOT NULL DEFAULT '{}'::jsonb",
    "ALTER TABLE incidents ADD COLUMN IF NOT EXISTS attachment_used BOOLEAN NOT NULL DEFAULT false",
]


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency that provides a DB session per request."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def ping_db() -> bool:
    """Return True if the DB is reachable (used at startup)."""
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


def ensure_runtime_schema() -> None:
    with engine.begin() as conn:
        for statement in RUNTIME_MIGRATIONS:
            conn.execute(text(statement))
