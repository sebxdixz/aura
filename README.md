# AURA (Uptime & Resolution Agent) 🚀

**AURA** is an advanced, multi-tenant Site Reliability Engineering (SRE) Agent designed to ingest incident reports, perform automated intelligent triage, and orchestrate resolution workflows. Built for the **AgentX Hackathon 2026**, AURA bridges the gap between incident creation and resolution by dynamically analyzing codebase context, deduping issues, extracting multimodal inputs, and securely communicating with tools like Jira and Slack.

---

## 📖 Project Summary

When an incident occurs, AURA acts as the first line of defense:
1. **Ingest**: Receives reports via a brutalist, agency-grade UI supporting Multimodal inputs (Screenshots, PDFs, Audio, Text).
2. **Retrieve Context (RAG)**: Dynamically runs Vector Semantic Search (`pgvector`) against the synchronized GitHub E-Commerce codebase to pinpoint the buggy code.
3. **AI Triage**: Uses a Dual-Stage Orchestration pipeline (OpenRouter) to score severity mathematically, find the root cause, and propose CLI/code fixes.
4. **Action (MCP)**: Utilizes the Anthropic **Model Context Protocol (MCP)** via a custom, secure Node.js HTTP bridge to orchestrate ticketing (Jira/Linear) and team alerts (Slack/Teams).
5. **Insights**: Saves every token, cost (USD) and meta-usage into a robust PostgreSQL Audit Log, surfacing live metrics to a secure Administration Dashboard.

---

## 🏗️ Architecture Overview

AURA is implemented as a containerized, decoupled microservice architecture ensuring true B2B scalability.

- **Frontend (Nginx / Vanilla JS / CSS)**: Unified frontend server with route-level split: `"/"` welcome + onboarding, `"/dashboard"` for protected tenant admin, and `"/intake/{tenant}"` for public incident intake.
- **Backend (FastAPI / Python 3.11)**: The core AI brain handling deduplication, PostgreSQL integration (`pgvector`), RAG GitHub cloning, and OpenRouter hybrid-LLM calls (`google/gemini-2.5-flash` for extraction + `openai/gpt-4o-mini` for ReAct).
- **Tooling Proxy (Node.js MCP Bridge)**: Completely isolates external LLM execution from the system. It safely routes MCP tool calls via standard `stdio` to Anthropic's official `@modelcontextprotocol/server-slack` and `server-atlassian` without exposing environment security risks to the Python container.
- **Database (PostgreSQL 16 + pgvector)**: Handles both Vector Storage for semantic code search, and standard relational storage for Multi-Tenant `IncidentRecords`, `TenantRecords`, and `AuditLogs` tracking.

---

## 🛠️ Setup Instructions

> Note: For a detailed step-by-step, see [QUICKGUIDE.md](./QUICKGUIDE.md).

### Prerequisites
- Docker and Docker Compose installed.
- Valid API Keys (OpenRouter OR OpenAI).

### To Run
1. Clone this repository.
2. Copy the `.env.example` file to create your own `.env`:
   ```bash
   cp .env.example .env
   ```
3. Fill out the required LLM API keys (`OPENROUTER_API_KEY` or `OPENAI_API_KEY`) and your `TENANT_ADMIN_KEY`.
4. Fire up the orchestration using Docker Compose:
   ```bash
   docker compose up --build
   ```
5. Access the platform:
   - **Welcome / Onboarding**: `http://localhost:3000/`
   - **Admin Dashboard**: `http://localhost:3000/dashboard`
   - **Public Intake**: `http://localhost:3000/intake/{tenant}`

*(For full documentation, please review all `.md` files included in the repository).*
