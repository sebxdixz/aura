from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy.orm import Session

from .attachments import process_attachment
from .jobs import JOB_TYPE_NOTIFY_REPORTER, enqueue_job
from .models import IncidentLinkRecord, IncidentRecord, NotificationRecord, TicketRecord
from .multi_ticket import analyze_multi_ticket_intelligence, to_link_records
from .observability import log_event
from .telemetry import start_span
from .ticket_watchers import fetch_external_ticket_status, map_external_status_to_internal
from . import repository as repo
from .integrations.slack import notify_slack_resolved
from .services import (
    create_ticket,
    find_duplicate_incident,
    get_incident,
    notify_reporter,
    notify_team,
    run_triage,
    save_incident,
)


def handle_process_incident(db: Session, incident_id: str) -> IncidentRecord:
    with start_span("worker.process_incident", **{"incident.id": incident_id}):
        incident = get_incident(db, incident_id)
        if not incident:
            raise RuntimeError(f"incident {incident_id} not found")

        repo.update_incident_processing_state(db, incident_id, "processing")
        incident = get_incident(db, incident_id)
        if not incident:
            raise RuntimeError(f"incident {incident_id} disappeared during processing")

        attachment_record = incident.attachment
        file_bytes: bytes | None = None
        if attachment_record and attachment_record.attachment_storage_path:
            storage_path = Path(attachment_record.attachment_storage_path)
            if storage_path.exists():
                file_bytes = storage_path.read_bytes()
                with start_span(
                    "attachments.process",
                    **{
                        "incident.id": incident_id,
                        "attachment.used": True,
                    },
                ):
                    attachment_record = process_attachment(
                        incident_id=incident_id,
                        tenant_id=incident.tenant_id,
                        filename=attachment_record.attachment_filename,
                        content_type=attachment_record.attachment_mime_type,
                        content_bytes=file_bytes,
                        storage_path=attachment_record.attachment_storage_path,
                    )

        duplicate = find_duplicate_incident(db, tenant_id=incident.tenant_id, description=incident.description)
        if duplicate and duplicate.incident_id != incident_id:
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
            dedup_incident = IncidentRecord(
                incident_id=incident.incident_id,
                tenant_id=incident.tenant_id,
                reporter_email=incident.reporter_email,
                description=incident.description,
                status="open",
                processing_state="triaged",
                created_at=incident.created_at,
                resolved_at=incident.resolved_at,
                file_meta=incident.file_meta,
                attachment=attachment_record,
                triage=triage,
                ticket=duplicate.ticket,
                notifications=[dedup_note],
                related_links=[],
            )
            save_incident(db, dedup_incident)
            log_event("incident_deduplicated", incident_id=incident_id, tenant_id=incident.tenant_id, duplicate_of=duplicate.incident_id)
            return dedup_incident

        triage = run_triage(
            incident_id=incident_id,
            tenant_id=incident.tenant_id,
            reporter_email=str(incident.reporter_email),
            description=incident.description,
            has_file=attachment_record is not None,
            attachment=attachment_record,
            attachment_filename=incident.file_meta.filename if incident.file_meta else None,
            attachment_content_type=incident.file_meta.content_type if incident.file_meta else None,
            attachment_bytes=file_bytes,
            db=db,
        )
        repo.update_incident_processing_state(db, incident_id, "triaged")

        temp_incident = IncidentRecord(
            incident_id=incident.incident_id,
            tenant_id=incident.tenant_id,
            reporter_email=incident.reporter_email,
            description=incident.description,
            status=incident.status,
            processing_state="triaged",
            created_at=incident.created_at,
            resolved_at=incident.resolved_at,
            file_meta=incident.file_meta,
            attachment=attachment_record,
            triage=triage,
            ticket=TicketRecord(ticket_id="pending", provider="pending", url="", status="created"),
            notifications=[],
            related_links=[],
        )
        with start_span("multi_ticket.analyze", **{"incident.id": incident_id, "tenant.id": incident.tenant_id}):
            log_event("multi_ticket_started", incident_id=incident_id, tenant_id=incident.tenant_id)
            multi_ticket = analyze_multi_ticket_intelligence(db, temp_incident)

        if multi_ticket.is_duplicate and multi_ticket.duplicate_of_incident_id:
            log_event("duplicate_detected", incident_id=incident_id, tenant_id=incident.tenant_id, duplicate_of=multi_ticket.duplicate_of_incident_id)
        if multi_ticket.related_incident_ids:
            log_event("related_incidents_linked", incident_id=incident_id, tenant_id=incident.tenant_id, related_count=len(multi_ticket.related_incident_ids))
        if multi_ticket.recurrence.pattern_detected:
            log_event(
                "recurrence_detected",
                incident_id=incident_id,
                tenant_id=incident.tenant_id,
                recurrence_count_7d=multi_ticket.recurrence.recurrence_count_7d,
                recurrence_count_30d=multi_ticket.recurrence.recurrence_count_30d,
            )
        if multi_ticket.cluster_id:
            log_event("cluster_assigned", incident_id=incident_id, tenant_id=incident.tenant_id, cluster_id=multi_ticket.cluster_id)
        log_event(
            "multi_ticket_completed",
            incident_id=incident_id,
            tenant_id=incident.tenant_id,
            is_duplicate=multi_ticket.is_duplicate,
            related_count=len(multi_ticket.related_incident_ids),
            recurrence_count_7d=multi_ticket.recurrence.recurrence_count_7d,
            recurrence_count_30d=multi_ticket.recurrence.recurrence_count_30d,
            cluster_id=multi_ticket.cluster_id,
        )

        triage.is_duplicate = triage.is_duplicate or multi_ticket.is_duplicate
        triage.duplicate_of_incident_id = triage.duplicate_of_incident_id or multi_ticket.duplicate_of_incident_id
        triage.dedup_confidence = triage.dedup_confidence or multi_ticket.dedup_confidence
        triage.related_incident_ids = multi_ticket.related_incident_ids
        triage.cluster_id = multi_ticket.cluster_id
        triage.recurrence_count_7d = multi_ticket.recurrence.recurrence_count_7d
        triage.recurrence_count_30d = multi_ticket.recurrence.recurrence_count_30d
        triage.scope_assessment = multi_ticket.scope_assessment or triage.scope_assessment
        triage.multi_ticket_influence_reasoning = multi_ticket.multi_ticket_influence_reasoning

        with start_span("ticket.create", **{"incident.id": incident_id, "tenant.id": incident.tenant_id}):
            ticket = create_ticket(
                incident_id=incident_id,
                triage=triage,
                tenant_id=incident.tenant_id,
                description=incident.description,
            )

        with start_span("notify.team", **{"incident.id": incident_id, "tenant.id": incident.tenant_id}):
            team_notification = notify_team(
                incident_id=incident_id,
                ticket=ticket,
                triage=triage,
                tenant_id=incident.tenant_id,
                reporter_email=str(incident.reporter_email),
                description=incident.description,
            )

        final_incident = IncidentRecord(
            incident_id=incident.incident_id,
            tenant_id=incident.tenant_id,
            reporter_email=incident.reporter_email,
            description=incident.description,
            status="open",
            processing_state="ticketed",
            created_at=incident.created_at,
            resolved_at=incident.resolved_at,
            file_meta=incident.file_meta,
            attachment=attachment_record,
            triage=triage,
            ticket=ticket,
            notifications=[team_notification],
            related_links=[
                IncidentLinkRecord(
                    source_incident_id=incident_id,
                    target_incident_id=link.target_incident_id,
                    relationship_type=link.relationship_type,
                    similarity_score=link.similarity_score,
                    reasoning=link.reasoning,
                    shared_signals=link.shared_signals,
                )
                for link in to_link_records(multi_ticket)
            ],
        )
        save_incident(db, final_incident)
        if final_incident.related_links:
            repo.save_incident_links(db, tenant_id=incident.tenant_id, source_incident_id=incident_id, links=final_incident.related_links)
        return final_incident


