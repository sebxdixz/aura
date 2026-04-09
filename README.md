# AURA

**AURA is a multimodal incident intake and triage system for e-commerce teams.**  
It accepts customer incident reports from a UI, analyzes them with structured triage plus repo-grounded context, creates a ticket, notifies the technical team, and notifies the original reporter when the incident is resolved.

## Why this project is strong

AURA is not just a form plus a model call. It implements the full incident loop:

- UI-based incident intake
- multimodal evidence handling (`text + screenshot/log`)
- triage with explainability
- repo/docs context via RAG
- ticket creation
- team notification
- async worker processing
- polling-based resolution watcher
- reporter notification on resolution
- observability with structured logs and OpenTelemetry

It is **production-minded but honestly scoped for a hackathon**:

- mock integrations are available by default for reproducibility
- real Jira, Slack, and reporter email paths are supported through configuration
- the queue is a database-backed job table rather than an external broker
- resolution watcher is polling-first today, webhook-first is documented as a next step

## Problem

E-commerce incident reporting is often fragmented:

- customers send incomplete incident reports
- screenshots and logs are not normalized into useful evidence
- triage lacks repo-specific context
- the handoff to engineering is manual or inconsistent
- reporter follow-up is easy to forget after a ticket is resolved

AURA turns that into a single, auditable flow.

## What AURA does end-to-end

1. A customer or operator submits an incident from the UI.
2. AURA validates the input and stores the incident immediately.
3. A worker processes the incident asynchronously.
4. The worker extracts multimodal evidence from the attachment.
5. The triage layer scores severity, recommends routing, and generates explainable output.
6. RAG pulls relevant code or docs context from the configured e-commerce repo.
7. Multi-ticket intelligence checks for duplicates, related incidents, and recurrence.
8. AURA creates a ticket and notifies the technical team.
9. A polling-based watcher monitors ticket status.
10. When the ticket is resolved, AURA enqueues reporter notification and sends it through the configured email provider.

## Architecture

### Runtime services

- `web` on `http://localhost:3000`
  - welcome flow
  - login/register
  - admin dashboard
  - tenant intake routes
- `web_dashboard` on `http://localhost:3001`
  - focused dashboard/admin surface
- `web_report` on `http://localhost:3002`
  - focused public intake surface
- `api` on `http://localhost:8000`
  - FastAPI backend
  - incident APIs
  - triage orchestration
  - integrations
- `worker`
  - async incident processing
  - ticket resolution watcher
  - reporter notification delivery
- `db`
  - PostgreSQL + pgvector
  - incidents, jobs, audit logs, vector chunks
- `mcp_bridge`
  - optional MCP tool bridge for Jira/Slack workflows
- `jaeger`
  - optional local trace UI when OTLP export is enabled

### Processing model

- **submit path:** fast, persistence-first, queues work
- **worker path:** attachment processing, triage, multi-ticket analysis, ticketing, team notification
- **watcher path:** polling sync of ticket state, local resolution propagation, reporter notification enqueue

## Major features

### Multimodal incident intake

- UI-based incident submission
- text description plus optional file
- screenshot, log, text, JSON, and PDF handling
- attachment evidence extraction stored with the incident

### Triage with explainability

- severity scoring
- routing recommendation
- summary, RCA hypothesis, and recommended investigation
- score breakdown and visible reasoning in the UI

### Repo-grounded context via RAG

- tenant-scoped repository indexing into pgvector
- retrieval of relevant code/doc chunks during triage
- visible RAG evidence in the result output

### Multi-ticket intelligence

- duplicate detection
- related incident linking
- recurrence counts
- scope assessment
- operator-facing summary in the result UI

### Guardrails and tenant isolation

- input and file validation
- tenant-scoped admin access
- tenant-scoped RAG and integration settings
- explicit mock vs real integration control

### Async architecture

