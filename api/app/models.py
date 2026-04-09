from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, EmailStr, Field


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class FileMeta(BaseModel):
    filename: str
    content_type: str
    size_bytes: int


class AttachmentRecord(BaseModel):
    attachment_type: str
    attachment_filename: str
    attachment_mime_type: str
    attachment_size_bytes: int
    attachment_storage_path: str
    attachment_text_extracted: str = ""
    attachment_summary: str = ""
    evidence_from_attachment: list[str] = Field(default_factory=list)
    attachment_signals: dict = Field(default_factory=dict)
    attachment_used: bool = False
    extraction_method: str = "none"


class TriageOutput(BaseModel):
    severity: Literal["low", "medium", "high", "critical"]
    affected_service: str
    incident_type: str = "unknown"
    affected_surface: str = "unknown"
    observed_error: str = "unknown"
    user_scope: str = "unknown"
    scope_assessment: str = ""
    target_team: str = "Platform/SRE"
    routing_confidence: float = 0.0
    secondary_service_candidates: list[str] = Field(default_factory=list)
    technical_summary: str
    triage_summary: str = ""
    retrieved_context_paths: list[str] = Field(default_factory=list)
    rag_evidence: list[str] = Field(default_factory=list)
    used_attachment_signals: list[str] = Field(default_factory=list)
    description_signals: list[str] = Field(default_factory=list)
    relevant_files: list[str] = Field(default_factory=list)
    severity_score: int = 0
    description_score: int = 0
    attachment_score: int = 0
    criticality_score: int = 0
    impact_score: int = 0
    scope_score: int = 0
    reporter_score: int = 0
    error_code_score: int = 0
    component_score: int = 0
    severity_rationale: str = ""
    severity_reasoning: str = ""
    routing_reasoning: str = ""
    workaround_present: bool = False
    security_risk: bool = False
    business_impact_signals: list[str] = Field(default_factory=list)
    security_risk_signals: list[str] = Field(default_factory=list)
    urgency_signals: list[str] = Field(default_factory=list)
    runbook_suggestions: list[str] = Field(default_factory=list)
    is_duplicate: bool = False
    duplicate_of_incident_id: str | None = None
    dedup_confidence: float | None = None
    related_incident_ids: list[str] = Field(default_factory=list)
    cluster_id: str | None = None
    recurrence_count_7d: int = 0
    recurrence_count_30d: int = 0
    multi_ticket_influence_reasoning: str = ""
    root_cause_analysis: str
    proposed_fix: str
    proposed_cli_command: str
    llm_mode: str
    attachment_used: bool = False
    attachment_type: str | None = None
    attachment_text_extracted: str = ""
    evidence_from_attachment: list[str] = Field(default_factory=list)
    attachment_summary: str = ""
    attachment_influence_reasoning: str = ""
    confidence: float = 0.0
    severity_confidence: float = 0.0
    root_cause_confidence: float = 0.0
    context_adherence_score: float = 0.0
    llm_used: bool = False
    live_llm_used: bool = False
    fallback_used: bool = False
    retrieval_empty: bool = False
    triage_mode: str = ""


class TicketRecord(BaseModel):
    ticket_id: str
    provider: str
    url: str
    status: Literal["created", "failed"] = "created"
    title: str = ""
    description: str = ""


class NotificationRecord(BaseModel):
    channel: Literal["team_communicator", "reporter_email"]
    status: Literal["sent", "failed"] = "sent"
    sent_at: str = Field(default_factory=utc_now_iso)
    detail: str


class IncidentLinkRecord(BaseModel):
    source_incident_id: str
    target_incident_id: str
    relationship_type: Literal["duplicate", "strongly_related", "weakly_related"]
    similarity_score: float
    reasoning: str = ""
    shared_signals: list[str] = Field(default_factory=list)
    created_at: str = Field(default_factory=utc_now_iso)


class IncidentRecord(BaseModel):
    incident_id: str
    tenant_id: str
    reporter_email: EmailStr
    description: str
    status: Literal["open", "resolved"] = "open"
    created_at: str = Field(default_factory=utc_now_iso)
    resolved_at: str | None = None
    file_meta: FileMeta | None = None
    attachment: AttachmentRecord | None = None
    triage: TriageOutput
    ticket: TicketRecord
    notifications: list[NotificationRecord] = Field(default_factory=list)
    related_links: list[IncidentLinkRecord] = Field(default_factory=list)


class TenantRecord(BaseModel):
    tenant_id: str
    name: str
    intake_url: str
    created_at: str = Field(default_factory=utc_now_iso)


class TenantDashboard(BaseModel):
    tenant_id: str
    open_incidents: int
    resolved_incidents: int
    critical_incidents: int
    total_incidents: int


class AuditLogRecord(BaseModel):
    id: int
    tenant_id: str | None = None
    incident_id: str | None = None
    stage: str
    payload: dict = Field(default_factory=dict)
    created_at: str


class TenantInsightsSummary(BaseModel):
    tenant_id: str
    total_incidents: int
    open_incidents: int
    resolved_incidents: int
    duplicate_incidents: int
    low_incidents: int
    medium_incidents: int
    high_incidents: int
    critical_incidents: int
