from __future__ import annotations

import re
from datetime import datetime, timezone

from .models import AttachmentRecord, TriageOutput
from .triage_types import ExtractedEntities, NormalizedIncidentInput, RetrievedContext, RoutingDecision, SeverityAssessment

SERVICE_KEYWORDS: dict[str, tuple[str, ...]] = {
    "checkout-service": ("checkout", "cart", "coupon", "order review"),
    "payment-service": ("payment", "gateway", "card", "charge", "declined"),
    "auth-service": ("auth", "login", "signin", "session", "token", "password"),
    "catalog-service": ("catalog", "product", "search", "inventory", "listing"),
    "orders-service": ("order", "orders", "fulfillment", "shipment"),
    "web-app": ("ui", "frontend", "page", "screen", "browser"),
}

TEAM_BY_SERVICE = {
    "checkout-service": "Checkout Backend",
    "payment-service": "Payments",
    "auth-service": "Identity/Auth",
    "catalog-service": "Catalog",
    "orders-service": "Orders",
    "web-app": "Commerce Frontend",
}

SURFACE_KEYWORDS = {
    "checkout": ("checkout", "cart", "coupon"),
    "payment": ("payment", "card", "gateway", "declined"),
    "login": ("login", "signin", "auth", "session", "password"),
    "catalog": ("catalog", "product", "search", "inventory"),
    "orders": ("order", "orders", "shipment"),
}

ERROR_PATTERNS: list[tuple[str, str]] = [
    ("http_500", r"\b500\b|internal server error|5xx"),
    ("timeout", r"\btimeout\b|timed out|deadline exceeded"),
    ("payment_declined", r"payment failed|payment declined|card declined"),
    ("auth_failure", r"\b401\b|\b403\b|unauthorized|forbidden|session expired"),
    ("not_found", r"\b404\b|not found"),
    ("blank_page", r"blank page|white screen|empty screen"),
    ("slow_response", r"slow|latency|degraded"),
]


def normalize_incident_input(
    *,
    incident_id: str | None,
    tenant_id: str | None,
    reporter_email: str | None,
    description: str,
    attachment: AttachmentRecord | None,
    trace_id: str,
) -> NormalizedIncidentInput:
    attachment_text = (attachment.attachment_text_extracted if attachment else "").strip()
    attachment_summary = (attachment.attachment_summary if attachment else "").strip()
    normalized_description = " ".join(description.strip().split())
    reporter_value = (reporter_email or "").strip()
    return NormalizedIncidentInput(
        incident_id=incident_id,
        tenant_id=tenant_id,
        reporter_email=reporter_value,
        reporter_type=_infer_reporter_type(reporter_value, normalized_description),
        raw_description=description,
        normalized_description=normalized_description,
        attachment_present=attachment is not None,
        attachment_type=attachment.attachment_type if attachment else "none",
        attachment_text=attachment_text,
        attachment_summary=attachment_summary,
        attachment_signals=dict(attachment.attachment_signals or {}) if attachment else {},
        submitted_at=datetime.now(timezone.utc).isoformat(),
        trace_id=trace_id,
    )


def extract_entities(normalized: NormalizedIncidentInput) -> ExtractedEntities:
    combined = _combined_text(normalized)
    affected_surface = _detect_surface(combined)
    observed_error = _detect_observed_error(combined)
    incident_type = _detect_incident_type(combined, affected_surface, observed_error)
    suspected_area = _detect_suspected_area(normalized, affected_surface)
    user_scope = _detect_user_scope(combined)
    workaround_present = any(token in combined for token in ("workaround", "retry works", "manual refresh", "temporary fix", "refresh fixes"))
    business_impact_signals = _collect_matching_signals(
        combined,
        (
            "checkout blocked",
            "cannot pay",
            "payment failed",
            "cannot login",
            "orders delayed",
            "sitewide",
            "all users",
            "merchant escalation",
        ),
    )
    security_risk_signals = _collect_matching_signals(
        combined,
        ("unauthorized", "data leak", "token exposed", "security", "auth bypass"),
    )
    urgency_signals = _collect_matching_signals(
        combined,
        ("critical", "urgent", "sev1", "sev2", "asap", "production", "customer impact", "outage"),
    )
    keywords = _extract_keywords(combined)
    reproduction_steps = _extract_reproduction_steps(normalized.raw_description)
    possible_environment = _detect_environment(combined)
    incident_summary = normalized.normalized_description.split(".")[0][:180].strip() or "Incident reported"
    return ExtractedEntities(
        incident_summary=incident_summary,
        incident_type=incident_type,
        affected_surface=affected_surface,
        observed_error=observed_error,
        suspected_area=suspected_area,
        reproduction_steps=reproduction_steps,
        user_scope=user_scope,
        workaround_present=workaround_present,
        business_impact_signals=business_impact_signals,
        security_risk_signals=security_risk_signals,
        urgency_signals=urgency_signals,
        possible_environment=possible_environment,
        keywords=keywords,
    )


