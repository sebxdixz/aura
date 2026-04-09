"""
services.py - Business-logic layer for AURA.
"""
from __future__ import annotations

import os
import time
import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from . import repository as repo
from .attachments import attachment_context_from_record
from .guardrails import validate_tool_name
from .integrations.jira import create_jira_ticket
from .integrations.llm import (
    generate_model_triage,
    generate_two_stage_triage,
    is_model_enabled,
    is_two_stage_openrouter_enabled,
)
from .integrations.slack import notify_slack, notify_slack_resolved
from .models import (
    AttachmentRecord,
    IncidentRecord,
    NotificationRecord,
    TenantDashboard,
    TenantRecord,
    TicketRecord,
    TriageOutput,
)
from .observability import log_event
from .rag import retrieve_code_context
from .react_orchestrator import create_ticket_via_react, is_react_mcp_enabled, notify_team_via_react

FAIL_COUNTS: dict[str, int] = {}


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def infer_service(description: str) -> str:
    text = description.lower()
    if "checkout" in text or "payment" in text:
        return "checkout-service"
    if "login" in text or "auth" in text:
        return "auth-service"
    if "catalog" in text or "product" in text:
        return "catalog-service"
    return "web-app"


def infer_severity(description: str) -> str:
    severity, _, _ = calculate_severity(description=description, has_file=False)
    return severity


def calculate_severity(
    description: str,
    has_file: bool,
    factors: dict[str, object] | None = None,
) -> tuple[str, int, str]:
    text = description.lower()
    score = 10
    reasons: list[str] = []

    weighted_tokens = {
        "outage": 20,
        "down": 18,
        "500": 12,
        "critical": 15,
        "payment": 8,
        "checkout": 6,
        "failed": 8,
        "error": 6,
        "timeout": 8,
        "login": 5,
        "auth": 5,
        "degraded": 4,
        "slow": 3,
    }

    for token, weight in weighted_tokens.items():
        if token in text:
            score += weight
            reasons.append(token)

    if has_file:
        score += 5
        reasons.append("attachment")

    if factors:
        score += int(factors.get("impact_score", 0))
        score += int(factors.get("scope_score", 0))
        score += int(factors.get("reporter_score", 0))
        score += int(factors.get("error_code_score", 0))
        score += int(factors.get("component_score", 0))
        if bool(factors.get("security_risk", False)):
            score += 10
            reasons.append("security_risk")
        if bool(factors.get("workaround_present", False)):
            score -= 8
            reasons.append("workaround_present")

    score = max(0, min(score, 100))
    severity = _severity_from_score(score)
    rationale = (
        f"Severity score {score}/100 based on detected signals: {', '.join(reasons)}."
        if reasons
        else f"Severity score {score}/100 with low-impact signals."
    )
    return severity, score, rationale


