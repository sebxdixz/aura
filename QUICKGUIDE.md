# QUICKGUIDE

## Fastest path

### 1. Clone and enter the repo

```bash
git clone <your-repo-url>
cd aura
```

### 2. Create `.env`

```bash
cp .env.example .env
```

**No external credentials are required for the default mock/demo path.**

### 3. Start the stack

```bash
docker compose up --build
```

### 4. Open these URLs

- Main app: `http://localhost:3000`
- Dashboard-only view: `http://localhost:3001`
- Intake-only view: `http://localhost:3002/intake/demo`
- API health: `http://localhost:8000/health`

## 2-minute smoke test

### A. Create or use a tenant

1. Open `http://localhost:3000`
2. Register tenant `demo` if it does not exist
3. Log in with:
   - `tenant_id`: `demo`
   - admin key: `change-me`

### B. Submit an incident

Use either:

- `http://localhost:3000/dashboard` -> `Report Incident`
- or `http://localhost:3002/intake/demo`

Submit:

- a short incident description
- an attachment such as:
  - screenshot
  - log
  - text file

### C. Validate the main flow

Confirm that AURA:

1. stores the incident immediately
2. processes it asynchronously through the worker
3. shows triage output with severity and explainability
4. creates a mock or real ticket depending on config
5. notifies the team
6. can resolve the incident from the dashboard
7. triggers reporter notification on resolution

## Optional: enable Jaeger tracing

Edit `.env`:

```env
OTEL_EXPORTER_MODE=otlp
```

Then restart:

```bash
docker compose up --build
```

Open:

- Jaeger UI: `http://localhost:16686`

Expected traces:

- `api.submit_incident`
- `worker.process_incident`
- `rag.retrieve_context`
- `ticket.create`
- `notify.team`
- `worker.sync_ticket_status`
- `worker.notify_reporter`

## Optional: enable real integrations

### Jira

```env
MOCK_MODE=false
TICKETING_PROVIDER=jira
```

Then fill Jira credentials in `.env` or through tenant settings.

### Slack

```env
COMMUNICATOR_PROVIDER=slack
```

Then fill Slack credentials.

### Reporter email

```env
EMAIL_PROVIDER=resend
EMAIL_RESEND_API_KEY=re_...
EMAIL_FROM=alerts@your-domain.com
EMAIL_FROM_NAME=AURA
```

## Troubleshooting

- Old containers from previous runs:
  - `docker compose up --build --remove-orphans`
- Main UI loads but data is missing:
  - verify you are logged into the correct tenant
- No real provider output:
  - confirm you are not still using mock mode
- No Jaeger traces:
  - confirm `OTEL_EXPORTER_MODE=otlp`
