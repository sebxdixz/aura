from __future__ import annotations

import os
import socket
import time

from .database import SessionLocal, ensure_runtime_schema
from .job_handlers import handle_notify_reporter, handle_process_incident, handle_sync_ticket_status
from .jobs import (
    JOB_TYPE_NOTIFY_REPORTER,
    JOB_TYPE_PROCESS_INCIDENT,
    JOB_TYPE_SYNC_TICKET_STATUS,
    claim_next_job,
    complete_job,
    enqueue_job,
    fail_job,
    has_pending_job,
    reschedule_job,
)
from .observability import log_event
from .telemetry import setup_telemetry, start_span
from . import repository as repo

POLL_INTERVAL_SECONDS = float(os.getenv("WORKER_POLL_INTERVAL_SECONDS", "2"))
SYNC_INTERVAL_SECONDS = float(os.getenv("WORKER_TICKET_SYNC_INTERVAL_SECONDS", "60"))
RETRY_DELAY_SECONDS = int(os.getenv("WORKER_RETRY_DELAY_SECONDS", "5"))


def run_job(job: dict[str, object]) -> None:
    payload = dict(job["payload"])
    incident_id = payload.get("incident_id")
    job_type = str(job["job_type"])
    with SessionLocal() as db:
        log_event("job_started", incident_id=incident_id, job_id=job["id"], job_type=job_type)
        with start_span("worker.run_job", **{"job.id": int(job["id"]), "job.type": job_type, "incident.id": incident_id}):
            if job_type == JOB_TYPE_PROCESS_INCIDENT:
                handle_process_incident(db, str(incident_id))
            elif job_type == JOB_TYPE_SYNC_TICKET_STATUS:
                handle_sync_ticket_status(
                    db,
                    incident_id=str(incident_id),
                    provider=str(payload.get("provider", "")),
                    external_ticket_id=str(payload.get("external_ticket_id", "")),
                )
            elif job_type == JOB_TYPE_NOTIFY_REPORTER:
                handle_notify_reporter(db, str(incident_id))
            else:
                raise RuntimeError(f"unknown job type: {job_type}")


def schedule_sync_jobs() -> None:
    with SessionLocal() as db:
        for incident in repo.list_open_incidents_with_external_ticket(db):
            if not incident.ticket.ticket_id or not incident.ticket.provider:
                continue
            if has_pending_job(db, JOB_TYPE_SYNC_TICKET_STATUS, incident.incident_id):
                continue
            enqueue_job(
                db,
                JOB_TYPE_SYNC_TICKET_STATUS,
                {
                    "incident_id": incident.incident_id,
                    "provider": incident.ticket.provider,
                    "external_ticket_id": incident.ticket.ticket_id,
                },
                incident_id=incident.incident_id,
            )


def main() -> None:
    ensure_runtime_schema()
    setup_telemetry()
    worker_name = os.getenv("WORKER_NAME", f"worker-{socket.gethostname()}")
    last_sync = 0.0
    log_event("worker_started", worker_name=worker_name)

    while True:
        try:
            now = time.time()
            if now - last_sync >= SYNC_INTERVAL_SECONDS:
                schedule_sync_jobs()
                last_sync = now

            with SessionLocal() as db:
                with start_span("worker.claim_job", **{"worker.name": worker_name}):
                    job = claim_next_job(db, worker_name)
            if not job:
                time.sleep(POLL_INTERVAL_SECONDS)
                continue

            incident_id = dict(job["payload"]).get("incident_id")
            job_type = str(job["job_type"])
            try:
                run_job(job)
                with SessionLocal() as db:
                    complete_job(db, int(job["id"]), incident_id=str(incident_id) if incident_id else None, job_type=job_type)
            except Exception as exc:
                if job_type == JOB_TYPE_SYNC_TICKET_STATUS:
                    log_event(
                        "ticket_status_sync_failed",
                        incident_id=str(incident_id) if incident_id else None,
                        job_id=int(job["id"]),
                        error=str(exc),
                    )
                with SessionLocal() as db:
                    if int(job["attempts"]) < int(job["max_attempts"]):
                        reschedule_job(
                            db,
                            int(job["id"]),
                            RETRY_DELAY_SECONDS,
                            str(exc),
                            incident_id=str(incident_id) if incident_id else None,
                            job_type=job_type,
                        )
                    else:
                        fail_job(
                            db,
                            int(job["id"]),
                            str(exc),
                            incident_id=str(incident_id) if incident_id else None,
                            job_type=job_type,
                        )
                        if incident_id:
                            repo.update_incident_processing_state(db, str(incident_id), "failed", last_error=str(exc))
        except Exception as exc:
            log_event("worker_loop_failed", worker_name=worker_name, error=str(exc))
            time.sleep(POLL_INTERVAL_SECONDS)


if __name__ == "__main__":
    main()
