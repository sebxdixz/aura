const express = require("express");
const { spawn } = require("node:child_process");

const app = express();

const PORT = Number(process.env.PORT || 8080);
const REQUEST_TIMEOUT_MS = Number(process.env.MCP_BRIDGE_TIMEOUT_MS || 35000);
const MCP_BRIDGE_TOKEN = String(process.env.MCP_BRIDGE_TOKEN || "").trim();

const JIRA_DEFAULT_ISSUE_TYPE = String(process.env.JIRA_DEFAULT_ISSUE_TYPE || "Bug").trim() || "Bug";
const JIRA_DEFAULT_PROJECT_KEY = String(process.env.JIRA_PROJECT_KEY || "").trim();
const SLACK_DEFAULT_CHANNEL_ID = String(process.env.SLACK_DEFAULT_CHANNEL_ID || "").trim();

app.use(express.json({ limit: "1mb" }));

const SERVERS = {
  jira: {
    command: process.env.JIRA_MCP_COMMAND || "mcp-atlassian",
    args: parseArgs(process.env.JIRA_MCP_ARGS || ""),
  },
  slack: {
    command: process.env.SLACK_MCP_COMMAND || "npx",
    args: parseArgs(process.env.SLACK_MCP_ARGS || "-y @modelcontextprotocol/server-slack"),
  },
};

app.get("/health", (_req, res) => {
  res.json({ status: "ok", service: "mcp-bridge" });
});

app.post("/invoke", requireBridgeToken, async (req, res) => {
  const payload = req.body || {};
  const server = String(payload.server || "").trim().toLowerCase();
  const tool = String(payload.tool || "").trim();
  const args = isObject(payload.arguments) ? payload.arguments : {};

  if (!server || !tool) {
    return res.status(400).json({ ok: false, error: "request must include server and tool" });
  }
  if (!SERVERS[server]) {
    return res.status(404).json({ ok: false, error: `MCP server '${server}' is not configured` });
  }

  const resolvedTool = resolveToolName(server, tool);
  const preparedArgs = prepareArguments(server, resolvedTool, args);
  if (preparedArgs.error) {
    return res.status(400).json({ ok: false, error: preparedArgs.error });
  }

  try {
    const rawResult = await callToolViaStdio({
      server,
      tool: resolvedTool,
      args: preparedArgs.value,
    });
    const normalized = normalizeBridgeResult(server, resolvedTool, rawResult, preparedArgs.value);
    return res.json({ ok: true, result: normalized });
  } catch (error) {
    return res.status(500).json({
      ok: false,
      error: error instanceof Error ? error.message : String(error),
    });
  }
});

app.listen(PORT, () => {
  console.log(`[mcp-bridge] listening on :${PORT}`);
});

function requireBridgeToken(req, res, next) {
  if (!MCP_BRIDGE_TOKEN) {
    return next();
  }
  const auth = String(req.headers.authorization || "");
  if (auth !== `Bearer ${MCP_BRIDGE_TOKEN}`) {
    return res.status(401).json({ ok: false, error: "unauthorized" });
  }
  return next();
}

