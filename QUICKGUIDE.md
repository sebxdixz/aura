# AURA Quick Setup Guide ⚡

Follow this guide to spin up the local microservices container architecture and run the E2E Demo natively.

## 1. Clone the project

Open up your terminal and clone the repository locally:

```bash
git clone <repository_url>
cd aura
```

## 2. Environment Variables

Create your environment configuration by copying the template file:

```bash
cp .env.example .env
```

Open `.env` in your favorite editor. The main thing you need to authorize is your API provider for the Hybrid Multi-Modal Pipeline. AURA gracefully supports both standalone **OpenAI** integration and **OpenRouter** orchestrations.

We highly recommend utilizing **OpenRouter** to spin up the multi-staged (Gemini 2.5 + GPT) default pipeline.

Inside the `.env` file, fill the following key mapping:
```env
OPENROUTER_API_KEY=sk-or-v1-xxx...
TENANT_ADMIN_KEY=hackathon2024
```
*(If you do not have OpenRouter, simply leave it blank and fill out the `OPENAI_API_KEY=sk-...` field instead. The LLM processor will gracefully fallback automatically).*

## 3. Build & Run Containers

Our docker architecture builds out the Web UI, API Backend, Node proxy and Databases simultaneously.

```bash
docker compose up --build
```
*Wait a few minutes while Alpine packages and Python libraries compile internally and standard PostgreSQL instances initialize.*

## 4. Test the End-to-End Workflow

AURA serves one unified web entrypoint:

1. **Welcome (Port 3000):** Navigate to `http://localhost:3000`. From there you can login/register your tenant and understand the platform flow.
2. **Public Intake:** Use `http://localhost:3000/intake/{tenant}` for customer incident reports.
3. **Admin Dashboard:** Use `http://localhost:3000/dashboard`.
   - Click `Demo Judge` in dashboard login or authenticate with your tenant and `TENANT_ADMIN_KEY`.
   - Explore incident statistics and use Settings to sync GitHub into tenant-scoped Vector RAG.

## Troubleshooting
If a system rate-limit hits or you do not have access to Jira/Slack official webhook tokens, don't worry! By default `.env` forces `MOCK_MODE=false` combined with predefined `mock-slack` fallback modes. AURA will intercept execution requests and mock the internal process returning 200 OP codes to demonstrate the workflow gracefully rather than crashing.
