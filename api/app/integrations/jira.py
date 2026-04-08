"""
integrations/jira.py – Real Jira Cloud integration for AURA.

Requires env vars:
  JIRA_BASE_URL   e.g. https://your-org.atlassian.net
  JIRA_EMAIL      e.g. sre@your-org.com
  JIRA_API_TOKEN  (Atlassian API token)
  JIRA_PROJECT_KEY e.g. AURA  (default: AURA)

When any of the above is missing or MOCK_MODE=true, falls back to mock.

API reference:
  POST /rest/api/3/issue
  https://developer.atlassian.com/cloud/jira/platform/rest/v3/api-group-issues/#api-rest-api-3-issue-post
"""
from __future__ import annotations

import json
import os
from base64 import b64encode
from typing import Any
from urllib import request as urllib_request, error as urllib_error

from ..models import TicketRecord
from ..observability import log_event


# ── Severity → Jira priority mapping ───────────────────────────
_PRIORITY_MAP: dict[str, str] = {
    "critical": "Highest",
    "high":     "High",
    "medium":   "Medium",
    "low":      "Low",
}

_ISSUE_TYPE = "Bug"      # Change to "Incident" if your project has that type


def _jira_available() -> bool:
    """Return True if all required env vars are set and MOCK_MODE is off."""
    if os.getenv("MOCK_MODE", "true").lower() in {"1", "true", "yes", "on"}:
        return False
    required = ["JIRA_BASE_URL", "JIRA_EMAIL", "JIRA_API_TOKEN"]
    return all(os.getenv(k, "").strip() for k in required)


def _basic_auth_header() -> str:
    email = os.getenv("JIRA_EMAIL", "")
    token = os.getenv("JIRA_API_TOKEN", "")
    credentials = f"{email}:{token}"
    encoded = b64encode(credentials.encode()).decode()
    return f"Basic {encoded}"


def _http_post(url: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Minimal HTTP POST using stdlib (no requests dependency needed)."""
    body = json.dumps(payload).encode("utf-8")
    req = urllib_request.Request(
        url,
        data=body,
        headers={
            "Authorization": _basic_auth_header(),
            "Content-Type":  "application/json",
            "Accept":        "application/json",
        },
        method="POST",
    )
    try:
        with urllib_request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib_error.HTTPError as exc:
        body_text = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Jira HTTP {exc.code}: {body_text}") from exc
    except OSError as exc:
        raise RuntimeError(f"Jira connection error: {exc}") from exc


def create_jira_ticket(
    incident_id: str,
    summary: str,
    description: str,
    severity: str,
    affected_service: str,
    rca: str,
    proposed_fix: str,
    cli_command: str,
    tenant_id: str,
) -> TicketRecord:
    """
    Create a real Jira issue and return a TicketRecord.
    Falls back to mock if Jira is not configured.
    """
    if not _jira_available():
        return _mock_ticket(incident_id)

    base_url     = os.getenv("JIRA_BASE_URL", "").rstrip("/")
    project_key  = os.getenv("JIRA_PROJECT_KEY", "AURA")
    priority     = _PRIORITY_MAP.get(severity, "Medium")

    # Jira API v3 uses Atlassian Document Format (ADF) for rich text
    adf_body = {
        "version": 1,
        "type": "doc",
        "content": [
            _adf_heading("🤖 AURA Automated Triage", 2),
            _adf_paragraph(f"**Tenant:** {tenant_id}  |  **Service:** {affected_service}  |  **Severity:** {severity.upper()}"),
            _adf_heading("📋 Description", 3),
            _adf_paragraph(description),
            _adf_heading("🔎 Root Cause Analysis", 3),
            _adf_paragraph(rca),
            _adf_heading("🛠 Proposed Fix", 3),
            _adf_paragraph(proposed_fix),
            _adf_heading("⚡ Suggested CLI Command", 3),
            _adf_code_block(cli_command),
            _adf_paragraph(f"Incident ID: {incident_id}"),
        ],
    }

    payload = {
        "fields": {
            "project":   {"key": project_key},
            "summary":   f"[AURA/{severity.upper()}] {summary[:200]}",
            "issuetype": {"name": _ISSUE_TYPE},
            "priority":  {"name": priority},
            "description": adf_body,
            "labels":    ["aura", f"severity-{severity}", f"service-{affected_service}", tenant_id],
        }
    }

    url = f"{base_url}/rest/api/3/issue"

    try:
        resp = _http_post(url, payload)
        issue_key  = resp.get("key", f"AURA-???")
        issue_id   = resp.get("id", "")
        issue_url  = f"{base_url}/browse/{issue_key}"

        log_event(
            "jira_ticket_created",
            incident_id=incident_id,
            issue_key=issue_key,
            issue_id=issue_id,
        )

        return TicketRecord(
            ticket_id=issue_key,
            provider="jira",
            url=issue_url,
            status="created",
        )

    except RuntimeError as exc:
        log_event("jira_ticket_failed", incident_id=incident_id, error=str(exc))
        raise


def _mock_ticket(incident_id: str) -> TicketRecord:
    ticket_id = f"AURA-{incident_id[-6:].upper()}"
    return TicketRecord(
        ticket_id=ticket_id,
        provider="mock-jira",
        url=f"https://mock-jira.local/browse/{ticket_id}",
        status="created",
    )


# ── ADF helpers ─────────────────────────────────────────────────

def _adf_paragraph(text: str) -> dict:
    return {
        "type": "paragraph",
        "content": [{"type": "text", "text": str(text)}],
    }


def _adf_heading(text: str, level: int) -> dict:
    return {
        "type": "heading",
        "attrs": {"level": level},
        "content": [{"type": "text", "text": str(text)}],
    }


def _adf_code_block(code: str) -> dict:
    return {
        "type": "codeBlock",
        "attrs": {"language": "bash"},
        "content": [{"type": "text", "text": str(code)}],
    }