def merge_extracted_entities(
    base: ExtractedEntities,
    model_payload: dict[str, object] | None,
) -> tuple[ExtractedEntities, bool]:
    if not isinstance(model_payload, dict):
        return base, False

    merged = ExtractedEntities(
        incident_summary=_coerce_text(model_payload.get("incident_summary"), base.incident_summary),
        incident_type=_coerce_choice(
            model_payload.get("incident_type"),
            {
                "unknown",
                "availability",
                "payment_failure",
                "authentication_failure",
                "performance_degradation",
                "security",
                "data_integrity",
                "ui_bug",
            },
            base.incident_type,
        ),
        affected_surface=_coerce_choice(
            model_payload.get("affected_surface"),
            {"unknown", "checkout", "payment", "login", "catalog", "orders"},
            base.affected_surface,
        ),
        observed_error=_coerce_choice(
            model_payload.get("observed_error"),
            {"unknown", "http_500", "timeout", "payment_declined", "auth_failure", "not_found", "blank_page", "slow_response"},
            base.observed_error,
        ),
        suspected_area=_coerce_text(model_payload.get("suspected_area"), base.suspected_area),
        reproduction_steps=_coerce_string_list(model_payload.get("reproduction_steps"), base.reproduction_steps),
        user_scope=_coerce_choice(
            model_payload.get("user_scope"),
            {"unknown", "single_user_report", "small_subset", "many_users", "global", "critical_flow_unconfirmed_scope"},
            base.user_scope,
        ),
        workaround_present=_coerce_bool(model_payload.get("workaround_present"), base.workaround_present),
        business_impact_signals=_coerce_string_list(
            model_payload.get("business_impact_signals"),
            base.business_impact_signals,
        ),
        security_risk_signals=_coerce_string_list(
            model_payload.get("security_risk_signals"),
            base.security_risk_signals,
        ),
        urgency_signals=_coerce_string_list(model_payload.get("urgency_signals"), base.urgency_signals),
        possible_environment=_coerce_choice(
            model_payload.get("possible_environment"),
            {"unknown", "production", "staging", "sandbox"},
            base.possible_environment,
        ),
        keywords=_coerce_string_list(model_payload.get("keywords"), base.keywords),
    )
    changed = merged != base
    return merged, changed


def build_rag_query(normalized: NormalizedIncidentInput, entities: ExtractedEntities) -> str:
    parts = [
        normalized.normalized_description,
        normalized.attachment_summary,
        normalized.attachment_text[:300],
        entities.affected_surface,
        entities.observed_error,
        entities.suspected_area,
        " ".join(entities.keywords[:8]),
    ]
    return " ".join(part for part in parts if part and part != "unknown").strip()


def summarize_retrieved_context(query_text: str, raw_chunks: list[dict[str, object]]) -> RetrievedContext:
    retrieved_paths: list[str] = []
    service_hints: list[str] = []
    relevant_terms: list[str] = []
    for chunk in raw_chunks:
        file_path = str(chunk.get("file_path", "")).strip()
        if file_path and file_path not in retrieved_paths:
            retrieved_paths.append(file_path)
        lowered_path = file_path.lower()
        for service, keywords in SERVICE_KEYWORDS.items():
            if any(keyword in lowered_path for keyword in keywords) and service not in service_hints:
                service_hints.append(service)
        snippet = str(chunk.get("content", "")).lower()
        for term in ("checkout", "payment", "auth", "login", "catalog", "order", "gateway", "timeout"):
            if term in snippet and term not in relevant_terms:
                relevant_terms.append(term)
    return RetrievedContext(
        query_text=query_text,
        chunks=raw_chunks,
        retrieved_paths=retrieved_paths,
        service_hints=service_hints,
        relevant_terms=relevant_terms,
        retrieval_empty=len(raw_chunks) == 0,
    )


