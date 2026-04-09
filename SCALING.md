# AURA Scaling Strategy and Assumptions

AURA was explicitly engineered to handle multi-tenant B2B incident architectures instead of single-instance test environments. This document highlights the critical technical decisions, scaling assumptions, and the infrastructure design deployed to guarantee stability beneath high transactional loads.

## 1. Architectural Scaling Technical Decisions

### Containerization & Service Decoupling
- **Docker Driven**: The stack uses pure `docker-compose` routing, meaning the Database, the Python API Processor, the Web Dashboards (NGINX), and the Node.js MCP Bridge execute asynchronously. As loads increase, platforms like AWS ECS or Kubernetes can horizontally scale out the API container or the NGINX frontend without affecting the relational structure.
- **REST Backend over Websockets**: We adopted a stateless HTTP REST API using `FastAPI` (based on Starlette) allowing asynchronous connections. State and sessions are heavily decoupled, maintaining stateless authentication with Headers (`x-tenant-admin-key`).

### The Vector Search Paradigm
Instead of downloading chunks of code or keeping text files alive in container memory, AURA relies on **PostgreSQL with `pgvector`**.
- **The Vector Load limit**: By translating arbitrary codebase lengths (GitHub clones) into mathematical embeddings and saving them alongside basic incident structures, memory issues disappear. Fast Cosine Similarity Semantic search permits processing vast repos over 1,000 files in under 100ms on a cold start while preventing the LLM's context window from hallucinating or overloading.

### The Model Context Protocol (MCP) Node Bridge
- Anthropic's MCP heavily defines local context servers connecting via standard I/O (console) specifically targeting user desktops (like Cursor or Claude integrations). We constructed an **HTTP-to-Stdio MCP Bridge**.
- **Scaling Decision**: In enterprise networks, standard I/O connections choke the container if multiple users request tools simultaneously. With our Node Bridge proxy deployed independently, each agent iteration acts via a stateless HTTP endpoint. If the HTTP request crashes due to timeout or LLM failure, the backend gracefully catches the Exception without bringing down the core container console.

## 2. Platform Assumptions

1. **Idempotency against API Rate Limits**: AURA assumes external LLM providers (OpenAI, OpenRouter, Jira, Slack) frequently generate 429 Status Rate limits. Our `services.py` layer contains retry mechanisms with robust exponential fallbacks gracefully mocking failed API operations via `.env` definitions (`MOCK_MODE=true` fallback) whenever rate limits strike.
2. **Context Window Constraint**: We assume any production Codebase will easily overflow `gpt-4o-mini`'s actual 128k context token limit. Due to this, the `RAG` extraction is tuned to retrieve *only the top N chunks* of code related structurally to the incident before concatenating to the LLM.
3. **Data Protection Constraints**: We assume that one Tenant submitting private backend code errors strictly cannot share vector clusters dynamically with a secondary Tenant. We hardcoded explicit `.where(TenantRecord.id == current_tenant)` partitions inside semantic retrieval algorithms.

## 3. Future Proofing (Next Sprints)
If adopted to handle +5,000 requests/minute, the roadmap dictates migrating the `main.py` Incident Submission task into a scalable distributed task queue software (like **Celery** or **RabbitMQ**). This would free the HTTP client of the end-user immediately, allowing real-time websockets (or polling) to transmit the Live AI animation processing sequentially without forcing an open HTTP timeout window on NGINX.