def run_triage(
    incident_id: str | None,
    tenant_id: str | None,
    description: str,
    has_file: bool,
    attachment: AttachmentRecord | None = None,
    attachment_filename: str | None = None,
    attachment_content_type: str | None = None,
    attachment_bytes: bytes | None = None,
    db: Session | None = None,
) -> TriageOutput:
    triage_started_at = time.perf_counter()
    trace_id = incident_id or f"triage-{uuid.uuid4().hex[:10]}"
    attachment_type = attachment.attachment_type if attachment else "none"
    log_event(
        "triage_started",
        incident_id=incident_id,
        tenant_id=tenant_id,
        trace_id=trace_id,
        attachment_type=attachment_type,
        has_file=has_file,
    )
    severity_factors = _calculate_severity_factors(description=description, attachment=attachment)
    severity, severity_score, severity_rationale = calculate_severity(
        description=description,
        has_file=has_file,
        factors=severity_factors,
    )
    service = _infer_service_with_attachment(description, attachment)
    attachment_context = attachment_context_from_record(attachment)
    log_event(
        "attachment_context_built",
        incident_id=incident_id,
        tenant_id=tenant_id,
        trace_id=trace_id,
        attachment_type=attachment_type,
        service=service,
        attachment_used=bool(attachment and attachment.attachment_used),
    )
    attachment_text = str(attachment_context.get("extracted_text", ""))

    attachment_adjustment, attachment_reasons = _attachment_score_adjustment(attachment)
    if attachment_adjustment:
        severity_score = max(0, min(100, severity_score + attachment_adjustment))
        severity = _severity_from_score(severity_score)
    log_event(
        "attachment_score_adjusted",
        incident_id=incident_id,
        tenant_id=tenant_id,
        trace_id=trace_id,
        attachment_type=attachment_type,
        severity=severity,
        severity_score=severity_score,
        service=service,
        adjustment=attachment_adjustment,
        adjustment_reasons=attachment_reasons,
    )

    rag_query = f"{description}\n{attachment_text}".strip()
    code_context: list[dict[str, object]] = []
    rag_started_at = time.perf_counter()
    if db is not None:
        try:
            code_context = retrieve_code_context(db, tenant_id=tenant_id, query_text=rag_query)
        except Exception:
            code_context = []
    rag_duration_ms = round((time.perf_counter() - rag_started_at) * 1000, 2)

    context_paths: list[str] = []
    for item in code_context:
        candidate = str(item.get("file_path", "")).strip()
        if candidate and candidate not in context_paths:
            context_paths.append(candidate)
    retrieval_empty = len(code_context) == 0
    log_event(
        "rag_context_retrieved",
        incident_id=incident_id,
        tenant_id=tenant_id,
        trace_id=trace_id,
        attachment_type=attachment_type,
        severity=severity,
        severity_score=severity_score,
        service=service,
        rag_context_count=len(code_context),
        rag_duration_ms=rag_duration_ms,
        retrieval_empty=retrieval_empty,
    )

    context_hint = f" Related code/docs: {', '.join(context_paths[:3])}." if context_paths else ""
    attachment_summary = str(attachment_context.get("summary", "")).strip()
    attachment_evidence = list(attachment_context.get("evidence", []) or [])
    used_attachment_signals = _used_attachment_signals(attachment)
    file_hint = attachment_summary if has_file and attachment_summary else "No attachment provided."
    technical_summary = (
        f"Likely issue detected on {service}. "
        f"Initial severity is {severity}. "
        f"{file_hint}"
        f"{context_hint}"
    )
    triage_summary = technical_summary
    if attachment_evidence:
        triage_summary = f"{technical_summary} Attachment evidence: {' '.join(attachment_evidence[:3])}"

    root_cause_analysis = _infer_rca(description=description, service=service, severity=severity)
    proposed_fix = _infer_fix(service=service)
    proposed_cli_command = _infer_cli(service=service)
    severity_reasoning = severity_rationale
    if attachment_reasons:
        severity_reasoning = (
            f"{severity_rationale} Attachment evidence increased confidence via "
            f"{', '.join(attachment_reasons)}."
        )
    routing_reasoning = _build_routing_reasoning(description=description, service=service, attachment=attachment, context_paths=context_paths)
    attachment_influence_reasoning = _attachment_influence_reasoning(attachment=attachment, adjustment=attachment_adjustment, service=service)
    context_adherence_score = _context_adherence_score(
        description=description,
        attachment=attachment,
        context_paths=context_paths,
    )

    live_llm_enabled = is_model_enabled() or is_two_stage_openrouter_enabled()
    fallback_mode = "multimodal_live_fallback" if live_llm_enabled else "mock_multimodal"
    fallback_used = not live_llm_enabled
    fallback = TriageOutput(
        severity=severity,  # type: ignore[arg-type]
        affected_service=service,
        technical_summary=technical_summary,
        triage_summary=triage_summary,
        retrieved_context_paths=context_paths[:5],
        used_attachment_signals=used_attachment_signals,
        relevant_files=context_paths[:3] or ["app/checkout.py" if service == "checkout-service" else "app/main.py"],
        severity_score=severity_score,
        impact_score=int(severity_factors["impact_score"]),
        scope_score=int(severity_factors["scope_score"]),
        reporter_score=int(severity_factors["reporter_score"]),
        error_code_score=int(severity_factors["error_code_score"]),
        component_score=int(severity_factors["component_score"]),
        severity_rationale=severity_rationale,
        severity_reasoning=severity_reasoning,
        routing_reasoning=routing_reasoning,
        workaround_present=bool(severity_factors["workaround_present"]),
        security_risk=bool(severity_factors["security_risk"]),
        runbook_suggestions=_runbook_suggestions(service=service, severity=severity),
        is_duplicate=False,
        duplicate_of_incident_id=None,
        dedup_confidence=None,
        root_cause_analysis=root_cause_analysis,
        proposed_fix=proposed_fix,
        proposed_cli_command=proposed_cli_command,
        llm_mode=fallback_mode,
        attachment_used=bool(attachment and attachment.attachment_used),
        attachment_type=attachment.attachment_type if attachment else None,
        attachment_text_extracted=attachment.attachment_text_extracted if attachment else "",
        evidence_from_attachment=attachment.evidence_from_attachment if attachment else [],
        attachment_summary=attachment.attachment_summary if attachment else "",
        attachment_influence_reasoning=attachment_influence_reasoning,
        confidence=_triage_confidence(
            attachment=attachment,
            context_paths=context_paths,
            context_adherence_score=context_adherence_score,
            fallback_used=fallback_used,
            llm_used=False,
        ),
        context_adherence_score=context_adherence_score,
        llm_used=False,
        fallback_used=fallback_used,
        retrieval_empty=retrieval_empty,
    )

    if attachment and attachment.attachment_used:
        log_event(
            "attachment_injected_into_triage",
            incident_id=incident_id,
            tenant_id=tenant_id,
            trace_id=trace_id,
            attachment_type=attachment.attachment_type,
            severity=severity,
            severity_score=severity_score,
            service=service,
            rag_context_count=len(code_context),
        )

    llm_duration_ms = 0.0
    log_event(
        "two_stage_triage_attempted",
        incident_id=incident_id,
        tenant_id=tenant_id,
        trace_id=trace_id,
        attachment_type=attachment_type,
        severity=severity,
        severity_score=severity_score,
        service=service,
        rag_context_count=len(code_context),
    )
    two_stage_started_at = time.perf_counter()
    two_stage_output = generate_two_stage_triage(
        description=description,
        attachment_context=attachment_context,
        attachment_filename=attachment_filename,
        attachment_content_type=attachment_content_type,
        attachment_bytes=attachment_bytes,
        code_context=code_context,
    )
    llm_duration_ms += round((time.perf_counter() - two_stage_started_at) * 1000, 2)
    if two_stage_output:
        parsed = _triage_from_model(two_stage_output, fallback=fallback)
        if parsed is not None:
            parsed.llm_used = True
            parsed.fallback_used = False
            parsed.retrieval_empty = retrieval_empty
            parsed.context_adherence_score = max(parsed.context_adherence_score, context_adherence_score)
            parsed.retrieved_context_paths = parsed.retrieved_context_paths or context_paths[:5]
            parsed.used_attachment_signals = parsed.used_attachment_signals or used_attachment_signals
            parsed.confidence = _triage_confidence(
                attachment=attachment,
                context_paths=context_paths,
                context_adherence_score=parsed.context_adherence_score,
                fallback_used=False,
                llm_used=True,
            )
            total_duration_ms = round((time.perf_counter() - triage_started_at) * 1000, 2)
            log_event(
                "two_stage_triage_succeeded",
                incident_id=incident_id,
                tenant_id=tenant_id,
                trace_id=trace_id,
                attachment_type=attachment_type,
                severity=parsed.severity,
                severity_score=parsed.severity_score,
                service=parsed.affected_service,
                rag_context_count=len(code_context),
                llm_duration_ms=llm_duration_ms,
                llm_used=True,
            )
            log_event(
                "triage_completed",
                incident_id=incident_id,
                tenant_id=tenant_id,
                trace_id=trace_id,
                attachment_type=attachment_type,
                severity=parsed.severity,
                severity_score=parsed.severity_score,
                service=parsed.affected_service,
                rag_context_count=len(code_context),
                triage_duration_ms=total_duration_ms,
                rag_duration_ms=rag_duration_ms,
                llm_duration_ms=llm_duration_ms,
                llm_mode=parsed.llm_mode,
                triage_confidence=parsed.confidence,
                context_adherence_score=parsed.context_adherence_score,
                llm_used=True,
                fallback_used=False,
                retrieval_empty=parsed.retrieval_empty,
            )
            return parsed
    log_event(
        "two_stage_triage_failed",
        incident_id=incident_id,
        tenant_id=tenant_id,
        trace_id=trace_id,
        attachment_type=attachment_type,
        severity=severity,
        severity_score=severity_score,
        service=service,
        rag_context_count=len(code_context),
        llm_duration_ms=llm_duration_ms,
    )

    log_event(
        "model_triage_attempted",
        incident_id=incident_id,
        tenant_id=tenant_id,
        trace_id=trace_id,
        attachment_type=attachment_type,
        severity=severity,
        severity_score=severity_score,
        service=service,
        rag_context_count=len(code_context),
    )
    model_started_at = time.perf_counter()
    model_output = generate_model_triage(
        description=description,
        attachment_context=attachment_context,
        code_context=code_context,
    )
    llm_duration_ms += round((time.perf_counter() - model_started_at) * 1000, 2)
    if not model_output:
        return _complete_with_fallback(
            fallback=fallback,
            incident_id=incident_id,
            tenant_id=tenant_id,
            trace_id=trace_id,
            attachment_type=attachment_type,
            service=service,
            code_context=code_context,
            triage_started_at=triage_started_at,
            rag_duration_ms=rag_duration_ms,
            llm_duration_ms=llm_duration_ms,
        )

    parsed = _triage_from_model(model_output, fallback=fallback)
    if parsed is None:
        return _complete_with_fallback(
            fallback=fallback,
            incident_id=incident_id,
            tenant_id=tenant_id,
            trace_id=trace_id,
            attachment_type=attachment_type,
            service=service,
            code_context=code_context,
            triage_started_at=triage_started_at,
            rag_duration_ms=rag_duration_ms,
            llm_duration_ms=llm_duration_ms,
        )

    parsed.llm_used = True
    parsed.fallback_used = False
    parsed.retrieval_empty = retrieval_empty
    parsed.context_adherence_score = max(parsed.context_adherence_score, context_adherence_score)
    parsed.retrieved_context_paths = parsed.retrieved_context_paths or context_paths[:5]
    parsed.used_attachment_signals = parsed.used_attachment_signals or used_attachment_signals
    parsed.confidence = _triage_confidence(
        attachment=attachment,
        context_paths=context_paths,
        context_adherence_score=parsed.context_adherence_score,
        fallback_used=False,
        llm_used=True,
    )
    total_duration_ms = round((time.perf_counter() - triage_started_at) * 1000, 2)
    log_event(
        "model_triage_succeeded",
        incident_id=incident_id,
        tenant_id=tenant_id,
        trace_id=trace_id,
        attachment_type=attachment_type,
        severity=parsed.severity,
        severity_score=parsed.severity_score,
        service=parsed.affected_service,
        rag_context_count=len(code_context),
        llm_duration_ms=llm_duration_ms,
        llm_used=True,
    )
    log_event(
        "triage_completed",
        incident_id=incident_id,
        tenant_id=tenant_id,
        trace_id=trace_id,
        attachment_type=attachment_type,
        severity=parsed.severity,
        severity_score=parsed.severity_score,
        service=parsed.affected_service,
        rag_context_count=len(code_context),
        triage_duration_ms=total_duration_ms,
        rag_duration_ms=rag_duration_ms,
        llm_duration_ms=llm_duration_ms,
        llm_mode=parsed.llm_mode,
        triage_confidence=parsed.confidence,
        context_adherence_score=parsed.context_adherence_score,
        llm_used=True,
        fallback_used=False,
        retrieval_empty=parsed.retrieval_empty,
    )
    return parsed


