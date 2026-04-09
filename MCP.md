# MCP Integrations Guide (Jira + Slack)

Guia tecnica para configurar integraciones de ticketing y notificaciones en AURA usando el flujo actual:

- Configuracion por tenant desde el Dashboard (`/dashboard`).
- Orquestacion via ReAct + MCP Bridge.
- Fallback controlado a integraciones directas si el tool-calling MCP falla.

## 1. Arquitectura de Integracion

1. El usuario configura secretos por tenant en `Settings` del dashboard.
2. AURA guarda secretos cifrados por `tenant_id` en `tenant_integrations`.
3. El backend decide ruta de ejecucion:
   - ReAct + MCP (si esta habilitado y disponible).
   - Integracion directa Jira/Slack (si hay credenciales tenant).
   - Mock/fallback (si falta configuracion o hay error externo).

## 2. Configuracion Slack

### 2.1 Crear App en Slack

1. Ir a [Slack API Dashboard](https://api.slack.com/apps).
2. Crear app `From scratch`.
3. Seleccionar el workspace objetivo.

### 2.2 Permisos recomendados

En `OAuth & Permissions` agregar scopes de bot:

- `chat:write`
- `channels:read`
- `groups:read`
- `im:write`

Instalar la app en el workspace y obtener:

- `Bot User OAuth Token` (`xoxb-...`)
- (Opcional) Incoming Webhook URL

### 2.3 Datos requeridos en AURA (tenant settings)

- `webhook_url` (opcional, recomendado para inicio rapido)
- `bot_token` (opcional si usas webhook, obligatorio si no)
- `default_channel_id` (obligatorio con bot token)
- `team_id` (opcional segun implementacion del entorno)

Nota: El bot debe estar invitado al canal (`/invite @<bot-name>`).

## 3. Configuracion Jira

### 3.1 Token de API

1. Ir a [Atlassian API Tokens](https://id.atlassian.com/manage-profile/security/api-tokens).
2. Crear token para AURA.
3. Guardar el token de forma segura.

### 3.2 Datos requeridos en AURA (tenant settings)

- `base_url` (ej: `https://your-org.atlassian.net`)
- `email` (usuario Atlassian del token)
- `api_token`
- `project_key` (key o nombre del proyecto)
- `issue_type` (nombre o ID; AURA aplica fallback automatico si no coincide)

## 4. Variables de Entorno del Bridge / Backend

Estas variables habilitan la capa MCP y su conexion interna:

```env
MOCK_MODE=false
REACT_ENGINE=openrouter_mcp
MCP_BRIDGE_URL=http://mcp_bridge:8080/invoke
MCP_JIRA_SERVER=jira
MCP_JIRA_TOOL=jira_create_issue
MCP_SLACK_SERVER=slack
MCP_SLACK_TOOL=slack_post_message
```

Opcionales para tooling MCP:

```env
JIRA_MCP_COMMAND=mcp-atlassian
SLACK_MCP_COMMAND=npx
SLACK_MCP_ARGS=-y @modelcontextprotocol/server-slack
```

## 5. Configuracion recomendada en Dashboard

1. Abrir `http://localhost:3000/dashboard`.
2. Login con `tenant_id` + `x-tenant-admin-key`.
3. Ir a `Settings`.
4. Guardar configuracion Jira y Slack para el tenant.
5. Ejecutar `Test Jira` y `Test Slack`.
6. Verificar salida `ok: true` en el panel `Result`.

## 6. Troubleshooting

### Jira: `issuetype` invalido

- Verificar que el proyecto tenga ese issue type habilitado.
- Usar nombre exacto del tipo o ID.
- AURA intenta fallback automatico al primer tipo valido no-subtask.

### Jira: `401 Unauthorized`

- Revisar `email` + `api_token`.
- Confirmar permisos de `Create Issues` en el proyecto.

### Slack: no envia mensaje

- Verificar webhook URL o `bot_token + channel_id`.
- Asegurar que el bot este invitado al canal.
- Confirmar que `MOCK_MODE=false`.

### Ruta MCP no disponible

- Revisar `docker compose ps` y salud de `mcp_bridge`.
- Confirmar `MCP_BRIDGE_URL` accesible desde `api`.
- Verificar que los comandos MCP del bridge esten instalados.

## 7. Verificacion E2E Minima

1. Probar integraciones desde `/dashboard` (`Test Jira`, `Test Slack`).
2. Enviar incidente por `http://localhost:3000/intake/<tenant>`.
3. Revisar incidente en dashboard del mismo tenant.
4. Confirmar en respuesta/API:
   - `ticket.provider = jira`
   - `notifications` incluye detalle de Slack.
