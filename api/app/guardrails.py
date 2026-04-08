from __future__ import annotations

import re

MAX_DESCRIPTION_LENGTH = 4000
MAX_FILE_BYTES = 5 * 1024 * 1024

ALLOWED_FILE_TYPES = {
    "text/plain",
    "text/csv",
    "application/json",
    "application/pdf",
    "image/png",
    "image/jpeg",
    "audio/wav",
    "audio/x-wav",
    "audio/mpeg",
    "audio/mp3",
    "audio/mp4",
    "audio/x-m4a",
    "audio/webm",
    "audio/ogg",
}

BLOCKED_PATTERNS = [
    r"ignore\s+previous\s+instructions",
    r"system\s+prompt",
    r"<script",
    r"BEGIN\s+PROMPT\s+INJECTION",
]

ALLOWED_TOOL_NAMES = {"create_ticket", "notify_team", "notify_reporter"}


def validate_description(description: str) -> None:
    if not description or not description.strip():
        raise ValueError("description is required")
    if len(description) > MAX_DESCRIPTION_LENGTH:
        raise ValueError(f"description too long (max {MAX_DESCRIPTION_LENGTH})")
    lowered = description.lower()
    for pattern in BLOCKED_PATTERNS:
        if re.search(pattern, lowered, flags=re.IGNORECASE):
            raise ValueError("possible prompt injection pattern detected")


def validate_file(content_type: str | None, size_bytes: int | None) -> None:
    if content_type is None or size_bytes is None:
        return
    if content_type not in ALLOWED_FILE_TYPES:
        raise ValueError(f"file content_type '{content_type}' is not allowed")
    if size_bytes > MAX_FILE_BYTES:
        raise ValueError(f"file too large (max {MAX_FILE_BYTES} bytes)")


def validate_tool_name(tool_name: str) -> None:
    if tool_name not in ALLOWED_TOOL_NAMES:
        raise ValueError(f"tool '{tool_name}' is not allowed")