def create_incident_id() -> str:
    return uuid.uuid4().hex[:12]


def _triage_from_model(payload: dict[str, object], fallback: TriageOutput) -> TriageOutput | None:
    try:
        severity = _coerce_severity(payload.get("severity"), fallback.severity)
        affected_service = _coerce_text(payload.get("affected_service"), fallback.affected_service)
        technical_summary = _coerce_text(payload.get("technical_summary"), fallback.technical_summary)
        triage_summary = _coerce_text(payload.get("triage_summary"), fallback.triage_summary or fallback.technical_summary)
        retrieved_context_paths = _coerce_string_list(payload.get("retrieved_context_paths"), fallback.retrieved_context_paths)
        used_attachment_signals = _coerce_string_list(payload.get("used_attachment_signals"), fallback.used_attachment_signals)
        relevant_files = _coerce_string_list(payload.get("relevant_files"), fallback.relevant_files)
        severity_score = _coerce_int(payload.get("severity_score"), fallback.severity_score, minimum=0, maximum=100)
        impact_score = _coerce_int(payload.get("impact_score"), fallback.impact_score, minimum=0, maximum=30)
        scope_score = _coerce_int(payload.get("scope_score"), fallback.scope_score, minimum=0, maximum=20)
        reporter_score = _coerce_int(payload.get("reporter_score"), fallback.reporter_score, minimum=0, maximum=10)
        error_code_score = _coerce_int(payload.get("error_code_score"), fallback.error_code_score, minimum=0, maximum=20)
        component_score = _coerce_int(payload.get("component_score"), fallback.component_score, minimum=0, maximum=20)
        severity_rationale = _coerce_text(payload.get("severity_rationale"), fallback.severity_rationale)
        severity_reasoning = _coerce_text(payload.get("severity_reasoning"), fallback.severity_reasoning)
        routing_reasoning = _coerce_text(payload.get("routing_reasoning"), fallback.routing_reasoning)
        workaround_present = _coerce_bool(payload.get("workaround_present"), fallback.workaround_present)
        security_risk = _coerce_bool(payload.get("security_risk"), fallback.security_risk)
        runbook_suggestions = _coerce_string_list(payload.get("runbook_suggestions"), fallback.runbook_suggestions)
        root_cause_analysis = _coerce_text(payload.get("root_cause_analysis"), fallback.root_cause_analysis)
        proposed_fix = _coerce_text(payload.get("proposed_fix"), fallback.proposed_fix)
        proposed_cli_command = _coerce_text(payload.get("proposed_cli_command"), fallback.proposed_cli_command)
        llm_mode = _coerce_text(payload.get("llm_mode"), "multimodal_live")
        attachment_influence_reasoning = _coerce_text(
            payload.get("attachment_influence_reasoning"),
            fallback.attachment_influence_reasoning,
        )
        confidence = _coerce_float(payload.get("confidence"), fallback.confidence, minimum=0.0, maximum=1.0)
        return TriageOutput(
            severity=severity,  # type: ignore[arg-type]
            affected_service=affected_service,
            technical_summary=technical_summary,
            triage_summary=triage_summary,
            retrieved_context_paths=retrieved_context_paths,
            used_attachment_signals=used_attachment_signals,
            relevant_files=relevant_files,
            severity_score=severity_score,
            impact_score=impact_score,
            scope_score=scope_score,
            reporter_score=reporter_score,
            error_code_score=error_code_score,
            component_score=component_score,
            severity_rationale=severity_rationale,
            severity_reasoning=severity_reasoning,
            routing_reasoning=routing_reasoning,
            workaround_present=workaround_present,
            security_risk=security_risk,
            runbook_suggestions=runbook_suggestions,
            is_duplicate=False,
            duplicate_of_incident_id=None,
            dedup_confidence=None,
            root_cause_analysis=root_cause_analysis,
            proposed_fix=proposed_fix,
            proposed_cli_command=proposed_cli_command,
            llm_mode=llm_mode,
            attachment_used=fallback.attachment_used,
            attachment_type=fallback.attachment_type,
            attachment_text_extracted=fallback.attachment_text_extracted,
            evidence_from_attachment=fallback.evidence_from_attachment,
            attachment_summary=fallback.attachment_summary,
            attachment_influence_reasoning=attachment_influence_reasoning,
            confidence=confidence,
            context_adherence_score=_coerce_float(
                payload.get("context_adherence_score"),
                fallback.context_adherence_score,
                minimum=0.0,
                maximum=1.0,
            ),
            llm_used=_coerce_bool(payload.get("llm_used"), True),
            fallback_used=_coerce_bool(payload.get("fallback_used"), False),
            retrieval_empty=_coerce_bool(payload.get("retrieval_empty"), fallback.retrieval_empty),
        )
    except Exception:
        return None


