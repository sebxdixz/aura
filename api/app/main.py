from __future__ import annotations

import json
import os

from pydantic import BaseModel

from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

from .attachments import persist_attachment
from .database import SessionLocal, ensure_runtime_schema, get_db, ping_db
from .guardrails import validate_attachment, validate_description
from .insights import get_tenant_audit_logs, get_tenant_insights_summary
from .jobs import JOB_TYPE_PROCESS_INCIDENT, enqueue_job
from .models import (
    AuditLogRecord,
    AttachmentRecord,
    FileMeta,
    IncidentRecord,
    NotificationRecord,
    TenantDashboard,
    TenantInsightsSummary,
    TenantRecord,
)
from .observability import log_event, metrics_snapshot
from .rag import auto_index_enabled, index_github_repository, rag_status, reindex_codebase
from .services import (
    create_incident_id,
    ensure_tenant,
    find_duplicate_incident,
    get_incident,
    get_tenant,
    list_incidents,
    pending_ticket_record,
    queued_triage_output,
    register_tenant,
    resolve_incident,
    save_incident,
    tenant_dashboard,
)
from . import repository as repo
from .telemetry import setup_telemetry, start_span

app = FastAPI(title="AURA API", version="0.4.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class TenantRegisterPayload(BaseModel):
    tenant_id: str
    name: str


class GithubSyncPayload(BaseModel):
    tenant_id: str
    repo_url: str
    branch: str | None = None


@app.on_event("startup")
def startup_rag_bootstrap() -> None:
    setup_telemetry()
    ensure_runtime_schema()
    db = SessionLocal()
    try:
        status = rag_status(db)
        if auto_index_enabled():
            log_event("rag_index_started", repo_name=status["repo_name"])
            result = reindex_codebase(db)
            log_event(
                "rag_index_finished",
                repo_name=result.get("repo_name"),
                indexed_chunks=result.get("indexed_chunks", 0),
                indexed_files=result.get("indexed_files", 0),
                skipped=result.get("skipped", False),
            )
    except Exception as exc:
        log_event("rag_index_failed", error=str(exc))
    finally:
        db.close()


@app.get("/health")
def health() -> dict[str, str]:
    log_event("health_check")
    db_status = "ok" if ping_db() else "degraded"
    return {"status": "ok", "service": "api", "db": db_status}


@app.get("/")
def root() -> dict[str, str]:
    return {"name": "AURA API", "stage": "multi_tenant_persistent"}


@app.get("/metrics")
def metrics() -> dict[str, object]:
    snapshot = metrics_snapshot()
    return {"service": "api", **snapshot}


@app.get("/api/incidents", response_model=list[IncidentRecord])
def api_list_incidents(
    tenant_id: str | None = None,
    db: Session = Depends(get_db),
) -> list[IncidentRecord]:
    return list_incidents(db, tenant_id=tenant_id)


@app.get("/api/incidents/{incident_id}", response_model=IncidentRecord)
def api_get_incident(
    incident_id: str,
    db: Session = Depends(get_db),
) -> IncidentRecord:
    incident = get_incident(db, incident_id)
    if not incident:
        raise HTTPException(status_code=404, detail="incident not found")
    return incident


@app.post("/api/incidents/submit", response_model=IncidentRecord)
async def submit_incident(
    tenant_id: str = Form(...),
    reporter_email: str = Form(...),
    description: str = Form(...),
    attachment: UploadFile | None = File(default=None),
    db: Session = Depends(get_db),
) -> IncidentRecord:
    with start_span("api.submit_incident", **{"tenant.id": tenant_id}):
        try:
            validate_description(description)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        incident_id = create_incident_id()
        ensure_tenant(db, tenant_id=tenant_id)

        file_meta: FileMeta | None = None
        attachment_record: AttachmentRecord | None = None
        has_file = attachment is not None

        if attachment is not None:
            file_bytes = await attachment.read()
            content_type = attachment.content_type or "application/octet-stream"
            try:
                log_event(
                    "attachment_received",
                    incident_id=incident_id,
                    tenant_id=tenant_id,
                    attachment_type=content_type.lower(),
                )
                safe_filename = validate_attachment(
                    filename=attachment.filename,
                    content_type=attachment.content_type,
                    size_bytes=len(file_bytes),
                    content_bytes=file_bytes,
                )
                log_event(
                    "attachment_validated",
                    incident_id=incident_id,
                    tenant_id=tenant_id,
                    attachment_type=content_type.lower(),
                )
            except ValueError as exc:
                log_event(
                    "attachment_rejected",
                    incident_id=incident_id,
                    tenant_id=tenant_id,
                    attachment_type=content_type.lower(),
                    error=str(exc),
                )
                raise HTTPException(status_code=400, detail=str(exc)) from exc

            storage_path = persist_attachment(
                incident_id=incident_id,
                filename=safe_filename,
                content_bytes=file_bytes,
            )
            attachment_kind = "image" if content_type.startswith("image/") else "text"
            attachment_record = AttachmentRecord(
                attachment_type=attachment_kind,
                attachment_filename=safe_filename,
                attachment_mime_type=content_type,
                attachment_size_bytes=len(file_bytes),
                attachment_storage_path=storage_path,
                attachment_used=False,
            )
            file_meta = FileMeta(
                filename=safe_filename,
                content_type=content_type,
                size_bytes=len(file_bytes),
            )
            log_event(
                "attachment_saved",
                incident_id=incident_id,
                tenant_id=tenant_id,
                attachment_type=content_type.lower(),
            )

        log_event("incident_ingested", incident_id=incident_id, tenant_id=tenant_id, has_file=has_file)

        duplicate = find_duplicate_incident(db, tenant_id=tenant_id, description=description)
        if duplicate:
            triage = duplicate.triage.model_copy(deep=True)
            triage.is_duplicate = True
            triage.duplicate_of_incident_id = duplicate.incident_id
            triage.dedup_confidence = 0.98
            triage.technical_summary = (
                f"Deduplicated incident linked to {duplicate.incident_id}. "
                f"{triage.technical_summary}"
            )
            dedup_note = NotificationRecord(
                channel="team_communicator",
                status="sent",
                detail=f"Deduplicated with {duplicate.incident_id}; skipped new ticket/alert.",
            )
            incident = IncidentRecord(
                incident_id=incident_id,
                tenant_id=tenant_id,
                reporter_email=reporter_email,
                description=description,
                status="open",
                processing_state="triaged",
                file_meta=file_meta,
                attachment=attachment_record,
                triage=triage,
                ticket=duplicate.ticket,
                notifications=[dedup_note],
                related_links=[],
            )
            save_incident(db, incident)
            log_event("incident_deduplicated", incident_id=incident_id, tenant_id=tenant_id, duplicate_of=duplicate.incident_id)
            return incident

        incident = IncidentRecord(
            incident_id=incident_id,
            tenant_id=tenant_id,
            reporter_email=reporter_email,
            description=description,
            status="open",
            processing_state="submitted",
            file_meta=file_meta,
            attachment=attachment_record,
            triage=queued_triage_output(description),
            ticket=pending_ticket_record(),
            notifications=[],
            related_links=[],
        )
        save_incident(db, incident)
        enqueue_job(
            db,
            JOB_TYPE_PROCESS_INCIDENT,
            {"incident_id": incident_id},
            incident_id=incident_id,
        )
        return get_incident(db, incident_id) or incident


@app.post("/api/incidents/{incident_id}/resolve", response_model=IncidentRecord)
def api_resolve_incident(
    incident_id: str,
    db: Session = Depends(get_db),
) -> IncidentRecord:
    with start_span("api.resolve_incident", **{"incident.id": incident_id}):
        incident = resolve_incident(db, incident_id)
        if not incident:
            raise HTTPException(status_code=404, detail="incident not found")
        return incident


@app.post("/api/tenants/register", response_model=TenantRecord)
def api_register_tenant(
    payload: TenantRegisterPayload,
    db: Session = Depends(get_db),
) -> TenantRecord:
    if not payload.tenant_id.strip() or not payload.name.strip():
        raise HTTPException(status_code=400, detail="tenant_id and name are required")
    return register_tenant(db, tenant_id=payload.tenant_id.strip(), name=payload.name.strip())


@app.get("/api/tenants/{tenant_id}", response_model=TenantRecord)
def api_get_tenant(
    tenant_id: str,
    db: Session = Depends(get_db),
) -> TenantRecord:
    tenant = get_tenant(db, tenant_id)
    if not tenant:
        raise HTTPException(status_code=404, detail="tenant not found")
    return tenant


@app.get("/api/tenants/{tenant_id}/dashboard", response_model=TenantDashboard)
def api_tenant_dashboard(
    tenant_id: str,
    db: Session = Depends(get_db),
) -> TenantDashboard:
    tenant = get_tenant(db, tenant_id)
    if not tenant:
        raise HTTPException(status_code=404, detail="tenant not found")
    return tenant_dashboard(db, tenant_id=tenant_id)


@app.get("/api/tenants/{tenant_id}/audit-logs", response_model=list[AuditLogRecord])
def api_tenant_audit_logs(
    tenant_id: str,
    limit: int = 100,
    incident_id: str | None = None,
    db: Session = Depends(get_db),
) -> list[AuditLogRecord]:
    tenant = get_tenant(db, tenant_id)
    if not tenant:
        raise HTTPException(status_code=404, detail="tenant not found")
    return get_tenant_audit_logs(db, tenant_id=tenant_id, limit=limit, incident_id=incident_id)


@app.get("/api/tenants/{tenant_id}/insights/summary", response_model=TenantInsightsSummary)
def api_tenant_insights_summary(
    tenant_id: str,
    db: Session = Depends(get_db),
) -> TenantInsightsSummary:
    tenant = get_tenant(db, tenant_id)
    if not tenant:
        raise HTTPException(status_code=404, detail="tenant not found")
    return get_tenant_insights_summary(db, tenant_id=tenant_id)


@app.get("/api/rag/status")
def api_rag_status(tenant_id: str | None = None, db: Session = Depends(get_db)) -> dict[str, object]:
    return rag_status(db, tenant_id=tenant_id)


@app.post("/api/rag/reindex")
def api_rag_reindex(
    tenant_id: str,
    x_tenant_admin_key: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    _assert_tenant_admin(tenant_id, x_tenant_admin_key)
    log_event("rag_reindex_triggered")
    return reindex_codebase(db, tenant_id=tenant_id)


@app.post("/api/rag/github-sync")
def api_rag_github_sync(
    payload: GithubSyncPayload,
    x_tenant_admin_key: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> dict:
    tenant_id = payload.tenant_id.strip()
    if not tenant_id:
        raise HTTPException(status_code=400, detail="tenant_id is required")
    if not payload.repo_url.strip():
        raise HTTPException(status_code=400, detail="repo_url is required")

    tenant = get_tenant(db, tenant_id)
    if not tenant:
        raise HTTPException(status_code=404, detail="tenant not found")

    _assert_tenant_admin(tenant_id, x_tenant_admin_key)
    log_event("github_sync_triggered", tenant_id=tenant_id, url=payload.repo_url)
    try:
        return index_github_repository(
            db,
            tenant_id=tenant_id,
            repo_url=payload.repo_url.strip(),
            branch=payload.branch,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def _assert_tenant_admin(tenant_id: str, provided_key: str | None) -> None:
    token = (provided_key or "").strip()
    if not token:
        raise HTTPException(status_code=401, detail="x-tenant-admin-key header is required")

    per_tenant_raw = os.getenv("TENANT_ADMIN_KEYS_JSON", "").strip()
    if per_tenant_raw:
        try:
            mapping = json.loads(per_tenant_raw)
        except json.JSONDecodeError as exc:
            raise HTTPException(status_code=500, detail="TENANT_ADMIN_KEYS_JSON is invalid JSON") from exc
        if isinstance(mapping, dict):
            expected = str(mapping.get(tenant_id, "")).strip()
            if expected and token == expected:
                return

    fallback = os.getenv("TENANT_ADMIN_KEY", "").strip()
    if fallback and token == fallback:
        return
    raise HTTPException(status_code=403, detail="invalid tenant admin credentials")


@app.post("/api/auth/verify")
def api_auth_verify(
    tenant_id: str = Header(..., alias="x-tenant-id"),
    x_tenant_admin_key: str = Header(...),
) -> dict:
    _assert_tenant_admin(tenant_id, x_tenant_admin_key)
    return {"status": "ok", "tenant_id": tenant_id}
