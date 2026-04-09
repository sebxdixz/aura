# SCALING

## Purpose

This document explains how AURA scales today, what its current limits are, and how the architecture would evolve beyond hackathon scope.

The goal is not to claim that the current stack is fully production-ready.
The goal is to show that the design choices are **production-minded, intentional, and extensible**.

## 1. Current architecture

Today the system is split into:

- web surfaces
  - unified app
  - dashboard-only surface
  - intake-only surface
- stateless API
- separate worker
- PostgreSQL + pgvector
- MCP bridge for optional tool execution
- optional Jaeger tracing UI

That separation already solves an important scaling problem:

- user-facing intake stays fast
- heavy work runs asynchronously
- resolution monitoring does not block the request path

## 2. What scales reasonably well today

### API layer

The API is mostly stateless and persistence-first.
That makes horizontal scaling straightforward in principle:

- more API replicas
- same shared database
- same shared integrations

This is stronger than an inline-only hackathon design because:

- submit does not need to wait for full triage
- ticket creation and notification are off the critical path

### Worker separation

The worker is the most important scaling feature already present.

It allows:

- async incident processing
- retries without client involvement
- isolation of slow integrations
- future move to multiple worker replicas

### RAG retrieval

Current RAG usage is bounded:

- tenant-scoped retrieval
- top-k retrieval
- chunk count limits
- max files and max bytes controls

This keeps context retrieval predictable for the current scope.

### Multi-tenant model

AURA already treats tenant isolation as a first-class concern:

- tenant-scoped incidents
- tenant-scoped vector chunks
- tenant-scoped integration settings
- tenant-scoped admin access

That is the right foundation for growth.

## 3. Current bottlenecks and honest limits

### Job queue

The queue is a database-backed `jobs` table.

That is good for:

- reproducibility
- debugging
- hackathon review
- simple retry behavior

But it is not ideal for:

- very high concurrency
- bursty workloads
- large fleets of workers

At larger scale, a dedicated broker would be more appropriate.

### Resolution watcher

The watcher is polling-first today.

That is good for:

- simplicity
- provider independence
- reliable demo behavior

But it has known scaling costs:

- repeated sync jobs
- unnecessary provider calls
- slower resolution propagation than webhooks

### Observability backend

OpenTelemetry is already wired in, but Jaeger is local/demo oriented.

That is enough to prove:

- traces exist
- timings exist
- async worker flow is observable

It is not yet a long-term shared observability backend.

### RAG storage

PostgreSQL + pgvector is a good fit for the current demo scope.
Eventually, scale pressure will show up in:

- index size
- ingestion time
- query latency across many tenants and large repos

## 4. How AURA would scale next

### Queue and worker evolution

Next step after the current `jobs` table:

- move to a dedicated queue or broker
  - Redis-backed worker system
  - RabbitMQ
  - SQS
  - Kafka only if the broader platform needs it

Why:

- better fan-out
- better worker concurrency control
- cleaner retry/dead-letter semantics
- easier isolation of job types

### Watcher evolution: polling-first to webhook-first

Current model:

- polling sync jobs check ticket state

Better future model:

- webhook-first from Jira/provider
- polling retained as backup reconciliation

Why that is the right direction:

- fewer external API calls
- lower latency to resolution
- lower worker load
- cleaner large-tenant behavior

### RAG scaling path

Current path:

- pgvector in the same operational database family

Future path if repo size or tenant count grows:

- separate vector store or dedicated retrieval service
- background indexing workers
- repository sync scheduling and backpressure
- per-tenant indexing quotas and retention policies

### Observability scaling path

Current path:

- local Jaeger + OTLP

Future path:

- OpenTelemetry Collector
- shared trace backend such as Tempo, Jaeger, or vendor APM
- central log aggregation
- dashboards for queue depth, watcher lag, provider failures, and tenant hotspots

## 5. Multi-tenant growth considerations

As tenant count grows, the main concerns are:

- isolation
- noisy-neighbor effects
- integration credential management
- indexing fairness
- queue fairness

The current design already helps because:

- tenant ID is embedded in the main data path
- integrations are tenant-scoped
- RAG retrieval is tenant-scoped
- admin access is tenant-scoped

Future improvements would include:

- per-tenant worker quotas
- per-tenant queue partitioning
- per-tenant RAG indexing budgets
- tenant-aware rate limiting

## 6. What is intentionally simplified today

These choices are intentional for the current scope:

- database-backed queue instead of external broker
- polling watcher instead of webhook-first
- local Jaeger instead of centralized observability stack
- narrow real-provider support instead of many provider integrations
- mock-first defaults for reproducibility

These simplifications reduce setup friction without invalidating the core architecture.

## 7. Why the current design is still credible

Even with hackathon simplifications, AURA already demonstrates the right architectural moves:

- fast submit path
- separate worker
- explicit job lifecycle
- idempotent reporter notification
- tenant-scoped RAG
- provider abstraction for external systems
- traceable async flow

That is the difference between:

- a single-process demo
- and a design that can actually evolve into a real incident operations system

## 8. Near-term roadmap

If this project continued past the hackathon, the highest-value next steps would be:

1. move job execution to a dedicated broker
2. add webhook-first resolution updates
3. add queue depth and watcher lag dashboards
4. separate vector indexing from request-serving concerns
5. expand provider coverage with the same abstraction patterns
