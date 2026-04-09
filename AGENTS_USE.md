# AGENTS_USE.md

This document explains how AURA agents are implemented and how they are used in the current version.

## 1. Use Cases

- Intake and triage of incident reports from UI.
- Role-separated frontend:
  - public report portal (`web`, port 3000)
  - operations dashboard (`web_dashboard`, port 3001)
- Conversion of unstructured input into strict structured output.
- Automatic creation of a Jira ticket (real or mock).
- Team notification via Slack webhook (real or mock).
- Reporter notification when incident is marked resolved (mock email, real SMTP TBD).
- Separate worker execution for async triage, ticket sync, and reporter notification.

## 2. Agent Design

### Agent A: Ingestor (Structured Triage)

Responsibilities:

- Validate and sanitize incoming content.
- Accept multimodal payloads (text + attachment).
- Produce strict triage JSON schema with:
  - `severity` + `severity_score` + `severity_rationale`
  - `affected_service`
  - `technical_summary`
  - `root_cause_analysis`
  - `proposed_fix`
  - `proposed_cli_command`
  - `runbook_suggestions`
  - `relevant_files`
  - `is_duplicate` / `duplicate_of_incident_id`
  - `llm_mode`

Current implementation:

- Endpoint: `POST /api/incidents/submit`
- Submit persists incident + attachment metadata, then enqueues `process_incident` for the worker.
- Schema: `api/app/models.py`
- Guardrails: `api/app/guardrails.py`
- RAG retrieval over e-commerce codebase chunks stored in PostgreSQL + pgvector.
- Tenant-scoped GitHub ingestion to vector DB is available via `POST /api/rag/github-sync`
  (no local `git clone`; requires `x-tenant-admin-key`).
- Optional two-stage live path via OpenRouter:
  - Stage 1 extractor model (`OPENROUTER_MULTIMODAL_MODEL`, default `google/gemini-2.5-flash`)
  - Stage 2 analysis model (`OPENROUTER_ANALYSIS_MODEL`) for final triage JSON.

### Agent B: ReAct Orchestrator (Operational Actions)

Responsibilities:

- Create ticket via Jira Cloud API or mock.
- Notify team via Slack Incoming Webhook or mock.
- Notify reporter on resolution.
- Post Slack resolution message when incident is resolved.

Current implementation:

- Ticket tool: `create_ticket` in `api/app/services.py`
  - Routes to `api/app/integrations/jira.py` when `TICKETING_PROVIDER=jira`
- Team notify tool: `notify_team` in `api/app/services.py`
  - Routes to `api/app/integrations/slack.py` when `COMMUNICATOR_PROVIDER=slack`
- Reporter notify tool: `notify_reporter` in `api/app/services.py`
- Slack resolution: `notify_slack_resolved` called automatically on resolve
- Resolution watcher:
  - polling-based `sync_ticket_status` job in worker
  - explicit `map_external_status_to_internal(provider, external_status)`
  - webhook path intentionally left as a future extension
- Optional ReAct mode (`REACT_ENGINE=openrouter_mcp`):
  - planner model via OpenRouter API
  - Jira/Slack action execution via MCP tools
  - fallback to direct providers when MCP/OpenRouter path fails

## 3. Observability Evidence

Current API emits structured logs for stages:

- `incident_ingested`
- `incident_triaged`
- `ticket_created`
- `jira_ticket_created` / `jira_ticket_failed`
- `team_notified`
- `slack_notification_sent` / `slack_notification_failed`
- `incident_resolved`
- `slack_resolved_sent`
- `reporter_notified`
- `job_enqueued`
- `job_claimed`
- `job_started`
- `job_completed`
- `job_failed`
- `job_retried`
- `ticket_status_sync_started`
- `ticket_status_fetched`
- `ticket_status_changed`
- `external_resolution_detected`
- `reporter_resolution_notification_enqueued`
- `reporter_resolution_notification_sent`
- `integration_retry`
- `integration_fallback`
- `tenant_registered`
- `incident_saved`

All events persisted in `audit_logs` table (PostgreSQL).

Where:

- Log function: `api/app/observability.py`
- Metrics endpoint: `GET /metrics`
- Correlation key: `incident_id` (plus `tenant_id` where available)
- OpenTelemetry tracer setup: `api/app/telemetry.py`
- Exporters:
  - `OTEL_EXPORTER_MODE=console` for logs-only tracing
  - `OTEL_EXPORTER_MODE=otlp` for Jaeger via OTLP HTTP
