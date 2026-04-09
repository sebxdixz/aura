from __future__ import annotations

import base64
import io
import json
import os
from typing import Any

try:
    from pypdf import PdfReader
except Exception:  # pragma: no cover - dependency/runtime guard
    PdfReader = None  # type: ignore[assignment]

try:
    from openai import OpenAI
except Exception:  # pragma: no cover - dependency/runtime guard
    OpenAI = None  # type: ignore[assignment]

from .openrouter import is_openrouter_enabled, openrouter_json_completion


TEXT_LIKE_TYPES = {"text/plain", "text/csv", "application/json"}
AUDIO_TYPES = {
    "audio/wav",
    "audio/x-wav",
    "audio/mpeg",
    "audio/mp3",
    "audio/mp4",
    "audio/x-m4a",
    "audio/webm",
    "audio/ogg",
}
IMAGE_TYPES = {"image/png", "image/jpeg", "image/jpg", "image/webp"}


def is_model_enabled() -> bool:
    if os.getenv("MOCK_MODE", "true").lower() == "true":
        return False
    return bool(os.getenv("OPENAI_API_KEY"))


def is_two_stage_openrouter_enabled() -> bool:
    if os.getenv("MOCK_MODE", "true").lower() == "true":
        return False
    mode = os.getenv("MULTIMODAL_PIPELINE", "legacy").strip().lower()
    if mode not in {"openrouter_two_stage", "two_stage_openrouter"}:
        return False
    return is_openrouter_enabled()


def get_openai_client():
    return _build_client()


def build_attachment_context(
    *,
    filename: str | None,
    content_type: str | None,
    content_bytes: bytes | None,
) -> dict[str, Any]:
    if not filename or not content_type or content_bytes is None:
        return {
            "attachment_type": "none",
            "extraction_method": "none",
            "summary": "No attachment provided.",
            "extracted_text": "",
        }

    if content_type in TEXT_LIKE_TYPES:
        text = _decode_text(content_bytes)
        return {
            "attachment_type": content_type,
            "extraction_method": "decode_text",
            "summary": _shorten(text),
            "extracted_text": text,
        }

    if content_type == "application/pdf":
        extracted = _extract_pdf_text(content_bytes)
        return {
            "attachment_type": content_type,
            "extraction_method": "pdf_extract",
            "summary": _shorten(extracted),
            "extracted_text": extracted,
        }

    if content_type in AUDIO_TYPES:
        transcript = _transcribe_audio(
            filename=filename,
            content_bytes=content_bytes,
        )
        return {
            "attachment_type": content_type,
            "extraction_method": "audio_transcription" if transcript else "audio_not_transcribed",
            "summary": _shorten(transcript) if transcript else "Audio attached. Transcript unavailable in current mode.",
            "extracted_text": transcript,
        }

    # image or unknown supported type
    return {
        "attachment_type": content_type,
        "extraction_method": "metadata_only",
        "summary": f"Attachment received ({content_type}, {len(content_bytes)} bytes).",
        "extracted_text": "",
    }


def generate_model_triage(
    *,
    description: str,
    attachment_context: dict[str, Any],
    code_context: list[dict[str, Any]] | None = None,
) -> dict[str, Any] | None:
    if not is_model_enabled():
        return None

    client = _build_client()
    if client is None:
        return None

    model = os.getenv("OPENAI_TRIAGE_MODEL", "gpt-4o-mini")
    prompt = _triage_prompt(
        description=description,
        attachment_context=attachment_context,
        code_context=code_context or [],
    )

    response = client.chat.completions.create(
        model=model,
        temperature=0.2,
        response_format={"type": "json_object"},
        messages=[
            {
                "role": "system",
                "content": (
                    "You are an SRE triage assistant. Return strict JSON only with keys: "
                    "severity, affected_service, technical_summary, relevant_files, "
                    "root_cause_analysis, proposed_fix, proposed_cli_command, "
                    "severity_score, severity_rationale, runbook_suggestions."
                ),
            },
            {"role": "user", "content": prompt},
        ],
    )

    content = response.choices[0].message.content or "{}"
    parsed = json.loads(content)
    if not isinstance(parsed, dict):
        return None
        
    u_p = getattr(response.usage, "prompt_tokens", 0) if response.usage else 0
    u_c = getattr(response.usage, "completion_tokens", 0) if response.usage else 0
    cost = 0.0
    if "gpt-4o-mini" in model:
        cost = (u_p * 0.150/1_000_000) + (u_c * 0.600/1_000_000)
    parsed["_meta_usage"] = {
        "model": model,
        "prompt_tokens": u_p,
        "completion_tokens": u_c,
        "total_tokens": u_p + u_c,
        "cost_usd": cost,
    }
    return parsed


