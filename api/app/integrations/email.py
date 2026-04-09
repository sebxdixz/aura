from __future__ import annotations

import json
import os
import uuid
from dataclasses import dataclass
from html import escape
from typing import Any
from urllib import error as urllib_error
from urllib import request as urllib_request

from ..models import IncidentRecord, NotificationRecord
from ..telemetry import start_span


@dataclass(slots=True)
class ReporterEmailPayload:
    subject: str
    text_body: str
    html_body: str


class ReporterEmailDeliveryError(RuntimeError):
    def __init__(self, provider: str, message: str) -> None:
        super().__init__(message)
        self.provider = provider
        self.message = message


@dataclass(slots=True)
class ReporterEmailDeliveryResult:
    provider: str
    detail: str
    external_message_id: str | None = None


class ReporterEmailProvider:
    provider_name = "mock-email"

    def send(
        self,
        *,
        incident: IncidentRecord,
        reporter_email: str,
        payload: ReporterEmailPayload,
        fail_flag: str | None = None,
    ) -> ReporterEmailDeliveryResult:
        raise NotImplementedError


class MockReporterEmailProvider(ReporterEmailProvider):
    def __init__(self, provider_name: str = "mock-email") -> None:
        self.provider_name = provider_name

    def send(
        self,
        *,
        incident: IncidentRecord,
        reporter_email: str,
        payload: ReporterEmailPayload,
        fail_flag: str | None = None,
    ) -> ReporterEmailDeliveryResult:
        _maybe_fail(fail_flag, self.provider_name)
        message_id = f"{self.provider_name}-{incident.incident_id}-{uuid.uuid4().hex[:8]}"
        return ReporterEmailDeliveryResult(
            provider=self.provider_name,
            detail=f"Reporter {reporter_email} notified by {self.provider_name}.",
            external_message_id=message_id,
        )


class ResendReporterEmailProvider(ReporterEmailProvider):
    provider_name = "resend"

    def send(
        self,
        *,
        incident: IncidentRecord,
        reporter_email: str,
        payload: ReporterEmailPayload,
        fail_flag: str | None = None,
    ) -> ReporterEmailDeliveryResult:
        _maybe_fail(fail_flag, self.provider_name)
        api_key = os.getenv("EMAIL_RESEND_API_KEY", "").strip()
        sender = _format_sender()
        if not api_key:
            raise ReporterEmailDeliveryError(self.provider_name, "Resend API key is not configured.")
        if not sender:
            raise ReporterEmailDeliveryError(self.provider_name, "EMAIL_FROM is not configured.")

        body = {
            "from": sender,
            "to": [reporter_email],
            "subject": payload.subject,
            "text": payload.text_body,
            "html": payload.html_body,
        }
        reply_to = os.getenv("EMAIL_REPLY_TO", "").strip()
        if reply_to:
            body["reply_to"] = reply_to

        with start_span(
            "reporter_email.resend.send",
            **{
                "incident.id": incident.incident_id,
                "email.provider": self.provider_name,
                "email.to": reporter_email,
            },
        ):
            response = _http_post(
                os.getenv("EMAIL_RESEND_BASE_URL", "https://api.resend.com/emails").strip(),
                payload=body,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                },
                timeout=_email_timeout_seconds(),
            )

        message_id = str(response.get("id", "")).strip() or None
        return ReporterEmailDeliveryResult(
            provider=self.provider_name,
            detail=f"Reporter {reporter_email} notified by resend.",
            external_message_id=message_id,
        )


