"""
services.py – Business-logic layer for AURA.

State is no longer held in memory.  Every mutating function receives a
SQLAlchemy Session and delegates persistence to repository.py.

Public API is unchanged so that main.py requires minimal edits:
  create_incident_id, run_triage, create_ticket, notify_team,
  notify_reporter, save_incident, get_incident, list_incidents,
  resolve_incident, get_tenant, register_tenant, ensure_tenant,
  tenant_dashboard
"""
from __future__ import annotations

import os
import time
import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from . import repository as repo
from .guardrails import validate_tool_name
from .integrations.jira import create_jira_ticket
from .integrations.llm import (
    build_attachment_context,
    generate_model_triage,
    generate_two_stage_triage,
    is_model_enabled,
    is_two_stage_openrouter_enabled,
)
from .integrations.slack import notify_slack, notify_slack_resolved
from .models import (
    IncidentRecord,
    NotificationRecord,
    TenantRecord,
    TenantDashboard,
    TicketRecord,
    TriageOutput,
)
from .observability import log_event
from .rag import retrieve_code_context
from .react_orchestrator import create_ticket_via_react, is_react_mcp_enabled, notify_team_via_react

# ---------------------------------------------------------------------------
# FAIL_COUNTS stays in-memory intentionally – it tracks transient retry state
# for the current process and does not need cross-process durability.
# ---------------------------------------------------------------------------
FAIL_COUNTS: dict[str, int] = {}


# ──────────────────────────────────────────────────────────────
# Pure helpers (no I/O)
# ──────────────────────────────────────────────────────────────

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


def calculate_severity(description: str, has_file: bool) -> tuple[str, int, str]:
    text = description.lower()
    score = 10
    reasons: list[str] = []

    weighted_tokens = {
        "outage": 55,
        "down": 50,
        "500": 45,
        "critical": 45,
        "payment": 20,
        "checkout": 18,
        "failed": 20,
        "error": 15,
        "timeout": 15,
        "login": 12,
        "auth": 12,
        "degraded": 10,
        "slow": 8,
    }

    for token, weight in weighted_tokens.items():
        if token in text:
            score += weight
            reasons.append(token)

    if has_file:
        score += 5
        reasons.append("attachment")

    score = max(0, min(score, 100))
    if score >= 80:
        severity = "critical"
    elif score >= 60:
        severity = "high"
    elif score >= 35:
        severity = "medium"
    else:
        severity = "low"

    rationale = (
        f"Severity score {score}/100 based on detected signals: {', '.join(reasons)}."
        if reasons
        else f"Severity score {score}/100 with low-impact signals."
    )
    return severity, score, rationale


def run_triage(
    tenant_id: str | None,
    description: str,
    has_file: bool,
    attachment_filename: str | None = None,
    attachment_content_type: str | None = None,
    attachment_bytes: bytes | None = None,
    db: Session | None = None,
) -> TriageOutput:
    severity, severity_score, severity_rationale = calculate_severity(description=description, has_file=has_file)
    service = infer_service(description)
    attachment_context = build_attachment_context(
        filename=attachment_filename,
        content_type=attachment_content_type,
        content_bytes=attachment_bytes,
    )
    attachment_text = str(attachment_context.get("extracted_text", ""))
    rag_query = f"{description}\n{attachment_text}".strip()
    code_context: list[dict[str, object]] = []
    if db is not None:
        try:
            code_context = retrieve_code_context(db, tenant_id=tenant_id, query_text=rag_query)
        except Exception:
            code_context = []

    context_paths: list[str] = []
    for item in code_context:
        candidate = str(item.get("file_path", "")).strip()
        if candidate and candidate not in context_paths:
            context_paths.append(candidate)
    context_hint = (
        f" Related code/docs: {', '.join(context_paths[:3])}."
        if context_paths
        else ""
    )

    attachment_summary = str(attachment_context.get("summary", "")).strip()
    file_hint = attachment_summary if has_file and attachment_summary else "No attachment provided."
    summary = (
        f"Likely issue detected on {service}. "
        f"Initial severity is {severity}. "
        f"{file_hint}"
        f"{context_hint}"
    )
    root_cause_analysis = _infer_rca(description=description, service=service, severity=severity)
    proposed_fix = _infer_fix(service=service)
    proposed_cli_command = _infer_cli(service=service)
    live_llm_enabled = is_model_enabled() or is_two_stage_openrouter_enabled()
    fallback_mode = "multimodal_live_fallback" if live_llm_enabled else "mock_multimodal"
    fallback = TriageOutput(
        severity=severity,  # type: ignore[arg-type]
        affected_service=service,
        technical_summary=summary,
        relevant_files=context_paths[:3] or ["app/checkout.py" if service == "checkout-service" else "app/main.py"],
        severity_score=severity_score,
        severity_rationale=severity_rationale,
        runbook_suggestions=_runbook_suggestions(service=service, severity=severity),
        is_duplicate=False,
        duplicate_of_incident_id=None,
        dedup_confidence=None,
        root_cause_analysis=root_cause_analysis,
        proposed_fix=proposed_fix,
        proposed_cli_command=proposed_cli_command,
        llm_mode=fallback_mode,
    )

    two_stage_output = generate_two_stage_triage(
        description=description,
        attachment_context=attachment_context,
        attachment_filename=attachment_filename,
        attachment_content_type=attachment_content_type,
        attachment_bytes=attachment_bytes,
        code_context=code_context,
    )
    if two_stage_output:
        parsed = _triage_from_model(two_stage_output, fallback=fallback)
        if parsed is not None:
            return parsed

    model_output = generate_model_triage(
        description=description,
        attachment_context=attachment_context,
        code_context=code_context,
    )
    if not model_output:
        return fallback

    parsed = _triage_from_model(model_output, fallback=fallback)
    if parsed is None:
        return fallback
    return parsed