def generate_two_stage_triage(
    *,
    description: str,
    attachment_context: dict[str, Any],
    attachment_filename: str | None = None,
    attachment_content_type: str | None = None,
    attachment_bytes: bytes | None = None,
    code_context: list[dict[str, Any]] | None = None,
) -> dict[str, Any] | None:
    if not is_two_stage_openrouter_enabled():
        return None

    extractor_model = _extractor_model()
    analysis_model = _analysis_model()
    evidence_payload = _attachment_for_prompt(attachment_context)
    image_data_url = _image_data_url(attachment_content_type, attachment_bytes)
    audio_input = _audio_input(attachment_content_type, attachment_bytes)

    extraction = openrouter_json_completion(
        model=extractor_model,
        temperature=0.1,
        system_prompt=(
            "You are a multimodal SRE incident extraction agent. "
            "Extract factual evidence only. Return strict JSON without markdown."
        ),
        user_prompt=_stage1_prompt(
            description=description,
            attachment_filename=attachment_filename,
            attachment_content_type=attachment_content_type,
            evidence_payload=evidence_payload,
        ),
        image_data_url=image_data_url,
        audio_input=audio_input,
    )
    if not isinstance(extraction, dict):
        return None

    analysis = openrouter_json_completion(
        model=analysis_model,
        temperature=0.2,
        system_prompt=(
            "You are a senior SRE triage analyst. "
            "Use extracted facts plus code context to produce operational triage JSON. "
            "Return strict JSON only."
        ),
        user_prompt=_stage2_prompt(
            description=description,
            extraction=extraction,
            code_context=code_context or [],
        ),
    )
    if not isinstance(analysis, dict):
        return None

    analysis["llm_mode"] = "multimodal_two_stage_openrouter"
    
    # Merge meta usage
    ext_meta = extraction.pop("_meta_usage", {})
    ana_meta = analysis.pop("_meta_usage", {})
    if ext_meta or ana_meta:
        analysis["_meta_usage"] = {
            "model": f"{ext_meta.get('model','')}, {ana_meta.get('model','')}",
            "prompt_tokens": ext_meta.get("prompt_tokens",0) + ana_meta.get("prompt_tokens",0),
            "completion_tokens": ext_meta.get("completion_tokens",0) + ana_meta.get("completion_tokens",0),
            "total_tokens": ext_meta.get("total_tokens",0) + ana_meta.get("total_tokens",0),
            "cost_usd": ext_meta.get("cost_usd",0) + ana_meta.get("cost_usd",0),
        }
    return analysis


def _build_client():
    if OpenAI is None:
        return None
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return None
    base_url = os.getenv("OPENAI_BASE_URL")
    if base_url:
        return OpenAI(api_key=api_key, base_url=base_url)
    return OpenAI(api_key=api_key)


def _decode_text(content_bytes: bytes) -> str:
    for encoding in ("utf-8", "latin-1"):
        try:
            return content_bytes.decode(encoding, errors="ignore")
        except Exception:
            continue
    return ""


def _extract_pdf_text(content_bytes: bytes) -> str:
    if PdfReader is None:
        return "PDF attached but extraction library is unavailable."
    try:
        reader = PdfReader(io.BytesIO(content_bytes))
        texts = []
        for page in reader.pages:
            texts.append(page.extract_text() or "")
        joined = "\n".join(t for t in texts if t).strip()
        return joined or "PDF attached but no extractable text found."
    except Exception:
        return "PDF attached but extraction failed."


def _transcribe_audio(*, filename: str, content_bytes: bytes) -> str:
    if not is_model_enabled():
        return ""
    client = _build_client()
    if client is None:
        return ""
    model = os.getenv("OPENAI_TRANSCRIPTION_MODEL", "gpt-4o-mini-transcribe")
    try:
        file_obj = io.BytesIO(content_bytes)
        file_obj.name = filename or "audio.wav"
        transcript = client.audio.transcriptions.create(model=model, file=file_obj)
        text = getattr(transcript, "text", "")
        return text or ""
    except Exception:
        return ""


def _triage_prompt(
    *,
    description: str,
    attachment_context: dict[str, Any],
    code_context: list[dict[str, Any]],
) -> str:
    return (
        "Analyze this incident and produce triage JSON.\n\n"
        f"Description:\n{description}\n\n"
        f"Attachment context:\n{json.dumps(attachment_context, ensure_ascii=True)}\n\n"
        f"Codebase context (RAG):\n{json.dumps(code_context, ensure_ascii=True)}\n\n"
        "Rules:\n"
        "- severity must be one of: low, medium, high, critical.\n"
        "- severity_score is integer 0..100.\n"
        "- relevant_files and runbook_suggestions must be arrays.\n"
    )