def infer_service(
    *,
    normalized: NormalizedIncidentInput,
    entities: ExtractedEntities,
    retrieved_context: RetrievedContext,
) -> tuple[str, list[str]]:
    scores = {service: 0 for service in SERVICE_KEYWORDS}
    combined = _combined_text(normalized)
    for service, keywords in SERVICE_KEYWORDS.items():
        for keyword in keywords:
            if keyword in combined:
                scores[service] += 3
            if keyword in entities.keywords:
                scores[service] += 2
            if keyword in entities.suspected_area:
                scores[service] += 3
        if service in retrieved_context.service_hints:
            scores[service] += 4
        if service.replace("-service", "") in " ".join(retrieved_context.relevant_terms):
            scores[service] += 2

    attachment_service = str(normalized.attachment_signals.get("suspected_service_from_attachment") or "").strip()
    if attachment_service in scores:
        corroborated = any(
            keyword in normalized.normalized_description.lower()
            for keyword in SERVICE_KEYWORDS.get(attachment_service, ())
        ) or attachment_service in retrieved_context.service_hints
        if corroborated:
            scores[attachment_service] += 5

    ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)
    primary_service = ranked[0][0] if ranked and ranked[0][1] > 0 else "web-app"
    secondary = [service for service, score in ranked[1:4] if score > 0]
    return primary_service, secondary


def score_severity(
    *,
    normalized: NormalizedIncidentInput,
    entities: ExtractedEntities,
    retrieved_context: RetrievedContext,
    primary_service: str,
) -> SeverityAssessment:
    combined = _combined_text(normalized)
    impact_score = 0
    if entities.incident_type in {"payment_failure", "availability", "security"}:
        impact_score += 18
    if entities.affected_surface in {"payment", "checkout", "login"}:
        impact_score += 10
    if any(token in combined for token in ("outage", "down", "all users", "cannot pay", "cannot login")):
        impact_score += 8

    scope_score_map = {
        "global": 20,
        "many_users": 14,
        "small_subset": 8,
        "single_user_report": 4,
        "critical_flow_unconfirmed_scope": 9,
        "unknown": 5,
    }
    scope_score = scope_score_map.get(entities.user_scope, 5)

    reporter_score = 2
    if normalized.reporter_type == "internal_support":
        reporter_score += 4
    elif normalized.reporter_type == "merchant":
        reporter_score += 5

    error_code_score = 0
    if entities.observed_error in {"http_500", "timeout"}:
        error_code_score += 14
    elif entities.observed_error in {"auth_failure", "payment_declined"}:
        error_code_score += 10
    elif entities.observed_error != "unknown":
        error_code_score += 6

    component_score = 6
    if primary_service in {"payment-service", "checkout-service", "auth-service"}:
        component_score += 7
    if normalized.attachment_present and normalized.attachment_type in {"image", "log", "text", "json"}:
        component_score += 3
    if retrieved_context.retrieved_paths:
        component_score += min(6, len(retrieved_context.retrieved_paths))

    security_risk = bool(entities.security_risk_signals)
    workaround_present = entities.workaround_present

    score = impact_score + scope_score + reporter_score + error_code_score + component_score
    if security_risk:
        score += 20
    if workaround_present:
        score -= 8
    if normalized.attachment_signals.get("severity_hints"):
        hints = [str(item).lower() for item in normalized.attachment_signals.get("severity_hints", [])]
        if "critical" in hints:
            score += 12
        elif "high" in hints:
            score += 7

    score = max(0, min(score, 100))
    label = _map_score_to_severity(score)
    rationale = (
        f"Base severity from impact={impact_score}, scope={scope_score}, reporter={reporter_score}, "
        f"error={error_code_score}, component={component_score}."
    )
    reasoning_parts = [
        f"Incident type {entities.incident_type} on {entities.affected_surface} points to {primary_service}.",
        f"Observed error {entities.observed_error} and scope {entities.user_scope} drove the score to {score}/100.",
    ]
    if security_risk:
        reasoning_parts.append("Security-risk signals increased severity.")
    if workaround_present:
        reasoning_parts.append("A workaround was detected, so severity was reduced slightly.")
    if normalized.attachment_present and normalized.attachment_text:
        reasoning_parts.append("Attachment evidence contributed to the severity assessment.")
    if retrieved_context.retrieved_paths:
        reasoning_parts.append("Retrieved code/runbook context reinforced that this is on a critical path.")
    return SeverityAssessment(
        label=label,
        score=score,
        impact_score=impact_score,
        scope_score=scope_score,
        reporter_score=reporter_score,
        error_code_score=error_code_score,
        component_score=component_score,
        security_risk=security_risk,
        workaround_present=workaround_present,
        rationale=rationale,
        reasoning=" ".join(reasoning_parts),
    )


