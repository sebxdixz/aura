"""
integrations/slack.py - Real Slack Incoming Webhook integration for AURA.
"""
from __future__ import annotations

import json
import os
from urllib import error as urllib_error
from urllib import request as urllib_request

from ..models import TicketRecord, TriageOutput
from ..observability import log_event
from ..telemetry import start_span

_SEV_COLORS: dict[str, str] = {
    "critical": "#ef4444",
    "high": "#f97316",
    "medium": "#eab308",
    "low": "#22c55e",
}

_SEV_EMOJI: dict[str, str] = {
    "critical": "red_circle",
    "high": "large_orange_circle",
    "medium": "large_yellow_circle",
    "low": "large_green_circle",
}


def _slack_available(credentials: dict[str, str] | None = None) -> bool:
    if os.getenv("MOCK_MODE", "true").lower() in {"1", "true", "yes", "on"}:
        return False
    webhook_url = str((credentials or {}).get("webhook_url") or os.getenv("SLACK_WEBHOOK_URL", "")).strip()
    return bool(webhook_url)


def _http_post_json(url: str, payload: dict) -> None:
    body = json.dumps(payload).encode("utf-8")
    req = urllib_request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib_request.urlopen(req, timeout=10) as resp:
            response_text = resp.read().decode("utf-8", errors="replace")
            if response_text.strip() != "ok":
                raise RuntimeError(f"Slack unexpected response: {response_text}")
    except urllib_error.HTTPError as exc:
        body_text = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Slack HTTP {exc.code}: {body_text}") from exc
    except OSError as exc:
        raise RuntimeError(f"Slack connection error: {exc}") from exc


def notify_slack(
    incident_id: str,
    tenant_id: str,
    ticket: TicketRecord,
    triage: TriageOutput,
    reporter_email: str,
    credentials: dict[str, str] | None = None,
) -> str:
    with start_span("notify.slack.send", **{"incident.id": incident_id, "ticket.id": ticket.ticket_id, "ticket.provider": ticket.provider}):
        if not _slack_available(credentials):
            return _mock_detail(ticket, triage)

        webhook_url = str((credentials or {}).get("webhook_url") or os.getenv("SLACK_WEBHOOK_URL", ""))
        sev = triage.severity
        color = _SEV_COLORS.get(sev, "#94a3b8")
        emoji = _SEV_EMOJI.get(sev, "white_circle")
        ticket_link = f"<{ticket.url}|{ticket.ticket_id}>" if ticket.url else ticket.ticket_id

        blocks = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": f":{emoji}: AURA Incident Alert - {sev.upper()}",
                    "emoji": True,
                },
            },
            {"type": "divider"},
            {
                "type": "section",
                "fields": [
                    {"type": "mrkdwn", "text": f"*Incident ID*\n`{incident_id}`"},
                    {"type": "mrkdwn", "text": f"*Tenant*\n`{tenant_id}`"},
                    {"type": "mrkdwn", "text": f"*Severity*\n*{sev.upper()}*"},
                    {"type": "mrkdwn", "text": f"*Service*\n`{triage.affected_service}`"},
                    {"type": "mrkdwn", "text": f"*Ticket*\n{ticket_link}"},
                    {"type": "mrkdwn", "text": f"*Reporter*\n{reporter_email}"},
                ],
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Summary*\n{triage.technical_summary}",
                },
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Attachment Evidence*\n{triage.attachment_summary or 'No attachment evidence captured.'}",
                },
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Attachment Influence*\n{triage.attachment_influence_reasoning or 'No attachment influence.'}",
                },
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Root Cause*\n{triage.root_cause_analysis}",
                },
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Auto-Fix*\n{triage.proposed_fix}",
                },
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*CLI Command*\n```{triage.proposed_cli_command}```",
                },
            },
        ]

        if triage.runbook_suggestions:
            runbook_text = "\n".join(f"- {step}" for step in triage.runbook_suggestions[:4])
            blocks.append(
                {
                    "type": "section",
                    "text": {"type": "mrkdwn", "text": f"*Runbook Steps*\n{runbook_text}"},
                }
            )

        payload = {
            "attachments": [
                {
                    "color": color,
                    "blocks": blocks,
                    "fallback": f"[AURA/{sev.upper()}] {incident_id} on {triage.affected_service} - Ticket: {ticket.ticket_id}",
                }
            ]
        }

        try:
            _http_post_json(webhook_url, payload)
            detail = (
                f"Team notified on Slack (webhook). Ticket={ticket.ticket_id}, "
                f"service={triage.affected_service}, severity={sev}. "
                f"Attachment evidence={triage.attachment_summary or 'none'}."
            )
            log_event("slack_notification_sent", incident_id=incident_id, ticket_id=ticket.ticket_id, severity=sev)
            return detail
        except RuntimeError as exc:
            log_event("slack_notification_failed", incident_id=incident_id, error=str(exc))
            raise


def notify_slack_resolved(
    incident_id: str,
    tenant_id: str,
    ticket: TicketRecord,
    reporter_email: str,
    credentials: dict[str, str] | None = None,
) -> str:
    with start_span("notify.slack.send", **{"incident.id": incident_id, "ticket.id": ticket.ticket_id, "ticket.provider": ticket.provider}):
        if not _slack_available(credentials):
            return f"[mock] Resolved notification sent for {incident_id}."

        webhook_url = str((credentials or {}).get("webhook_url") or os.getenv("SLACK_WEBHOOK_URL", ""))
        ticket_link = f"<{ticket.url}|{ticket.ticket_id}>" if ticket.url else ticket.ticket_id
        payload = {
            "attachments": [
                {
                    "color": "#22c55e",
                    "blocks": [
                        {
                            "type": "header",
                            "text": {"type": "plain_text", "text": "Incident Resolved", "emoji": True},
                        },
                        {
                            "type": "section",
                            "fields": [
                                {"type": "mrkdwn", "text": f"*Incident ID*\n`{incident_id}`"},
                                {"type": "mrkdwn", "text": f"*Tenant*\n`{tenant_id}`"},
                                {"type": "mrkdwn", "text": f"*Ticket*\n{ticket_link}"},
                                {"type": "mrkdwn", "text": f"*Reporter notified*\n{reporter_email}"},
                            ],
                        },
                    ],
                    "fallback": f"[AURA] Incident {incident_id} has been resolved.",
                }
            ]
        }
        try:
            _http_post_json(webhook_url, payload)
            log_event("slack_resolved_sent", incident_id=incident_id)
            return f"Resolved notification sent to Slack. Ticket={ticket.ticket_id}."
        except RuntimeError as exc:
            log_event("slack_resolved_failed", incident_id=incident_id, error=str(exc))
            raise


def _mock_detail(ticket: TicketRecord, triage: TriageOutput) -> str:
    return (
        f"Team notified on mock-slack. Ticket={ticket.ticket_id}, "
        f"service={triage.affected_service}, severity={triage.severity}. "
        f"Attachment evidence={triage.attachment_summary or 'none'}."
    )


def test_slack_credentials(credentials: dict[str, str]) -> tuple[bool, str]:
    webhook_url = str(credentials.get("webhook_url", "")).strip()
    if not webhook_url:
        return False, "Slack webhook_url is required."
    try:
        _http_post_json(webhook_url, {"text": "AURA Slack integration test"})
        return True, "Slack webhook delivered successfully."
    except Exception as exc:
        return False, str(exc)
