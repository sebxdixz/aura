from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class NormalizedIncidentInput:
    incident_id: str | None
    tenant_id: str | None
    reporter_email: str
    reporter_type: str
    raw_description: str
    normalized_description: str
    attachment_present: bool
    attachment_type: str
    attachment_text: str
    attachment_summary: str
    attachment_signals: dict[str, object] = field(default_factory=dict)
    submitted_at: str = ""
    trace_id: str = ""


@dataclass(slots=True)
class ExtractedEntities:
    incident_summary: str
    incident_type: str
    affected_surface: str
    observed_error: str
    suspected_area: str
    reproduction_steps: list[str] = field(default_factory=list)
    user_scope: str = "unknown"
    workaround_present: bool = False
    business_impact_signals: list[str] = field(default_factory=list)
    security_risk_signals: list[str] = field(default_factory=list)
    urgency_signals: list[str] = field(default_factory=list)
    possible_environment: str = "unknown"
    keywords: list[str] = field(default_factory=list)


@dataclass(slots=True)
class RetrievedContext:
    query_text: str
    chunks: list[dict[str, object]] = field(default_factory=list)
    retrieved_paths: list[str] = field(default_factory=list)
    service_hints: list[str] = field(default_factory=list)
    relevant_terms: list[str] = field(default_factory=list)
    retrieval_empty: bool = True


@dataclass(slots=True)
class SeverityAssessment:
    label: str
    score: int
    impact_score: int
    scope_score: int
    reporter_score: int
    error_code_score: int
    component_score: int
    security_risk: bool
    workaround_present: bool
    rationale: str
    reasoning: str


@dataclass(slots=True)
class RoutingDecision:
    target_team: str
    primary_service: str
    secondary_candidates: list[str] = field(default_factory=list)
    routing_confidence: float = 0.0
    reasoning: str = ""
