from __future__ import annotations

import os
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from .integrations.jira import fetch_jira_ticket_status
from .models import IncidentRecord
from .observability import log_event
from . import repository as repo

RESOLVED_EXTERNAL_STATUSES = {"done", "resolved", "closed"}


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def fetch_external_ticket_status(
    provider: str,
    external_ticket_id: str,
    *,
    incident: IncidentRecord | None = None,
) -> str:
    normalized = provider.lower()
    if normalized == "jira":
        return fetch_jira_ticket_status(external_ticket_id)
    if normalized in {"mock-jira", "mock-linear"}:
        current = (incident.ticket.external_status or incident.ticket.status or "Created") if incident else "Created"
        auto_resolve = os.getenv("MOCK_TICKET_AUTO_RESOLVE", "false").strip().lower() in {"1", "true", "yes", "on"}
        after_seconds = int(os.getenv("MOCK_TICKET_AUTO_RESOLVE_AFTER_SECONDS", "0") or "0")
        if auto_resolve and incident:
            created_at = datetime.fromisoformat(incident.created_at.replace("Z", "+00:00"))
            age_seconds = (datetime.now(timezone.utc) - created_at).total_seconds()
            if age_seconds >= max(after_seconds, 1):
                return "Resolved"
        return current
    return "Created"


def map_external_status_to_internal(provider: str, external_status: str) -> str:
    normalized = (external_status or "").strip().lower()
    if normalized in RESOLVED_EXTERNAL_STATUSES:
        return "resolved"
    if normalized in {"in progress", "started", "doing"}:
        return "processing"
    return "open"


def resolve_local_incident_from_external_state(
    db: Session,
    incident: IncidentRecord,
    provider: str,
    external_status: str,
) -> IncidentRecord | None:
    synced_at = _utc_now_iso()
    updated = repo.update_ticket_sync_state(db, incident.incident_id, external_status, synced_at)
    if updated and updated.status != "resolved" and map_external_status_to_internal(provider, external_status) == "resolved":
        log_event(
            "external_resolution_detected",
            incident_id=incident.incident_id,
            tenant_id=incident.tenant_id,
            ticket_id=incident.ticket.ticket_id,
            ticket_provider=provider,
            external_status=external_status,
        )
    return updated


def poll_open_tickets(db: Session) -> list[IncidentRecord]:
    incidents = repo.list_open_incidents_with_external_ticket(db)
    results: list[IncidentRecord] = []
    for incident in incidents:
        provider = incident.ticket.provider
        external_ticket_id = incident.ticket.ticket_id
        log_event(
            "ticket_status_sync_started",
            incident_id=incident.incident_id,
            tenant_id=incident.tenant_id,
            ticket_id=external_ticket_id,
            ticket_provider=provider,
        )
        external_status = fetch_external_ticket_status(
            provider,
            external_ticket_id,
            incident=incident,
        )
        log_event(
            "ticket_status_fetched",
            incident_id=incident.incident_id,
            tenant_id=incident.tenant_id,
            ticket_id=external_ticket_id,
            ticket_provider=provider,
            external_status=external_status,
        )
        current_external_status = incident.ticket.external_status or incident.ticket.status
        if external_status != current_external_status:
            log_event(
                "ticket_status_changed",
                incident_id=incident.incident_id,
                tenant_id=incident.tenant_id,
                ticket_id=external_ticket_id,
                ticket_provider=provider,
                old_status=current_external_status,
                new_status=external_status,
            )
        updated = resolve_local_incident_from_external_state(db, incident, provider, external_status)
        if updated:
            results.append(updated)
    return results
