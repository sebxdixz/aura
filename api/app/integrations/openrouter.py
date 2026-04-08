from __future__ import annotations

import json
import os
from typing import Any

try:
    from openai import OpenAI
except Exception:  # pragma: no cover - dependency/runtime guard
    OpenAI = None  # type: ignore[assignment]


def is_openrouter_enabled() -> bool:
    return bool(os.getenv("OPENROUTER_API_KEY", "").strip())


def get_openrouter_client():
    if OpenAI is None:
        return None
    api_key = os.getenv("OPENROUTER_API_KEY", "").strip()
    if not api_key:
        return None
    base_url = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1").strip()
    return OpenAI(api_key=api_key, base_url=base_url)


def openrouter_json_completion(
    *,
    model: str,
    system_prompt: str,
    user_prompt: str,
    image_data_url: str | None = None,
    audio_input: dict[str, str] | None = None,
    temperature: float = 0.1,
) -> dict[str, Any] | None:
    client = get_openrouter_client()
    if client is None:
        return None

    user_content: Any = user_prompt
    if image_data_url or audio_input:
        user_content = [{"type": "text", "text": user_prompt}]
        if image_data_url:
            user_content.append({"type": "image_url", "image_url": {"url": image_data_url}})
        if audio_input:
            user_content.append({"type": "input_audio", "input_audio": audio_input})

    try:
        response = client.chat.completions.create(
            model=model,
            temperature=temperature,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
        )
        content = response.choices[0].message.content or "{}"
        parsed = json.loads(content)
        if isinstance(parsed, dict):
            return parsed
    except Exception:
        return None
    return None


def plan_react_actions(context: dict[str, Any]) -> dict[str, Any] | None:
    model = os.getenv("OPENROUTER_MODEL", "openai/gpt-4o-mini").strip() or "openai/gpt-4o-mini"
    prompt = _build_prompt(context)
    return openrouter_json_completion(
        model=model,
        temperature=0.1,
        system_prompt=(
            "You are a ReAct SRE orchestrator. "
            "Return strict JSON only. "
            "Do not include markdown."
        ),
        user_prompt=prompt,
    )


def _build_prompt(context: dict[str, Any]) -> str:
    return (
        "Create an action plan for two MCP tool calls: Jira ticket + Slack notify.\n\n"
        "Return JSON with exactly this schema:\n"
        "{\n"
        '  "reasoning": "short reason",\n'
        '  "ticket_tool": {\n'
        '    "server": "jira",\n'
        '    "tool": "create_issue",\n'
        '    "arguments": { ... }\n'
        "  },\n"
        '  "slack_tool": {\n'
        '    "server": "slack",\n'
        '    "tool": "post_message",\n'
        '    "arguments": { ... }\n'
        "  }\n"
        "}\n\n"
        "Context:\n"
        f"{json.dumps(context, ensure_ascii=True)}\n\n"
        "Rules:\n"
        "- Keep arguments concise.\n"
        "- Ensure severity and service are included in both tools.\n"
        "- Include incident_id and tenant_id.\n"
    )
