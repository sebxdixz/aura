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
    "ALTER TABLE incidents ADD COLUMN IF NOT EXISTS processing_state VARCHAR(20) NOT NULL DEFAULT 'submitted'",
    "ALTER TABLE incidents ADD COLUMN IF NOT EXISTS attachment_filename VARCHAR(255)",
    "ALTER TABLE incidents ADD COLUMN IF NOT EXISTS attachment_mime_type VARCHAR(120)",
    "ALTER TABLE incidents ADD COLUMN IF NOT EXISTS attachment_size_bytes INTEGER",
    "ALTER TABLE incidents ADD COLUMN IF NOT EXISTS attachment_storage_path TEXT",
    "ALTER TABLE incidents ADD COLUMN IF NOT EXISTS attachment_text_extracted TEXT",
    "ALTER TABLE incidents ADD COLUMN IF NOT EXISTS attachment_summary TEXT",
    "ALTER TABLE incidents ADD COLUMN IF NOT EXISTS evidence_from_attachment JSONB NOT NULL DEFAULT '[]'::jsonb",
    "ALTER TABLE incidents ADD COLUMN IF NOT EXISTS attachment_signals JSONB NOT NULL DEFAULT '{}'::jsonb",
    "ALTER TABLE incidents ADD COLUMN IF NOT EXISTS attachment_used BOOLEAN NOT NULL DEFAULT false",
    "ALTER TABLE incidents ADD COLUMN IF NOT EXISTS duplicate_of_incident_id VARCHAR(64)",
    "ALTER TABLE incidents ADD COLUMN IF NOT EXISTS cluster_id TEXT",
    "ALTER TABLE incidents ADD COLUMN IF NOT EXISTS recurrence_count_7d INTEGER NOT NULL DEFAULT 0",
    "ALTER TABLE incidents ADD COLUMN IF NOT EXISTS recurrence_count_30d INTEGER NOT NULL DEFAULT 0",
    "ALTER TABLE incidents ADD COLUMN IF NOT EXISTS related_links JSONB NOT NULL DEFAULT '[]'::jsonb",
    "ALTER TABLE incidents ADD COLUMN IF NOT EXISTS scope_assessment TEXT",
    "ALTER TABLE incidents ADD COLUMN IF NOT EXISTS multi_ticket_influence_reasoning TEXT",
    (
        "CREATE TABLE IF NOT EXISTS incident_links ("
        "id BIGSERIAL PRIMARY KEY, "
        "tenant_id VARCHAR(100) NOT NULL, "
        "source_incident_id VARCHAR(64) NOT NULL, "
        "target_incident_id VARCHAR(64) NOT NULL, "
        "relationship_type VARCHAR(32) NOT NULL, "
        "similarity_score DOUBLE PRECISION NOT NULL, "
        "reasoning TEXT, "
        "shared_signals JSONB NOT NULL DEFAULT '[]'::jsonb, "
        "created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()"
        ")"
    ),
    "CREATE INDEX IF NOT EXISTS idx_incident_links_tenant ON incident_links (tenant_id)",
    "CREATE INDEX IF NOT EXISTS idx_incident_links_source ON incident_links (source_incident_id)",
    "CREATE INDEX IF NOT EXISTS idx_incident_links_target ON incident_links (target_incident_id)",
    (
        "CREATE TABLE IF NOT EXISTS jobs ("
        "id BIGSERIAL PRIMARY KEY, "
        "job_type TEXT NOT NULL, "
        "status TEXT NOT NULL DEFAULT 'queued', "
        "payload JSONB NOT NULL, "
        "attempts INTEGER NOT NULL DEFAULT 0, "
        "max_attempts INTEGER NOT NULL DEFAULT 3, "
        "run_after TIMESTAMPTZ NOT NULL DEFAULT NOW(), "
        "locked_at TIMESTAMPTZ NULL, "
        "locked_by TEXT NULL, "
        "last_error TEXT NULL, "
        "created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), "
        "updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()"
        ")"
    ),
    "CREATE INDEX IF NOT EXISTS idx_incidents_processing_state ON incidents (processing_state)",
    "CREATE INDEX IF NOT EXISTS idx_jobs_status_run_after ON jobs (status, run_after)",
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
