# AURA

AURA is a multi-tenant SRE incident intake and triage platform for e-commerce teams.
It receives customer incident reports, analyzes them with LLM + RAG context, and routes actions to Jira and Slack.

## Current Functionalities (Implemented)

- Login and register flow from `http://localhost:3000/`
- Multi-tenant data isolation by `tenant_id`
- Unique public intake URL per tenant: `/intake/{tenant}`
- Public customer intake separated from admin dashboard
- Multimodal incident intake: text, image, pdf, audio, and logs
- Two-stage LLM pipeline (multimodal extraction + deeper analysis)
- RAG over tenant-scoped vector database (`pgvector`)
- GitHub repository indexing directly into vector DB (no local clone required)
- Jira integration (tenant config + test + ticket creation in flow)
- Slack integration (tenant config + test + team notifications in flow)
- ReAct orchestration path through MCP bridge, with fallback path
- Incident resolution workflow with mandatory resolution notes
- Incident token usage and USD cost visible in dashboard incident views
- Bilingual UI support (ES/EN) on welcome/dashboard/intake/thanks flows
- Observability endpoints for metrics, audit logs, and tenant insights

## Main Routes

- `GET /` -> welcome and onboarding
- `GET /dashboard` -> admin dashboard (tenant operator)
- `GET /intake/{tenant}` -> public intake form (customer side)
- `GET /thanks` -> confirmation page after intake submission

## End-to-End Flow

1. Customer submits incident from `/intake/{tenant}` with optional files.
2. API performs guardrails and multimodal extraction.
3. API retrieves tenant RAG context from vector DB.
4. API generates triage output (severity, summary, affected service, proposed fix).
5. ReAct/MCP or direct integrations create Jira ticket and notify Slack.
6. Incident appears in tenant dashboard with status, triage data, token/cost.
7. Operator resolves incident with mandatory resolution notes.
8. Reporter notification step is executed (real or mocked by environment).

## Tech Stack

- Frontend: Nginx + Vanilla HTML/CSS/JS (single container, route split)
- API: FastAPI (Python)
- Database: PostgreSQL 16 + pgvector
- LLM gateway: OpenRouter/OpenAI integration layer
- Tool orchestration: MCP bridge (Node.js) for Jira/Slack tools
- Orchestration: Docker Compose
- E2E tests: Playwright

## Local Run

1. Copy environment template:
   - `cp .env.example .env`
2. Set required vars in `.env`:
   - `OPENROUTER_API_KEY` (or `OPENAI_API_KEY`)
   - `TENANT_ADMIN_KEY`
3. Start stack:
   - `docker compose up --build`
4. Open:
   - `http://localhost:3000/`

## Documentation Map

- [QUICKGUIDE.md](./QUICKGUIDE.md): fast setup + smoke validation
- [BACKLOG.md](./BACKLOG.md): prioritized work and delivery status
- [AGENTS_USE.md](./AGENTS_USE.md): agent design and execution details
- [MCP.md](./MCP.md): Jira/Slack integration and MCP setup details
- [SCALING.md](./SCALING.md): scaling assumptions and strategy
