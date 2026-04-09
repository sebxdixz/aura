# AGENTS_USE.md

## 1. Agent Overview and Tech Stack
AURA is a multi-tenant SRE incident intake and triage platform for e-commerce operations.  
Core stack: FastAPI (Python), PostgreSQL + pgvector, OpenRouter (multimodal + reasoning models), MCP bridge (Node.js) for Jira/Slack tools, one Nginx frontend with route-level split (welcome + public intake + admin dashboard), Docker Compose orchestration, and Playwright E2E validation.

## 2. Agents and Capabilities
### Agent A: Multimodal Ingestion Agent
- Accepts text + files (`pdf`, `image`, `audio`, logs).
- Extracts/normalizes incident facts into structured triage fields.
- Produces technical summary inputs for downstream analysis.

### Agent B: Analysis and Triage Agent
- Enriches incident context with RAG retrieval from tenant-scoped vector store.
- Computes severity, RCA, proposed fix, and runbook suggestions.
- Handles duplicate incident detection.

### Agent C: ReAct Orchestrator Agent
- Plans operational actions (ticket + team notification).
- Executes Jira/Slack actions through MCP tools.
- Falls back to direct/mocked integrations if MCP path fails.

## 3. Architecture, Orchestration, and Error Handling
- Flow: `submit -> ingest -> triage -> ticket -> notify team -> resolve -> notify reporter`.
- Service boundaries:
  - `web` (single entrypoint: welcome + public intake + admin operations routes).
  - `api` (agents + orchestration + integrations).
  - `db` (incidents, audit logs, vectors).
  - `mcp_bridge` (HTTP-to-MCP tool execution).
- Error handling:
  - Guardrail validation errors return `400`.
  - Integration failures trigger retry + fallback providers.
  - ReAct/MCP failures are logged and degraded gracefully to non-MCP path.
  - Audit write failures do not block main transaction flow.

## 4. Context Engineering Approach
- Multi-source context package:
  - User report text.
  - Attachment-derived text/evidence.
  - Tenant-scoped retrieved code chunks from pgvector.
- Prompt strategy:
  - Stage 1 multimodal extraction (fast model).
  - Stage 2 deeper SRE reasoning (stronger model) with structured JSON output.
- Tenant isolation in context:
  - Retrieval queries are filtered by `tenant_id`.
  - RAG sync/reindex endpoints require tenant admin credentials.

## 5. Use Cases with Step-by-Step Flows
### Use Case A: Public customer reports an incident
1. Customer opens `https://<host>/intake/{tenant}`.
2. Submits description and optional file evidence.
3. AURA ingests and triages automatically.
4. A ticket is created (real or mock).
5. Team is notified (real or mock).
6. Customer gets confirmation page (`/thanks`).

### Use Case B: Ops team manages incidents
1. Admin logs in at `https://<host>/dashboard`.
2. Reviews dashboard metrics and incident list.
3. Resolves incident from dashboard.
4. Reporter notification is sent automatically.

### Use Case C: Tenant admin syncs codebase into RAG
1. Admin opens dashboard settings.
2. Runs GitHub sync (tenant + repo URL + admin key).
3. API ingests repository directly into vector DB (no local git clone).
4. Dashboard shows RAG index status (repo/chunk count/state).

## 6. Observability (Logging, Tracing, Metrics) — Evidence
- Structured logs:
  - Emitted via `log_event(...)` in `api/app/observability.py`.
  - Key stages include `incident_ingested`, `incident_triaged`, `ticket_created`, `team_notified`, `incident_resolved`, `reporter_notified`.
- Metrics endpoint:
  - `GET /metrics` returns stage and severity counters.
- Tenant-level audit and insights:
  - `GET /api/tenants/{tenant_id}/audit-logs`
  - `GET /api/tenants/{tenant_id}/insights/summary`
- Evidence from tests:
  - `npm run test:e2e:api` validates full API flow, multimodal intake, guardrails, dedup, RAG enrichment.
  - `npm run test:e2e:web` validates welcome + intake + dashboard separation flow.

## 7. Security and Guardrails — Evidence
- Input guardrails (`api/app/guardrails.py`):
  - Prompt-injection pattern blocking.
  - Max description length.
  - File type allowlist and size limits.
- Tool safety:
  - Strict tool allowlist (`create_ticket`, `notify_team`, `notify_reporter`).
- Tenant isolation:
  - Data partition by `tenant_id` in incidents/audit/RAG retrieval.
  - Admin-protected endpoints require `x-tenant-admin-key`.
- MCP boundary:
  - API does not execute arbitrary shell for Jira/Slack; calls MCP bridge over controlled HTTP interface.
- Evidence from tests:
  - Prompt-injection rejection tested in `tests/e2e/api-contract.spec.js`.

## 8. Scalability Summary
- Stateless API + horizontal scaling readiness.
- PostgreSQL persistence with indexed tenant queries.
- pgvector for semantic retrieval with tenant filtering.
- Decoupled integration layer (providers + MCP + fallback modes).
- Separate public/admin web surfaces for clear traffic segmentation.

## 9. Lessons Learned and Team Reflections
- Separating public intake from admin dashboard reduced UX confusion and security risk.
- Two-stage LLM design improved reliability: fast extraction + stronger analysis.
- MCP-based tool execution gave cleaner integration boundaries and safer operations.
- E2E tests were critical to stabilize rapid parallel development and prevent regressions.