def _stage1_prompt(
    *,
    description: str,
    attachment_filename: str | None,
    attachment_content_type: str | None,
    evidence_payload: dict[str, Any],
) -> str:
    return (
        "Normalize the incident input into structured evidence.\n\n"
        "Return JSON with exactly these keys:\n"
        "{\n"
        '  "incident_facts": {\n'
        '    "symptom": "string",\n'
        '    "suspected_service": "string",\n'
        '    "error_signals": ["string"],\n'
        '    "impact": "string",\n'
        '    "urgency_hint": "low|medium|high|critical"\n'
        "  },\n"
        '  "multimodal_evidence": [\n'
        '    {"source": "description|attachment", "type": "text|pdf|audio|image|unknown", "detail": "string"}\n'
        "  ],\n"
        '  "missing_data": ["string"],\n'
        '  "confidence": 0.0\n'
        "}\n\n"
        "Incident description:\n"
        f"{_trim_prompt_text(description, limit=2500)}\n\n"
        "Attachment metadata:\n"
        f"filename={attachment_filename or 'none'}\n"
        f"content_type={attachment_content_type or 'none'}\n\n"
        "Attachment extracted context:\n"
        f"{json.dumps(evidence_payload, ensure_ascii=True)}\n\n"
        "Rules:\n"
        "- If an image is attached, inspect it and include image evidence details.\n"
        "- Keep details concise and factual.\n"
    )


def _stage2_prompt(
    *,
    description: str,
    extraction: dict[str, Any],
    code_context: list[dict[str, Any]],
) -> str:
    return (
        "Produce final SRE triage JSON from normalized evidence and code context.\n\n"
        "Return strict JSON with keys:\n"
        "- severity\n"
        "- affected_service\n"
        "- technical_summary\n"
        "- relevant_files\n"
        "- root_cause_analysis\n"
        "- proposed_fix\n"
        "- proposed_cli_command\n"
        "- severity_score\n"
        "- severity_rationale\n"
        "- runbook_suggestions\n\n"
        "Incident description:\n"
        f"{_trim_prompt_text(description, limit=2500)}\n\n"
        "Extractor output:\n"
        f"{json.dumps(extraction, ensure_ascii=True)}\n\n"
        "Codebase context (RAG):\n"
        f"{json.dumps(code_context, ensure_ascii=True)}\n\n"
        "Rules:\n"
        "- severity must be low|medium|high|critical.\n"
        "- severity_score must be integer 0..100.\n"
        "- relevant_files and runbook_suggestions must be arrays.\n"
        "- Prefer files present in code_context.\n"
    )


def _extractor_model() -> str:
    value = os.getenv("OPENROUTER_MULTIMODAL_MODEL", "google/gemini-2.5-flash").strip()
    return value or "google/gemini-2.5-flash"


def _analysis_model() -> str:
    value = os.getenv("OPENROUTER_ANALYSIS_MODEL", "").strip()
    if value:
        return value
    fallback = os.getenv("OPENROUTER_MODEL", "openai/gpt-4o-mini").strip()
    return fallback or "openai/gpt-4o-mini"


def _attachment_for_prompt(attachment_context: dict[str, Any]) -> dict[str, Any]:
    extracted_text = _trim_prompt_text(str(attachment_context.get("extracted_text", "")), limit=6000)
    summary = _trim_prompt_text(str(attachment_context.get("summary", "")), limit=1000)
    return {
        "attachment_type": str(attachment_context.get("attachment_type", "none")),
        "extraction_method": str(attachment_context.get("extraction_method", "none")),
        "summary": summary,
        "extracted_text": extracted_text,
    }


def _image_data_url(content_type: str | None, content_bytes: bytes | None) -> str | None:
    if not content_type or content_bytes is None:
        return None
    normalized = content_type.lower().strip()
    if normalized not in IMAGE_TYPES:
        return None
    encoded = base64.b64encode(content_bytes).decode("ascii")
    return f"data:{normalized};base64,{encoded}"


def _audio_input(content_type: str | None, content_bytes: bytes | None) -> dict[str, str] | None:
    if not content_type or content_bytes is None:
        return None
    normalized = content_type.lower().strip()
    format_hint = _audio_format_hint(normalized)
    if not format_hint:
        return None
    encoded = base64.b64encode(content_bytes).decode("ascii")
    return {"format": format_hint, "data": encoded}


def _audio_format_hint(content_type: str) -> str | None:
    mapping = {
        "audio/wav": "wav",
        "audio/x-wav": "wav",
        "audio/mpeg": "mp3",
        "audio/mp3": "mp3",
        "audio/mp4": "mp4",
        "audio/x-m4a": "mp4",
        "audio/webm": "webm",
        "audio/ogg": "ogg",
    }
    return mapping.get(content_type)


def _trim_prompt_text(text: str, limit: int) -> str:
    compact = " ".join((text or "").split())
    if len(compact) <= limit:
        return compact
    return compact[: limit - 3] + "..."


def _shorten(text: str, limit: int = 400) -> str:
    compact = " ".join((text or "").split())
    if len(compact) <= limit:
        return compact
    return compact[: limit - 3] + "..."
