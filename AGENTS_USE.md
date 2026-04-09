# AGENTS_USE.md

This document explains how AURA uses agents, orchestration, context, observability, and safety in the current version.

## 1. Overview

AURA is an incident intake and triage system for e-commerce operations.

It accepts:

- text-only incidents
- text + screenshot
- text + log

It then:

1. validates and stores the incident
2. processes attachment evidence
3. runs structured triage
4. enriches with repository/document context
5. adds multi-ticket intelligence
6. creates or simulates a ticket
7. notifies the team
8. watches ticket status
9. notifies the original reporter when resolved

## 2. Agent and Capability Model

### Agent A: Intake + Structured Triage

Responsibilities:

- validate description and attachment
- normalize the incident input
- extract structured entities
- combine deterministic rules with optional model enrichment
- produce explainable `TriageOutput`

Core outputs:

- `severity`
- `severity_score`
- `severity_reasoning`
- `affected_service`
- `incident_type`
- `target_team`
- `routing_reasoning`
- `confidence`
- `description_score`
- `attachment_score`
- `criticality_score`
- `rag_evidence`
- `related_incident_ids`
- `cluster_id`
- `recurrence_count_7d`
- `recurrence_count_30d`

### Agent B: Operational Orchestrator

Responsibilities:

- create ticket through provider or mock path
- notify technical team
- watch ticket status
- notify reporter on resolution

Current implementation is not a freeform agent loop.
It is a controlled orchestration layer around explicit functions and provider integrations.

## 3. Architecture and Orchestration

### Services

- `web`: public intake UI
- `web_dashboard`: operator dashboard
- `api`: HTTP API and orchestration entrypoints
- `worker`: async processing and watcher execution
- `db`: PostgreSQL + pgvector
- `mcp_bridge`: bridge for MCP-backed Jira/Slack tooling
- `jaeger`: optional trace viewer

### Orchestration model

Current flow:

1. API receives incident submit
2. API validates and persists the incident
3. API enqueues `process_incident`
4. worker claims the job
5. worker runs multimodal processing -> triage -> multi-ticket -> ticket -> notify
6. worker schedules or executes `sync_ticket_status`
7. if provider/mock ticket resolves, worker updates local incident
8. worker enqueues and sends reporter notification

This is intentionally:

- asynchronous
- persisted
- explainable
- retryable

## 4. Context Engineering

AURA does not rely on only the user text.

It builds context from:

- normalized description
- attachment OCR / parsed log signals
- extracted structured entities
- repository/document retrieval via RAG
- incident history and related incidents

RAG is used to surface:

- relevant files
- runbooks
- service hints
- matched repository paths

This context directly influences:

- severity reasoning
- routing
- technical summary
- runbook suggestions
- confidence

## 5. Use Cases

Primary use cases:

- checkout/payment outage reports
- authentication failures
- degraded performance signals
- repeated incidents that belong to the same pattern
- multimodal intake where screenshot/log evidence changes triage

Operator use cases:

- view a commander-style incident brief
- inspect evidence and score breakdown
- see related incidents and recurrence
- follow worker-driven processing instead of waiting on inline submit

## 6. Observability with Evidence

### What is instrumented

Structured logs:

- intake stages
- attachment validation and processing
- triage stages
- RAG stages
- job lifecycle
- ticket creation
- team notification
- ticket status sync
- external resolution detection
- reporter notification

Examples of emitted stages:

- `incident_ingested`
- `job_enqueued`
- `job_claimed`
- `job_started`
- `triage_started`
- `rag_context_retrieved`
- `ticket_created`
- `team_notified`
- `ticket_status_sync_started`
- `ticket_status_fetched`
- `external_resolution_detected`
- `reporter_resolution_notification_sent`

### Metrics

Exposed via `GET /metrics`:

- stage counters
- severity counters
- attachment counters
- fallback / LLM counters
- triage durations
- worker retry counts
- ticket sync failure counts

### Tracing

OpenTelemetry is configured in:

- `api/app/telemetry.py`

Current span coverage includes:

- `api.submit_incident`
- `api.resolve_incident`
- `worker.claim_job`
- `worker.run_job`
- `worker.process_incident`
- `worker.sync_ticket_status`
- `worker.notify_reporter`
- `triage.run`
- `rag.retrieve_context`
- `ticket.create`
- `notify.team`
- `notify.reporter`
- Jira create/status fetch
- Slack notify

### Evidence

Tracing can be shown in two ways:

- `OTEL_EXPORTER_MODE=console`
  - spans appear in logs
- `OTEL_EXPORTER_MODE=otlp`
  - spans are exported to Jaeger
  - open [http://localhost:16686](http://localhost:16686)

Correlation:

- `incident_id`
- `tenant_id`
- `trace_id` when available

## 7. Security with Evidence

### Guardrails in current build

- description validation
- attachment MIME/type allowlist
- attachment size limits
- prompt-injection heuristics
- tool allowlist
- no execution of uploaded artifacts

### Important design rule

Attachments are treated as:

- evidence

not as:

- instructions

This applies to:

- OCR text from screenshots
- raw log content
- parsed attachment text

### Security evidence in code

- `api/app/guardrails.py`
- `api/app/attachments.py`
- `api/app/services.py`

## 8. Scalability

The current architecture is intentionally simple but scales conceptually in the right direction.

Already present:

- separate worker
- persisted jobs
- polling watcher
- tenant-scoped persistence
- RAG in PostgreSQL + pgvector
- OpenTelemetry hooks

Natural next steps:

- webhook-first watcher with polling fallback
- dedicated queue backend
- centralized tracing backend
- stronger attachment scanning
- higher-volume RAG indexing pipelines

See [SCALING.md](./SCALING.md) for the detailed plan.

## 9. Lessons Learned

The biggest lessons from building AURA were:

- multimodality only matters if it visibly changes the result
- a controlled pipeline is stronger than a freeform chatbot
- observability must cover the async path, not only the request path
- polling-first is a good delivery choice when webhook setup would slow execution
- score breakdown and reasoning matter almost as much as the prediction itself
- related-incident context makes the system feel much more operationally mature

## 10. What Is Real vs Mock

By default the project is demo-safe:

- ticketing: mock by default
- communicator: mock by default
- reporter email: mock by default
- watcher logic: real, provider status often mock in default demo mode
- tracing: real OpenTelemetry, exporter depends on environment

Real providers can be enabled through `.env` without changing architecture.