def _coerce_severity(value: object, fallback: str) -> str:
    normalized = str(value or "").strip().lower()
    return normalized if normalized in {"low", "medium", "high", "critical"} else fallback


def _coerce_text(value: object, fallback: str) -> str:
    if isinstance(value, str):
        cleaned = value.strip()
        if cleaned:
            return cleaned
    return fallback


def _coerce_string_list(value: object, fallback: list[str]) -> list[str]:
    if isinstance(value, list):
        cleaned = [str(item).strip() for item in value if str(item).strip()]
        if cleaned:
            return cleaned
    return fallback


def _coerce_int(value: object, fallback: int, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value)  # type: ignore[arg-type]
    except Exception:
        return fallback
    return max(minimum, min(parsed, maximum))


def _coerce_float(value: object, fallback: float, minimum: float, maximum: float) -> float:
    try:
        parsed = float(value)  # type: ignore[arg-type]
    except Exception:
        return fallback
    return max(minimum, min(parsed, maximum))


def _coerce_bool(value: object, fallback: bool) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"true", "1", "yes", "on"}:
            return True
        if lowered in {"false", "0", "no", "off"}:
            return False
    return fallback


def create_ticket(incident_id: str, triage: TriageOutput, tenant_id: str = "", description: str = "") -> TicketRecord:
    validate_tool_name("create_ticket")
    ticket_summary = _ticket_summary(description=description, triage=triage)
    ticket_description = _ticket_description(incident_id=incident_id, tenant_id=tenant_id, description=description, triage=triage)

    if is_react_mcp_enabled():
        try:
            ticket = create_ticket_via_react(
                incident_id=incident_id,
                tenant_id=tenant_id,
                description=ticket_description,
                triage=triage,
            )
            ticket.title = ticket.title or ticket_summary
            ticket.description = ticket.description or ticket_description
            log_event("ticket_created", incident_id=incident_id, ticket_id=ticket.ticket_id, severity=triage.severity)
            return ticket
        except RuntimeError as exc:
            log_event("react_ticket_failed", incident_id=incident_id, error=str(exc))

    provider = os.getenv("TICKETING_PROVIDER", "mock-jira")
    fallback_provider = os.getenv("TICKETING_FALLBACK_PROVIDER", "mock-linear")

    def _attempt(prov: str, fail_flag: str) -> TicketRecord:
        if prov == "jira":
            return create_jira_ticket(
                incident_id=incident_id,
                summary=ticket_summary,
                description=ticket_description,
                severity=triage.severity,
                affected_service=triage.affected_service,
                rca=triage.root_cause_analysis,
                proposed_fix=triage.proposed_fix,
                cli_command=triage.proposed_cli_command,
                tenant_id=tenant_id,
            )
        return _create_ticket_with_provider(
            incident_id=incident_id,
            provider=prov,
            fail_flag=fail_flag,
            summary=ticket_summary,
            description=ticket_description,
        )

    try:
        ticket = _attempt(provider, "FORCE_FAIL_PRIMARY_TICKETING")
    except RuntimeError:
        log_event("integration_fallback", incident_id=incident_id, integration="ticketing", fallback_provider=fallback_provider)
        ticket = _attempt(fallback_provider, "FORCE_FAIL_FALLBACK_TICKETING")

    log_event("ticket_created", incident_id=incident_id, ticket_id=ticket.ticket_id, severity=triage.severity)
    return ticket