def route_incident(
    *,
    primary_service: str,
    secondary_candidates: list[str],
    entities: ExtractedEntities,
    normalized: NormalizedIncidentInput,
    retrieved_context: RetrievedContext,
) -> RoutingDecision:
    target_team = TEAM_BY_SERVICE.get(primary_service, "Platform/SRE")
    if entities.affected_surface == "payment" or primary_service == "payment-service":
        target_team = "Payments"
    elif entities.affected_surface == "checkout" and entities.observed_error in {"http_500", "timeout"}:
        target_team = "Checkout Backend"
    elif entities.observed_error in {"http_500", "timeout"} and len(retrieved_context.service_hints) > 1:
        target_team = "Platform/SRE"
    routing_confidence = 0.45
    if primary_service in retrieved_context.service_hints:
        routing_confidence += 0.2
    if normalized.attachment_signals.get("suspected_service_from_attachment") == primary_service:
        routing_confidence += 0.15
    if entities.affected_surface != "unknown":
        routing_confidence += 0.1
    if target_team in {"Payments", "Checkout Backend"} and entities.observed_error in {"http_500", "timeout", "payment_declined"}:
        routing_confidence += 0.08
    if secondary_candidates:
        routing_confidence -= 0.05
    routing_confidence = round(max(0.2, min(routing_confidence, 0.95)), 2)
    reasoning_parts = [
        f"Primary service inferred as {primary_service} from report text and extracted entities.",
        f"Target team mapped to {target_team}.",
    ]
    if entities.affected_surface == "payment":
        reasoning_parts.append("Payment flow signals were stronger than generic checkout/frontend cues.")
    elif entities.affected_surface == "checkout" and entities.observed_error in {"http_500", "timeout"}:
        reasoning_parts.append("Backend failure signals outweighed a pure frontend interpretation.")
    if normalized.attachment_signals.get("suspected_service_from_attachment"):
        reasoning_parts.append("Attachment signals were considered during routing.")
    if retrieved_context.retrieved_paths:
        reasoning_parts.append(f"RAG matched {', '.join(retrieved_context.retrieved_paths[:2])}.")
    if secondary_candidates:
        reasoning_parts.append(f"Secondary candidates were {', '.join(secondary_candidates[:3])}.")
    return RoutingDecision(
        target_team=target_team,
        primary_service=primary_service,
        secondary_candidates=secondary_candidates,
        routing_confidence=routing_confidence,
        reasoning=" ".join(reasoning_parts),
    )


def validate_triage_output(output: TriageOutput) -> TriageOutput:
    if output.severity not in {"low", "medium", "high", "critical"}:
        output.severity = "medium"
    output.severity_score = max(0, min(output.severity_score, 100))
    output.routing_confidence = max(0.0, min(output.routing_confidence, 1.0))
    output.confidence = max(0.0, min(output.confidence, 1.0))
    if not output.target_team.strip():
        output.target_team = TEAM_BY_SERVICE.get(output.affected_service, "Platform/SRE")
    if not output.routing_reasoning.strip():
        output.routing_reasoning = f"Routed to {output.target_team} based on {output.affected_service}."
    if not output.severity_reasoning.strip():
        output.severity_reasoning = output.severity_rationale or f"Severity score {output.severity_score}/100."
    if not output.incident_type.strip():
        output.incident_type = "unknown"
    if not output.scope_assessment.strip():
        output.scope_assessment = "Impact scope is still unconfirmed."
    if not output.triage_mode.strip():
        output.triage_mode = "deterministic + multimodal extraction"
    return output


def _infer_reporter_type(reporter_email: str, description: str) -> str:
    text = description.lower()
    email = reporter_email.lower()
    if any(token in text for token in ("support", "on-call", "merchant", "customer care")):
        return "internal_support"
    if email.endswith("@acme.com") or email.endswith("@company.com") or email.endswith("@internal.local"):
        return "internal_support"
    if "merchant" in email:
        return "merchant"
    return "customer"


