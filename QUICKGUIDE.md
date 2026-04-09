# QUICKGUIDE

This guide is the fastest way to run AURA locally and demo the full async incident flow.

## 1. What You Need

- Docker Desktop or Docker Engine with Compose
- Optional: Node.js only if you want to run Playwright tests
- Free local ports:
  - `3000` intake portal
  - `3001` operations dashboard
  - `8000` API
  - `5432` PostgreSQL
  - `16686` Jaeger UI (optional)

## 2. First Run

From the repo root:

```bash
cp .env.example .env
docker compose up --build
```

If you are on Windows PowerShell:

```powershell
Copy-Item .env.example .env
docker compose up --build
```

## 3. Choose Tracing Mode

In `.env`:

- `OTEL_EXPORTER_MODE=console`
  - simplest mode
  - traces appear in API/worker logs
- `OTEL_EXPORTER_MODE=otlp`
  - sends traces to Jaeger
  - open [http://localhost:16686](http://localhost:16686)

Recommended for demo:

```env
OTEL_EXPORTER_MODE=otlp
```

## 4. Open the App

- Public intake: [http://localhost:3000/intake/hackathon-demo](http://localhost:3000/intake/hackathon-demo)
- Operations dashboard: [http://localhost:3001/?tenant_id=hackathon-demo](http://localhost:3001/?tenant_id=hackathon-demo)
- API docs: [http://localhost:8000/docs](http://localhost:8000/docs)
- Health: [http://localhost:8000/health](http://localhost:8000/health)
- Metrics: [http://localhost:8000/metrics](http://localhost:8000/metrics)
- Jaeger: [http://localhost:16686](http://localhost:16686)

## 5. Tenant Admin Access

The public intake route does not require credentials.

The dashboard/admin flow uses:

- `tenant_id`
- tenant admin key

Default example from `.env.example`:

```env
TENANT_ADMIN_KEYS_JSON={"demo":"change-me"}
```

If you want to use `hackathon-demo` in the dashboard too, set one of these:

```env
TENANT_ADMIN_KEYS_JSON={"demo":"change-me","hackathon-demo":"change-me"}
```

or:

```env
TENANT_ADMIN_KEY=change-me
```

Restart the stack after changing `.env`.

## 6. Demo Flow in 2 Minutes

### Step 1: submit one strong incident

Open the intake portal and send:

- Reporter Name: `Demo Operator`
- Reporter Email: `demo@acme.com`
- Issue Category: `Checkout / Gateway`
- Description:

```text
Customers cannot complete payment in checkout. We are seeing HTTP 500 in production after clicking Pay. No workaround confirmed yet.
```

- Attachment file:

```text
2026-04-09T20:10:00Z ERROR checkout-service payment failed HTTP 500
2026-04-09T20:10:01Z ERROR payment-service gateway timeout
environment=production
```

### Step 2: show async behavior

Point out that:

- submit returns quickly
- the incident is queued
- the UI polls until the worker finishes
- the final commander brief appears after async processing

### Step 3: show explainability

Call out:

- score breakdown
- routing decision
- description influence
- attachment evidence
- RAG evidence
- incident pattern / recurrence if available

### Step 4: show ops view

Open the dashboard and show:

- `Command Brief`
- `Triage Score`
- `Matched Context`
- `Multi-Ticket Intelligence`
- `Recommended Investigation`

### Step 5: show tracing

If `OTEL_EXPORTER_MODE=otlp`, open Jaeger and search for traces from:

- `api.submit_incident`
- `worker.process_incident`
- `triage.run`
- `rag.retrieve_context`
- `ticket.create`
- `notify.team`

## 7. Resolution Watcher Demo

The current resolution watcher is polling-first.

To demo it quickly in mock mode, you can enable auto-resolution in `.env`:

```env
MOCK_TICKET_AUTO_RESOLVE=true
MOCK_TICKET_AUTO_RESOLVE_AFTER_SECONDS=45
```

Then restart:

```bash
docker compose up --build
```

What happens:

- worker schedules ticket status sync
- mock ticket becomes `Resolved`
- local incident becomes `resolved`
- reporter notification is enqueued automatically

## 8. If Something Does Not Show Up

### No incidents in dashboard

Check that you are using the same tenant in intake and dashboard.

Example:

- intake: `hackathon-demo`
- dashboard query param: `?tenant_id=hackathon-demo`

### Incident stuck in queue

Check worker logs:

```bash
docker compose logs worker
```

### API looks healthy but no traces in Jaeger

Check `.env`:

```env
OTEL_EXPORTER_MODE=otlp
```

Then rebuild:

```bash
docker compose up --build
```

## 9. Test Commands

Compile backend:

```bash
python -m compileall api/app tests
```

Run API E2E after installing Node dependencies:

```bash
npm install
npx playwright install chromium
npm run test:e2e
```

## 10. What Is Mock vs Real

By default, the stack is demo-safe:

- ticketing: mock by default
- team communicator: mock by default
- reporter email: mock by default
- resolution watcher: real polling logic, mock provider state unless you wire a real provider
- tracing: real OpenTelemetry, console or Jaeger depending on exporter mode

Real integrations can be enabled through `.env` without changing code.