def notify_team(
    incident_id: str,
    ticket: TicketRecord,
    triage: TriageOutput,
    tenant_id: str = "",
    reporter_email: str = "",
    description: str = "",
) -> NotificationRecord:
    validate_tool_name("notify_team")
    notify_description = _ticket_description(incident_id=incident_id, tenant_id=tenant_id, description=description, triage=triage)

    if is_react_mcp_enabled():
        try:
            detail = notify_team_via_react(
                incident_id=incident_id,
                tenant_id=tenant_id,
                reporter_email=reporter_email,
                description=notify_description,
                triage=triage,
                ticket=ticket,
            )
            event = NotificationRecord(channel="team_communicator", status="sent", detail=detail)
            log_event("team_notified", incident_id=incident_id, ticket_id=ticket.ticket_id)
            return event
        except RuntimeError as exc:
            log_event("react_notify_failed", incident_id=incident_id, error=str(exc))

    provider = os.getenv("COMMUNICATOR_PROVIDER", "mock-slack")
    fallback_provider = os.getenv("COMMUNICATOR_FALLBACK_PROVIDER", "mock-teams")

    def _attempt(prov: str, fail_flag: str) -> str:
        if prov == "slack":
            return notify_slack(
                incident_id=incident_id,
                tenant_id=tenant_id,
                ticket=ticket,
                triage=triage,
                reporter_email=reporter_email,
            )
        return _notify_team_with_provider(prov, ticket, triage, fail_flag=fail_flag)

    try:
        detail = _attempt(provider, "FORCE_FAIL_PRIMARY_COMMUNICATOR")
    except RuntimeError:
        log_event("integration_fallback", incident_id=incident_id, integration="team_communicator", fallback_provider=fallback_provider)
        detail = _attempt(fallback_provider, "FORCE_FAIL_FALLBACK_COMMUNICATOR")

    event = NotificationRecord(channel="team_communicator", status="sent", detail=detail)
    log_event("team_notified", incident_id=incident_id, ticket_id=ticket.ticket_id)
    return event


def notify_reporter(incident_id: str, reporter_email: str) -> NotificationRecord:
    validate_tool_name("notify_reporter")
    provider = os.getenv("EMAIL_PROVIDER", "mock-email")
    fallback_provider = os.getenv("EMAIL_FALLBACK_PROVIDER", "mock-ses")
    try:
        detail = _notify_reporter_with_provider(provider, reporter_email, fail_flag="FORCE_FAIL_PRIMARY_EMAIL")
    except RuntimeError:
        log_event("integration_fallback", incident_id=incident_id, integration="reporter_email", fallback_provider=fallback_provider)
        detail = _notify_reporter_with_provider(fallback_provider, reporter_email, fail_flag="FORCE_FAIL_FALLBACK_EMAIL")
    event = NotificationRecord(channel="reporter_email", status="sent", detail=detail)
    log_event("reporter_notified", incident_id=incident_id, reporter_email=reporter_email)
    return event


def save_incident(db: Session, record: IncidentRecord) -> IncidentRecord:
    result = repo.save_incident(db, record)
    repo.write_audit_log(
        db,
        stage="incident_saved",
        tenant_id=record.tenant_id,
        incident_id=record.incident_id,
        payload={"severity": record.triage.severity, "service": record.triage.affected_service},
    )
    return result


def get_incident(db: Session, incident_id: str) -> IncidentRecord | None:
    return repo.get_incident(db, incident_id)


def list_incidents(db: Session, tenant_id: str | None = None) -> list[IncidentRecord]:
    return repo.list_incidents(db, tenant_id=tenant_id)


def find_duplicate_incident(db: Session, tenant_id: str, description: str) -> IncidentRecord | None:
    return repo.find_open_duplicate_incident(db, tenant_id=tenant_id, description=description)


def resolve_incident(db: Session, incident_id: str) -> IncidentRecord | None:
    record = repo.get_incident(db, incident_id)
    if not record:
        return None

    reporter_event = notify_reporter(incident_id, str(record.reporter_email))
    updated = repo.resolve_incident(db, incident_id, extra_notification=reporter_event)
    if updated:
        repo.write_audit_log(db, stage="incident_resolved", tenant_id=updated.tenant_id, incident_id=incident_id)
        log_event("incident_resolved", incident_id=incident_id)

        communicator = os.getenv("COMMUNICATOR_PROVIDER", "mock-slack")
        if communicator == "slack":
            try:
                notify_slack_resolved(
                    incident_id=incident_id,
                    tenant_id=updated.tenant_id,
                    ticket=updated.ticket,
                    reporter_email=str(updated.reporter_email),
                )
            except RuntimeError as exc:
                log_event("slack_resolved_skipped", incident_id=incident_id, error=str(exc))
    return updated


