from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from .observability import log_event

JOB_TYPE_PROCESS_INCIDENT = "process_incident"
JOB_TYPE_SYNC_TICKET_STATUS = "sync_ticket_status"
JOB_TYPE_NOTIFY_REPORTER = "notify_reporter"

JOB_STATUS_QUEUED = "queued"
JOB_STATUS_RUNNING = "running"
JOB_STATUS_COMPLETED = "completed"
JOB_STATUS_FAILED = "failed"


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def enqueue_job(
    db: Session,
    job_type: str,
    payload: dict[str, Any],
    *,
    max_attempts: int = 3,
    run_after: datetime | None = None,
    incident_id: str | None = None,
) -> int:
    row = db.execute(
        text(
            """
            INSERT INTO jobs (job_type, status, payload, max_attempts, run_after)
            VALUES (:job_type, 'queued', cast(:payload as jsonb), :max_attempts, :run_after)
            RETURNING id
            """
        ),
        {
            "job_type": job_type,
            "payload": json.dumps(payload),
            "max_attempts": max_attempts,
            "run_after": run_after or _utc_now(),
        },
    ).fetchone()
    db.commit()
    job_id = int(row.id)
    log_event("job_enqueued", incident_id=incident_id, job_id=job_id, job_type=job_type)
    return job_id


def has_pending_job(db: Session, job_type: str, incident_id: str) -> bool:
    row = db.execute(
        text(
            """
            SELECT 1
            FROM jobs
            WHERE job_type = :job_type
              AND status IN ('queued', 'running')
              AND payload->>'incident_id' = :incident_id
            LIMIT 1
            """
        ),
        {"job_type": job_type, "incident_id": incident_id},
    ).fetchone()
    return bool(row)


def claim_next_job(db: Session, worker_name: str) -> dict[str, Any] | None:
    row = db.execute(
        text(
            """
            WITH candidate AS (
                SELECT id
                FROM jobs
                WHERE status = 'queued'
                  AND run_after <= NOW()
                ORDER BY created_at ASC
                FOR UPDATE SKIP LOCKED
                LIMIT 1
            )
            UPDATE jobs
            SET status = 'running',
                attempts = attempts + 1,
                locked_at = NOW(),
                locked_by = :worker_name,
                updated_at = NOW()
            WHERE id IN (SELECT id FROM candidate)
            RETURNING id, job_type, status, payload, attempts, max_attempts, run_after, locked_at, locked_by, last_error, created_at, updated_at
            """
        ),
        {"worker_name": worker_name},
    ).fetchone()
    db.commit()
    if not row:
        return None
    payload = row.payload if isinstance(row.payload, dict) else json.loads(row.payload or "{}")
    incident_id = payload.get("incident_id")
    log_event("job_claimed", incident_id=incident_id, job_id=row.id, job_type=row.job_type, worker_name=worker_name)
    return {
        "id": row.id,
        "job_type": row.job_type,
        "status": row.status,
        "payload": payload,
        "attempts": row.attempts,
        "max_attempts": row.max_attempts,
    }


def complete_job(db: Session, job_id: int, *, incident_id: str | None = None, job_type: str | None = None) -> None:
    db.execute(
        text(
            """
            UPDATE jobs
            SET status = 'completed',
                updated_at = NOW()
            WHERE id = :job_id
            """
        ),
        {"job_id": job_id},
    )
    db.commit()
    log_event("job_completed", incident_id=incident_id, job_id=job_id, job_type=job_type)


def fail_job(
    db: Session,
    job_id: int,
    error: str,
    *,
    incident_id: str | None = None,
    job_type: str | None = None,
) -> None:
    db.execute(
        text(
            """
            UPDATE jobs
            SET status = 'failed',
                last_error = :error,
                updated_at = NOW()
            WHERE id = :job_id
            """
        ),
        {"job_id": job_id, "error": error[:2000]},
    )
    db.commit()
    log_event("job_failed", incident_id=incident_id, job_id=job_id, job_type=job_type, error=error[:500])


def reschedule_job(
    db: Session,
    job_id: int,
    delay_seconds: int,
    error: str,
    *,
    incident_id: str | None = None,
    job_type: str | None = None,
) -> None:
    run_after = _utc_now() + timedelta(seconds=max(delay_seconds, 1))
    db.execute(
        text(
            """
            UPDATE jobs
            SET status = 'queued',
                locked_at = NULL,
                locked_by = NULL,
                run_after = :run_after,
                last_error = :error,
                updated_at = NOW()
            WHERE id = :job_id
            """
        ),
        {"job_id": job_id, "run_after": run_after, "error": error[:2000]},
    )
    db.commit()
    log_event("job_retried", incident_id=incident_id, job_id=job_id, job_type=job_type, error=error[:500], delay_seconds=delay_seconds)
