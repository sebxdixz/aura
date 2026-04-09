# AGENTS_USE

## 1. Agent overview and tech stack

AURA is a multi-tenant SRE incident intake and triage platform for e-commerce operations.
Stack:

- API: FastAPI (Python)
- DB: PostgreSQL + pgvector
- LLM orchestration: OpenRouter/OpenAI adapters
- Tool execution: MCP bridge (Node.js) for Jira/Slack
- Web: Single Nginx frontend with route split (`/`, `/dashboard`, `/intake/{tenant}`)
- Runtime: Docker Compose
- Validation: Playwright E2E

Implemented platform features snapshot:

- Login/register
- Multi-tenant isolation
- Tenant-specific public intake URL
- Tenant-scoped RAG
- GitHub indexing to vector DB
- Jira and Slack integrations
- ES/EN UI language support

## 2. Agents and their capabilities

Agent 1 - Multimodal Ingestion Agent

- Accepts text and optional files (image, pdf, audio, logs)
- Normalizes inputs into structured incident evidence
- Produces extraction output for triage stage

Agent 2 - Analysis and Triage Agent

- Retrieves tenant-scoped code context from vector DB
- Computes severity, technical summary, affected service, and fix proposal
- Handles dedup and runbook suggestion logic

Agent 3 - ReAct Orchestrator Agent

- Plans tool actions for ticketing and notifications
- Executes Jira/Slack actions through MCP bridge
- Falls back to direct/mock providers on bridge/tool errors

## 3. Architecture, orchestration, and error handling

Flow:

`submit -> ingest -> triage -> ticket -> notify team -> resolve -> notify reporter`

Service boundaries:

- `web`: welcome, intake, dashboard UI
- `api`: business logic, RAG, agent pipeline, integration routing
- `db`: incidents, tenant settings, audit logs, vector chunks
- `mcp_bridge`: HTTP to MCP tool call adapter

Error handling:

- Guardrails and validation return structured `4xx`
- Integration failures trigger fallback path
- MCP errors degrade to direct/mock integration path
- Audit/telemetry failures do not block primary incident transaction

## 4. Context engineering approach

- Context package includes:
  - customer text input
  - parsed file evidence
  - tenant-scoped retrieved code chunks from pgvector
- Two-stage prompting:
  - Stage A: fast multimodal extraction
  - Stage B: stronger reasoning model for final triage JSON
- Tenant isolation:
  - retrieval filters by `tenant_id`
  - sync/index endpoints require tenant admin key

## 5. Use cases with step-by-step flows

Use case A - Customer reports incident

1. Customer opens `/intake/{tenant}`.
2. Customer submits text plus optional file evidence.
3. AURA ingests, validates, and triages.
4. AURA creates ticket and notifies team.
5. Customer sees confirmation page.

Use case B - Operator manages incidents

1. Operator logs in at `/dashboard`.
2. Reviews incidents and triage details.
3. Resolves incident with mandatory resolution notes.
4. Reporter notification step is triggered.

Use case C - Tenant admin indexes codebase

1. Admin opens dashboard settings.
2. Submits GitHub repository URL for sync.
3. API indexes repository into tenant vector DB.
4. Dashboard shows index status and chunk count.

## 6. Observability - logging, tracing, metrics (evidence)

Evidence endpoints:

- `GET /metrics`
- `GET /api/tenants/{tenant_id}/audit-logs`
- `GET /api/tenants/{tenant_id}/insights/summary`

Evidence in behavior:

- Incident lifecycle events are persisted with tenant and incident context.
- Dashboard surfaces incident-level token usage and cost in USD.

Evidence in tests:

- `tests/e2e/api-contract.spec.js`
- `tests/e2e/web-intake.spec.js`

## 7. Security and guardrails (evidence)

Evidence in code and runtime behavior:

- Input guardrails for malicious prompt patterns
- File type and size controls for uploads
- Strict tenant boundary by `tenant_id`
- Admin endpoints protected by `x-tenant-admin-key`
- Tool calls constrained by MCP bridge endpoint and allowed operations

Evidence in tests:

- Prompt-injection rejection covered in API E2E tests
- Tenant-isolated workflows validated in web/API E2E paths

## 8. Scalability summary

- Stateless API supports horizontal scaling.
- PostgreSQL stores transactional and vector data with tenant filters.
- Integration layer is decoupled from core incident flow.
- Single frontend entrypoint with route split simplifies deployment and ops.

## 9. Lessons learned and team reflections

- Public intake and admin dashboard must be separated for safety and UX clarity.
- Two-stage LLM design improves reliability compared to one-shot reasoning.
- Tenant-scoped RAG is critical for useful triage in real e-commerce contexts.
- Fallback and mock paths are required for stable demos under API constraints.
