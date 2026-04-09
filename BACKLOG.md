# AURA Product Backlog

Backlog operativo para construir AURA con foco en entrega de hackathon.

---

## Snapshot para Revision AI (2026-04-09)

Funcionalidades clave pedidas y estado:

- [x] Login y register en welcome (`/`)
- [x] Multi-tenant real con aislamiento por `tenant_id`
- [x] Dashboard privado por tenant (`/dashboard`)
- [x] Formulario publico unico por tenant (`/intake/{tenant}`)
- [x] Ingesta multimodal (texto + imagen/pdf/audio/log)
- [x] Pipeline LLM de dos etapas (extraccion multimodal + analisis tecnico)
- [x] RAG con `pgvector` en la misma base Docker
- [x] Indexacion de repositorios GitHub directo a vector DB (sin clone local)
- [x] Integracion Jira por tenant (config + test + creacion de ticket)
- [x] Integracion Slack por tenant (config + test + notificacion a equipo)
- [x] Soporte multilenguaje ES/EN en UI principal
- [x] Observabilidad (`/metrics`, audit logs, insights)
- [x] ReAct + MCP bridge con fallback a integracion directa/mock

Implementacion actual:

- Arquitectura activa: `web`, `api`, `db`, `mcp_bridge` en Docker Compose.
- Frontend unificado por rutas: `/`, `/dashboard`, `/intake/{tenant}`, `/thanks`.
- API E2E con endpoints de submit/list/get/resolve.
- Guardrails basicos activos para input y tool-calling.
- Persistencia real en PostgreSQL con esquema canonico en `db/init/001_schema.sql`.
- Endpoints de observabilidad por tenant:
  - `GET /api/tenants/{tenant_id}/audit-logs`
  - `GET /api/tenants/{tenant_id}/insights/summary`
- RCA/Auto-Fix, deduplicacion, severity scoring y runbook suggestions activos.
- Pipeline multimodal cableado en backend para archivos y texto.

---

## Objetivo de Entrega

Entregar un sistema demoable que cumpla el flujo:

`submit -> triage -> ticket -> team notify -> resolved -> reporter notify`

---

## Requisitos Obligatorios del Hackathon (No Opcionales)

- La aplicacion debe ejecutarse con `docker compose up --build`.
- Debe aceptar entrada multimodal (minimo texto + imagen/log/video).
- Debe usar LLM multimodal en el triage.
- Debe incluir guardrails basicos contra prompt injection y artefactos maliciosos.
- Debe incluir observabilidad por etapas (ingest, triage, ticket, notify, resolved).
- Debe integrar ticketing + email + communicator (real o mockeado, pero demoable).
- Debe apoyarse en un codebase e-commerce de complejidad media/alta.
- Deben existir y estar completos los entregables:
  `README.md`, `AGENTS_USE.md`, `SCALING.md`, `QUICKGUIDE.md`, `.env.example`, `docker-compose.yml`, `LICENSE`.

---

## Backlog Priorizado

## P0 - Debe quedar si o si

- [x] `P0-01` Docker Compose levanta `web`, `api`, `db` sin pasos manuales.
- [x] `P0-02` Intake UI acepta texto + archivo.
- [x] `P0-03` API procesa incidente y ejecuta triage con LLM multimodal.
- [x] `P0-04` Triage produce salida JSON valida y consistente.
- [x] `P0-05` Se crea ticket (Jira/Linear/Mock) con severidad y resumen tecnico.
- [x] `P0-06` Se notifica al equipo por communicator (Slack/Mock).
- [x] `P0-07` Se notifica al reporter cuando el ticket queda resuelto.
- [x] `P0-08` Guardrails basicos activos en input y tool-calling.
- [x] `P0-09` Observabilidad minima por etapa (logs con correlacion por `incident_id`).
- [x] `P0-10` Entregables obligatorios completos y coherentes.

## P1 - Suma puntos fuertes

- [x] `P1-01` Multi-tenant real con `tenant_id` y aislamiento de datos.
- [x] `P1-02` URL publica unica por tenant para intake.
- [x] `P1-03` Dashboard de tenant con metricas clave.
- [x] `P1-04` RCA/Auto-Fix con propuesta de archivo/comando.
- [x] `P1-05` Reintentos y fallback en integraciones externas.

## P2 - Nice to have

- [x] `P2-01` Deduplicacion de incidentes.
- [x] `P2-02` Severity scoring mas fino.
- [x] `P2-03` Runbook suggestions automaticas.
- [x] `P2-04` Vista de trazas/metricas enriquecida.

---

## Definition of Done (DoD)

Una historia se considera terminada solo si:

- Tiene evidencia ejecutable local por Docker.
- Tiene logs verificables de su etapa.
- Tiene manejo de error basico.
- Tiene documentacion minima en `QUICKGUIDE.md` o `AGENTS_USE.md`.
- No rompe el flujo E2E completo.

---

## Riesgos y Mitigaciones

- Riesgo: Integraciones externas inestables.
  Mitigacion: modo mock por `env` y fallback controlado.
- Riesgo: Regresiones por cambios paralelos en frontend.
  Mitigacion: separar pipeline de pruebas API (`npm run test:e2e`) y web (`npm run test:e2e:web`).
- Riesgo: Falta de evidencia para jurado.
  Mitigacion: mantener smoke tests y reportes Playwright.

---

## Proxima Accion del Equipo

- Validar demo con `MOCK_MODE=false` + credenciales reales del modelo para registrar evidencia en video.
- Mantener Playwright API como gate tecnico.
- Cerrar ajustes finales de frontend y correr `npm run test:e2e:all` cuando UI quede estable.
