from __future__ import annotations

import json
import logging
from collections import Counter
from datetime import datetime, timezone
from typing import Any

LOGGER_NAME = "aura"
STAGE_COUNTER = Counter()
SEVERITY_COUNTER = Counter()


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
    payload = {
        "ts": _utc_now_iso(),
        "stage": stage,
        "incident_id": incident_id,
        **extra,
    }
    LOGGER.info(json.dumps(payload, ensure_ascii=True))


def metrics_snapshot() -> dict[str, object]:
    return {
        "stage_counts": dict(STAGE_COUNTER),
        "severity_counts": dict(SEVERITY_COUNTER),
        "deduplicated_incidents": int(STAGE_COUNTER.get("incident_deduplicated", 0)),
    }