def build_reporter_resolution_email(
    incident: IncidentRecord,
    *,
    reporter_facing_message: str | None = None,
) -> ReporterEmailPayload:
    ticket_ref = incident.ticket.ticket_id if incident.ticket.ticket_id and incident.ticket.ticket_id != "pending" else "Pending"
    summary = reporter_facing_message or (
        incident.triage.proposed_fix.strip()
        or incident.triage.root_cause_analysis.strip()
        or "The reported issue has been resolved and normal service should be restored."
    )
    subject = f"[AURA] Incident {incident.incident_id} resolved"
    text_lines = [
        "Your reported incident has been resolved.",
        "",
        f"Incident reference: {incident.incident_id}",
        f"Ticket reference: {ticket_ref}",
        "Resolution status: Resolved",
        "",
        "Resolution summary:",
        summary,
    ]
    if incident.resolved_at:
        text_lines.extend(["", f"Resolved at: {incident.resolved_at}"])
    if incident.ticket.url:
        text_lines.extend(["", f"Tracking link: {incident.ticket.url}"])
    text_lines.extend(["", "Thank you,", "AURA Incident Response"])
    text_body = "\n".join(text_lines)
    tracking_html = ""
    if incident.ticket.url:
        tracking_html = f'<p><strong>Tracking link:</strong> <a href="{escape(incident.ticket.url)}">Open ticket</a></p>'

    html_body = f"""
    <div style="font-family:Arial,sans-serif;color:#1f2937;line-height:1.5;">
      <h2 style="margin-bottom:12px;">Your reported incident has been resolved</h2>
      <p><strong>Incident reference:</strong> {escape(incident.incident_id)}</p>
      <p><strong>Ticket reference:</strong> {escape(ticket_ref)}</p>
      <p><strong>Resolution status:</strong> Resolved</p>
      <div style="margin-top:16px;padding:12px 14px;border:1px solid #d1d5db;border-radius:10px;background:#f9fafb;">
        <strong>Resolution summary</strong>
        <p style="margin:8px 0 0 0;">{escape(summary)}</p>
      </div>
      {tracking_html}
      <p style="margin-top:18px;">Thank you,<br/>AURA Incident Response</p>
    </div>
    """.strip()
    return ReporterEmailPayload(subject=subject, text_body=text_body, html_body=html_body)


def send_reporter_resolution_email(
    *,
    incident: IncidentRecord,
    reporter_email: str,
    provider_name: str,
    reporter_facing_message: str | None = None,
    fail_flag: str | None = None,
) -> NotificationRecord:
    payload = build_reporter_resolution_email(incident, reporter_facing_message=reporter_facing_message)
    provider = get_reporter_email_provider(provider_name)
    result = provider.send(incident=incident, reporter_email=reporter_email, payload=payload, fail_flag=fail_flag)
    return NotificationRecord(
        channel="reporter_email",
        status="sent",
        provider=result.provider,
        detail=result.detail,
        external_message_id=result.external_message_id,
    )


def get_reporter_email_provider(provider_name: str) -> ReporterEmailProvider:
    normalized = normalize_email_provider(provider_name)
    if normalized == "resend":
        return ResendReporterEmailProvider()
    if normalized in {"mock-email", "mock-ses"}:
        return MockReporterEmailProvider(provider_name=normalized)
    raise ReporterEmailDeliveryError(normalized, f"Unsupported reporter email provider: {provider_name}")


def normalize_email_provider(provider_name: str | None) -> str:
    normalized = (provider_name or "mock-email").strip().lower()
    return normalized or "mock-email"


def _format_sender() -> str:
    email_from = os.getenv("EMAIL_FROM", "").strip()
    from_name = os.getenv("EMAIL_FROM_NAME", "").strip()
    if not email_from:
        return ""
    if not from_name:
        return email_from
    return f"{from_name} <{email_from}>"


def _email_timeout_seconds() -> float:
    raw = os.getenv("EMAIL_TIMEOUT_SECONDS", "10").strip()
    try:
        return max(1.0, float(raw))
    except ValueError:
        return 10.0


def _maybe_fail(flag_name: str | None, provider_name: str) -> None:
    if not flag_name:
        return
    if os.getenv(flag_name, "false").strip().lower() in {"1", "true", "yes", "on"}:
        raise ReporterEmailDeliveryError(provider_name, f"{provider_name} temporary outage")


def _http_post(url: str, payload: dict[str, Any], headers: dict[str, str], timeout: float) -> dict[str, Any]:
    request = urllib_request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    try:
        with urllib_request.urlopen(request, timeout=timeout) as response:
            raw = response.read().decode("utf-8")
            return json.loads(raw) if raw else {}
    except urllib_error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise ReporterEmailDeliveryError("resend", f"Resend HTTP {exc.code}: {body}") from exc
    except OSError as exc:
        raise ReporterEmailDeliveryError("resend", f"Resend connection error: {exc}") from exc
