from __future__ import annotations

import os
from typing import Any

from .integrations.mcp import call_mcp_tool
from .integrations.openrouter import is_openrouter_enabled, plan_react_actions
from .models import TicketRecord, TriageOutput
from .observability import log_event

_PLAN_CACHE: dict[str, dict[str, Any]] = {}


def is_react_mcp_enabled() -> bool:
    return os.getenv("REACT_ENGINE", "legacy").strip().lower() == "openrouter_mcp"


def create_ticket_via_react(
    *,
    incident_id: str,
    tenant_id: str,
    description: str,
    triage: TriageOutput,
) -> TicketRecord:
    plan = _ensure_plan(
        incident_id=incident_id,
        tenant_id=tenant_id,
        description=description,
        triage=triage,
    )
    tool_payload = plan["ticket_tool"]
    result = call_mcp_tool(
        server=tool_payload["server"],
        tool=tool_payload["tool"],
        arguments=tool_payload["arguments"],
    )

    ticket_id = str(
        result.get("ticket_id")
        or result.get("issue_key")
        or result.get("key")
        or f"AURA-{incident_id[-6:].upper()}"
    )
    ticket_url = str(result.get("url") or result.get("issue_url") or "")
    provider = f"mcp:{tool_payload['server']}/{tool_payload['tool']}"

    log_event(
        "react_tool_executed",
        incident_id=incident_id,
        action="create_ticket",
        server=tool_payload["server"],
        tool=tool_payload["tool"],
    )
    return TicketRecord(
        ticket_id=ticket_id,
        provider=provider,
        url=ticket_url,
        status="created",
    )


def notify_team_via_react(
    *,
    incident_id: str,
    tenant_id: str,
    reporter_email: str,
    description: str,
    triage: TriageOutput,
    ticket: TicketRecord,
) -> str:
    plan = _ensure_plan(
        incident_id=incident_id,
        tenant_id=tenant_id,
        description=description,
        triage=triage,
    )
    tool_payload = plan["slack_tool"]
    args = dict(tool_payload["arguments"])
    args.setdefault("ticket_id", ticket.ticket_id)
    args.setdefault("ticket_url", ticket.url)
    args.setdefault("reporter_email", reporter_email)

    result = call_mcp_tool(
        server=tool_payload["server"],
        tool=tool_payload["tool"],
        arguments=args,
    )

    _PLAN_CACHE.pop(incident_id, None)
    log_event(
        "react_tool_executed",
        incident_id=incident_id,
        action="notify_team",
        server=tool_payload["server"],
        tool=tool_payload["tool"],
    )
    return str(
        result.get("detail")
        or result.get("message")
        or f"Team notified via MCP ({tool_payload['server']}/{tool_payload['tool']})."
    )


def _ensure_plan(
    *,
    incident_id: str,
    tenant_id: str,
    description: str,
    triage: TriageOutput,
) -> dict[str, Any]:
    cached = _PLAN_CACHE.get(incident_id)
    if cached:
        return cached

    context = {
        "incident_id": incident_id,
        "tenant_id": tenant_id,
        "description": description,
        "severity": triage.severity,
        "affected_service": triage.affected_service,
        "technical_summary": triage.technical_summary,
        "root_cause_analysis": triage.root_cause_analysis,
        "proposed_fix": triage.proposed_fix,
        "proposed_cli_command": triage.proposed_cli_command,
    }

    raw_plan = plan_react_actions(context) if is_openrouter_enabled() else None
    plan = _normalize_plan(raw_plan, context=context)
    _PLAN_CACHE[incident_id] = plan

    log_event(
        "react_plan_created",
        incident_id=incident_id,
        source="openrouter" if raw_plan else "default",
    )
    return plan


def _normalize_plan(raw_plan: dict[str, Any] | None, *, context: dict[str, Any]) -> dict[str, Any]:
    ticket_defaults = _default_ticket_tool(context)
    slack_defaults = _default_slack_tool(context)

    if not isinstance(raw_plan, dict):
        return {"ticket_tool": ticket_defaults, "slack_tool": slack_defaults}

    ticket_tool = _merge_tool(raw_plan.get("ticket_tool"), ticket_defaults)
    slack_tool = _merge_tool(raw_plan.get("slack_tool"), slack_defaults)
    return {
        "reasoning": str(raw_plan.get("reasoning", "")),
        "ticket_tool": ticket_tool,
        "slack_tool": slack_tool,
    }


def _default_ticket_tool(context: dict[str, Any]) -> dict[str, Any]:
    return {
        "server": os.getenv("MCP_JIRA_SERVER", "jira"),
        "tool": os.getenv("MCP_JIRA_TOOL", "create_issue"),
        "arguments": {
            "incident_id": context["incident_id"],
            "tenant_id": context["tenant_id"],
            "summary": f"[AURA/{str(context['severity']).upper()}] {str(context['description'])[:140]}",
            "description": context["description"],
            "severity": context["severity"],
            "affected_service": context["affected_service"],
            "root_cause_analysis": context["root_cause_analysis"],
            "proposed_fix": context["proposed_fix"],
            "proposed_cli_command": context["proposed_cli_command"],
        },
    }


def _default_slack_tool(context: dict[str, Any]) -> dict[str, Any]:
    return {
        "server": os.getenv("MCP_SLACK_SERVER", "slack"),
        "tool": os.getenv("MCP_SLACK_TOOL", "post_message"),
        "arguments": {
            "incident_id": context["incident_id"],
            "tenant_id": context["tenant_id"],
            "severity": context["severity"],
            "affected_service": context["affected_service"],
            "summary": context["technical_summary"],
            "root_cause_analysis": context["root_cause_analysis"],
            "proposed_fix": context["proposed_fix"],
            "proposed_cli_command": context["proposed_cli_command"],
        },
    }


def _merge_tool(candidate: Any, fallback: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(candidate, dict):
        return fallback

    server = str(candidate.get("server") or fallback["server"]).strip() or fallback["server"]
    tool = str(candidate.get("tool") or fallback["tool"]).strip() or fallback["tool"]
    args = dict(fallback["arguments"])
    user_args = candidate.get("arguments")
    if isinstance(user_args, dict):
        for key, value in user_args.items():
            args[str(key)] = value

    return {"server": server, "tool": tool, "arguments": args}

