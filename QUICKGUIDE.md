# QUICKGUIDE

## 1. Prerequisites

- Docker Desktop (or Docker Engine + Compose plugin)
- Node.js available for Playwright tests
- Ports:
  - `3000` report portal (public intake)
  - `3001` dashboard (ops/internal)
  - `8000` api
  - `5432` db
- DB image uses `pgvector` (vector store in same Postgres container).

## 2. Run the stack

```bash
cd aura
cp .env.example .env
docker compose up --build
```

## 3. Open services

- Report portal: `http://localhost:3000/intake/{tenant_id}`
- Dashboard: `http://localhost:3001`
- API docs: `http://localhost:8000/docs`
- Health: `http://localhost:8000/health`
- Metrics: `http://localhost:8000/metrics`
- RAG status: `http://localhost:8000/api/rag/status`

## 4. API smoke flow (manual)

```bash
# Register tenant
curl -s -X POST http://localhost:8000/api/tenants/register \
  -H "Content-Type: application/json" \
  -d '{"tenant_id":"demo-tenant","name":"Demo Tenant"}'

# Submit incident
curl -s -X POST http://localhost:8000/api/incidents/submit \
  -F "tenant_id=demo-tenant" \
  -F "reporter_email=reporter@demo.com" \
  -F "description=Checkout payment 500 with coupon" \
  -F "attachment=@tests/fixtures/incident.txt;type=text/plain"

# Submit incident with PDF evidence
curl -s -X POST http://localhost:8000/api/incidents/submit \
  -F "tenant_id=demo-tenant" \
  -F "reporter_email=reporter@demo.com" \
  -F "description=Checkout outage attached in PDF evidence" \
  -F "attachment=@/path/to/incident.pdf;type=application/pdf"

# Submit incident with audio evidence
curl -s -X POST http://localhost:8000/api/incidents/submit \
  -F "tenant_id=demo-tenant" \
  -F "reporter_email=reporter@demo.com" \
  -F "description=Checkout outage reported by voice note" \
  -F "attachment=@/path/to/incident.wav;type=audio/wav"

# List incidents by tenant
curl -s "http://localhost:8000/api/incidents?tenant_id=demo-tenant"

# Resolve incident (replace INCIDENT_ID)
curl -s -X POST http://localhost:8000/api/incidents/INCIDENT_ID/resolve

# Check RAG/vector index status
curl -s http://localhost:8000/api/rag/status

# Trigger RAG reindex (after updating ecommerce_repo mount content)
curl -s -X POST http://localhost:8000/api/rag/reindex
```

## 5. Run automated tests (Playwright)

Install once:

```bash
npm install
npx playwright install chromium
```

Run API E2E suite:

```bash
npm run test:e2e
```

The command waits for API health before running tests.
If needed, you can tune wait behavior:

```bash
API_BASE_URL=http://127.0.0.1:8000
API_WAIT_TIMEOUT_MS=60000
API_WAIT_INTERVAL_MS=1500
```

Optional (when frontend is stable):

```bash
npm run test:e2e:web
npm run test:e2e:all
```

## 6. What the API tests validate

- Tenant registration
- Incident submit -> resolve E2E
- Guardrail rejection for prompt-injection patterns
- Deduplication for repeated open incidents in same tenant
- Tenant isolation with `tenant_id` filter
- Multimodal intake acceptance for `text/plain`, `application/pdf`, `audio/wav`
- Triage includes:
  - `severity_score`
  - `severity_rationale`
  - `runbook_suggestions`
- Observability endpoints:
  - `GET /api/tenants/{tenant_id}/audit-logs`
  - `GET /api/tenants/{tenant_id}/insights/summary`
- RAG/vector retrieval:
  - `GET /api/rag/status`
  - `POST /api/rag/reindex`

## 7. Notes

- Default mode is mock integrations (`MOCK_MODE=true`).
- Default triage mode is mock multimodal (`MOCK_MODE=true`).
- To use live model triage, set:
  - `MOCK_MODE=false`
  - `OPENAI_API_KEY=<your_key>`
  - optional `OPENAI_BASE_URL`
  - optional `OPENAI_TRIAGE_MODEL` and `OPENAI_TRANSCRIPTION_MODEL`
- To use two-stage multimodal triage via OpenRouter, set:
  - `MOCK_MODE=false`
  - `MULTIMODAL_PIPELINE=openrouter_two_stage`
  - `OPENROUTER_API_KEY=<your_key>`
  - `OPENROUTER_MULTIMODAL_MODEL=google/gemini-2.5-flash`
  - `OPENROUTER_ANALYSIS_MODEL=<stronger_model>`
- To use ReAct ops with OpenRouter + MCP, set:
  - `REACT_ENGINE=openrouter_mcp`
  - `OPENROUTER_API_KEY=<your_key>`
  - `OPENROUTER_MODEL=<model_on_openrouter>`
  - `MCP_BRIDGE_URL=<bridge_endpoint>` or `MCP_JIRA_URL` + `MCP_SLACK_URL`
- Retry/fallback behavior is controlled by `.env`.
- Persistent storage is PostgreSQL; data survives API restarts.