- Operational endpoints:
  - `GET /api/tenants/{tenant_id}/audit-logs`
  - `GET /api/tenants/{tenant_id}/insights/summary`
  - `GET /api/rag/status`
  - `POST /api/rag/reindex`

## 4. Safety Measures

- Input length limits and empty input rejection.
- Prompt-injection keyword detection (basic rule-based).
- File type allowlist and file size max limit.
- Tool allowlist to avoid unauthorized actions (`create_ticket`, `notify_team`, `notify_reporter`).

## 5. Integrations

### Activation

Set in `.env`:

```
# To enable real Jira:
MOCK_MODE=false
TICKETING_PROVIDER=jira
JIRA_BASE_URL=https://your-org.atlassian.net
JIRA_EMAIL=sre@your-org.com
JIRA_API_TOKEN=your-atlassian-api-token
JIRA_PROJECT_KEY=AURA

# To enable real Slack:
COMMUNICATOR_PROVIDER=slack
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/T.../B.../...

# To enable ReAct (OpenRouter + MCP):
REACT_ENGINE=openrouter_mcp
OPENROUTER_API_KEY=...
OPENROUTER_MODEL=openai/gpt-4o-mini
MCP_BRIDGE_URL=http://mcp_bridge:8080/invoke
MCP_JIRA_TOOL=jira_create_issue
MCP_SLACK_TOOL=slack_post_message
# or set MCP_JIRA_URL / MCP_SLACK_URL directly

# MCP Atlassian credentials (required for jira_create_issue):
JIRA_URL=https://your-org.atlassian.net
JIRA_USERNAME=sre@your-org.com
JIRA_API_TOKEN=...
JIRA_PROJECT_KEY=AURA

# MCP Slack credentials (required for slack_post_message):
SLACK_BOT_TOKEN=xoxb-...
SLACK_TEAM_ID=T01234567
SLACK_DEFAULT_CHANNEL_ID=C01234567

# To enable two-stage multimodal triage with OpenRouter:
MOCK_MODE=false
MULTIMODAL_PIPELINE=openrouter_two_stage
OPENROUTER_MULTIMODAL_MODEL=google/gemini-2.5-flash
OPENROUTER_ANALYSIS_MODEL=<stronger_model>
```

### Jira Integration (`api/app/integrations/jira.py`)

- Uses Jira REST API v3 (`POST /rest/api/3/issue`).
- Creates issues with Atlassian Document Format (ADF) rich text body.
- Body includes: severity, RCA, auto-fix, CLI command, tenant labels.
- Severity → Jira Priority mapping: `critical→Highest`, `high→High`, `medium→Medium`, `low→Low`.
- Falls back to mock when `MOCK_MODE=true` or credentials are missing.

### Slack Integration (`api/app/integrations/slack.py`)

- Uses Slack Incoming Webhooks with Block Kit.
- Sends rich alert block with: severity badge, service, ticket link, RCA, auto-fix, CLI, runbook steps.
- Color-coded: red (critical), orange (high), yellow (medium), green (low).
- Sends a separate "✅ Resolved" block when incident is marked resolved.
- Falls back to mock when `MOCK_MODE=true` or `SLACK_WEBHOOK_URL` is missing.

### Reliability

- Retries configurable with `INTEGRATION_RETRIES` and `INTEGRATION_RETRY_DELAY_MS`.
- Worker retries configurable with `WORKER_RETRY_DELAY_SECONDS`; jobs persist `attempts`, `max_attempts`, `run_after`, and `last_error`.
- Polling watcher is idempotent:
  - only resolves locally if incident is not already resolved
  - only enqueues reporter notification if it has not already been sent
- Provider fallback for each integration path:
  - Ticketing: `TICKETING_PROVIDER` → `TICKETING_FALLBACK_PROVIDER`
  - Team communicator: `COMMUNICATOR_PROVIDER` → `COMMUNICATOR_FALLBACK_PROVIDER`
  - Reporter email: `EMAIL_PROVIDER` → `EMAIL_FALLBACK_PROVIDER`

## 6. Multi-Tenant Isolation

- All data scoped to `tenant_id` at storage level (PostgreSQL).
- `GET /api/incidents?tenant_id=X` returns only tenant X's data.
- Dashboard queries use `WHERE tenant_id = :tid` with aggregate filters.
- Audit logs include `tenant_id` on every event.
