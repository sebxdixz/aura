from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from difflib import SequenceMatcher

from sqlalchemy.orm import Session

from . import repository as repo
from .models import IncidentLinkRecord, IncidentRecord
from .multi_ticket_types import IncidentFingerprint, IncidentSimilarityResult, MultiTicketAnalysisResult, RecurrenceResult


@dataclass(slots=True)
class _CandidateWindow:
    recent: list[IncidentRecord]
    historical: list[IncidentRecord]


def analyze_multi_ticket_intelligence(db: Session, incident: IncidentRecord) -> MultiTicketAnalysisResult:
    current_fp = build_incident_fingerprint(incident)
    candidates = _load_candidates(db, incident)

    similarity_results: list[IncidentSimilarityResult] = []
    for candidate in candidates.recent:
        candidate_fp = build_incident_fingerprint(candidate)
        result = score_incident_similarity(current_fp, candidate_fp)
        result = _normalize_relationship_for_candidate(result, candidate_fp)
        if result.relationship_type != "unrelated":
            similarity_results.append(result)

    is_duplicate, duplicate_of, dedup_confidence = select_primary_duplicate(similarity_results)
    recurrence = detect_recurrence(current_fp, candidates.historical)
    cluster_id = assign_cluster_id(current_fp, similarity_results, recurrence)
    related_ids = _top_related_ids(similarity_results)
    scope_assessment = infer_scope_assessment(
        incident=incident,
        is_duplicate=is_duplicate,
        related_results=similarity_results,
        recurrence=recurrence,
    )
    reasoning = build_multi_ticket_reasoning(
        is_duplicate=is_duplicate,
        duplicate_of=duplicate_of,
        related_results=similarity_results,
        recurrence=recurrence,
        cluster_id=cluster_id,
        scope_assessment=scope_assessment,
    )
    return MultiTicketAnalysisResult(
        is_duplicate=is_duplicate,
        duplicate_of_incident_id=duplicate_of,
        dedup_confidence=dedup_confidence,
        related_incident_ids=related_ids,
        related_links=similarity_results,
        cluster_id=cluster_id,
        recurrence=recurrence,
        scope_assessment=scope_assessment,
        multi_ticket_influence_reasoning=reasoning,
    )


def build_incident_fingerprint(incident: IncidentRecord) -> IncidentFingerprint:
    return IncidentFingerprint(
        incident_id=incident.incident_id,
        tenant_id=incident.tenant_id,
        status=incident.status,
        affected_service=incident.triage.affected_service,
        affected_surface=incident.triage.affected_surface,
        incident_type=incident.triage.incident_type,
        observed_error=incident.triage.observed_error,
        target_team=incident.triage.target_team,
        severity=incident.triage.severity,
        severity_score=incident.triage.severity_score,
        description_signals=incident.triage.description_signals,
        attachment_signals=incident.triage.used_attachment_signals,
        relevant_files=incident.triage.relevant_files or incident.triage.retrieved_context_paths,
        reporter_type=_infer_reporter_type(incident),
        created_at=incident.created_at,
    )


def score_incident_similarity(current_fp: IncidentFingerprint, candidate_fp: IncidentFingerprint) -> IncidentSimilarityResult:
    score = 0.0
    shared_signals: list[str] = []

    if current_fp.affected_service == candidate_fp.affected_service:
        score += 0.25
        shared_signals.append(f"service:{current_fp.affected_service}")
    if current_fp.affected_surface and current_fp.affected_surface == candidate_fp.affected_surface:
        score += 0.10
        shared_signals.append(f"surface:{current_fp.affected_surface}")
    if current_fp.incident_type and current_fp.incident_type == candidate_fp.incident_type:
        score += 0.10
        shared_signals.append(f"type:{current_fp.incident_type}")
    if current_fp.observed_error and current_fp.observed_error == candidate_fp.observed_error:
        score += 0.15
        shared_signals.append(f"error:{current_fp.observed_error}")

    description_overlap = _overlap_ratio(current_fp.description_signals, candidate_fp.description_signals)
    if description_overlap:
        score += 0.15 * description_overlap
        shared_signals.extend(_shared_list(current_fp.description_signals, candidate_fp.description_signals, prefix="desc"))

    attachment_overlap = _overlap_ratio(current_fp.attachment_signals, candidate_fp.attachment_signals)
    if attachment_overlap:
        score += 0.10 * attachment_overlap
        shared_signals.extend(_shared_list(current_fp.attachment_signals, candidate_fp.attachment_signals, prefix="attach"))

    file_overlap = _overlap_ratio(_normalize_paths(current_fp.relevant_files), _normalize_paths(candidate_fp.relevant_files))
    if file_overlap:
        score += 0.10 * file_overlap
        shared_signals.extend(_shared_list(_normalize_paths(current_fp.relevant_files), _normalize_paths(candidate_fp.relevant_files), prefix="rag"))

    semantic_similarity = _semantic_similarity(current_fp, candidate_fp)
    if semantic_similarity:
        score += 0.10 * semantic_similarity

    temporal_score = _temporal_proximity(current_fp.created_at, candidate_fp.created_at)
    score += 0.15 * temporal_score
    if temporal_score >= 0.7:
        shared_signals.append("time:close_window")

    score = round(min(score, 1.0), 2)
    relationship_type = classify_relationship(score)
    reasoning = build_similarity_reasoning(candidate_fp.incident_id, relationship_type, score, shared_signals)
    return IncidentSimilarityResult(
        compared_incident_id=candidate_fp.incident_id,
        similarity_score=score,
        relationship_type=relationship_type,
        shared_signals=shared_signals[:10],
        reasoning=reasoning,
    )


