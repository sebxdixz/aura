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


class TriageOutput(BaseModel):
    severity: Literal["low", "medium", "high", "critical"]
    affected_service: str
    technical_summary: str
    relevant_files: list[str] = Field(default_factory=list)
    severity_score: int = 0
    severity_rationale: str = ""
    runbook_suggestions: list[str] = Field(default_factory=list)
    is_duplicate: bool = False
    duplicate_of_incident_id: str | None = None
    dedup_confidence: float | None = None
    root_cause_analysis: str
    proposed_fix: str
    proposed_cli_command: str
    llm_mode: str
    llm_usage: dict = Field(default_factory=dict)


class TicketRecord(BaseModel):
    ticket_id: str
    provider: str
    url: str
    status: Literal["created", "failed"] = "created"


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
    resolution_notes: str | None = None
    file_meta: FileMeta | None = None
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


class IntegrationConfigStatus(BaseModel):
    provider: Literal["slack", "jira"]
    configured: bool
    configured_fields: list[str] = Field(default_factory=list)
    updated_at: str | None = None


class TenantIntegrationsStatus(BaseModel):
    tenant_id: str
    slack: IntegrationConfigStatus
    jira: IntegrationConfigStatus


class SlackIntegrationPayload(BaseModel):
    webhook_url: str | None = None
    bot_token: str | None = None
    team_id: str | None = None
    default_channel_id: str | None = None


class JiraIntegrationPayload(BaseModel):
    base_url: str | None = None
    email: str | None = None
    api_token: str | None = None
    project_key: str | None = None
    issue_type: str | None = None


class IntegrationTestResult(BaseModel):
    provider: Literal["slack", "jira"]
    ok: bool
    detail: str
