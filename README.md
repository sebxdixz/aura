# AURA

AURA is an incident intake and triage system for e-commerce operations.

It accepts incident reports with:

- text only
- text + screenshot
- text + log

It then turns that report into an operational output:

- structured triage
- severity and routing
- repository-grounded technical context
- multi-ticket correlation and recurrence
- ticket creation
- team notification
- reporter notification on resolution

## What Problem AURA Solves

Incident reports are usually incomplete, noisy, and hard to route quickly.

AURA improves that by:

- extracting evidence from attachments
- grounding analysis in code/docs via RAG
- producing explainable triage output
- separating fast intake from heavy background processing
- watching ticket state until resolution

The goal is not to be a generic chatbot.
The goal is to be a defendable incident pipeline.

## Core Flow

1. User submits an incident through the intake UI.
2. API validates input and stores the incident immediately.
3. API enqueues async incident processing.
4. Worker processes attachment, triage, RAG, multi-ticket intelligence, ticketing, and team notify.
5. Dashboard shows the commander-style incident view.
6. Worker polls ticket status.
7. If the external/mock ticket resolves, AURA resolves the local incident and notifies the original reporter.

## Architecture

### Services

- `web`
  - public intake portal
- `web_dashboard`
  - operations dashboard
- `api`
  - FastAPI entrypoint, validation, persistence, orchestration start
- `worker`
  - async incident processing and ticket watcher
- `db`
  - PostgreSQL + pgvector
- `mcp_bridge`
  - MCP bridge for Jira/Slack tool execution
- `jaeger`
  - optional tracing UI

### Why the Worker Matters

The worker exists so that `submit` is fast and heavy work is retryable.

Without it, one request would block on:

- attachment processing
- triage
- RAG
- ticket creation
- team notification

With it:

- submit is quick
- failures are isolated
- retries are explicit
- observability covers jobs as first-class operations

## Triage Design

AURA uses a layered triage pipeline instead of a single freeform LLM call.

### Stages

1. input normalization
2. attachment evidence extraction
3. structured entity extraction
4. repository/document retrieval
5. severity scoring
6. routing decision
7. multi-ticket intelligence
8. ticket payload generation
9. validation and fallback

### Why This Matters

This gives:

- more control
- better explainability
- clearer observability
- safer multimodal handling

## Multi-Ticket Intelligence

AURA does not only classify a single incident in isolation.

It also detects:

- related incidents
- duplicates
- recurrence over 7d/30d
- cluster membership
- scope implications from repeated patterns

This influences:

- explainability
- scope assessment
- operator context
- ticket payload

## Observability

AURA has two layers of observability:

### 1. Custom operational observability

- structured logs
- metrics endpoint
- audit logs persisted to PostgreSQL

### 2. Formal tracing

- OpenTelemetry instrumentation
- console exporter by default
- optional OTLP export to Jaeger

Examples of traced stages:

- `api.submit_incident`
- `worker.process_incident`
- `triage.run`
- `rag.retrieve_context`
- `ticket.create`
- `notify.team`
- `worker.sync_ticket_status`
- `worker.notify_reporter`

## Resolution Watcher

Current implementation is intentionally:

- polling-first

This means:

- worker periodically syncs external/mock ticket status
- state is mapped into internal incident state
- if ticket becomes resolved, AURA resolves locally and notifies the reporter

Webhook support is intentionally left as the next extension, not forgotten.

## Mock vs Real

### Demo-safe defaults

By default:

- ticketing is mock
- communicator is mock
- reporter email is mock
- watcher logic is real but can use mock ticket state
- tracing is real

### Real integrations

You can enable real providers through `.env`:

- Jira
- Slack
- OpenRouter/OpenAI model paths
- MCP-backed operations

## Tech Stack

- Frontend: HTML + JS + Nginx
- API: FastAPI + Pydantic + SQLAlchemy
- Worker: Python process with persisted job queue
- Database: PostgreSQL + pgvector
- Tracing: OpenTelemetry
- Trace viewer: Jaeger
- Optional providers: Jira, Slack, OpenAI/OpenRouter, MCP bridge

## How to Run

### 1. Copy environment

```bash
cp .env.example .env
```

### 2. Choose trace exporter mode

In `.env`:

```env
OTEL_EXPORTER_MODE=console
```

or:

```env
OTEL_EXPORTER_MODE=otlp
```

### 3. Start the stack

```bash
docker compose up --build
```

### 4. Open the services

- Intake: [http://localhost:3000/intake/hackathon-demo](http://localhost:3000/intake/hackathon-demo)
- Dashboard: [http://localhost:3001/?tenant_id=hackathon-demo](http://localhost:3001/?tenant_id=hackathon-demo)
- API docs: [http://localhost:8000/docs](http://localhost:8000/docs)
- Metrics: [http://localhost:8000/metrics](http://localhost:8000/metrics)
- Jaeger: [http://localhost:16686](http://localhost:16686)

For a more step-by-step runbook, see [QUICKGUIDE.md](./QUICKGUIDE.md).

## Demo Script

### Best incident for demo

Use a checkout/payment case with clear backend failure evidence.

Description:

```text
Customers cannot complete payment in checkout. We are seeing HTTP 500 in production after clicking Pay. No workaround confirmed yet.
```

Attachment:

```text
2026-04-09T20:10:00Z ERROR checkout-service payment failed HTTP 500
2026-04-09T20:10:01Z ERROR payment-service gateway timeout
environment=production
```

### What to show

1. fast async submit
2. worker-driven completion
3. score breakdown
4. routing decision
5. attachment evidence
6. RAG evidence
7. related incidents / recurrence if present
8. Jaeger trace

## Key Delivery Documents

- [AGENTS_USE.md](./AGENTS_USE.md)
- [QUICKGUIDE.md](./QUICKGUIDE.md)
- [SCALING.md](./SCALING.md)
- [.env.example](./.env.example)
- [docker-compose.yml](./docker-compose.yml)

## Validation

Backend compilation:

```bash
python -m compileall api/app tests
```

Optional Playwright API E2E:

```bash
npm install
npx playwright install chromium
npm run test:e2e
```

## License

MIT. See [LICENSE](./LICENSE).