def _combined_text(normalized: NormalizedIncidentInput) -> str:
    return " ".join(
        [
            normalized.normalized_description.lower(),
            normalized.attachment_text.lower(),
            normalized.attachment_summary.lower(),
            " ".join(str(item).lower() for item in normalized.attachment_signals.get("keywords_found", [])),
            " ".join(str(item).lower() for item in normalized.attachment_signals.get("error_codes_found", [])),
        ]
    ).strip()


def _detect_surface(combined: str) -> str:
    for surface, keywords in SURFACE_KEYWORDS.items():
        if any(keyword in combined for keyword in keywords):
            return surface
    return "unknown"


def _detect_observed_error(combined: str) -> str:
    for name, pattern in ERROR_PATTERNS:
        if re.search(pattern, combined):
            return name
    return "unknown"


def _detect_incident_type(combined: str, affected_surface: str, observed_error: str) -> str:
    if any(token in combined for token in ("security", "data leak", "token exposed", "unauthorized")):
        return "security"
    if affected_surface == "payment" or observed_error == "payment_declined":
        return "payment_failure"
    if affected_surface == "login" or observed_error == "auth_failure":
        return "authentication_failure"
    if observed_error in {"http_500", "timeout"}:
        return "availability"
    if observed_error == "slow_response":
        return "performance_degradation"
    if "wrong" in combined or "mismatch" in combined:
        return "data_integrity"
    if "blank page" in combined or "ui" in combined:
        return "ui_bug"
    return "unknown"


def _detect_suspected_area(normalized: NormalizedIncidentInput, affected_surface: str) -> str:
    attachment_candidate = str(normalized.attachment_signals.get("suspected_service_from_attachment") or "").strip()
    if attachment_candidate:
        return attachment_candidate
    return affected_surface if affected_surface != "unknown" else "web-app"


def _detect_user_scope(combined: str) -> str:
    if any(token in combined for token in ("all users", "everyone", "global", "sitewide", "all tenants")):
        return "global"
    if any(token in combined for token in ("many users", "multiple users", "customers are", "several users")):
        return "many_users"
    if any(token in combined for token in ("subset", "some users", "small cohort")):
        return "small_subset"
    if any(token in combined for token in ("single user", "one user", "customer only")):
        return "single_user_report"
    if any(token in combined for token in ("checkout", "payment", "login")):
        return "critical_flow_unconfirmed_scope"
    return "unknown"


def _detect_environment(combined: str) -> str:
    if "production" in combined or "prod" in combined:
        return "production"
    if "staging" in combined:
        return "staging"
    if "sandbox" in combined:
        return "sandbox"
    return "unknown"


def _extract_keywords(combined: str) -> list[str]:
    ordered_tokens = [
        "checkout",
        "payment",
        "gateway",
        "login",
        "auth",
        "session",
        "catalog",
        "product",
        "order",
        "timeout",
        "500",
        "403",
        "404",
        "latency",
        "outage",
        "security",
    ]
    return [token for token in ordered_tokens if token in combined]


def _extract_reproduction_steps(description: str) -> list[str]:
    steps: list[str] = []
    for chunk in re.split(r"[.\n]", description):
        line = chunk.strip()
        lowered = line.lower()
        if not line:
            continue
        if any(marker in lowered for marker in ("step", "open", "click", "submit", "retry", "login", "checkout")):
            steps.append(line[:140])
    return steps[:4]


def _collect_matching_signals(combined: str, tokens: tuple[str, ...]) -> list[str]:
    return [token for token in tokens if token in combined][:6]


def _map_score_to_severity(score: int) -> str:
    if score >= 80:
        return "critical"
    if score >= 60:
        return "high"
    if score >= 35:
        return "medium"
    return "low"


def _coerce_text(value: object, fallback: str) -> str:
    if isinstance(value, str):
        cleaned = " ".join(value.strip().split())
        if cleaned:
            return cleaned[:240]
    return fallback


def _coerce_string_list(value: object, fallback: list[str]) -> list[str]:
    if isinstance(value, list):
        cleaned = []
        for item in value:
            text = _coerce_text(item, "")
            if text:
                cleaned.append(text)
        if cleaned:
            return cleaned[:8]
    return fallback


def _coerce_choice(value: object, allowed: set[str], fallback: str) -> str:
    normalized = str(value or "").strip().lower()
    return normalized if normalized in allowed else fallback


def _coerce_bool(value: object, fallback: bool) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "1", "yes", "on"}:
            return True
        if normalized in {"false", "0", "no", "off"}:
            return False
    return fallback
