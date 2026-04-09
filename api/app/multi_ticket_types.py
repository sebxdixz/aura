from __future__ import annotations

from pydantic import BaseModel, Field


class IncidentFingerprint(BaseModel):
    incident_id: str
    tenant_id: str
    affected_service: str
    affected_surface: str | None = None
    incident_type: str | None = None
    observed_error: str | None = None
    target_team: str | None = None
    severity: str
    severity_score: int
    description_signals: list[str] = Field(default_factory=list)
    attachment_signals: list[str] = Field(default_factory=list)
    relevant_files: list[str] = Field(default_factory=list)
    reporter_type: str | None = None
    created_at: str


class IncidentSimilarityResult(BaseModel):
    compared_incident_id: str
    similarity_score: float
    relationship_type: str
    shared_signals: list[str] = Field(default_factory=list)
    reasoning: str


class RecurrenceResult(BaseModel):
    recurrence_count_7d: int = 0
    recurrence_count_30d: int = 0
    last_seen_at: str | None = None
    first_seen_at: str | None = None
    pattern_detected: bool = False
    pattern_reasoning: str = ""


class MultiTicketAnalysisResult(BaseModel):
    is_duplicate: bool = False
    duplicate_of_incident_id: str | None = None
    dedup_confidence: float | None = None
    related_incident_ids: list[str] = Field(default_factory=list)
    related_links: list[IncidentSimilarityResult] = Field(default_factory=list)
    cluster_id: str | None = None
    recurrence: RecurrenceResult = Field(default_factory=RecurrenceResult)
    scope_assessment: str = ""
    multi_ticket_influence_reasoning: str = ""