- `POST /api/incidents/submit` returns quickly
- job lifecycle is persisted in the database
- job states include `queued`, `running`, `completed`, and `failed`
- worker handles heavy processing
- retries use the existing job lifecycle

### Resolution watcher

- polling-first ticket sync
- external/mock ticket state mapped to internal incident state
- idempotent reporter notification enqueue on resolution

### Observability

- structured lifecycle logs
- audit logs
- metrics endpoint
- OpenTelemetry spans
- Jaeger UI available locally when OTLP mode is enabled

## Mock vs real integrations

| Capability | Default local mode | Real mode |
|---|---|---|
| Ticketing | `mock-jira` | Jira |
| Team notification | `mock-slack` | Slack |
| Reporter notification | `mock-email` | Resend |
| LLM path | mock / deterministic fallback | OpenAI or OpenRouter |
| Tracing export | console | OTLP -> Jaeger |

This matters for evaluation:

- **AURA runs in mock mode with no external credentials**
- **the real integration paths are configurable and implemented**
- documentation explicitly distinguishes the two

## Local run

### Fastest path

1. Copy the environment template:
   - `cp .env.example .env`
2. Keep the default mock values unless you want real integrations.
3. Start the stack:
   - `docker compose up --build`
4. Open:
   - `http://localhost:3000`

Default demo tenant credentials after creating or using tenant `demo`:

- tenant id: `demo`
- admin key: `change-me`

### Key URLs

- Main app: `http://localhost:3000`
- Dashboard-only view: `http://localhost:3001`
- Intake-only view: `http://localhost:3002/intake/demo`
- API health: `http://localhost:8000/health`
- Jaeger UI: `http://localhost:16686`

## Demo-oriented main flow

### Reporter / intake flow

1. Open `http://localhost:3002/intake/demo`
2. Submit a description plus a screenshot or log
3. Watch AURA return a structured incident result

### Admin flow

1. Open `http://localhost:3000`
2. Register or log into a tenant
3. Review incidents, routing, severity, and explainability
4. Resolve an incident with resolution notes
5. Let the worker send the reporter notification

## Optional real integrations

### Jira

- Set `MOCK_MODE=false`
- Set `TICKETING_PROVIDER=jira`
- Configure Jira credentials in `.env` or tenant settings

### Slack

- Set `COMMUNICATOR_PROVIDER=slack`
- Configure Slack webhook/token values

### Reporter email

- Set `EMAIL_PROVIDER=resend`
- Configure:
  - `EMAIL_RESEND_API_KEY`
  - `EMAIL_FROM`
  - `EMAIL_FROM_NAME`

## Optional Jaeger tracing

By default, AURA writes spans to logs:

- `OTEL_EXPORTER_MODE=console`

To view traces in Jaeger:

1. Set:
   - `OTEL_EXPORTER_MODE=otlp`
2. Start the stack:
   - `docker compose up --build`
3. Open:
   - `http://localhost:16686`

The compose stack already includes Jaeger; switching the exporter mode is enough.

## Current limitations / honest scope

- the queue is a database-backed job table, not Kafka/Celery/RabbitMQ
- resolution watcher is polling-first, not webhook-first
- real provider coverage is intentionally narrow:
  - Jira
  - Slack
  - Resend
- the stack is optimized for reproducibility and review, not full production hardening

These are deliberate tradeoffs for a hackathon submission, and each has a documented upgrade path in [SCALING.md](./SCALING.md).

## Documentation map

- [QUICKGUIDE.md](./QUICKGUIDE.md)
  - shortest path to run and validate the app
- [AGENTS_USE.md](./AGENTS_USE.md)
  - evaluation-facing architecture and agent documentation
- [SCALING.md](./SCALING.md)
  - honest scaling plan and architectural tradeoffs
- [MCP.md](./MCP.md)
  - MCP bridge and tool integration notes
- [BACKLOG.md](./BACKLOG.md)
  - remaining work and backlog items
