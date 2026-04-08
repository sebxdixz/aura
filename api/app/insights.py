from __future__ import annotations

from sqlalchemy.orm import Session

from . import repository as repo
from .models import AuditLogRecord, TenantInsightsSummary


def get_tenant_audit_logs(
    db: Session,
    tenant_id: str,
    limit: int = 100,
    incident_id: str | None = None,
) -> list[AuditLogRecord]:
    return repo.list_audit_logs(db, tenant_id=tenant_id, limit=limit, incident_id=incident_id)


def get_tenant_insights_summary(db: Session, tenant_id: str) -> TenantInsightsSummary:
    return repo.tenant_insights_summary(db, tenant_id=tenant_id)
