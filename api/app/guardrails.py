from __future__ import annotations

import os
import re
from pathlib import Path

MAX_DESCRIPTION_LENGTH = 4000

ALLOWED_FILE_TYPES = {
    "text/plain",
    "application/json",
    "application/pdf",
    "image/png",
    "image/jpeg",
    "image/jpg",
    "image/webp",
    "audio/wav",
    "audio/x-wav",
    "audio/mpeg",
    "audio/mp3",
    "audio/mp4",
    "audio/x-m4a",
    "audio/webm",
    "audio/ogg",
}

ALLOWED_ATTACHMENT_EXTENSIONS = {
    ".txt": {"text/plain"},
    ".log": {"text/plain"},
    ".json": {"application/json", "text/plain"},
    ".pdf": {"application/pdf"},
    ".png": {"image/png"},
    ".jpg": {"image/jpeg", "image/jpg"},
    ".jpeg": {"image/jpeg", "image/jpg"},
    ".webp": {"image/webp"},
    ".wav": {"audio/wav", "audio/x-wav"},
    ".mp3": {"audio/mpeg", "audio/mp3"},
    ".mp4": {"audio/mp4", "audio/x-m4a"},
    ".m4a": {"audio/mp4", "audio/x-m4a"},
    ".webm": {"audio/webm"},
    ".ogg": {"audio/ogg"},
}

BLOCKED_PATTERNS = [
    r"ignore\s+previous\s+instructions",
    r"system\s+prompt",
    r"<script",
    r"BEGIN\s+PROMPT\s+INJECTION",
]

ALLOWED_TOOL_NAMES = {"create_ticket", "notify_team", "notify_reporter"}


def max_attachment_bytes() -> int:
    raw = os.getenv("MAX_ATTACHMENT_BYTES", str(5 * 1024 * 1024))
    try:
        return max(1024, int(raw))
    except ValueError:
        return 5 * 1024 * 1024


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
    if size_bytes > max_attachment_bytes():
        raise ValueError(f"file too large (max {max_attachment_bytes()} bytes)")


def validate_tool_name(tool_name: str) -> None:
    if tool_name not in ALLOWED_TOOL_NAMES:
        raise ValueError(f"tool '{tool_name}' is not allowed")


def sanitize_filename(filename: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "-", (filename or "").strip())
    cleaned = cleaned.strip(".-") or "attachment"
    return cleaned[:120]


def detect_attachment_injection(text: str) -> None:
    lowered = text.lower()
    for pattern in BLOCKED_PATTERNS + [r"act\s+as\s+", r"tool\s*:", r"assistant\s*:", r"developer\s*message"]:
        if re.search(pattern, lowered, flags=re.IGNORECASE):
            raise ValueError("possible prompt injection pattern detected in attachment")


def validate_attachment(
    *,
    filename: str | None,
    content_type: str | None,
    size_bytes: int,
    content_bytes: bytes,
) -> str:
    if not filename or not filename.strip():
        raise ValueError("attachment filename is required")
    if size_bytes <= 0 or not content_bytes:
        raise ValueError("attachment is empty")
    if size_bytes > max_attachment_bytes():
        raise ValueError(f"attachment too large (max {max_attachment_bytes()} bytes)")
    if content_type is None or content_type.lower().strip() not in ALLOWED_FILE_TYPES:
        raise ValueError(f"attachment content_type '{content_type}' is not allowed")

    safe_name = sanitize_filename(filename)
    extension = Path(safe_name).suffix.lower()
    if extension not in ALLOWED_ATTACHMENT_EXTENSIONS:
        raise ValueError(f"attachment extension '{extension or 'none'}' is not allowed")

    normalized_type = content_type.lower().strip()
    allowed_mime_types = ALLOWED_ATTACHMENT_EXTENSIONS[extension]
    if normalized_type not in allowed_mime_types:
        raise ValueError("attachment MIME type does not match file extension")

    if extension in {".txt", ".log", ".json"}:
        text = content_bytes.decode("utf-8", errors="ignore")
        detect_attachment_injection(text[:4000])
    return safe_name
