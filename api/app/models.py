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
    technical_summary: str
    triage_summary: str = ""
    retrieved_context_paths: list[str] = Field(default_factory=list)
    used_attachment_signals: list[str] = Field(default_factory=list)
    relevant_files: list[str] = Field(default_factory=list)
    severity_score: int = 0
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
    runbook_suggestions: list[str] = Field(default_factory=list)
    is_duplicate: bool = False
    duplicate_of_incident_id: str | None = None
    dedup_confidence: float | None = None
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
    context_adherence_score: float = 0.0
    llm_used: bool = False
    fallback_used: bool = False
    retrieval_empty: bool = False


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
