from __future__ import annotations

from types import SimpleNamespace

import pytest

from api.app import job_handlers, services
from api.app.integrations.email import ReporterEmailDeliveryError
from api.app.models import IncidentRecord, NotificationRecord, TicketRecord, TriageOutput


def _incident(*, notifications: list[NotificationRecord] | None = None, status: str = "resolved") -> IncidentRecord:
    triage = TriageOutput(
        severity="low",
        affected_service="web-app",
        technical_summary="Checkout issue resolved.",
        root_cause_analysis="A temporary client/server mismatch caused localized failures.",
        proposed_fix="Patched request validation and redeployed the frontend.",
        proposed_cli_command="pytest -k incident_hotfix",
        llm_mode="mock",
    )
    ticket = TicketRecord(
        ticket_id="AURA-123",
        provider="mock-jira",
        url="https://mock-jira.local/browse/AURA-123",
        status="created",
        external_status="Resolved",
    )
    return IncidentRecord(
        incident_id="inc-123",
        tenant_id="demo",
        reporter_email="reporter@example.com",
        description="Checkout returns 500 for some users.",
        status=status,  # type: ignore[arg-type]
        processing_state="resolved",
        triage=triage,
        ticket=ticket,
        notifications=notifications or [],
    )


def test_notify_reporter_mock_provider_still_works(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EMAIL_PROVIDER", "mock-email")
    monkeypatch.setenv("EMAIL_FALLBACK_PROVIDER", "mock-email")

    event = services.notify_reporter(
        "inc-123",
        "reporter@example.com",
        incident=_incident(),
    )

    assert event.status == "sent"
    assert event.provider == "mock-email"
    assert event.external_message_id


def test_notify_reporter_real_provider_path_selectable(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    def fake_http_post(url: str, payload: dict[str, object], headers: dict[str, str], timeout: float) -> dict[str, str]:
        captured["url"] = url
        captured["payload"] = payload
        captured["headers"] = headers
        captured["timeout"] = timeout
        return {"id": "re_12345"}

    monkeypatch.setenv("EMAIL_PROVIDER", "resend")
    monkeypatch.setenv("EMAIL_FALLBACK_PROVIDER", "mock-email")
    monkeypatch.setenv("EMAIL_RESEND_API_KEY", "re_test_123")
    monkeypatch.setenv("EMAIL_FROM", "alerts@example.com")
    monkeypatch.setenv("EMAIL_FROM_NAME", "AURA")
    monkeypatch.setattr("api.app.integrations.email._http_post", fake_http_post)

    event = services.notify_reporter(
        "inc-123",
        "reporter@example.com",
        incident=_incident(),
    )

    assert event.status == "sent"
    assert event.provider == "resend"
    assert event.external_message_id == "re_12345"
    assert captured["url"] == "https://api.resend.com/emails"
    assert captured["payload"]["to"] == ["reporter@example.com"]  # type: ignore[index]


def test_resolve_incident_enqueues_notify_reporter_job(monkeypatch: pytest.MonkeyPatch) -> None:
    incident = _incident(status="open")
    resolved_incident = _incident(status="resolved")
    captured: dict[str, object] = {}

    monkeypatch.setenv("COMMUNICATOR_PROVIDER", "mock-slack")
    monkeypatch.setattr("api.app.services.repo.get_incident", lambda db, incident_id: incident)
    monkeypatch.setattr("api.app.services.repo.mark_incident_resolved", lambda db, incident_id: resolved_incident)
    monkeypatch.setattr("api.app.services.repo.write_audit_log", lambda *args, **kwargs: None)
    monkeypatch.setattr("api.app.services.has_pending_job", lambda db, job_type, incident_id: False)

    def fake_enqueue_job(db, job_type, payload, **kwargs):  # type: ignore[no-untyped-def]
        captured["job_type"] = job_type
        captured["payload"] = payload
        return 1

    monkeypatch.setattr("api.app.services.enqueue_job", fake_enqueue_job)

    updated = services.resolve_incident(SimpleNamespace(), incident.incident_id)

    assert updated is resolved_incident
    assert captured["job_type"] == "notify_reporter"
    assert captured["payload"] == {"incident_id": incident.incident_id}


def test_handle_notify_reporter_skips_duplicate_success(monkeypatch: pytest.MonkeyPatch) -> None:
    incident = _incident(
        notifications=[
            NotificationRecord(
                channel="reporter_email",
                status="sent",
                provider="mock-email",
                detail="Reporter already notified.",
            )
        ]
    )
    captured: dict[str, NotificationRecord] = {}

    monkeypatch.setattr("api.app.job_handlers.get_incident", lambda db, incident_id: incident)
    def fake_append(db, incident_id, notification):  # type: ignore[no-untyped-def]
        captured["notification"] = notification
        return incident

    monkeypatch.setattr("api.app.job_handlers.repo.append_incident_notification", fake_append)
    monkeypatch.setattr("api.app.job_handlers.notify_reporter", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("should not send")))

    job_handlers.handle_notify_reporter(SimpleNamespace(), incident.incident_id)

    assert captured["notification"].status == "skipped"
    assert captured["notification"].channel == "reporter_email"


def test_handle_notify_reporter_records_failed_send(monkeypatch: pytest.MonkeyPatch) -> None:
    incident = _incident()
    captured: dict[str, NotificationRecord] = {}

    monkeypatch.setattr("api.app.job_handlers.get_incident", lambda db, incident_id: incident)

    def fake_append(db, incident_id, notification):  # type: ignore[no-untyped-def]
        captured["notification"] = notification
        return incident

    monkeypatch.setattr("api.app.job_handlers.repo.append_incident_notification", fake_append)
    monkeypatch.setattr(
        "api.app.job_handlers.notify_reporter",
        lambda *args, **kwargs: (_ for _ in ()).throw(ReporterEmailDeliveryError("resend", "provider down")),
    )

    with pytest.raises(ReporterEmailDeliveryError):
        job_handlers.handle_notify_reporter(SimpleNamespace(), incident.incident_id)

    assert captured["notification"].status == "failed"
    assert captured["notification"].provider == "resend"
    assert "provider down" in captured["notification"].detail


def test_handle_notify_reporter_persists_successful_send(monkeypatch: pytest.MonkeyPatch) -> None:
    incident = _incident()
    sent_event = NotificationRecord(
        channel="reporter_email",
        status="sent",
        provider="resend",
        external_message_id="re_abc123",
        detail="Reporter reporter@example.com notified by resend.",
    )
    updated = _incident(notifications=[sent_event])
    captured: dict[str, NotificationRecord] = {}

    monkeypatch.setattr("api.app.job_handlers.get_incident", lambda db, incident_id: incident)
    monkeypatch.setattr("api.app.job_handlers.notify_reporter", lambda *args, **kwargs: sent_event)

    def fake_append(db, incident_id, notification):  # type: ignore[no-untyped-def]
        captured["notification"] = notification
        return updated

    monkeypatch.setattr("api.app.job_handlers.repo.append_incident_notification", fake_append)

    result = job_handlers.handle_notify_reporter(SimpleNamespace(), incident.incident_id)

    assert result is updated
    assert captured["notification"].status == "sent"
    assert captured["notification"].provider == "resend"
    assert captured["notification"].external_message_id == "re_abc123"
