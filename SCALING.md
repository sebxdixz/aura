# SCALING

This document explains how AURA scales from the current hackathon architecture to a more production-ready incident platform.

## 1. Current Baseline

AURA currently runs with:

- `web` for public intake
- `web_dashboard` for operators
- `api` for request validation and orchestration entrypoints
- `worker` for async incident processing and ticket sync
- `db` for PostgreSQL + pgvector
- `jaeger` optional for trace visualization
- `mcp_bridge` for MCP-backed integrations

This is intentionally simple, local, and demoable with Docker Compose.

## 2. Why We Added a Worker

The worker exists because inline incident processing becomes fragile very quickly.

Without a worker:

- submit requests block on attachment parsing
- triage and RAG increase latency
- ticketing and notification failures directly impact user experience
- retries are hard to manage cleanly

With the worker:

- intake stays fast
- heavy processing becomes retryable
- failures are isolated from the request path
- observability can follow jobs as their own operational unit

Current design:

- API persists the incident
- API enqueues `process_incident`
- worker claims the job
- worker performs:
  - multimodal processing
  - triage
  - multi-ticket analysis
  - ticket creation
  - team notification

## 3. Why Polling First for Resolution Watcher

We implemented ticket resolution sync with polling first because it is the best tradeoff for hackathon delivery:

- easier to demo locally
- fewer provider-specific webhook edge cases
- works for both mock and real-ish providers
- easy to reason about in Docker Compose

Current watcher design:

- worker periodically schedules `sync_ticket_status`
- watcher fetches external or mock ticket status
- AURA maps provider state into internal incident state
- if ticket becomes resolved, AURA resolves the local incident and enqueues reporter notification

## 4. How We Would Move to Webhooks

Webhook migration is straightforward from the current design.

Next step:

- add `POST /api/webhooks/ticketing/{provider}`
- verify webhook authenticity
- normalize provider payload into internal event schema
- reuse the same internal resolution/update functions already used by polling

Recommended future shape:

- webhook is primary path
- polling remains fallback and reconciliation path

That gives:

- lower latency
- fewer API calls
- resilience when a webhook is missed

## 5. Queue Evolution

Current queue implementation is intentionally lightweight:

- persisted `jobs` table in PostgreSQL
- worker claims jobs with lifecycle states
- retry behavior via `attempts`, `max_attempts`, and `run_after`

Why this is acceptable now:

- simple to inspect
- no extra infra dependency
- easy to explain in a hackathon

How to scale later:

- move to Redis + Dramatiq/RQ/Celery
- or move to Temporal for long-running workflows

Migration path:

1. preserve job payload contract
2. preserve handler boundaries
3. swap storage/claim mechanism
4. keep business handlers stable

## 6. Database Scaling

Current DB responsibilities:

- incidents
- tickets and notifications
- audit logs
- jobs
- code/document chunks for RAG
- incident links for multi-ticket intelligence

Scaling path:

- add more targeted indexes as query patterns stabilize
- partition:
  - `audit_logs` by time
  - `jobs` by time or status if needed
  - `incidents` by tenant or time for large tenants
- introduce read replicas for dashboard/analytics
- move cold incident history to cheaper archival storage

## 7. RAG Scaling

Current RAG is sufficient for demo and medium repos:

- curated code/docs indexing
- pgvector-backed retrieval
- tenant-scoped retrieval

Scaling path:

- asynchronous indexing jobs
- selective indexing by domain
- better chunk metadata
- cache hot retrieval results
- optionally move to a dedicated vector database if corpus size grows substantially

We intentionally avoid indexing the whole repo blindly because that hurts relevance and cost.

## 8. Observability Scaling

Current state:

- custom structured logs
- metrics endpoint
- OpenTelemetry spans
- optional Jaeger

Scaling path:

- OTLP exporter to managed tracing backend
- structured logs shipped to centralized log storage
- Prometheus/OpenTelemetry metrics collection
- alerts on:
  - job failures
  - queue backlog
  - ticket sync failures
  - notification failure rate
  - worker latency

## 9. Security Scaling

Current security posture:

- allowlisted attachments
- size validation
- prompt-injection heuristics
- tool allowlist
- no execution of uploaded artifacts

Scaling path:

- file malware scanning
- stronger OCR/text sanitization
- provider secret rotation
- signed webhook verification
- tighter RBAC for tenant admin flows

## 10. Current Limitations

These are real limitations today:

- resolution watcher is polling-first, not webhook-first
- job queue is DB-backed, not a dedicated queue system
- tracing backend is optional and local-first
- reporter notification is still mock-first by default
- some confidence/relevance metrics are heuristic, not learned

## 11. Why This Is Still a Strong Architecture

The current design is intentionally opinionated:

- simple enough to ship and demo
- structured enough to defend technically
- modular enough to evolve without rewriting everything

The most important architectural moves are already present:

- async worker separation
- explicit watcher layer
- persisted jobs
- formal tracing
- explainable triage
- multimodal evidence flow

That is the right foundation for moving from hackathon-quality delivery to production maturity.