def create_incident_id() -> str:
    return uuid.uuid4().hex[:12]


def _triage_from_model(payload: dict[str, object], fallback: TriageOutput) -> TriageOutput | None:
    try:
        severity = _coerce_severity(payload.get("severity"), fallback.severity)
        affected_service = _coerce_text(payload.get("affected_service"), fallback.affected_service)
        technical_summary = _coerce_text(payload.get("technical_summary"), fallback.technical_summary)
        relevant_files = _coerce_string_list(payload.get("relevant_files"), fallback.relevant_files)
        severity_score = _coerce_int(payload.get("severity_score"), fallback.severity_score, minimum=0, maximum=100)
        severity_rationale = _coerce_text(payload.get("severity_rationale"), fallback.severity_rationale)
        runbook_suggestions = _coerce_string_list(payload.get("runbook_suggestions"), fallback.runbook_suggestions)
        root_cause_analysis = _coerce_text(payload.get("root_cause_analysis"), fallback.root_cause_analysis)
        proposed_fix = _coerce_text(payload.get("proposed_fix"), fallback.proposed_fix)
        proposed_cli_command = _coerce_text(payload.get("proposed_cli_command"), fallback.proposed_cli_command)
        llm_mode = _coerce_text(payload.get("llm_mode"), "multimodal_live")
        return TriageOutput(
            severity=severity,  # type: ignore[arg-type]
            affected_service=affected_service,
            technical_summary=technical_summary,
            relevant_files=relevant_files,
            severity_score=severity_score,
            severity_rationale=severity_rationale,
            runbook_suggestions=runbook_suggestions,
            is_duplicate=False,
            duplicate_of_incident_id=None,
            dedup_confidence=None,
            root_cause_analysis=root_cause_analysis,
            proposed_fix=proposed_fix,
            proposed_cli_command=proposed_cli_command,
            llm_mode=llm_mode,
        )
    except Exception:
        return None


def _coerce_severity(value: object, fallback: str) -> str:
    normalized = str(value or "").strip().lower()
    if normalized in {"low", "medium", "high", "critical"}:
        return normalized
    return fallback


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


# ──────────────────────────────────────────────────────────────
# Integration helpers (ticket / notify) — unchanged logic
# ──────────────────────────────────────────────────────────────