def classify_relationship(score: float) -> str:
    if score >= 0.85:
        return "duplicate"
    if score >= 0.65:
        return "strongly_related"
    if score >= 0.45:
        return "weakly_related"
    return "unrelated"


def select_primary_duplicate(results: list[IncidentSimilarityResult]) -> tuple[bool, str | None, float | None]:
    duplicates = [result for result in results if result.relationship_type == "duplicate"]
    if not duplicates:
        return False, None, None
    top = max(duplicates, key=lambda result: result.similarity_score)
    return True, top.compared_incident_id, top.similarity_score


def detect_recurrence(fingerprint: IncidentFingerprint, historical_incidents: list[IncidentRecord]) -> RecurrenceResult:
    now = _parse_datetime(fingerprint.created_at)
    count_7d = 0
    count_30d = 0
    matched_times: list[datetime] = []
    for incident in historical_incidents:
        candidate_fp = build_incident_fingerprint(incident)
        similarity = score_incident_similarity(fingerprint, candidate_fp)
        similarity = _normalize_relationship_for_candidate(similarity, candidate_fp)
        if similarity.relationship_type not in {"duplicate", "strongly_related"}:
            continue
        created_at = _parse_datetime(candidate_fp.created_at)
        matched_times.append(created_at)
        if created_at >= now - timedelta(days=7):
            count_7d += 1
        count_30d += 1

    matched_times.sort()
    pattern_detected = count_7d >= 2 or count_30d >= 4
    if pattern_detected:
        reasoning = f"Pattern seen {count_7d} times in 7d and {count_30d} times in 30d."
    elif count_30d:
        reasoning = f"Related pattern seen {count_30d} times in 30d."
    else:
        reasoning = "No recurring pattern detected."
    return RecurrenceResult(
        recurrence_count_7d=count_7d,
        recurrence_count_30d=count_30d,
        last_seen_at=matched_times[-1].isoformat() if matched_times else None,
        first_seen_at=matched_times[0].isoformat() if matched_times else None,
        pattern_detected=pattern_detected,
        pattern_reasoning=reasoning,
    )


def assign_cluster_id(
    fingerprint: IncidentFingerprint,
    related_results: list[IncidentSimilarityResult],
    recurrence: RecurrenceResult,
) -> str | None:
    strong_links = [
        result for result in related_results if result.relationship_type in {"duplicate", "strongly_related"}
    ]
    if len(strong_links) < 2 and not recurrence.pattern_detected:
        return None
    date_part = _parse_datetime(fingerprint.created_at).strftime("%Y%m%d")
    service_part = (fingerprint.affected_service or "unknown").replace("_", "-")
    error_part = (fingerprint.observed_error or "unknown").replace("_", "-")
    return f"{service_part}-{error_part}-{date_part}"


def infer_scope_assessment(
    *,
    incident: IncidentRecord,
    is_duplicate: bool,
    related_results: list[IncidentSimilarityResult],
    recurrence: RecurrenceResult,
) -> str:
    strong_count = len([result for result in related_results if result.relationship_type in {"duplicate", "strongly_related"}])
    if is_duplicate:
        return "duplicate_report_linked_to_existing_incident"
    if strong_count >= 3 or recurrence.recurrence_count_7d >= 3:
        return "likely_multi_user"
    if recurrence.pattern_detected or recurrence.recurrence_count_30d >= 2:
        return "ongoing_recurring_pattern"
    if strong_count >= 1:
        return "localized_repeat"
    return incident.triage.scope_assessment or "single_report"


def build_multi_ticket_reasoning(
    *,
    is_duplicate: bool,
    duplicate_of: str | None,
    related_results: list[IncidentSimilarityResult],
    recurrence: RecurrenceResult,
    cluster_id: str | None,
    scope_assessment: str,
) -> str:
    parts: list[str] = []
    if is_duplicate and duplicate_of:
        parts.append(f"Marked as duplicate of {duplicate_of}.")
    strong = [result for result in related_results if result.relationship_type in {"duplicate", "strongly_related"}]
    if strong:
        parts.append(f"Linked to {len(strong)} strongly related incidents in the recent window.")
    if recurrence.recurrence_count_30d:
        parts.append(f"Recurring pattern seen {recurrence.recurrence_count_30d} times in the last 30 days.")
    if cluster_id:
        parts.append(f"Assigned to cluster {cluster_id}.")
    parts.append(f"Scope assessment: {scope_assessment}.")
    return " ".join(parts)


