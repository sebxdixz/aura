"""
integrations/slack.py – Real Slack Incoming Webhook integration for AURA.

Requires env vars:
  SLACK_WEBHOOK_URL   Full Incoming Webhook URL from Slack App config
                      e.g. https://hooks.slack.com/services/T.../B.../...

When the URL is missing or MOCK_MODE=true, falls back to mock.

Slack Incoming Webhooks docs:
  https://api.slack.com/messaging/webhooks
  https://api.slack.com/reference/block-kit/blocks
"""
from __future__ import annotations

import json
import os
from urllib import request as urllib_request, error as urllib_error

from ..models import TicketRecord, TriageOutput
from ..observability import log_event


_SEV_COLORS: dict[str, str] = {
    "critical": "#ef4444",
    "high":     "#f97316",
    "medium":   "#eab308",
    "low":      "#22c55e",
}

_SEV_EMOJI: dict[str, str] = {
    "critical": "🔴",
    "high":     "🟠",
    "medium":   "🟡",
    "low":      "🟢",
}


def _slack_available() -> bool:
    if os.getenv("MOCK_MODE", "true").lower() in {"1", "true", "yes", "on"}:
        return False
    return bool(os.getenv("SLACK_WEBHOOK_URL", "").strip())


def _http_post_json(url: str, payload: dict) -> None:
    body = json.dumps(payload).encode("utf-8")
    req  = urllib_request.Request(
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
) -> str:
    """
    Send a rich Block Kit message to Slack.
    Returns a detail string for the NotificationRecord.
    Falls back to mock if Slack is not configured.
    """
    if not _slack_available():
        return _mock_detail(ticket, triage)

    webhook_url = os.getenv("SLACK_WEBHOOK_URL", "")
    sev         = triage.severity
    color       = _SEV_COLORS.get(sev, "#94a3b8")
    emoji       = _SEV_EMOJI.get(sev, "⚪")
    ticket_link = f"<{ticket.url}|{ticket.ticket_id}>" if ticket.url else ticket.ticket_id

    blocks = [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": f"{emoji} AURA Incident Alert — {sev.upper()}",
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
                "text": f"*📋 Summary*\n{triage.technical_summary}",
            },
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"*🔎 Root Cause*\n{triage.root_cause_analysis}",
            },
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"*🛠 Auto-Fix*\n{triage.proposed_fix}",
            },
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"*⚡ CLI Command*\n```{triage.proposed_cli_command}```",
            },
        },
    ]

    # Add runbook if present
    if triage.runbook_suggestions:
        runbook_text = "\n".join(f"• {s}" for s in triage.runbook_suggestions[:4])
        blocks.append({
            "type": "section",
            "text": {"type": "mrkdwn", "text": f"*📖 Runbook Steps*\n{runbook_text}"},
        })

    blocks.append({"type": "divider"})
    blocks.append({
        "type": "context",
        "elements": [
            {
                "type": "mrkdwn",
                "text": f"🤖 Sent by AURA SRE Intelligence  •  Ticket via {ticket.provider}  •  <{ticket.url}|Open ticket>",
            }
        ],
    })

    payload = {
        "attachments": [
            {
                "color":  color,
                "blocks": blocks,
                "fallback": f"[AURA/{sev.upper()}] {incident_id} on {triage.affected_service} — Ticket: {ticket.ticket_id}",
            }
        ]
    }

    try:
        _http_post_json(webhook_url, payload)
        detail = (
            f"Team notified on Slack (webhook). "
            f"Ticket={ticket.ticket_id}, service={triage.affected_service}, severity={sev}."
        )
        log_event(
            "slack_notification_sent",
            incident_id=incident_id,
            ticket_id=ticket.ticket_id,
            severity=sev,
        )
        return detail

    except RuntimeError as exc:
        log_event("slack_notification_failed", incident_id=incident_id, error=str(exc))
        raise


def notify_slack_resolved(
    incident_id: str,
    tenant_id: str,
    ticket: TicketRecord,
    reporter_email: str,
) -> str:
    """
    Send a resolution notification to Slack.
    """
    if not _slack_available():
        return f"[mock] Resolved notification sent for {incident_id}."

    webhook_url = os.getenv("SLACK_WEBHOOK_URL", "")
    ticket_link = f"<{ticket.url}|{ticket.ticket_id}>" if ticket.url else ticket.ticket_id

    payload = {
        "attachments": [
            {
                "color": "#22c55e",
                "blocks": [
                    {
                        "type": "header",
                        "text": {"type": "plain_text", "text": "✅ Incident Resolved", "emoji": True},
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
                    {
                        "type": "context",
                        "elements": [{"type": "mrkdwn", "text": "🤖 AURA SRE Intelligence · Automated resolution notification"}],
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
        f"Team notified on mock-slack. "
        f"Ticket={ticket.ticket_id}, service={triage.affected_service}, severity={triage.severity}."
    )
