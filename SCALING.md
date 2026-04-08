# SCALING

## 1. Current architecture baseline

- `web`: stateless frontend served by Nginx.
- `api`: FastAPI service handling intake, triage, ticketing, and notifications.
- `db`: PostgreSQL for persistent incident data.

The current implementation is a hackathon baseline with in-memory incident state in API.

## 2. Scaling assumptions

- Multi-tenant traffic will increase over time.
- Incident creation has burst patterns (outages produce spikes).
- Integrations (ticketing, communicator, email) can fail or throttle.

## 3. Scaling plan

### 3.1 API horizontal scaling

- Run multiple API replicas behind a load balancer.
- Move incident state fully to PostgreSQL (remove in-memory singleton state).
- Keep API stateless to allow autoscaling.

### 3.2 Queue-based orchestration

- Split synchronous ingestion from asynchronous tasks:
  - Ticket creation
  - Team notifications
  - Reporter notifications
- Use a job queue (Redis + worker or cloud equivalent) with retries and dead-letter strategy.

### 3.3 Database strategy

- Add indexes by `tenant_id`, `status`, and `created_at`.
- Partition high-volume tables by time and/or tenant.
- Add read replicas for analytics/dashboard workloads.

### 3.4 Multi-tenant isolation model

- Start with shared schema + `tenant_id`.
- Evolve to schema-per-tenant for high-sensitivity clients.
- Enforce tenant filters at repository/service layer.

### 3.5 Observability at scale

- Ship structured logs to centralized log platform.
- Add tracing across ingest/triage/ticket/notify stages.
- Define SLOs:
  - ingest latency
  - triage success rate
  - ticket creation success rate
  - notification delivery success rate

### 3.6 Security hardening

- Stronger content scanning for attachments.
- Secrets manager for API keys and provider tokens.
- Least-privilege service credentials.

## 4. Reliability and failure handling

- Retry policy with exponential backoff for external integrations.
- Circuit breaker for unstable providers.
- Idempotency keys for incident submission and downstream actions.

## 5. Cost and performance considerations

- Cache code/document context for triage to reduce LLM cost.
- Route low-severity incidents to smaller/cheaper models.
- Keep critical incidents on higher-quality models.
