"""
repository.py – Data-access layer for AURA.

All SQL uses SQLAlchemy Core text() so it works with SQLAlchemy 2.x.
Every public function receives a Session and applies tenant_id
filtering where required for strict multi-tenant isolation.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from .models import (
    AuditLogRecord,
    IncidentRecord,
    NotificationRecord,
    TenantInsightsSummary,
    TenantDashboard,
    TenantRecord,
)


# ──────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────

def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: Any) -> str:
    if value is None:
        return ""
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def _iso_or_none(value: Any) -> str | None:
    if value is None:
        return None
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def _row_to_tenant(row: Any) -> TenantRecord:
    return TenantRecord(
        tenant_id=row.tenant_id,
        name=row.name,
        intake_url=row.intake_url,
        created_at=_iso(row.created_at),
    )


def _row_to_incident(row: Any) -> IncidentRecord:
    """Reconstruct a full IncidentRecord from a DB row.

    psycopg2 deserialises JSONB columns into Python dicts automatically,
    so we can pass them directly to Pydantic for coercion.
    """
    notifications_raw: list[dict] = row.notifications or []
    notifications = [NotificationRecord(**n) for n in notifications_raw]

    return IncidentRecord(
        incident_id=row.incident_id,
        tenant_id=row.tenant_id,
        reporter_email=row.reporter_email,
        description=row.description,
        status=row.status,
        created_at=_iso(row.created_at),
        resolved_at=_iso_or_none(row.resolved_at),
        file_meta=row.file_meta,       # dict | None  → Pydantic coerces to FileMeta
        triage=row.triage,             # dict         → Pydantic coerces to TriageOutput
        ticket=row.ticket,             # dict         → Pydantic coerces to TicketRecord
        notifications=notifications,
    )


def _row_to_audit(row: Any) -> AuditLogRecord:
    payload = row.payload if isinstance(row.payload, dict) else (row.payload or {})
    return AuditLogRecord(
        id=row.id,
        tenant_id=row.tenant_id,
        incident_id=row.incident_id,
        stage=row.stage,
        payload=payload,
        created_at=_iso(row.created_at),
    )


# ──────────────────────────────────────────────────────────────
# Tenant repository
# ──────────────────────────────────────────────────────────────

def get_tenant(db: Session, tenant_id: str) -> TenantRecord | None:
    row = db.execute(
        text(
            "SELECT tenant_id, name, intake_url, created_at "
            "FROM tenants WHERE tenant_id = :tid"
        ),
        {"tid": tenant_id},
    ).fetchone()
    return _row_to_tenant(row) if row else None


def upsert_tenant(db: Session, tenant_id: str, name: str) -> TenantRecord:
    """Insert or return existing tenant (idempotent / upsert)."""
    existing = get_tenant(db, tenant_id)
    if existing:
        return existing
    intake_url = f"/intake/{tenant_id}"
    db.execute(
        text(
            "INSERT INTO tenants (tenant_id, name, intake_url) "
            "VALUES (:tid, :name, :url) "
            "ON CONFLICT (tenant_id) DO NOTHING"
        ),
        {"tid": tenant_id, "name": name, "url": intake_url},
    )
    db.commit()
    return TenantRecord(tenant_id=tenant_id, name=name, intake_url=intake_url)


# ──────────────────────────────────────────────────────────────
# Incident repository
# ──────────────────────────────────────────────────────────────

def save_incident(db: Session, record: IncidentRecord) -> IncidentRecord:
    db.execute(
        text(
            """
            INSERT INTO incidents
                (incident_id, tenant_id, reporter_email, description,
                 status, file_meta, triage, ticket, notifications)
            VALUES
                (:iid, :tid, :email, :desc,
                 :status,
                 cast(:file_meta as jsonb),
                 cast(:triage   as jsonb),
                 cast(:ticket   as jsonb),
                 cast(:notifs   as jsonb))
            ON CONFLICT (incident_id) DO NOTHING
            """
        ),
        {
            "iid":       record.incident_id,
            "tid":       record.tenant_id,
            "email":     str(record.reporter_email),
            "desc":      record.description,
            "status":    record.status,
            "file_meta": json.dumps(record.file_meta.model_dump() if record.file_meta else None),
            "triage":    json.dumps(record.triage.model_dump()),
            "ticket":    json.dumps(record.ticket.model_dump()),
            "notifs":    json.dumps([n.model_dump() for n in record.notifications]),
        },
    )
    db.commit()
    return record


def get_incident(db: Session, incident_id: str) -> IncidentRecord | None:
    row = db.execute(
        text("SELECT * FROM incidents WHERE incident_id = :iid"),
        {"iid": incident_id},
    ).fetchone()
    return _row_to_incident(row) if row else None


def list_incidents(db: Session, tenant_id: str | None = None) -> list[IncidentRecord]:
    if tenant_id:
        rows = db.execute(
            text(
                "SELECT * FROM incidents "
                "WHERE tenant_id = :tid "
                "ORDER BY created_at DESC"
            ),
            {"tid": tenant_id},
        ).fetchall()
    else:
        rows = db.execute(
            text("SELECT * FROM incidents ORDER BY created_at DESC")
        ).fetchall()
    return [_row_to_incident(r) for r in rows]


def find_open_duplicate_incident(db: Session, tenant_id: str, description: str) -> IncidentRecord | None:
    """
    Find latest open incident in the same tenant with equivalent normalized
    description text. This is a pragmatic dedup baseline for hackathon scope.
    """
    normalized = " ".join(description.lower().split())
    row = db.execute(
        text(
            """
            SELECT *
            FROM incidents
            WHERE tenant_id = :tid
              AND status = 'open'
              AND regexp_replace(lower(description), '\\s+', ' ', 'g') = :desc_norm
            ORDER BY created_at DESC
            LIMIT 1
            """
        ),
        {"tid": tenant_id, "desc_norm": normalized},
    ).fetchone()
    return _row_to_incident(row) if row else None


def resolve_incident(
    db: Session,
    incident_id: str,
    extra_notification: NotificationRecord,
) -> IncidentRecord | None:
    """
    Mark incident as resolved, persist resolved_at, and append the
    reporter notification to the JSONB array — all in one UPDATE.
    Returns the refreshed record, or None if incident_id was not found.
    """
    row = db.execute(
        text("SELECT incident_id FROM incidents WHERE incident_id = :iid"),
        {"iid": incident_id},
    ).fetchone()
    if not row:
        return None

    now = _utc_now()
    db.execute(
        text(
            """
            UPDATE incidents
            SET  status       = 'resolved',
                 resolved_at  = :now,
                 notifications = notifications || cast(:notif as jsonb)
            WHERE incident_id = :iid
            """
        ),
        {
            "iid":   incident_id,
            "now":   now,
            "notif": json.dumps([extra_notification.model_dump()]),
        },
    )
    db.commit()
    return get_incident(db, incident_id)


def tenant_dashboard(db: Session, tenant_id: str) -> TenantDashboard:
    row = db.execute(
        text(
            """
            SELECT
                COUNT(*)                                                  AS total,
                COUNT(*) FILTER (WHERE status = 'open')                  AS open_count,
                COUNT(*) FILTER (WHERE status = 'resolved')              AS resolved_count,
                COUNT(*) FILTER (WHERE triage->>'severity' = 'critical') AS critical_count
            FROM incidents
            WHERE tenant_id = :tid
            """
        ),
        {"tid": tenant_id},
    ).fetchone()
    return TenantDashboard(
        tenant_id=tenant_id,
        total_incidents=row.total,
        open_incidents=row.open_count,
        resolved_incidents=row.resolved_count,
        critical_incidents=row.critical_count,
    )


def tenant_insights_summary(db: Session, tenant_id: str) -> TenantInsightsSummary:
    row = db.execute(
        text(
            """
            SELECT
                COUNT(*) AS total,
                COUNT(*) FILTER (WHERE status = 'open') AS open_count,
                COUNT(*) FILTER (WHERE status = 'resolved') AS resolved_count,
                COUNT(*) FILTER (WHERE COALESCE((triage->>'is_duplicate')::boolean, false) = true) AS duplicate_count,
                COUNT(*) FILTER (WHERE triage->>'severity' = 'low') AS low_count,
                COUNT(*) FILTER (WHERE triage->>'severity' = 'medium') AS medium_count,
                COUNT(*) FILTER (WHERE triage->>'severity' = 'high') AS high_count,
                COUNT(*) FILTER (WHERE triage->>'severity' = 'critical') AS critical_count
            FROM incidents
            WHERE tenant_id = :tid
            """
        ),
        {"tid": tenant_id},
    ).fetchone()

    return TenantInsightsSummary(
        tenant_id=tenant_id,
        total_incidents=row.total,
        open_incidents=row.open_count,
        resolved_incidents=row.resolved_count,
        duplicate_incidents=row.duplicate_count,
        low_incidents=row.low_count,
        medium_incidents=row.medium_count,
        high_incidents=row.high_count,
        critical_incidents=row.critical_count,
    )


def list_audit_logs(
    db: Session,
    tenant_id: str,
    limit: int = 100,
    incident_id: str | None = None,
) -> list[AuditLogRecord]:
    safe_limit = max(1, min(limit, 500))
    if incident_id:
        rows = db.execute(
            text(
                """
                SELECT id, tenant_id, incident_id, stage, payload, created_at
                FROM audit_logs
                WHERE tenant_id = :tid AND incident_id = :iid
                ORDER BY created_at DESC
                LIMIT :lim
                """
            ),
            {"tid": tenant_id, "iid": incident_id, "lim": safe_limit},
        ).fetchall()
    else:
        rows = db.execute(
            text(
                """
                SELECT id, tenant_id, incident_id, stage, payload, created_at
                FROM audit_logs
                WHERE tenant_id = :tid
                ORDER BY created_at DESC
                LIMIT :lim
                """
            ),
            {"tid": tenant_id, "lim": safe_limit},
        ).fetchall()
    return [_row_to_audit(r) for r in rows]


# ──────────────────────────────────────────────────────────────
# Audit log repository
# ──────────────────────────────────────────────────────────────

def write_audit_log(
    db: Session,
    stage: str,
    tenant_id: str | None = None,
    incident_id: str | None = None,
    payload: dict | None = None,
) -> None:
    """Fire-and-forget audit write.  Errors are swallowed so that an
    audit failure never aborts the main request flow."""
    try:
        db.execute(
            text(
                """
                INSERT INTO audit_logs (tenant_id, incident_id, stage, payload)
                VALUES (:tid, :iid, :stage, cast(:payload as jsonb))
                """
            ),
            {
                "tid":     tenant_id,
                "iid":     incident_id,
                "stage":   stage,
                "payload": json.dumps(payload or {}),
            },
        )
        db.commit()
    except Exception:
        db.rollback()
