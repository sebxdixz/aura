from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any
from uuid import uuid4

try:
    from PIL import Image
except Exception:  # pragma: no cover - optional dependency
    Image = None  # type: ignore[assignment]

try:
    from pypdf import PdfReader
except Exception:  # pragma: no cover - optional dependency
    PdfReader = None  # type: ignore[assignment]

try:
    import pytesseract
except Exception:  # pragma: no cover - optional dependency
    pytesseract = None  # type: ignore[assignment]

from .guardrails import sanitize_filename
from .models import AttachmentRecord
from .observability import log_event

TEXTUAL_MIME_TYPES = {"text/plain", "application/json"}
IMAGE_MIME_TYPES = {"image/png", "image/jpeg", "image/jpg", "image/webp"}
PDF_MIME_TYPES = {"application/pdf"}
AUDIO_MIME_TYPES = {
    "audio/wav",
    "audio/x-wav",
    "audio/mpeg",
    "audio/mp3",
    "audio/mp4",
    "audio/x-m4a",
    "audio/webm",
    "audio/ogg",
}
MAX_TEXT_EXTRACTED = 6000

_ERROR_CODE_RE = re.compile(r"\b(?:4\d{2}|5\d{2}|timeout|timed out|connection reset|connection refused)\b", re.IGNORECASE)
_TIMESTAMP_RE = re.compile(r"\b\d{4}-\d{2}-\d{2}[T ][0-2]\d:[0-5]\d:[0-5]\d(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2})?\b")
_STACK_TRACE_RE = re.compile(r"\bTraceback\b|\bat\s+[A-Za-z0-9_.$]+\(|\bException\b", re.IGNORECASE)
_SERVICE_HINTS = {
    "checkout": "checkout-service",
    "payment": "checkout-service",
    "coupon": "checkout-service",
    "auth": "auth-service",
    "login": "auth-service",
    "catalog": "catalog-service",
}
_KEYWORD_HINTS = {
    "critical": ["outage", "sev1", "critical", "payment failed", "internal server error"],
    "high": ["http 500", "500", "timeout", "failed", "exception"],
    "medium": ["latency", "slow", "degraded", "warn"],
}


def attachments_dir() -> Path:
    path = Path(os.getenv("ATTACHMENTS_DIR", "/tmp/aura_attachments"))
    path.mkdir(parents=True, exist_ok=True)
    return path


def persist_attachment(*, incident_id: str, filename: str, content_bytes: bytes) -> str:
    safe_name = sanitize_filename(filename)
    ext = Path(safe_name).suffix.lower()
    target = attachments_dir() / f"{incident_id}-{uuid4().hex[:8]}{ext}"
    target.write_bytes(content_bytes)
    return str(target)


def process_attachment(
    *,
    incident_id: str,
    tenant_id: str,
    filename: str,
    content_type: str,
    content_bytes: bytes,
    storage_path: str,
) -> AttachmentRecord:
    lower_type = content_type.lower().strip()
    log_event("attachment_processed", incident_id=incident_id, tenant_id=tenant_id, attachment_type=lower_type)

    if lower_type in IMAGE_MIME_TYPES:
        return _process_image(
            incident_id=incident_id,
            tenant_id=tenant_id,
            filename=filename,
            content_type=lower_type,
            content_bytes=content_bytes,
            storage_path=storage_path,
        )

    if lower_type in TEXTUAL_MIME_TYPES:
        return _process_textual(
            incident_id=incident_id,
            tenant_id=tenant_id,
            filename=filename,
            content_type=lower_type,
            content_bytes=content_bytes,
            storage_path=storage_path,
        )

    if lower_type in PDF_MIME_TYPES:
        return _process_pdf(
            filename=filename,
            content_type=lower_type,
            content_bytes=content_bytes,
            storage_path=storage_path,
        )

    if lower_type in AUDIO_MIME_TYPES:
        return AttachmentRecord(
            attachment_type="audio",
            attachment_filename=filename,
            attachment_mime_type=lower_type,
            attachment_size_bytes=len(content_bytes),
            attachment_storage_path=storage_path,
            attachment_summary="Audio attachment stored. Transcript extraction is not available in the attachment processor.",
            extraction_method="stored_only",
        )

    return AttachmentRecord(
        attachment_type=_attachment_kind(lower_type),
        attachment_filename=filename,
        attachment_mime_type=lower_type,
        attachment_size_bytes=len(content_bytes),
        attachment_storage_path=storage_path,
        attachment_summary=f"Attachment stored ({lower_type}) but no processor is configured for this type.",
        extraction_method="stored_only",
    )


def attachment_context_from_record(attachment: AttachmentRecord | None) -> dict[str, Any]:
    if attachment is None:
        return {
            "attachment_type": "none",
            "extraction_method": "none",
            "summary": "No attachment provided.",
            "extracted_text": "",
            "signals": {},
            "evidence": [],
        }
    return {
        "attachment_type": attachment.attachment_type,
        "extraction_method": attachment.extraction_method,
        "summary": attachment.attachment_summary,
        "extracted_text": attachment.attachment_text_extracted,
        "signals": attachment.attachment_signals,
        "evidence": attachment.evidence_from_attachment,
    }


