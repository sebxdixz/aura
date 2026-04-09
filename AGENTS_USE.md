# AGENTS_USE

## 1. Overview

AURA is a **multimodal incident intake and triage system for e-commerce operations**.
It accepts incident reports from a UI, analyzes them with deterministic extraction plus optional model-assisted reasoning, creates a ticket, notifies the technical team, and notifies the original reporter when the incident is resolved.

The project is **production-minded but honestly hackathon-scoped**:

- reproducible with `docker compose up --build`
- mock-first by default
- real Jira, Slack, and reporter email integrations available through configuration
- async worker and resolution watcher included
- OpenTelemetry + Jaeger path included for local trace visibility

## 2. Agent / decision layers

### Layer A: Multimodal intake and evidence extraction

Responsibilities:

- accept incident text plus optional attachment
- validate file type and size
- persist the raw incident immediately
- extract evidence from screenshots, logs, text, JSON, and PDFs

Implementation notes:

- attachment handling is deterministic and auditable
- screenshot OCR is best-effort
- extracted evidence is stored on the incident record

### Layer B: Triage and explainability

Responsibilities:

- score severity
- infer likely service and incident type
- recommend routing target
- generate summary, RCA hypothesis, and recommended investigation
- expose explainability in a reviewer-friendly format

Implementation notes:

- deterministic extraction runs first
- optional model enrichment runs only when configured
- fallback behavior remains deterministic and usable

### Layer C: Repo-grounded context (RAG)

Responsibilities:

- index repository content into pgvector
- retrieve relevant code/doc chunks during triage
- expose repository evidence back into the incident result

Implementation notes:

- tenant-scoped retrieval
- bounded top-k retrieval
- designed to improve grounding, not replace deterministic triage

### Layer D: Multi-ticket intelligence

Responsibilities:

- detect duplicates
- link related incidents
- compute recurrence windows
- derive scope assessment

Implementation notes:

- this is used as context and operator support
- it improves handoff quality and duplicate handling
- it is intentionally visible in the UI instead of being hidden backend logic

### Layer E: Ticketing and team notification

Responsibilities:

- create a ticket
- notify the technical team
- support mock and real provider paths

Implementation notes:

- direct/provider-first execution is available
- optional MCP/ReAct path exists for tool-oriented execution
- fallbacks are explicit rather than silent

### Layer F: Worker, watcher, and reporter notification

Responsibilities:

- process incidents asynchronously
- monitor ticket status through polling
- mark incidents resolved locally
- enqueue reporter notification
- send reporter email through mock or real provider

Implementation notes:

- worker uses a persisted job table
- reporter notification is idempotent
- resolution watcher is polling-first today

## 3. Capabilities

Implemented capabilities:

- UI-based incident intake
- multimodal triage (`text + screenshot/log`)
- repo-grounded context via RAG
- ticket creation
- team notification
- reporter notification on resolution
- async worker processing
- polling-based resolution watcher
- explainability in the UI
- structured logging, metrics, and tracing
- tenant-scoped integrations and RAG sync

## 4. Architecture and orchestration

Core runtime services:

- `web`
  - welcome, login/register, dashboard, tenant intake routes
- `web_dashboard`
  - dashboard-only surface
- `web_report`
  - intake-only surface
- `api`
  - HTTP API and orchestration layer
- `worker`
  - async incident processing and watcher execution
- `db`
  - PostgreSQL + pgvector
- `mcp_bridge`
  - optional MCP execution bridge
- `jaeger`
  - optional local trace UI

Primary flow:

`submit -> persist -> enqueue -> worker triage -> ticket -> notify team -> watch resolution -> notify reporter`

Key orchestration choices:

- submit is fast and non-blocking
- heavy work is offloaded to the worker
- watcher runs through the same job mechanism
- reporter notification stays async and idempotent

## 5. Context engineering

The triage context package is intentionally layered:

- user description
- attachment-derived evidence
- deterministic extracted signals
- retrieved repository context
- related incident context

Why this matters:

- keeps reasoning grounded
- avoids over-reliance on a single LLM call
- preserves useful behavior in mock or fallback mode

Current model behavior is intentionally scoped:

- deterministic extraction always runs
- live model usage is optional
- fallback mode is part of the design, not a hidden degraded path

## 6. Use cases

### Use case A: Customer reports an incident

1. Customer opens `/intake/{tenant}` or the intake-only surface.
2. Customer submits text plus screenshot or log.
3. API validates and stores the incident.
4. Worker performs multimodal triage and creates the ticket.
5. Team notification is sent.

### Use case B: Operator manages incidents

1. Operator logs in from the main app or dashboard surface.
2. Reviews severity, routing, explainability, and related incident context.
3. Resolves an incident with resolution notes.
4. Reporter notification is enqueued and sent asynchronously.

### Use case C: Tenant admin configures context and integrations

1. Admin configures tenant-specific Jira and Slack values.
2. Admin syncs repository content into tenant-scoped RAG.
3. Future incidents benefit from grounded context.

## 7. Observability

### What is implemented

- structured lifecycle logs
- metrics endpoint
- audit logs endpoint
- OpenTelemetry spans
- optional Jaeger UI for local trace inspection

### What can be observed today

- incident submit
- worker job claim and execution
- triage
- RAG retrieval
- ticket creation
- team notification
- watcher sync
- reporter email delivery

### Evidence in the repo

- metrics:
  - [api/app/observability.py](./api/app/observability.py)
- tracing:
  - [api/app/telemetry.py](./api/app/telemetry.py)
- worker spans:
  - [api/app/worker.py](./api/app/worker.py)
  - [api/app/job_handlers.py](./api/app/job_handlers.py)

### Evidence to capture before submission

- Jaeger screenshot showing one incident trace across API and worker
- log sample containing `trace_id` and incident lifecycle stages
- screenshot of `/metrics` or tenant insights output

## 8. Security and guardrails

### What is implemented

- description validation
- file allowlist and size guardrails
- attachment sanitization
- tenant-scoped isolation by `tenant_id`
- admin-key protection for tenant admin endpoints
- constrained tool execution paths

### Evidence in the repo

- guardrails:
  - [api/app/guardrails.py](./api/app/guardrails.py)
- tenant admin verification:
  - [api/app/main.py](./api/app/main.py)
- integration secret handling:
  - [api/app/secrets.py](./api/app/secrets.py)

### Evidence to capture before submission

- screenshot or API sample of invalid admin key rejection
- screenshot or API sample of rejected unsafe attachment/input
- screenshot of tenant-scoped dashboard or incident list proving separation

## 9. Scalability

Current scalability wins:

- stateless API
- persisted job lifecycle
- separate worker
- tenant-scoped data model
- bounded RAG retrieval
- provider abstraction for integrations

Current intentional limits:

- database-backed queue instead of a dedicated broker
- polling-first watcher instead of webhook-first
- local Jaeger instead of a shared tracing backend

These tradeoffs are documented in [SCALING.md](./SCALING.md).

## 10. Lessons learned

- incident intake should persist first and process later
- multimodal evidence is only useful when surfaced back to the operator
- fallback behavior should be explicit and testable
- tenant-scoped RAG is more important than generic retrieval quality
- observability matters more once async worker flow is introduced
- hackathon systems benefit from mock-first defaults and honest real-mode extensions
