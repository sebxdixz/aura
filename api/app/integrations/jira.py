"""
integrations/jira.py - Real Jira Cloud integration for AURA.
"""
from __future__ import annotations

import json
import os
from base64 import b64encode
from typing import Any
from urllib import error as urllib_error
from urllib import request as urllib_request

from ..models import TicketRecord
from ..observability import log_event
from ..telemetry import start_span

_PRIORITY_MAP: dict[str, str] = {
    "critical": "Highest",
    "high": "High",
    "medium": "Medium",
    "low": "Low",
}

_ISSUE_TYPE = "Bug"


def _jira_available(credentials: dict[str, str] | None = None) -> bool:
    if os.getenv("MOCK_MODE", "true").lower() in {"1", "true", "yes", "on"}:
        return False
    if credentials:
        required = ["base_url", "email", "api_token"]
        return all(str(credentials.get(key, "")).strip() for key in required)
    required = ["JIRA_BASE_URL", "JIRA_EMAIL", "JIRA_API_TOKEN"]
    return all(os.getenv(key, "").strip() for key in required)


def _basic_auth_header(credentials: dict[str, str] | None = None) -> str:
    email = str((credentials or {}).get("email") or os.getenv("JIRA_EMAIL", ""))
    token = str((credentials or {}).get("api_token") or os.getenv("JIRA_API_TOKEN", ""))
    credentials = f"{email}:{token}"
    encoded = b64encode(credentials.encode()).decode()
    return f"Basic {encoded}"


def _http_post(url: str, payload: dict[str, Any], credentials: dict[str, str] | None = None) -> dict[str, Any]:
    body = json.dumps(payload).encode("utf-8")
    req = urllib_request.Request(
        url,
        data=body,
        headers={
            "Authorization": _basic_auth_header(credentials),
            "Content-Type": "application/json",
            "Accept": "application/json",
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


def _http_get(url: str, credentials: dict[str, str] | None = None) -> dict[str, Any]:
    req = urllib_request.Request(
        url,
        headers={
            "Authorization": _basic_auth_header(credentials),
            "Accept": "application/json",
        },
        method="GET",
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
    credentials: dict[str, str] | None = None,
) -> TicketRecord:
    with start_span("ticketing.jira.create", **{"incident.id": incident_id, "tenant.id": tenant_id}):
        if not _jira_available(credentials):
            return _mock_ticket(incident_id, summary, description)

        base_url = str((credentials or {}).get("base_url") or os.getenv("JIRA_BASE_URL", "")).rstrip("/")
        project_key = str((credentials or {}).get("project_key") or os.getenv("JIRA_PROJECT_KEY", "AURA"))
        priority = _PRIORITY_MAP.get(severity, "Medium")

        adf_body = {
            "version": 1,
            "type": "doc",
            "content": [
                _adf_heading("AURA Automated Triage", 2),
                _adf_paragraph(f"Tenant: {tenant_id} | Service: {affected_service} | Severity: {severity.upper()}"),
                _adf_heading("Description", 3),
                _adf_paragraph(description),
                _adf_heading("Root Cause Analysis", 3),
                _adf_paragraph(rca),
                _adf_heading("Proposed Fix", 3),
                _adf_paragraph(proposed_fix),
                _adf_heading("Suggested CLI Command", 3),
                _adf_code_block(cli_command),
                _adf_paragraph(f"Incident ID: {incident_id}"),
            ],
        }

        payload = {
            "fields": {
                "project": {"key": project_key},
                "summary": f"[AURA/{severity.upper()}] {summary[:200]}",
                "issuetype": {"name": str((credentials or {}).get("issue_type") or _ISSUE_TYPE)},
                "priority": {"name": priority},
                "description": adf_body,
                "labels": ["aura", f"severity-{severity}", f"service-{affected_service}", tenant_id],
            }
        }

        try:
            resp = _http_post(f"{base_url}/rest/api/3/issue", payload, credentials)
            issue_key = resp.get("key", "AURA-UNKNOWN")
            issue_id = resp.get("id", "")
            issue_url = f"{base_url}/browse/{issue_key}"
            log_event("jira_ticket_created", incident_id=incident_id, issue_key=issue_key, issue_id=issue_id)
            return TicketRecord(
                ticket_id=issue_key,
                provider="jira",
                url=issue_url,
                status="created",
                title=f"[AURA/{severity.upper()}] {summary[:200]}",
                description=description,
                external_status="To Do",
            )
        except RuntimeError as exc:
            log_event("jira_ticket_failed", incident_id=incident_id, error=str(exc))
            raise


def _mock_ticket(incident_id: str, summary: str, description: str) -> TicketRecord:
    ticket_id = f"AURA-{incident_id[-6:].upper()}"
    return TicketRecord(
        ticket_id=ticket_id,
        provider="mock-jira",
        url=f"https://mock-jira.local/browse/{ticket_id}",
        status="created",
        title=summary,
        description=description,
        external_status="Created",
    )


def fetch_jira_ticket_status(ticket_id: str, credentials: dict[str, str] | None = None) -> str:
    with start_span("ticketing.jira.fetch_status", **{"ticket.id": ticket_id, "ticket.provider": "jira"}):
        if not _jira_available(credentials):
            return "Created"

        base_url = str((credentials or {}).get("base_url") or os.getenv("JIRA_BASE_URL", "")).rstrip("/")
        payload = _http_get(f"{base_url}/rest/api/3/issue/{ticket_id}?fields=status", credentials)
        fields = payload.get("fields") or {}
        status = fields.get("status") or {}
        name = status.get("name")
        if not name:
            raise RuntimeError("Jira status payload missing fields.status.name")
        log_event("jira_ticket_status_fetched", ticket_id=ticket_id, external_status=name)
        return str(name)


def test_jira_credentials(credentials: dict[str, str], create_issue: bool = True) -> tuple[bool, str]:
    try:
        if not _jira_available(credentials):
            return False, "Missing Jira credentials."
        if not create_issue:
            base_url = str(credentials.get("base_url", "")).rstrip("/")
            _http_get(f"{base_url}/rest/api/3/myself", credentials)
            return True, "Jira credentials are valid."
        ticket = create_jira_ticket(
            incident_id="jira-test",
            summary="AURA Jira integration test",
            description="Integration validation from AURA.",
            severity="low",
            affected_service="web-app",
            rca="Connectivity validation",
            proposed_fix="No action required.",
            cli_command="echo test",
            tenant_id="integration-test",
            credentials=credentials,
        )
        return True, f"Jira test succeeded: {ticket.ticket_id}"
    except Exception as exc:
        return False, str(exc)


def _adf_paragraph(text: str) -> dict:
    return {"type": "paragraph", "content": [{"type": "text", "text": str(text)}]}


def _adf_heading(text: str, level: int) -> dict:
    return {"type": "heading", "attrs": {"level": level}, "content": [{"type": "text", "text": str(text)}]}


def _adf_code_block(code: str) -> dict:
    return {"type": "codeBlock", "attrs": {"language": "bash"}, "content": [{"type": "text", "text": str(code)}]}