def get_tenant(db: Session, tenant_id: str) -> TenantRecord | None:
    return repo.get_tenant(db, tenant_id)


def register_tenant(db: Session, tenant_id: str, name: str) -> TenantRecord:
    tenant = repo.upsert_tenant(db, tenant_id, name)
    repo.write_audit_log(db, stage="tenant_registered", tenant_id=tenant_id)
    log_event("tenant_registered", tenant_id=tenant_id)
    return tenant


def ensure_tenant(db: Session, tenant_id: str) -> TenantRecord:
    existing = repo.get_tenant(db, tenant_id)
    if existing:
        return existing
    return register_tenant(db, tenant_id=tenant_id, name=f"Tenant {tenant_id}")


def tenant_dashboard(db: Session, tenant_id: str) -> TenantDashboard:
    return repo.tenant_dashboard(db, tenant_id)


def _infer_rca(description: str, service: str, severity: str) -> str:
    text = description.lower()
    if service == "checkout-service":
        if "coupon" in text:
            return "Coupon validation path likely causing unhandled exception in checkout flow."
        return "Payment workflow dependency likely failing and surfacing a 5xx error."
    if service == "auth-service":
        return "Authentication/session token validation may be rejecting valid user states."
    if service == "catalog-service":
        return "Catalog query or cache invalidation likely causing stale or failing product reads."
    if severity in {"high", "critical"}:
        return "High-impact issue likely tied to a backend dependency or runtime exception."
    return "Issue appears localized and may come from input validation or UI/backend contract mismatch."


def _infer_fix(service: str) -> str:
    if service == "checkout-service":
        return "Add defensive null checks around coupon parsing and return controlled 4xx for invalid coupon payloads."
    if service == "auth-service":
        return "Harden token validation and add explicit handling for expired/invalid refresh token branches."
    if service == "catalog-service":
        return "Add timeout + fallback on catalog provider and ensure cache key consistency."
    return "Add stricter request validation and structured exception handling in entrypoint handler."


def _infer_cli(service: str) -> str:
    if service == "checkout-service":
        return "pytest tests/test_checkout.py -k coupon"
    if service == "auth-service":
        return "pytest tests/test_auth.py -k token"
    if service == "catalog-service":
        return "pytest tests/test_catalog.py -k cache"
    return "pytest -k incident_hotfix"


def _runbook_suggestions(service: str, severity: str) -> list[str]:
    base = [
        "Confirm incident scope and affected tenant/user cohort.",
        "Validate recent deployments/config changes in the affected service.",
    ]
    if service == "checkout-service":
        base.extend(
            [
                "Check payment gateway connectivity and error rate.",
                "Verify coupon parsing/validation branch for null/invalid payload handling.",
            ]
        )
    elif service == "auth-service":
        base.extend(
            [
                "Inspect auth token refresh logs and expiration handling.",
                "Validate identity provider latency and timeout budget.",
            ]
        )
    elif service == "catalog-service":
        base.extend(
            [
                "Inspect cache hit ratio and stale key invalidation flow.",
                "Check upstream catalog provider latency and fallback behavior.",
            ]
        )
    else:
        base.append("Review API gateway logs and request validation failures.")

    if severity in {"high", "critical"}:
        base.append("Escalate to on-call and start incident timeline tracking.")
    return base


def _infer_service_with_attachment(description: str, attachment: AttachmentRecord | None) -> str:
    inferred = infer_service(description)
    if attachment is None:
        return inferred
    candidate = str(attachment.attachment_signals.get("suspected_service_from_attachment") or "").strip()
    if not candidate:
        return inferred

    attachment_text = " ".join(
        [
            attachment.attachment_summary or "",
            attachment.attachment_text_extracted or "",
            " ".join(str(item) for item in attachment.evidence_from_attachment),
        ]
    ).lower()
    description_text = description.lower()
    corroborated = candidate.replace("-service", "").split("-")[0] in description_text
    corroborated = corroborated or candidate.replace("-service", "").split("-")[0] in attachment_text
    error_signals = len(attachment.attachment_signals.get("error_codes_found", []))
    severity_hints = len(attachment.attachment_signals.get("severity_hints", []))
    if attachment.attachment_used and (corroborated or error_signals >= 2 or severity_hints >= 2):
        return candidate
    return inferred


def _attachment_score_adjustment(attachment: AttachmentRecord | None) -> tuple[int, list[str]]:
    if attachment is None:
        return 0, []
    signals = attachment.attachment_signals or {}
    reasons: list[str] = []
    adjustment = 0
    error_codes = [str(item).lower() for item in signals.get("error_codes_found", [])]
    severity_hints = [str(item).lower() for item in signals.get("severity_hints", [])]
    if any(code.startswith("5") or "timeout" in code for code in error_codes):
        adjustment += 12
        reasons.append("error_signals")
    if "critical" in severity_hints:
        adjustment += 15
        reasons.append("critical_hint")
    elif "high" in severity_hints:
        adjustment += 8
        reasons.append("high_hint")
    if attachment.attachment_used:
        adjustment += 4
        reasons.append("attachment_evidence")
    return adjustment, reasons


def _severity_from_score(score: int) -> str:
    if score >= 80:
        return "critical"
    if score >= 60:
        return "high"
    if score >= 35:
        return "medium"
    return "low"


def _attachment_influence_reasoning(attachment: AttachmentRecord | None, adjustment: int, service: str) -> str:
    if attachment is None:
        return "No attachment was used."
    if not attachment.attachment_used:
        return f"Attachment stored as {attachment.attachment_type}, but it did not provide strong evidence."
    parts = [f"Attachment evidence from {attachment.attachment_type} was incorporated into triage."]
    if adjustment > 0:
        parts.append(f"It increased the severity score by {adjustment} points.")
    if attachment.attachment_signals.get("suspected_service_from_attachment"):
        parts.append(f"It reinforced routing toward {service}.")
    return " ".join(parts)


