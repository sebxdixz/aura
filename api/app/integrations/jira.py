"""
integrations/jira.py - Real Jira Cloud integration for AURA.

Requires env vars:
  JIRA_BASE_URL    e.g. https://your-org.atlassian.net
  JIRA_EMAIL       e.g. sre@your-org.com
  JIRA_API_TOKEN   (Atlassian API token)
  JIRA_PROJECT_KEY e.g. AURA (default: AURA)

When any of the above is missing or MOCK_MODE=true, falls back to mock.
"""
from __future__ import annotations

import json
import os
import re
from base64 import b64encode
from typing import Any
from urllib import error as urllib_error
from urllib import parse as urllib_parse
from urllib import request as urllib_request

from ..models import TicketRecord
from ..observability import log_event


_PRIORITY_MAP: dict[str, str] = {
    "critical": "Highest",
    "high": "High",
    "medium": "Medium",
    "low": "Low",
}

_ISSUE_TYPE = "Bug"


def _sanitize_label(value: str, default: str) -> str:
    text = str(value).strip().lower()
    text = re.sub(r"\s+", "-", text)
    text = re.sub(r"[^a-z0-9_-]", "-", text)
    text = re.sub(r"-{2,}", "-", text).strip("-_")
    if not text:
        text = default
    return text[:255]


def _build_labels(*, severity: str, affected_service: str, tenant_id: str) -> list[str]:
    return [
        _sanitize_label("aura", "aura"),
        _sanitize_label(f"severity-{severity}", "severity"),
        _sanitize_label(f"service-{affected_service}", "service"),
        _sanitize_label(tenant_id, "tenant"),
    ]


def _jira_available(credentials: dict[str, str] | None = None) -> bool:
    """Return True if all required credentials are set and MOCK_MODE is off."""
    if os.getenv("MOCK_MODE", "true").lower() in {"1", "true", "yes", "on"}:
        return False
    if credentials:
        required = ["base_url", "email", "api_token"]
        return all(str(credentials.get(k, "")).strip() for k in required)
    required = ["JIRA_BASE_URL", "JIRA_EMAIL", "JIRA_API_TOKEN"]
    return all(os.getenv(k, "").strip() for k in required)


def _basic_auth_header(credentials: dict[str, str] | None = None) -> str:
    email = str((credentials or {}).get("email", "")).strip() or os.getenv("JIRA_EMAIL", "")
    token = str((credentials or {}).get("api_token", "")).strip() or os.getenv("JIRA_API_TOKEN", "")
    encoded = b64encode(f"{email}:{token}".encode("utf-8")).decode("ascii")
    return f"Basic {encoded}"


def _format_http_error(status_code: int, body_text: str) -> str:
    detail = body_text.strip() or "Unknown Jira error"
    try:
        payload = json.loads(body_text)
        if isinstance(payload, dict):
            parts: list[str] = []
            messages = payload.get("errorMessages")
            if isinstance(messages, list):
                parts.extend(str(m).strip() for m in messages if str(m).strip())
            errors = payload.get("errors")
            if isinstance(errors, dict):
                for field, message in errors.items():
                    text = str(message).strip()
                    if text:
                        parts.append(f"{field}: {text}")
            if parts:
                detail = "; ".join(parts)
    except json.JSONDecodeError:
        pass
    if len(detail) > 500:
        detail = f"{detail[:500]}..."
    return f"Jira HTTP {status_code}: {detail}"