function parseArgs(value) {
  const source = String(value || "").trim();
  if (!source) {
    return [];
  }
  const matches = source.match(/(?:[^\s"]+|"[^"]*")+/g) || [];
  return matches.map((item) => item.replace(/^"(.*)"$/, "$1"));
}

function resolveToolName(server, requestedTool) {
  const alias = {
    jira: {
      create_issue: "jira_create_issue",
      jira_create_issue: "jira_create_issue",
    },
    slack: {
      post_message: "slack_post_message",
      slack_post_message: "slack_post_message",
    },
  };
  return alias[server]?.[requestedTool] || requestedTool;
}

function prepareArguments(server, tool, args) {
  if (server === "jira") {
    if (tool !== "jira_create_issue") {
      return { value: args };
    }
    const projectKey = String(args.project_key || JIRA_DEFAULT_PROJECT_KEY || "").trim();
    if (!projectKey) {
      return { error: "jira_create_issue requires project_key (or JIRA_PROJECT_KEY env var)" };
    }
    const summaryBase = String(args.summary || args.technical_summary || args.description || "AURA Incident").trim();
    const summary = truncate(summaryBase, 180);
    const description = buildJiraDescription(args);
    return {
      value: {
        project_key: projectKey,
        summary,
        issue_type: String(args.issue_type || JIRA_DEFAULT_ISSUE_TYPE || "Bug").trim() || "Bug",
        description,
      },
    };
  }

  if (server === "slack") {
    if (tool !== "slack_post_message") {
      return { value: args };
    }
    const channelId = String(args.channel_id || args.channel || SLACK_DEFAULT_CHANNEL_ID || "").trim();
    if (!channelId) {
      return { error: "slack_post_message requires channel_id (or SLACK_DEFAULT_CHANNEL_ID env var)" };
    }
    const text = buildSlackText(args);
    const prepared = { channel_id: channelId, text };
    if (args.thread_ts) {
      prepared.thread_ts = String(args.thread_ts);
    }
    return { value: prepared };
  }

  return { value: args };
}

function buildJiraDescription(args) {
  const lines = [];
  const incidentId = str(args.incident_id);
  const tenantId = str(args.tenant_id);
  const severity = str(args.severity).toUpperCase();
  const service = str(args.affected_service);
  const summary = str(args.summary);
  const description = str(args.description);
  const rca = str(args.root_cause_analysis);
  const fix = str(args.proposed_fix);
  const cli = str(args.proposed_cli_command);

  if (incidentId) lines.push(`*Incident ID:* ${incidentId}`);
  if (tenantId) lines.push(`*Tenant:* ${tenantId}`);
  if (severity) lines.push(`*Severity:* ${severity}`);
  if (service) lines.push(`*Service:* ${service}`);
  if (summary) lines.push(`*Summary:* ${summary}`);
  if (description) lines.push(`\n*Report Description*\n${description}`);
  if (rca) lines.push(`\n*Initial RCA*\n${rca}`);
  if (fix) lines.push(`\n*Proposed Fix*\n${fix}`);
  if (cli) lines.push(`\n*Verification Command*\n${cli}`);

  return lines.join("\n");
}

function buildSlackText(args) {
  const severity = str(args.severity).toUpperCase();
  const service = str(args.affected_service);
  const incidentId = str(args.incident_id);
  const summary = str(args.summary || args.description || "New incident reported");
  const ticketId = str(args.ticket_id);
  const ticketUrl = str(args.ticket_url);
  const rca = str(args.root_cause_analysis);
  const fix = str(args.proposed_fix);

  const lines = [];
  lines.push(`*AURA Incident Alert*`);
  if (severity) lines.push(`Severity: *${severity}*`);
  if (service) lines.push(`Service: ${service}`);
  if (incidentId) lines.push(`Incident: ${incidentId}`);
  lines.push(`Summary: ${summary}`);
  if (ticketId) lines.push(`Ticket: ${ticketId}${ticketUrl ? ` (${ticketUrl})` : ""}`);
  if (rca) lines.push(`RCA: ${rca}`);
  if (fix) lines.push(`Proposed fix: ${fix}`);
  return lines.join("\n");
}

async function callToolViaStdio({ server, tool, args }) {
  const cfg = SERVERS[server];
  const child = spawn(cfg.command, cfg.args, {
    env: process.env,
    stdio: ["pipe", "pipe", "pipe"],
    shell: false,
  });

  let resolved = false;
  let lineBuffer = "";
  let stderr = "";
  let nextId = 1;
  const pending = new Map();

  const timer = setTimeout(() => {
    if (!resolved) {
      settledReject(new Error(`timeout waiting for MCP response from ${server}`));
    }
  }, REQUEST_TIMEOUT_MS);

  const settledReject = (error) => {
    if (resolved) return;
    resolved = true;
    clearTimeout(timer);
    for (const waiter of pending.values()) {
      waiter.reject(error);
    }
    pending.clear();
    safeKill(child);
  };

  const settledResolve = (value, requestId) => {
    const waiter = pending.get(requestId);
    if (!waiter) return;
    pending.delete(requestId);
    waiter.resolve(value);
  };

  child.stdout.on("data", (chunk) => {
    lineBuffer += chunk.toString("utf8");
    const lines = lineBuffer.split(/\r?\n/);
    lineBuffer = lines.pop() || "";
    for (const line of lines) {
      const trimmed = line.trim();
      if (!trimmed) continue;
      let message;
      try {
        message = JSON.parse(trimmed);
      } catch (_error) {
        continue;
      }
      if (message && Object.prototype.hasOwnProperty.call(message, "id")) {
        const waiter = pending.get(message.id);
        if (!waiter) continue;
        if (message.error) {
          waiter.reject(new Error(`MCP error: ${JSON.stringify(message.error)}`));
          pending.delete(message.id);
          continue;
        }
        settledResolve(message.result, message.id);
      }
    }
  });

  child.stderr.on("data", (chunk) => {
    stderr += chunk.toString("utf8");
  });

  child.on("error", (error) => {
    settledReject(new Error(`failed to start MCP process for ${server}: ${error.message}`));
  });

  child.on("close", (code) => {
    if (!resolved && pending.size > 0) {
      settledReject(new Error(`MCP process for ${server} exited (${code}). stderr=${stderr.trim()}`));
    }
  });

  const sendRequest = (method, params) =>
    new Promise((resolve, reject) => {
      const id = nextId++;
      pending.set(id, { resolve, reject });
      try {
        child.stdin.write(
          JSON.stringify({
            jsonrpc: "2.0",
            id,
            method,
            params,
          }) + "\n"
        );
      } catch (error) {
        pending.delete(id);
        reject(error);
      }
    });

  const sendNotification = (method, params) => {
    child.stdin.write(
      JSON.stringify({
        jsonrpc: "2.0",
        method,
        params,
      }) + "\n"
    );
  };

  try {
    await sendRequest("initialize", {
      protocolVersion: "2024-11-05",
      capabilities: {},
      clientInfo: { name: "aura-mcp-bridge", version: "1.1.0" },
    });
    sendNotification("notifications/initialized", {});
    const toolResult = await sendRequest("tools/call", {
      name: tool,
      arguments: args,
    });
    resolved = true;
    clearTimeout(timer);
    safeKill(child);
    return toolResult;
  } catch (error) {
    settledReject(error instanceof Error ? error : new Error(String(error)));
    throw error;
  }
}

function normalizeBridgeResult(server, tool, rawResult, requestArgs) {
  if (isObject(rawResult) && rawResult.isError) {
    const errorText = extractErrorText(rawResult);
    throw new Error(errorText || `MCP tool ${server}/${tool} returned isError=true`);
  }

  const normalized = extractStructuredPayload(rawResult);

  if (server === "jira" && tool === "jira_create_issue") {
    const key =
      str(normalized.ticket_id) ||
      str(normalized.issue_key) ||
      str(normalized.key) ||
      extractIssueKeyFromText(str(normalized.message));
    const url = str(normalized.url) || str(normalized.issue_url) || str(normalized.browse_url);
    return {
      ...normalized,
      ticket_id: key || "",
      issue_key: key || "",
      key: key || "",
      url: url || "",
    };
  }

  if (server === "slack" && tool === "slack_post_message") {
    const detail = str(normalized.detail) || str(normalized.message) || "Slack message sent.";
    return {
      ...normalized,
      detail,
      channel_id: str(normalized.channel_id) || str(requestArgs.channel_id) || "",
    };
  }

  return normalized;
}

function extractStructuredPayload(rawResult) {
  if (isObject(rawResult)) {
    if (isObject(rawResult.structuredContent)) {
      return rawResult.structuredContent;
    }
    if (Array.isArray(rawResult.content)) {
      for (const item of rawResult.content) {
        if (!isObject(item) || item.type !== "text" || typeof item.text !== "string") continue;
        const text = item.text.trim();
        if (!text) continue;
        try {
          const parsed = JSON.parse(text);
          if (isObject(parsed)) return parsed;
        } catch (_error) {
          return { message: text };
        }
      }
    }
    return rawResult;
  }
  return { value: rawResult };
}

function extractErrorText(rawResult) {
  if (!isObject(rawResult) || !Array.isArray(rawResult.content)) return "";
  for (const item of rawResult.content) {
    if (isObject(item) && item.type === "text" && typeof item.text === "string") {
      const text = item.text.trim();
      if (text) return text;
    }
  }
  return "";
}

function extractIssueKeyFromText(text) {
  const match = String(text || "").match(/\b([A-Z][A-Z0-9]+-\d+)\b/);
  return match ? match[1] : "";
}

function truncate(value, maxLen) {
  const source = String(value || "");
  if (source.length <= maxLen) return source;
  return source.slice(0, Math.max(0, maxLen - 3)) + "...";
}

function str(value) {
  return typeof value === "string" ? value.trim() : "";
}

function isObject(value) {
  return value && typeof value === "object" && !Array.isArray(value);
}

function safeKill(child) {
  try {
    if (!child.killed) child.kill();
  } catch (_error) {
    // ignore
  }
}