def _process_textual(
    *,
    incident_id: str,
    tenant_id: str,
    filename: str,
    content_type: str,
    content_bytes: bytes,
    storage_path: str,
) -> AttachmentRecord:
    text = _decode_text(content_bytes)
    extracted_text = _trim_text(text)
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    relevant_lines = [line for line in lines if _ERROR_CODE_RE.search(line) or _STACK_TRACE_RE.search(line)]
    relevant_lines = relevant_lines[:8]
    error_codes = _unique_matches(_ERROR_CODE_RE, text)
    timestamps = _unique_matches(_TIMESTAMP_RE, text)
    keywords = _extract_keywords(text)
    suspected_service = _suspected_service(text)
    severity_hints = _severity_hints(text, error_codes)
    possible_environment = _possible_environment(text)

    evidence = []
    if suspected_service:
        evidence.append(f"Log referenced {suspected_service}.")
    if error_codes:
        evidence.append(f"Detected error codes/signals: {', '.join(error_codes[:5])}.")
    if relevant_lines:
        evidence.append(f"Relevant log lines found: {len(relevant_lines)}.")
    if timestamps:
        evidence.append(f"Timestamps extracted: {', '.join(timestamps[:2])}.")

    summary_parts = []
    if suspected_service:
        summary_parts.append(f"Log evidence points to {suspected_service}")
    if error_codes:
        summary_parts.append(f"with signals {', '.join(error_codes[:4])}")
    if possible_environment:
        summary_parts.append(f"in {possible_environment}")
    if not summary_parts:
        summary_parts.append("Text attachment processed with no strong routing signals")
    summary = " ".join(summary_parts) + "."

    signals = {
        "suspected_service_from_attachment": suspected_service,
        "error_codes_found": error_codes,
        "keywords_found": keywords,
        "severity_hints": severity_hints,
        "possible_environment": possible_environment,
        "timestamps_found": timestamps[:5],
        "relevant_lines": relevant_lines,
    }
    log_event("attachment_log_parsed", incident_id=incident_id, tenant_id=tenant_id, attachment_type="text")
    log_event("attachment_signals_extracted", incident_id=incident_id, tenant_id=tenant_id, attachment_type="text")
    return AttachmentRecord(
        attachment_type="log" if Path(filename).suffix.lower() in {".log", ".txt"} else "json",
        attachment_filename=filename,
        attachment_mime_type=content_type,
        attachment_size_bytes=len(content_bytes),
        attachment_storage_path=storage_path,
        attachment_text_extracted=extracted_text,
        attachment_summary=summary,
        evidence_from_attachment=evidence,
        attachment_signals=signals,
        attachment_used=bool(evidence or relevant_lines or suspected_service),
        extraction_method="decode_text",
    )


def _process_image(
    *,
    incident_id: str,
    tenant_id: str,
    filename: str,
    content_type: str,
    content_bytes: bytes,
    storage_path: str,
) -> AttachmentRecord:
    extracted_fragments: list[str] = []
    ocr_mode = "ocr_unavailable"

    png_text = _extract_png_text_chunks(content_bytes) if content_type == "image/png" else []
    if png_text:
        extracted_fragments.extend(png_text)

    if Image is not None and pytesseract is not None:
        try:
            from io import BytesIO

            image = Image.open(BytesIO(content_bytes))
            text = pytesseract.image_to_string(image) or ""
            text = " ".join(text.split())
            if text:
                extracted_fragments.append(text)
                ocr_mode = "ocr_tesseract"
                log_event("attachment_ocr_completed", incident_id=incident_id, tenant_id=tenant_id, attachment_type="image")
            else:
                ocr_mode = "ocr_empty"
                log_event("attachment_ocr_completed", incident_id=incident_id, tenant_id=tenant_id, attachment_type="image")
        except Exception as exc:
            ocr_mode = "ocr_failed"
            log_event("attachment_ocr_failed", incident_id=incident_id, tenant_id=tenant_id, attachment_type="image", error=str(exc))
    else:
        log_event("attachment_ocr_skipped", incident_id=incident_id, tenant_id=tenant_id, attachment_type="image")

    text = _trim_text("\n".join(fragment for fragment in extracted_fragments if fragment))
    combined_signal_text = " ".join([filename, text]).strip()
    error_codes = _unique_matches(_ERROR_CODE_RE, combined_signal_text)
    keywords = _extract_keywords(combined_signal_text)
    suspected_service = _suspected_service(combined_signal_text)
    severity_hints = _severity_hints(combined_signal_text, error_codes)

    evidence = []
    if text:
        evidence.append(f"Screenshot text extracted: {_short_sentence(text, limit=120)}")
    if suspected_service:
        evidence.append(f"Screenshot mentions {suspected_service}.")
    if error_codes:
        evidence.append(f"OCR detected {', '.join(error_codes[:4])}.")
    if not evidence:
        evidence.append("Screenshot stored successfully, but no readable text could be extracted.")

    summary = " ".join(
        part
        for part in [
            "Screenshot processed.",
            f"Extraction mode: {ocr_mode}.",
            f"Signals: {', '.join(error_codes[:4])}." if error_codes else "",
            f"Likely service: {suspected_service}." if suspected_service else "",
        ]
        if part
    ).strip()

    signals = {
        "suspected_service_from_attachment": suspected_service,
        "error_codes_found": error_codes,
        "keywords_found": keywords,
        "severity_hints": severity_hints,
        "ocr_mode": ocr_mode,
    }
    log_event("attachment_signals_extracted", incident_id=incident_id, tenant_id=tenant_id, attachment_type="image")
    return AttachmentRecord(
        attachment_type="image",
        attachment_filename=filename,
        attachment_mime_type=content_type,
        attachment_size_bytes=len(content_bytes),
        attachment_storage_path=storage_path,
        attachment_text_extracted=text,
        attachment_summary=summary,
        evidence_from_attachment=evidence,
        attachment_signals=signals,
        attachment_used=bool(text or error_codes or suspected_service),
        extraction_method=ocr_mode,
    )


