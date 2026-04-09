# AURA Quick Guide

This guide is optimized for fast local validation and AI-first review.

## 1. Prerequisites

- Docker + Docker Compose
- API key for at least one provider:
  - `OPENROUTER_API_KEY` (recommended), or
  - `OPENAI_API_KEY`

## 2. Configure Environment

```bash
cp .env.example .env
```

Minimum values to set:

```env
TENANT_ADMIN_KEY=hackathon2024
OPENROUTER_API_KEY=sk-or-v1-...
```

Optional integration and mode controls are in `.env.example`.

## 3. Start the Platform

```bash
docker compose up --build
```

Main URL:

- `http://localhost:3000/`

## 4. Core URLs

- Welcome: `http://localhost:3000/`
- Dashboard: `http://localhost:3000/dashboard`
- Public Intake: `http://localhost:3000/intake/{tenant}`
- Thanks page: `http://localhost:3000/thanks`

## 5. Smoke Test Checklist (Feature Validation)

1. Register a tenant from welcome page.
2. Login with `tenant_id` + `TENANT_ADMIN_KEY`.
3. Confirm dashboard loads tenant metrics and incidents.
4. In settings, configure Jira and Slack credentials and run test buttons.
5. In settings, run GitHub sync to index repository into tenant RAG.
6. Open public intake URL `/intake/{tenant}`.
7. Submit incident with text and optionally one file:
   - image, pdf, audio, or log/text file
8. Confirm incident appears in dashboard with triage fields.
9. Confirm incident shows token usage and USD cost.
10. Resolve incident and provide resolution notes.
11. Confirm ticket/notification outputs in dashboard result log and provider systems (or mock responses).

## 6. What the Reviewer Should See

- Login/register flow is active.
- Multi-tenant separation is active.
- Public intake and private dashboard are separated.
- RAG is tenant-scoped and reports indexed chunk count.
- GitHub indexing to vector DB works from dashboard settings.
- Jira and Slack are configurable per tenant and testable.
- UI supports ES/EN toggles.

## 7. Troubleshooting

- Dashboard without data:
  - Ensure valid login session (`tenant` + admin key).
  - Hard refresh `/dashboard`.
- Jira test returns issue type error:
  - Set valid `issue_type` for the selected project.
- Slack test does not post:
  - Verify webhook/token/channel and that bot is invited to channel.
- No external credentials available:
  - Use mock/fallback mode for demo continuity.