def _build_routing_reasoning(
    *,
    description: str,
    service: str,
    attachment: AttachmentRecord | None,
    context_paths: list[str],
) -> str:
    parts = [f"Report text routed the incident to {service}."]
    if attachment and attachment.attachment_signals.get("suspected_service_from_attachment"):
        parts.append(f"Attachment signals corroborated {service}.")
    if context_paths:
        parts.append(f"RAG matched {', '.join(context_paths[:2])}.")
    return " ".join(parts)


def _triage_confidence(
    *,
    attachment: AttachmentRecord | None,
    context_paths: list[str],
    context_adherence_score: float,
    fallback_used: bool,
    llm_used: bool,
) -> float:
    confidence = 0.4
    if attachment and attachment.attachment_used:
        confidence += 0.12
        signal_count = len(attachment.evidence_from_attachment) + len(attachment.attachment_signals.get("error_codes_found", []))
        if signal_count >= 2:
            confidence += 0.08
        if attachment.extraction_method in {"decode_text", "ocr_tesseract", "pdf_extract"}:
            confidence += 0.05
    if context_paths:
        confidence += min(0.15, 0.05 * len(context_paths))
    confidence += context_adherence_score * 0.18
    if llm_used:
        confidence += 0.06
    if fallback_used:
        confidence -= 0.08
    return round(min(confidence, 0.95), 2)


def _calculate_severity_factors(description: str, attachment: AttachmentRecord | None) -> dict[str, object]:
    text = description.lower()
    attachment_text = " ".join(
        [
            attachment.attachment_summary if attachment else "",
            attachment.attachment_text_extracted if attachment else "",
            " ".join(attachment.evidence_from_attachment) if attachment else "",
        ]
    ).lower()
    combined = f"{text} {attachment_text}".strip()

    impact_score = 0
    if any(token in combined for token in ("outage", "down", "cannot pay", "payment failed", "internal server error")):
        impact_score += 25
    elif any(token in combined for token in ("failed", "error", "timeout", "500")):
        impact_score += 16
    elif any(token in combined for token in ("degraded", "slow", "latency")):
        impact_score += 8

    scope_score = 0
    if any(token in combined for token in ("all users", "all tenants", "sitewide", "everyone", "global")):
        scope_score += 18
    elif any(token in combined for token in ("many users", "multiple users", "checkout users")):
        scope_score += 10
    elif any(token in combined for token in ("single user", "one user")):
        scope_score += 4

    workaround_present = any(token in combined for token in ("workaround", "temporary fix", "retry works", "manual refresh"))
    security_risk = any(token in combined for token in ("auth bypass", "data leak", "security", "token exposed", "unauthorized"))

    reporter_score = 0
    if any(token in combined for token in ("vip", "merchant", "on-call", "support escalation", "executive")):
        reporter_score += 6

    error_code_score = 0
    if any(token in combined for token in ("500", "502", "503", "504", "timeout")):
        error_code_score += 12
    elif any(token in combined for token in ("401", "403", "404")):
        error_code_score += 6

    component_score = 0
    if any(token in combined for token in ("checkout", "payment", "auth", "login", "catalog")):
        component_score += 8
    if attachment and attachment.attachment_used:
        component_score += 4

    return {
        "impact_score": impact_score,
        "scope_score": scope_score,
        "reporter_score": reporter_score,
        "error_code_score": error_code_score,
        "component_score": component_score,
        "workaround_present": workaround_present,
        "security_risk": security_risk,
    }


def _used_attachment_signals(attachment: AttachmentRecord | None) -> list[str]:
    if attachment is None:
        return []
    signals = attachment.attachment_signals or {}
    used: list[str] = []
    candidate = signals.get("suspected_service_from_attachment")
    if candidate:
        used.append(f"suspected_service:{candidate}")
    for code in signals.get("error_codes_found", [])[:4]:
        used.append(f"error_code:{code}")
    for hint in signals.get("severity_hints", [])[:3]:
        used.append(f"severity_hint:{hint}")
    if attachment.extraction_method:
        used.append(f"extraction_method:{attachment.extraction_method}")
    return used


def _context_adherence_score(
    *,
    description: str,
    attachment: AttachmentRecord | None,
    context_paths: list[str],
) -> float:
    score = 0.2
    if context_paths:
        score += min(0.35, 0.1 * len(context_paths))
    text = description.lower()
    if attachment and attachment.attachment_used:
        score += 0.15
        if attachment.attachment_signals.get("suspected_service_from_attachment"):
            score += 0.1
    if any(token in text for token in ("checkout", "payment")) and any("checkout" in path.lower() for path in context_paths):
        score += 0.15
    if any(token in text for token in ("auth", "login")) and any("auth" in path.lower() for path in context_paths):
        score += 0.15
    if any(token in text for token in ("catalog", "product")) and any("catalog" in path.lower() for path in context_paths):
        score += 0.15
    return round(min(score, 1.0), 2)


