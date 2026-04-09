from __future__ import annotations

import json
import logging
from collections import Counter
from datetime import datetime, timezone
from typing import Any

LOGGER_NAME = "aura"
STAGE_COUNTER = Counter()
SEVERITY_COUNTER = Counter()
ATTACHMENT_TYPE_COUNTER = Counter()
FLAG_COUNTER = Counter()
VALUE_TOTALS = Counter()
VALUE_COUNTS = Counter()


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def configure_logging() -> logging.Logger:
    logger = logging.getLogger(LOGGER_NAME)
    if logger.handlers:
        return logger
    logger.setLevel(logging.INFO)
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(handler)
    return logger


LOGGER = configure_logging()


def log_event(stage: str, incident_id: str | None = None, **extra: Any) -> None:
    STAGE_COUNTER[stage] += 1
    severity = extra.get("severity")
    if isinstance(severity, str) and severity:
        SEVERITY_COUNTER[severity] += 1
    attachment_type = extra.get("attachment_type")
    if isinstance(attachment_type, str) and attachment_type:
        ATTACHMENT_TYPE_COUNTER[attachment_type] += 1
    for flag_name in ("llm_used", "fallback_used", "retrieval_empty"):
        if extra.get(flag_name) is True:
            FLAG_COUNTER[flag_name] += 1
    for value_name in ("triage_confidence", "context_adherence_score", "triage_duration_ms", "rag_duration_ms", "llm_duration_ms"):
        value = extra.get(value_name)
        if isinstance(value, (int, float)):
            VALUE_TOTALS[value_name] += float(value)
            VALUE_COUNTS[value_name] += 1
    payload = {
        "ts": _utc_now_iso(),
        "stage": stage,
        "incident_id": incident_id,
        **extra,
    }
    LOGGER.info(json.dumps(payload, ensure_ascii=True))


def metrics_snapshot() -> dict[str, object]:
    def avg(name: str) -> float:
        count = VALUE_COUNTS.get(name, 0)
        if not count:
            return 0.0
        return round(VALUE_TOTALS[name] / count, 3)

    return {
        "stage_counts": dict(STAGE_COUNTER),
        "severity_counts": dict(SEVERITY_COUNTER),
        "deduplicated_incidents": int(STAGE_COUNTER.get("incident_deduplicated", 0)),
        "attachments_received_total": int(STAGE_COUNTER.get("attachment_received", 0)),
        "attachments_rejected_total": int(STAGE_COUNTER.get("attachment_rejected", 0)),
        "attachments_processed_total": int(STAGE_COUNTER.get("attachment_processed", 0)),
        "attachments_by_type": dict(ATTACHMENT_TYPE_COUNTER),
        "ocr_success_total": int(STAGE_COUNTER.get("attachment_ocr_completed", 0)),
        "ocr_failure_total": int(
            STAGE_COUNTER.get("attachment_ocr_failed", 0) + STAGE_COUNTER.get("attachment_ocr_skipped", 0)
        ),
        "log_parse_success_total": int(STAGE_COUNTER.get("attachment_log_parsed", 0)),
        "attachment_used_in_triage_total": int(STAGE_COUNTER.get("attachment_injected_into_triage", 0)),
        "llm_used_total": int(FLAG_COUNTER.get("llm_used", 0)),
        "fallback_used_total": int(FLAG_COUNTER.get("fallback_used", 0)),
        "retrieval_empty_total": int(FLAG_COUNTER.get("retrieval_empty", 0)),
        "avg_triage_confidence": avg("triage_confidence"),
        "avg_context_adherence_score": avg("context_adherence_score"),
        "avg_triage_duration_ms": avg("triage_duration_ms"),
        "avg_rag_duration_ms": avg("rag_duration_ms"),
        "avg_llm_duration_ms": avg("llm_duration_ms"),
    }