def _request_json(
    url: str,
    *,
    method: str,
    credentials: dict[str, str] | None = None,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    data: bytes | None = None
    headers = {
        "Authorization": _basic_auth_header(credentials),
        "Accept": "application/json",
    }
    if payload is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(payload).encode("utf-8")

    req = urllib_request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib_request.urlopen(req, timeout=12) as resp:
            raw = resp.read().decode("utf-8")
        if not raw.strip():
            return {}
        parsed = json.loads(raw)
        if isinstance(parsed, dict):
            return parsed
        return {"data": parsed}
    except urllib_error.HTTPError as exc:
        body_text = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(_format_http_error(exc.code, body_text)) from exc
    except OSError as exc:
        raise RuntimeError(f"Jira connection error: {exc}") from exc


def _http_get(url: str, *, credentials: dict[str, str] | None = None) -> dict[str, Any]:
    return _request_json(url, method="GET", credentials=credentials)


def _http_post(
    url: str,
    payload: dict[str, Any],
    *,
    credentials: dict[str, str] | None = None,
) -> dict[str, Any]:
    return _request_json(url, method="POST", credentials=credentials, payload=payload)


def _project_ref(credentials: dict[str, str] | None = None) -> str:
    value = str((credentials or {}).get("project_key", "")).strip() or os.getenv("JIRA_PROJECT_KEY", "AURA").strip()
    if not value:
        raise RuntimeError("Jira project is required. Set project_key in tenant settings.")
    return value


def _issue_type_ref(credentials: dict[str, str] | None = None) -> str:
    return str((credentials or {}).get("issue_type", "")).strip() or _ISSUE_TYPE


def _normalize_issue_types(raw: Any) -> list[dict[str, Any]]:
    if not isinstance(raw, list):
        return []
    issue_types: list[dict[str, Any]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        issue_id = str(item.get("id", "")).strip()
        issue_name = str(item.get("name", "")).strip()
        if not issue_id and not issue_name:
            continue
        issue_types.append(
            {
                "id": issue_id,
                "name": issue_name or issue_id,
                "subtask": bool(item.get("subtask", False)),
            }
        )
    return issue_types


def _parse_project(payload: dict[str, Any]) -> dict[str, Any]:
    key = str(payload.get("key", "")).strip()
    if not key:
        raise RuntimeError("Jira project response did not include a key.")
    return {
        "key": key,
        "name": str(payload.get("name", "")).strip() or key,
        "issue_types": _normalize_issue_types(payload.get("issueTypes")),
    }


def _find_project_via_search(
    *,
    base_url: str,
    project_ref: str,
    credentials: dict[str, str] | None,
) -> dict[str, Any]:
    query = urllib_parse.urlencode({"query": project_ref, "maxResults": 50})
    search_url = f"{base_url}/rest/api/3/project/search?{query}"
    search_payload = _http_get(search_url, credentials=credentials)
    values = search_payload.get("values")
    if not isinstance(values, list) or not values:
        raise RuntimeError(f"Jira project '{project_ref}' was not found.")

    ref_cf = project_ref.casefold()
    selected: dict[str, Any] | None = None
    for item in values:
        if not isinstance(item, dict):
            continue
        key = str(item.get("key", "")).strip()
        name = str(item.get("name", "")).strip()
        if key.casefold() == ref_cf or name.casefold() == ref_cf:
            selected = item
            break
    if selected is None and len(values) == 1 and isinstance(values[0], dict):
        selected = values[0]
    if selected is None:
        options: list[str] = []
        for item in values[:5]:
            if not isinstance(item, dict):
                continue
            key = str(item.get("key", "")).strip()
            name = str(item.get("name", "")).strip()
            if key or name:
                options.append(f"{name} ({key})")
        hint = ", ".join(options) or "no visible projects"
        raise RuntimeError(
            f"Jira project '{project_ref}' is ambiguous. Use project key. Visible projects: {hint}"
        )

    selected_key = str(selected.get("key", "")).strip()
    if not selected_key:
        raise RuntimeError(f"Jira project '{project_ref}' has no key in search response.")

    # Re-fetch by key to obtain issueTypes consistently.
    encoded_key = urllib_parse.quote(selected_key, safe="")
    payload = _http_get(f"{base_url}/rest/api/3/project/{encoded_key}", credentials=credentials)
    return _parse_project(payload)


def _resolve_project(
    *,
    base_url: str,
    project_ref: str,
    credentials: dict[str, str] | None,
) -> dict[str, Any]:
    encoded_ref = urllib_parse.quote(project_ref, safe="")
    try:
        payload = _http_get(f"{base_url}/rest/api/3/project/{encoded_ref}", credentials=credentials)
        return _parse_project(payload)
    except RuntimeError as exc:
        message = str(exc)
        if "Jira HTTP 400" not in message and "Jira HTTP 404" not in message:
            raise
    return _find_project_via_search(base_url=base_url, project_ref=project_ref, credentials=credentials)


def _resolve_issue_type(issue_types: list[dict[str, Any]], requested: str) -> tuple[dict[str, Any], str]:
    normalized = requested.casefold()
    if issue_types:
        if requested:
            for item in issue_types:
                if requested == str(item.get("id", "")).strip():
                    return item, "id"
            for item in issue_types:
                name = str(item.get("name", "")).strip()
                if name and name.casefold() == normalized:
                    return item, "name"

        for preferred in ("Bug", "Task", "Incident", "Story", "Tarea", "Incidencia", "Historia"):
            pref = preferred.casefold()
            for item in issue_types:
                name = str(item.get("name", "")).strip()
                if name and name.casefold() == pref:
                    return item, "preferred_name"

        for item in issue_types:
            if not bool(item.get("subtask", False)):
                return item, "first_non_subtask"
        return issue_types[0], "first_available"

    fallback_name = requested or _ISSUE_TYPE
    return {"id": "", "name": fallback_name, "subtask": False}, "provided_name"


def _issue_type_field(issue_type: dict[str, Any]) -> dict[str, str]:
    issue_id = str(issue_type.get("id", "")).strip()
    if issue_id:
        return {"id": issue_id}
    issue_name = str(issue_type.get("name", "")).strip() or _ISSUE_TYPE
    return {"name": issue_name}


def _same_issue_type(left: dict[str, Any], right: dict[str, Any]) -> bool:
    left_id = str(left.get("id", "")).strip()
    right_id = str(right.get("id", "")).strip()
    if left_id and right_id:
        return left_id == right_id
    left_name = str(left.get("name", "")).strip().casefold()
    right_name = str(right.get("name", "")).strip().casefold()
    return bool(left_name and right_name and left_name == right_name)


def _issue_type_candidates(target: dict[str, Any]) -> list[dict[str, Any]]:
    selected = target["issue_type"]
    all_types = [t for t in target["issue_types"] if isinstance(t, dict)]
    non_subtasks = [t for t in all_types if not bool(t.get("subtask", False))]
    subtasks = [t for t in all_types if bool(t.get("subtask", False))]

    ordered: list[dict[str, Any]] = [selected]
    for candidate in [*non_subtasks, *subtasks]:
        if not any(_same_issue_type(candidate, existing) for existing in ordered):
            ordered.append(candidate)
    return ordered


def _is_issue_type_error(error_text: str) -> bool:
    text = error_text.casefold()
    return "issuetype" in text or "tipo de incidencia" in text


def _create_issue_with_issue_type_fallback(
    *,
    base_url: str,
    base_fields: dict[str, Any],
    candidates: list[dict[str, Any]],
    credentials: dict[str, str] | None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    last_error: RuntimeError | None = None
    for index, issue_type in enumerate(candidates):
        fields = dict(base_fields)
        fields["issuetype"] = _issue_type_field(issue_type)
        try:
            created = _http_post(f"{base_url}/rest/api/3/issue", {"fields": fields}, credentials=credentials)
            return created, issue_type
        except RuntimeError as exc:
            last_error = exc
            if index >= len(candidates) - 1:
                break
            if not _is_issue_type_error(str(exc)):
                raise
            continue

    if last_error:
        raise last_error
    raise RuntimeError("Jira issue creation failed without explicit error.")


def _resolve_target(
    *,
    base_url: str,
    credentials: dict[str, str] | None,
) -> dict[str, Any]:
    project_ref = _project_ref(credentials)
    requested_issue_type = _issue_type_ref(credentials)
    project = _resolve_project(base_url=base_url, project_ref=project_ref, credentials=credentials)
    issue_types = project["issue_types"]
    selected_issue_type, selection_mode = _resolve_issue_type(issue_types, requested_issue_type)
    return {
        "project_ref": project_ref,
        "project_key": project["key"],
        "project_name": project["name"],
        "issue_types": issue_types,
        "requested_issue_type": requested_issue_type,
        "issue_type": selected_issue_type,
        "issue_type_selection_mode": selection_mode,
    }


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
    """
    Create a real Jira issue and return a TicketRecord.
    Falls back to mock if Jira is not configured.
    """
    if not _jira_available(credentials):
        return _mock_ticket(incident_id)

    base_url = (str((credentials or {}).get("base_url", "")).strip() or os.getenv("JIRA_BASE_URL", "")).rstrip("/")
    if not base_url:
        raise RuntimeError("Jira base URL is required.")

    target = _resolve_target(base_url=base_url, credentials=credentials)
    priority = _PRIORITY_MAP.get(severity, "Medium")

    adf_body = {
        "version": 1,
        "type": "doc",
        "content": [
            _adf_heading("AURA Automated Triage", 2),
            _adf_paragraph(
                f"Tenant: {tenant_id} | Service: {affected_service} | Severity: {severity.upper()}"
            ),
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

    base_fields = {
        "project": {"key": target["project_key"]},
        "summary": f"[AURA/{severity.upper()}] {summary[:200]}",
        "priority": {"name": priority},
        "description": adf_body,
        "labels": _build_labels(severity=severity, affected_service=affected_service, tenant_id=tenant_id),
    }

    try:
        resp, used_issue_type = _create_issue_with_issue_type_fallback(
            base_url=base_url,
            base_fields=base_fields,
            candidates=_issue_type_candidates(target),
            credentials=credentials,
        )
        issue_key = str(resp.get("key", "")).strip() or "AURA-???"
        issue_id = str(resp.get("id", "")).strip()
        issue_url = f"{base_url}/browse/{issue_key}"

        log_event(
            "jira_ticket_created",
            incident_id=incident_id,
            issue_key=issue_key,
            issue_id=issue_id,
            project=target["project_key"],
            issue_type=str(used_issue_type.get("name", "")).strip(),
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


def _format_issue_types_hint(issue_types: list[dict[str, Any]]) -> str:
    names: list[str] = []
    for item in issue_types:
        name = str(item.get("name", "")).strip()
        if name and name not in names:
            names.append(name)
    if not names:
        return "Issue types were not listed by Jira for this project."
    return f"Available issue types: {', '.join(names[:10])}"


def test_jira_credentials(credentials: dict[str, str], *, create_issue: bool = True) -> tuple[bool, str]:
    if not _jira_available(credentials):
        return False, "Missing required Jira credentials (base_url/email/api_token)."

    base_url = str(credentials.get("base_url", "")).strip().rstrip("/")
    if not base_url:
        return False, "Jira base_url is required."

    try:
        payload = _http_get(f"{base_url}/rest/api/3/myself", credentials=credentials)
        display = str(payload.get("displayName") or payload.get("emailAddress") or "unknown-user").strip()

        target = _resolve_target(base_url=base_url, credentials=credentials)
        issue_type_name = str(target["issue_type"].get("name", "")).strip() or _ISSUE_TYPE
        selection_mode = target["issue_type_selection_mode"]
        selection_note = ""
        if target["requested_issue_type"] and selection_mode not in {"id", "name", "provided_name"}:
            selection_note = (
                f" Requested issue type '{target['requested_issue_type']}' is not valid for this project; "
                f"using '{issue_type_name}'."
            )
        project_note = ""
        if str(target["project_ref"]).casefold() != str(target["project_key"]).casefold():
            project_note = f" Project resolved to key '{target['project_key']}'."

        if not create_issue:
            return (
                True,
                f"Jira authentication successful ({display}). "
                f"Project: {target['project_name']} ({target['project_key']}). "
                f"Issue type for create: {issue_type_name}.{project_note}{selection_note} "
                f"{_format_issue_types_hint(target['issue_types'])}"
            )

        base_fields = {
            "project": {"key": target["project_key"]},
            "summary": "[AURA] Integration test ticket",
            "description": {
                "version": 1,
                "type": "doc",
                "content": [
                    {
                        "type": "paragraph",
                        "content": [
                            {
                                "type": "text",
                                "text": "Ticket created by AURA integration test endpoint.",
                            }
                        ],
                    }
                ],
            },
            "labels": ["aura", "integration-test"],
        }
        created, used_issue_type = _create_issue_with_issue_type_fallback(
            base_url=base_url,
            base_fields=base_fields,
            candidates=_issue_type_candidates(target),
            credentials=credentials,
        )
        issue_key = str(created.get("key", "")).strip()
        issue_url = f"{base_url}/browse/{issue_key}" if issue_key else base_url
        if issue_key:
            used_issue_type_name = str(used_issue_type.get("name", "")).strip() or issue_type_name
            return (
                True,
                f"Jira test successful ({display}). Project: {target['project_key']}, issue type: {used_issue_type_name}. "
                f"Test issue created: {issue_key} ({issue_url}).{project_note}{selection_note}"
            )
        return True, f"Jira authentication successful ({display}), but issue key was not returned."
    except RuntimeError as exc:
        return False, str(exc)


def _mock_ticket(incident_id: str) -> TicketRecord:
    ticket_id = f"AURA-{incident_id[-6:].upper()}"
    return TicketRecord(
        ticket_id=ticket_id,
        provider="mock-jira",
        url=f"https://mock-jira.local/browse/{ticket_id}",
        status="created",
    )


def _adf_paragraph(text: str) -> dict[str, Any]:
    return {
        "type": "paragraph",
        "content": [{"type": "text", "text": str(text)}],
    }


def _adf_heading(text: str, level: int) -> dict[str, Any]:
    return {
        "type": "heading",
        "attrs": {"level": level},
        "content": [{"type": "text", "text": str(text)}],
    }


def _adf_code_block(code: str) -> dict[str, Any]:
    return {
        "type": "codeBlock",
        "attrs": {"language": "bash"},
        "content": [{"type": "text", "text": str(code)}],
    }
