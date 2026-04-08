from __future__ import annotations

import json
import os
import re
from typing import Any
from urllib import error as urllib_error
from urllib import request as urllib_request


def call_mcp_tool(server: str, tool: str, arguments: dict[str, Any]) -> dict[str, Any]:
    server_url = _server_specific_url(server)
    bridge_url = os.getenv("MCP_BRIDGE_URL", "").strip()
    token = os.getenv("MCP_BRIDGE_TOKEN", "").strip()

    if server_url:
        url = server_url
        payload: dict[str, Any] = {"tool": tool, "arguments": arguments}
    else:
        if not bridge_url:
            raise RuntimeError("MCP bridge is not configured (set MCP_BRIDGE_URL or MCP_<SERVER>_URL)")
        url = bridge_url
        payload = {"server": server, "tool": tool, "arguments": arguments}

    body = json.dumps(payload).encode("utf-8")
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    req = urllib_request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib_request.urlopen(req, timeout=20) as resp:
            parsed = json.loads(resp.read().decode("utf-8"))
            return _normalize_mcp_response(parsed)
    except urllib_error.HTTPError as exc:
        body_text = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"MCP HTTP {exc.code}: {body_text}") from exc
    except OSError as exc:
        raise RuntimeError(f"MCP connection error: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"MCP invalid JSON response: {exc}") from exc


def _normalize_mcp_response(payload: Any) -> dict[str, Any]:
    if isinstance(payload, dict):
        if payload.get("ok") is False:
            raise RuntimeError(str(payload.get("error") or "MCP tool failed"))
        result = payload.get("result")
        if isinstance(result, dict):
            return result
        return payload
    raise RuntimeError("MCP response format is invalid")


def _server_specific_url(server: str) -> str:
    env_name = "MCP_" + re.sub(r"[^A-Za-z0-9]", "_", server.upper()) + "_URL"
    return os.getenv(env_name, "").strip()