def create_ticket(incident_id: str, triage: TriageOutput, tenant_id: str = "", description: str = "") -> TicketRecord:
    validate_tool_name("create_ticket")

    if is_react_mcp_enabled():
        try:
            ticket = create_ticket_via_react(
                incident_id=incident_id,
                tenant_id=tenant_id,
                description=description,
                triage=triage,
            )
            log_event("ticket_created", incident_id=incident_id, ticket_id=ticket.ticket_id, severity=triage.severity)
            return ticket
        except RuntimeError as exc:
            log_event("react_ticket_failed", incident_id=incident_id, error=str(exc))

    provider          = os.getenv("TICKETING_PROVIDER", "mock-jira")
    fallback_provider = os.getenv("TICKETING_FALLBACK_PROVIDER", "mock-linear")

    def _attempt(prov: str, fail_flag: str) -> TicketRecord:
        # ── Real Jira ──────────────────────────────────────────
        if prov == "jira":
            return create_jira_ticket(
                incident_id=incident_id,
                summary=description[:120] or triage.technical_summary[:120],
                description=description or triage.technical_summary,
                severity=triage.severity,
                affected_service=triage.affected_service,
                rca=triage.root_cause_analysis,
                proposed_fix=triage.proposed_fix,
                cli_command=triage.proposed_cli_command,
                tenant_id=tenant_id,
            )
        # ── Mock / fallback ────────────────────────────────────
        return _create_ticket_with_provider(incident_id, prov, fail_flag=fail_flag)

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

    if is_react_mcp_enabled():
        try:
            detail = notify_team_via_react(
                incident_id=incident_id,
                tenant_id=tenant_id,
                reporter_email=reporter_email,
                description=description or triage.technical_summary,
                triage=triage,
                ticket=ticket,
            )
            event = NotificationRecord(channel="team_communicator", status="sent", detail=detail)
            log_event("team_notified", incident_id=incident_id, ticket_id=ticket.ticket_id)
            return event
        except RuntimeError as exc:
            log_event("react_notify_failed", incident_id=incident_id, error=str(exc))

    provider          = os.getenv("COMMUNICATOR_PROVIDER", "mock-slack")
    fallback_provider = os.getenv("COMMUNICATOR_FALLBACK_PROVIDER", "mock-teams")

    def _attempt(prov: str, fail_flag: str) -> str:
        # ── Real Slack ─────────────────────────────────────────
        if prov == "slack":
            return notify_slack(
                incident_id=incident_id,
                tenant_id=tenant_id,
                ticket=ticket,
                triage=triage,
                reporter_email=reporter_email,
            )
        # ── Mock / fallback ────────────────────────────────────
        return _notify_team_with_provider(prov, ticket, triage, fail_flag=fail_flag)

    try:
        detail = _attempt(provider, "FORCE_FAIL_PRIMARY_COMMUNICATOR")
    except RuntimeError:
        log_event(
            "integration_fallback",
            incident_id=incident_id,
            integration="team_communicator",
            fallback_provider=fallback_provider,
        )
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
        log_event(
            "integration_fallback",
            incident_id=incident_id,
            integration="reporter_email",
            fallback_provider=fallback_provider,
        )
        detail = _notify_reporter_with_provider(fallback_provider, reporter_email, fail_flag="FORCE_FAIL_FALLBACK_EMAIL")
    event = NotificationRecord(channel="reporter_email", status="sent", detail=detail)
    log_event("reporter_notified", incident_id=incident_id, reporter_email=reporter_email)
    return event


# ──────────────────────────────────────────────────────────────
# Persistent CRUD — all require a Session
# ──────────────────────────────────────────────────────────────

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
        repo.write_audit_log(
            db,
            stage="incident_resolved",
            tenant_id=updated.tenant_id,
            incident_id=incident_id,
        )
        log_event("incident_resolved", incident_id=incident_id)

        # ── Optional: send Slack resolved notification ─────────
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


# ──────────────────────────────────────────────────────────────
# Private RCA / fix / CLI helpers
# ──────────────────────────────────────────────────────────────

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


# ──────────────────────────────────────────────────────────────
# Retry / fail-injection helpers
# ──────────────────────────────────────────────────────────────

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


def _create_ticket_with_provider(incident_id: str, provider: str, fail_flag: str) -> TicketRecord:
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
        )

    return _with_retry(f"ticketing:{provider}", action)


def _notify_team_with_provider(provider: str, ticket: TicketRecord, triage: TriageOutput, fail_flag: str) -> str:
    def action() -> str:
        if _should_fail_once(fail_flag):
            raise RuntimeError(f"{provider} temporary outage")
        return (
            f"Team notified on {provider}. Ticket={ticket.ticket_id}, "
            f"service={triage.affected_service}, severity={triage.severity}."
        )

    return _with_retry(f"team_notify:{provider}", action)


def _notify_reporter_with_provider(provider: str, reporter_email: str, fail_flag: str) -> str:
    def action() -> str:
        if _should_fail_once(fail_flag):
            raise RuntimeError(f"{provider} temporary outage")
        return f"Reporter {reporter_email} notified by {provider}."

    return _with_retry(f"reporter_notify:{provider}", action)