def _process_pdf(
    *,
    filename: str,
    content_type: str,
    content_bytes: bytes,
    storage_path: str,
) -> AttachmentRecord:
    extracted_text = ""
    if PdfReader is not None:
        try:
            from io import BytesIO

            reader = PdfReader(BytesIO(content_bytes))
            extracted_text = "\n".join((page.extract_text() or "") for page in reader.pages)
        except Exception:
            extracted_text = ""
    extracted_text = _trim_text(extracted_text)
    return AttachmentRecord(
        attachment_type="pdf",
        attachment_filename=filename,
        attachment_mime_type=content_type,
        attachment_size_bytes=len(content_bytes),
        attachment_storage_path=storage_path,
        attachment_text_extracted=extracted_text,
        attachment_summary="PDF attachment processed." if extracted_text else "PDF attachment stored without extractable text.",
        evidence_from_attachment=["PDF text extracted."] if extracted_text else [],
        attachment_signals={},
        attachment_used=bool(extracted_text),
        extraction_method="pdf_extract" if extracted_text else "stored_only",
    )


def _decode_text(content_bytes: bytes) -> str:
    for encoding in ("utf-8", "latin-1"):
        try:
            return content_bytes.decode(encoding, errors="ignore")
        except Exception:
            continue
    return ""


def _trim_text(text: str, *, limit: int = MAX_TEXT_EXTRACTED) -> str:
    compact = text.strip()
    if len(compact) <= limit:
        return compact
    return compact[: limit - 3] + "..."


def _unique_matches(pattern: re.Pattern[str], text: str) -> list[str]:
    seen: list[str] = []
    for match in pattern.findall(text):
        value = match if isinstance(match, str) else match[0]
        normalized = str(value).strip()
        if normalized and normalized not in seen:
            seen.append(normalized)
    return seen


def _extract_keywords(text: str) -> list[str]:
    lowered = text.lower()
    found: list[str] = []
    for words in _KEYWORD_HINTS.values():
        for word in words:
            if word in lowered and word not in found:
                found.append(word)
    return found[:8]


def _suspected_service(text: str) -> str | None:
    lowered = text.lower()
    for token, service in _SERVICE_HINTS.items():
        if token in lowered:
            return service
    return None


def _severity_hints(text: str, error_codes: list[str]) -> list[str]:
    lowered = text.lower()
    hints: list[str] = []
    for level, words in _KEYWORD_HINTS.items():
        if any(word in lowered for word in words):
            hints.append(level)
    if any(code.startswith("5") for code in error_codes if code and code[0].isdigit()):
        hints.append("high")
    return list(dict.fromkeys(hints))


def _possible_environment(text: str) -> str | None:
    lowered = text.lower()
    if "prod" in lowered or "production" in lowered:
        return "production"
    if "staging" in lowered:
        return "staging"
    if "dev" in lowered:
        return "development"
    return None


def _attachment_kind(content_type: str) -> str:
    if content_type in IMAGE_MIME_TYPES:
        return "image"
    if content_type in TEXTUAL_MIME_TYPES:
        return "log"
    return "unknown"


def _extract_png_text_chunks(content_bytes: bytes) -> list[str]:
    if not content_bytes.startswith(b"\x89PNG\r\n\x1a\n"):
        return []
    texts: list[str] = []
    index = 8
    while index + 8 <= len(content_bytes):
        length = int.from_bytes(content_bytes[index:index + 4], "big")
        chunk_type = content_bytes[index + 4:index + 8]
        data_start = index + 8
        data_end = data_start + length
        if data_end + 4 > len(content_bytes):
            break
        chunk_data = content_bytes[data_start:data_end]
        if chunk_type in {b"tEXt", b"iTXt"}:
            try:
                texts.append(chunk_data.decode("latin-1", errors="ignore").replace("\x00", " "))
            except Exception:
                pass
        index = data_end + 4
        if chunk_type == b"IEND":
            break
    return [text.strip() for text in texts if text.strip()]


def _short_sentence(text: str, *, limit: int) -> str:
    compact = " ".join(text.split())
    if len(compact) <= limit:
        return compact
    return compact[: limit - 3] + "..."