def handle_sync_ticket_status(db: Session, incident_id: str, provider: str, external_ticket_id: str) -> IncidentRecord | None:
    with start_span(
        "worker.sync_ticket_status",
        **{"incident.id": incident_id, "ticket.id": external_ticket_id, "ticket.provider": provider},
    ):
        incident = get_incident(db, incident_id)
        if not incident:
            return None

        log_event("ticket_status_sync_started", incident_id=incident_id, tenant_id=incident.tenant_id, ticket_id=external_ticket_id, ticket_provider=provider)
        external_status = fetch_external_ticket_status(provider, external_ticket_id, incident=incident)
        log_event(
            "ticket_status_fetched",
            incident_id=incident_id,
            tenant_id=incident.tenant_id,
            ticket_id=external_ticket_id,
            ticket_provider=provider,
            external_status=external_status,
        )
        if external_status != (incident.ticket.external_status or incident.ticket.status):
            log_event(
                "ticket_status_changed",
                incident_id=incident_id,
                tenant_id=incident.tenant_id,
                ticket_id=external_ticket_id,
                ticket_provider=provider,
                old_status=incident.ticket.external_status or incident.ticket.status,
                new_status=external_status,
            )
        updated = repo.update_ticket_sync_state(
            db,
            incident_id,
            external_status,
            synced_at=datetime.now(timezone.utc).isoformat(),
        )
        if map_external_status_to_internal(provider, external_status) == "resolved" and incident.status != "resolved":
            repo.mark_incident_resolved(db, incident_id)
            repo.write_audit_log(
                db,
                stage="incident_resolved_external",
                tenant_id=incident.tenant_id,
                incident_id=incident_id,
                payload={"provider": provider, "external_status": external_status},
            )
            log_event("external_resolution_detected", incident_id=incident_id, tenant_id=incident.tenant_id, ticket_id=external_ticket_id, ticket_provider=provider)
            enqueue_job(db, JOB_TYPE_NOTIFY_REPORTER, {"incident_id": incident_id}, incident_id=incident_id)
            log_event("reporter_resolution_notification_enqueued", incident_id=incident_id, tenant_id=incident.tenant_id, ticket_id=external_ticket_id)
        return updated


def handle_notify_reporter(db: Session, incident_id: str) -> IncidentRecord | None:
    with start_span("worker.notify_reporter", **{"incident.id": incident_id}):
        incident = get_incident(db, incident_id)
        if not incident:
            return None
        if any(item.channel == "reporter_email" for item in incident.notifications):
            return incident

        event = notify_reporter(incident_id, str(incident.reporter_email))
        updated = repo.append_incident_notification(db, incident_id, event)
        communicator = os.getenv("COMMUNICATOR_PROVIDER", "mock-slack")
        if communicator == "slack" and updated:
            try:
                notify_slack_resolved(
                    incident_id=incident_id,
                    tenant_id=updated.tenant_id,
                    ticket=updated.ticket,
                    reporter_email=str(updated.reporter_email),
                )
            except RuntimeError as exc:
                log_event("slack_resolved_skipped", incident_id=incident_id, error=str(exc))
        log_event("reporter_resolution_notification_sent", incident_id=incident_id, reporter_email=str(incident.reporter_email))
        return updated