def to_link_records(analysis: MultiTicketAnalysisResult) -> list[IncidentLinkRecord]:
    return [
        IncidentLinkRecord(
            source_incident_id="",
            target_incident_id=result.compared_incident_id,
            relationship_type=result.relationship_type,  # type: ignore[arg-type]
            similarity_score=result.similarity_score,
            reasoning=result.reasoning,
            shared_signals=result.shared_signals,
        )
        for result in analysis.related_links
        if result.relationship_type in {"duplicate", "strongly_related", "weakly_related"}
    ]


def _normalize_relationship_for_candidate(
    result: IncidentSimilarityResult,
    candidate_fp: IncidentFingerprint,
) -> IncidentSimilarityResult:
    if result.relationship_type == "duplicate" and candidate_fp.status != "open":
        result.relationship_type = "strongly_related"
        result.reasoning = (
            f"{result.reasoning.rstrip('.')} Candidate incident is not open, so duplicate was downgraded to strongly_related."
        )
    return result


def _top_related_ids(results: list[IncidentSimilarityResult]) -> list[str]:
    ordered = sorted(
        [result for result in results if result.relationship_type in {"duplicate", "strongly_related"}],
        key=lambda item: item.similarity_score,
        reverse=True,
    )
    seen: set[str] = set()
    related_ids: list[str] = []
    for result in ordered:
        if result.compared_incident_id in seen:
            continue
        seen.add(result.compared_incident_id)
        related_ids.append(result.compared_incident_id)
        if len(related_ids) >= 5:
            break
    return related_ids


def _load_candidates(db: Session, incident: IncidentRecord) -> _CandidateWindow:
    recent = repo.find_recent_incidents_for_similarity(
        db,
        tenant_id=incident.tenant_id,
        current_incident_id=incident.incident_id,
        hours_back=72,
    )
    historical = repo.find_historical_incidents_for_recurrence(
        db,
        tenant_id=incident.tenant_id,
        current_incident_id=incident.incident_id,
        days_back=30,
    )
    return _CandidateWindow(recent=recent, historical=historical)


def _overlap_ratio(left: list[str], right: list[str]) -> float:
    left_set = {item.strip().lower() for item in left if item.strip()}
    right_set = {item.strip().lower() for item in right if item.strip()}
    if not left_set or not right_set:
        return 0.0
    overlap = left_set & right_set
    if not overlap:
        return 0.0
    return min(len(overlap) / max(min(len(left_set), len(right_set)), 1), 1.0)


def _shared_list(left: list[str], right: list[str], prefix: str) -> list[str]:
    left_set = {item.strip().lower() for item in left if item.strip()}
    right_set = {item.strip().lower() for item in right if item.strip()}
    return [f"{prefix}:{item}" for item in sorted(left_set & right_set)[:4]]


def _semantic_similarity(left: IncidentFingerprint, right: IncidentFingerprint) -> float:
    left_text = " ".join(left.description_signals + left.attachment_signals + [left.incident_type or "", left.observed_error or ""]).strip()
    right_text = " ".join(right.description_signals + right.attachment_signals + [right.incident_type or "", right.observed_error or ""]).strip()
    if not left_text or not right_text:
        return 0.0
    return SequenceMatcher(a=left_text.lower(), b=right_text.lower()).ratio()


def _temporal_proximity(left: str, right: str) -> float:
    delta = abs((_parse_datetime(left) - _parse_datetime(right)).total_seconds())
    if delta <= 1800:
        return 1.0
    if delta <= 7200:
        return 0.75
    if delta <= 21600:
        return 0.5
    if delta <= 86400:
        return 0.25
    return 0.1


def _parse_datetime(value: str) -> datetime:
    normalized = value.replace("Z", "+00:00")
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed


def _normalize_paths(paths: list[str]) -> list[str]:
    return [path.replace("\\", "/").lower() for path in paths]


def _infer_reporter_type(incident: IncidentRecord) -> str:
    email = str(incident.reporter_email).lower()
    if any(token in incident.description.lower() for token in ("support", "merchant", "on-call")):
        return "internal_support"
    if email.endswith("@acme.com") or email.endswith("@company.com"):
        return "internal_support"
    if "merchant" in email:
        return "merchant"
    return "customer"


def build_similarity_reasoning(candidate_id: str, relationship_type: str, score: float, shared_signals: list[str]) -> str:
    if not shared_signals:
        return f"Incident {candidate_id} scored {score} as {relationship_type}."
    return (
        f"Incident {candidate_id} scored {score} as {relationship_type} due to shared "
        f"signals: {', '.join(shared_signals[:5])}."
    )