def _complete_with_fallback(
    *,
    fallback: TriageOutput,
    incident_id: str | None,
    tenant_id: str | None,
    trace_id: str,
    attachment_type: str,
    service: str,
    code_context: list[dict[str, object]],
    triage_started_at: float,
    rag_duration_ms: float,
    llm_duration_ms: float,
) -> TriageOutput:
    total_duration_ms = round((time.perf_counter() - triage_started_at) * 1000, 2)
    log_event(
        "model_triage_failed",
        incident_id=incident_id,
        tenant_id=tenant_id,
        trace_id=trace_id,
        attachment_type=attachment_type,
        severity=fallback.severity,
        severity_score=fallback.severity_score,
        service=service,
        rag_context_count=len(code_context),
        llm_duration_ms=llm_duration_ms,
    )
    log_event(
        "fallback_triage_used",
        incident_id=incident_id,
        tenant_id=tenant_id,
        trace_id=trace_id,
        attachment_type=attachment_type,
        severity=fallback.severity,
        severity_score=fallback.severity_score,
        service=fallback.affected_service,
        rag_context_count=len(code_context),
        fallback_used=True,
    )
    log_event(
        "triage_completed",
        incident_id=incident_id,
        tenant_id=tenant_id,
        trace_id=trace_id,
        attachment_type=attachment_type,
        severity=fallback.severity,
        severity_score=fallback.severity_score,
        service=fallback.affected_service,
        rag_context_count=len(code_context),
        triage_duration_ms=total_duration_ms,
        rag_duration_ms=rag_duration_ms,
        llm_duration_ms=llm_duration_ms,
        llm_mode=fallback.llm_mode,
        triage_confidence=fallback.confidence,
        context_adherence_score=fallback.context_adherence_score,
        llm_used=fallback.llm_used,
        fallback_used=True,
        retrieval_empty=fallback.retrieval_empty,
    )
    return fallback


def _ticket_summary(*, description: str, triage: TriageOutput) -> str:
    base = description[:120] or triage.technical_summary[:120]
    if triage.attachment_used and triage.attachment_type:
        return f"{base} [attachment:{triage.attachment_type}]"
    return base


def _ticket_description(*, incident_id: str, tenant_id: str, description: str, triage: TriageOutput) -> str:
    lines = [
        f"Incident ID: {incident_id}",
        f"Tenant: {tenant_id or 'unknown'}",
        "",
        "Original description:",
        description or triage.technical_summary,
        "",
        f"Triage summary: {triage.triage_summary or triage.technical_summary}",
        f"Severity reasoning: {triage.severity_reasoning}",
        f"Routing reasoning: {triage.routing_reasoning}",
        f"Confidence: {triage.confidence}",
    ]
    if triage.retrieved_context_paths:
        lines.append(f"Retrieved context paths: {', '.join(triage.retrieved_context_paths[:4])}")
    if triage.used_attachment_signals:
        lines.append(f"Used attachment signals: {', '.join(triage.used_attachment_signals[:6])}")
    if triage.attachment_type:
        lines.extend(
            [
                "",
                f"Attachment evidence: {triage.attachment_summary}",
                f"Attachment influence: {triage.attachment_influence_reasoning}",
            ]
        )
        if triage.evidence_from_attachment:
            lines.append(f"Attachment findings: {' | '.join(triage.evidence_from_attachment[:4])}")
    return "\n".join(lines)


def _integration_retries() -> int:
    value = os.getenv("INTEGRATION_RETRIES", "2")
    try:
        return max(int(value), 1)
    except ValueError:
        return 2


def _integration_retry_delay() -> float:
    value = os.getenv("INTEGRATION_RETRY_DELAY_MS", "150")
    try:
        return max(int(value), 0) / 1000
    except ValueError:
        return 0.15


def _bool_env(name: str, default: bool = False) -> bool:
    raw = os.getenv(name, "true" if default else "false")
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _should_fail_once(flag_name: str) -> bool:
    if not _bool_env(flag_name, default=False):
        return False
    current = FAIL_COUNTS.get(flag_name, 0)
    if current == 0:
        FAIL_COUNTS[flag_name] = 1
        return True
    return False


def _with_retry(action: str, func):
    retries = _integration_retries()
    delay = _integration_retry_delay()
    last_error: RuntimeError | None = None
    for attempt in range(1, retries + 1):
        try:
            return func()
        except RuntimeError as exc:
            last_error = exc
            log_event("integration_retry", integration=action, attempt=attempt, error=str(exc))
            if attempt < retries and delay > 0:
                time.sleep(delay)
    if last_error is None:
        raise RuntimeError(f"integration '{action}' failed without explicit error")
    raise last_error


def _create_ticket_with_provider(
    incident_id: str,
    provider: str,
    fail_flag: str,
    summary: str,
    description: str,
) -> TicketRecord:
    def action() -> TicketRecord:
        if _should_fail_once(fail_flag):
            raise RuntimeError(f"{provider} temporary outage")
        ticket_id = f"AURA-{incident_id[-6:].upper()}"
        if provider == "mock-linear":
            ticket_id = f"LIN-{incident_id[-6:].upper()}"
        return TicketRecord(
            ticket_id=ticket_id,
            provider=provider,
            url=f"https://{provider}.mock.local/browse/{ticket_id}",
            status="created",
            title=summary,
            description=description,
        )

    return _with_retry(f"ticketing:{provider}", action)


def _notify_team_with_provider(provider: str, ticket: TicketRecord, triage: TriageOutput, fail_flag: str) -> str:
    def action() -> str:
        if _should_fail_once(fail_flag):
            raise RuntimeError(f"{provider} temporary outage")
        evidence = f" Attachment={triage.attachment_summary}." if triage.attachment_used and triage.attachment_summary else ""
        return (
            f"Team notified on {provider}. Ticket={ticket.ticket_id}, "
            f"service={triage.affected_service}, severity={triage.severity}.{evidence}"
        )

    return _with_retry(f"team_notify:{provider}", action)


def _notify_reporter_with_provider(provider: str, reporter_email: str, fail_flag: str) -> str:
    def action() -> str:
        if _should_fail_once(fail_flag):
            raise RuntimeError(f"{provider} temporary outage")
        return f"Reporter {reporter_email} notified by {provider}."

    return _with_retry(f"reporter_notify:{provider}", action)
