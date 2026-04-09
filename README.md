# AURA: Automated Uptime & Resolution Agent

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Hackathon](https://img.shields.io/badge/Hackathon-AgentX-blue)](#)
[![Docker](https://img.shields.io/badge/Docker-Mandatory-2496ED?logo=docker&logoColor=white)](#)

> Submission for `#AgentXHackathon`.
>
> AURA is a multi-tenant B2B SaaS platform for SRE incident triage. Instead of only routing tickets, AURA uses a dual-agent architecture to analyze incidents, enforce strict data schemas, and propose proactive root-cause fixes (Auto-Fix) before engineers begin manual triage.

---

## Project Summary

Incident reports in e-commerce often arrive with incomplete context and vague descriptions. AURA solves this by combining a guided intake experience with AI-powered triage and operational automation.

When a user submits an incident (text + PDF/audio/image/log evidence):

1. **Ingestor Agent** converts unstructured input into strict evidence JSON (Pydantic-ready).
   - Optional live path: `gemini-2.5-flash` (via OpenRouter) extracts multimodal evidence from text/audio/pdf/image.
2. **Analysis Agent** uses extracted evidence + code/document context (RAG) to build technical triage (`severity`, RCA, fix, runbook).
3. **ReAct Agent** routes to tools (Jira/Slack via MCP or direct providers) and closes the loop with notifications.

---

## Architecture Overview

AURA is designed for scale, safety, and precision.

- **Frontend Split by Role (Nginx):** 
  - Admin Dashboard (`/`) protected by strict Tenant ID / Access Key login.
  - Public Intake Portal (`/intake/{tenant}`) for end-users, locked to incident submission without admin access.
- **Backend (FastAPI + Python):** tenant logic, AI agent orchestration, and REST API.
- **Worker (Python):** asynchronous incident processing, ticket status polling, and reporter notification jobs.
- **MCP Bridge (Node.js):** adapter between AURA tool-calls and MCP servers (Jira + Slack).
- **MCP HTTP Bridge (Node.js/Express):** a custom microservice acting as an HTTP-to-Stdio proxy, allowing the containerized FastAPI backend to natively connect with Atlassian and Slack Model Context Protocol (MCP) console servers `npx` binaries.
- **Database (PostgreSQL):** tenant isolation, incident history, and metrics.
- **Vector Store (pgvector on PostgreSQL):** code/document chunks for RAG retrieval.
- **AI Layer (Dual-Agent System):**
  - **Agent 1: Ingestor (LLM + Pydantic):** strict schema output, multimodal handling, guardrails.
  - **Agent 2: ReAct Orchestrator:** tools for ticketing/notifications and Auto-Fix generation via MCP.

---

## Key Features

- **Multi-tenant SaaS architecture:** each company gets an isolated workspace and unique incident URL.
- **Strict structured output:** Pydantic-first pipeline for predictable, system-safe JSON.
- **Proactive Auto-Fix:** root-cause hypotheses with code/command suggestions.
- **Multimodal triage path:** text decoding + PDF extraction + audio transcription (live model mode).
- **Two-stage LLM pipeline (optional):** extraction model + stronger analysis model for better incident reasoning quality.
- **Guardrails:** input sanitization and safe tool usage patterns.
- **Mockable integrations:** stable hackathon demos with ticketing/notifications in `MOCK_MODE`.
- **Optional ReAct Ops mode:** OpenRouter plans actions, MCP tools execute Jira + Slack operations.

---

## Current Implementation Status

- `web`: A monochrome Brutalist frontend divided by Nginx routes:
  - Admin view (`index.html` at `/`) secured by a Tenant Login wrapper.
  - User intake (`intake.html` at `/intake/{tenant}`) completely isolated from dashboard code.
- `mcp-bridge`: Node.js Express server spawning `mcp-server-slack` and `mcp-server-atlassian` as child processes, converting HTTP JSON-RPC payloads to Stdio formatting for the orchestrator.
- File allowlist includes `text/plain`, `application/pdf`, image formats, and common audio types.
- `api` E2E flow:
  - `POST /api/incidents/submit`
  - `POST /api/incidents/{incident_id}/resolve`
  - `GET /api/incidents`
  - `GET /api/incidents/{incident_id}`
  - `GET /api/tenants/{tenant_id}/dashboard`
- Triage output includes RCA and Auto-Fix proposal:
  - `root_cause_analysis`
  - `proposed_fix`
  - `proposed_cli_command`
- Triage output also includes:
  - `severity_score`
  - `severity_rationale`
  - `runbook_suggestions`
  - dedup metadata (`is_duplicate`, `duplicate_of_incident_id`, `dedup_confidence`)
  - model execution marker (`llm_mode`: mock/live/fallback)
- Structured observability through logs and `GET /metrics`.
- Asynchronous processing with a persisted job queue and separate worker service.
- Polling-based resolution watcher for external/mock ticket status sync. Webhooks are intentionally left as a next-step extension.
- OpenTelemetry tracing with console exporter by default and optional OTLP export to Jaeger.
- RAG endpoints:
  - `GET /api/rag/status?tenant_id=<tenant>`
  - `POST /api/rag/reindex?tenant_id=<tenant>` (requires `x-tenant-admin-key`)
  - `POST /api/rag/github-sync` (direct GitHub -> vector DB; no clone; tenant admin only)
- Integrations include retry + fallback strategy (ticketing, communicator, reporter email).
- MCP bridge service included in Docker Compose for Jira/Slack MCP tool dispatch.
- PostgreSQL bootstrap schema under `db/init/001_schema.sql`.
- Playwright API E2E suite available via `npm run test:e2e`.

---

## Setup and Quick Start

For full instructions, see [QUICKGUIDE.md](./QUICKGUIDE.md).

1. **Clone the repository**

```bash
git clone https://github.com/your-username/aura-sre-agent.git
cd aura-sre-agent
```

2. **Configure environment**

```bash
cp .env.example .env
# Fill in API keys and integration settings (OpenAI/OpenRouter, Jira, Slack, etc.)
```

Optional two-stage multimodal triage:

```bash
MULTIMODAL_PIPELINE=openrouter_two_stage
OPENROUTER_API_KEY=<your_key>
OPENROUTER_MULTIMODAL_MODEL=google/gemini-2.5-flash
OPENROUTER_ANALYSIS_MODEL=<stronger_model_on_openrouter>
```

3. **Run with Docker Compose**

```bash
docker compose up --build
```

Optional tracing UI:

- Keep `OTEL_EXPORTER_MODE=console` for simple local trace output in logs.
- Set `OTEL_EXPORTER_MODE=otlp` to export traces to Jaeger.
- Open Jaeger at `http://localhost:16686`.

4. **Optional: swap sample codebase with a real e-commerce repository**

- Replace content under `./ecommerce_repo` (or change `ECOMMERCE_CODEBASE_PATH` mount target).
- Trigger reindex:

```bash
curl -X POST http://localhost:8000/api/rag/reindex
```

5. **Open the app**

5. **Open the app**

- **Frontend / Admins:** `http://localhost` (or the mapped Docker port, e.g. `localhost:3000`)
- **Frontend / Public Intake:** `http://localhost/intake/{tenant_id}`
- **Backend API docs:** `http://localhost:8000/docs`
- **Jaeger UI (optional):** `http://localhost:16686`
- **MCP Bridge:** Runs internally on port `8080` (not exposed directly to users).

---

## Async Processing and Resolution Watcher

- `POST /api/incidents/submit` now stores the incident and enqueues `process_incident` for the worker.
- Jobs persist with lifecycle states `queued`, `running`, `completed`, and `failed`, plus `attempts`, `max_attempts`, `run_after`, and `last_error`.
- Incident processing states are:
  - `submitted`
  - `processing`
  - `triaged`
  - `ticketed`
  - `resolved`
  - `failed`
- Resolution watcher is implemented with polling first:
  - worker schedules `sync_ticket_status`
  - fetches provider/mock status
  - maps external status into internal state
  - resolves the incident locally and enqueues reporter notification exactly once
- Webhook-based resolution is intentionally documented as a future extension, not omitted by accident.

---

## Hackathon Documentation

To comply with the AgentXHackathon deliverables, the repository includes (or should include):

- `README.md`
- `AGENTS_USE.md`
- `SCALING.md`
- `QUICKGUIDE.md`
- `.env.example`
- `docker-compose.yml`
- `LICENSE` (MIT)

---

## Demo Video

Watch the full end-to-end flow here:

- YouTube: `[link pending]`
- Tag: `#AgentXHackathon`

---

## License

This project is licensed under the MIT License. See [LICENSE](./LICENSE).
