const { test, expect } = require("@playwright/test");

const API_BASE_URL = process.env.API_BASE_URL || "http://127.0.0.1:8000";

function uniqueTenant(prefix = "pw-api") {
  const now = Date.now();
  const rand = Math.floor(Math.random() * 10000);
  return `${prefix}-${now}-${rand}`;
}

async function pollIncident(request, incidentId, timeoutMs = 90000) {
  const started = Date.now();
  while (Date.now() - started < timeoutMs) {
    const res = await request.get(`${API_BASE_URL}/api/incidents/${encodeURIComponent(incidentId)}`);
    expect(res.ok()).toBeTruthy();
    const incident = await res.json();
    if (!["submitted", "processing"].includes(String(incident.processing_state || ""))) {
      return incident;
    }
    await new Promise((resolve) => setTimeout(resolve, 1500));
  }
  throw new Error(`Timed out waiting for incident ${incidentId} to finish processing`);
}

function pngChunk(type, data) {
  const typeBuffer = Buffer.from(type, "ascii");
  const lengthBuffer = Buffer.alloc(4);
  lengthBuffer.writeUInt32BE(data.length, 0);
  const crcBuffer = Buffer.alloc(4);
  crcBuffer.writeUInt32BE(crc32(Buffer.concat([typeBuffer, data])), 0);
  return Buffer.concat([lengthBuffer, typeBuffer, data, crcBuffer]);
}

function crc32(buffer) {
  let crc = 0xffffffff;
  for (const byte of buffer) {
    crc ^= byte;
    for (let i = 0; i < 8; i += 1) {
      const mask = -(crc & 1);
      crc = (crc >>> 1) ^ (0xedb88320 & mask);
    }
  }
  return (crc ^ 0xffffffff) >>> 0;
}

function buildPngWithText(text) {
  const signature = Buffer.from("89504e470d0a1a0a", "hex");
  const ihdr = pngChunk("IHDR", Buffer.from("00000001000000010802000000", "hex"));
  const textChunk = pngChunk("tEXt", Buffer.from(`evidence\0${text}`, "latin1"));
  const idat = pngChunk("IDAT", Buffer.from("789c6360000000020001", "hex"));
  const iend = pngChunk("IEND", Buffer.alloc(0));
  return Buffer.concat([signature, ihdr, textChunk, idat, iend]);
}

test.describe("AURA API contract", () => {
  test("submit without attachment still works", async ({ request }) => {
    const tenant = uniqueTenant("api-basic");
    const reporter = `${tenant}@demo.com`;

    await request.post(`${API_BASE_URL}/api/tenants/register`, {
      data: { tenant_id: tenant, name: `Tenant ${tenant}` },
    });

    const submitRes = await request.post(`${API_BASE_URL}/api/incidents/submit`, {
      multipart: {
        tenant_id: tenant,
        reporter_email: reporter,
        description: "Checkout outage with payment 500 and coupon error.",
      },
    });

    expect(submitRes.ok()).toBeTruthy();
    const queued = await submitRes.json();
    const incident = await pollIncident(request, queued.incident_id);
    expect(incident.attachment).toBeNull();
    expect(incident.triage.attachment_used).toBeFalsy();
  });

  test("submit with valid log enriches triage and ticket description", async ({ request }) => {
    const tenant = uniqueTenant("api-log");
    const reporter = `${tenant}@demo.com`;

    await request.post(`${API_BASE_URL}/api/tenants/register`, {
      data: { tenant_id: tenant, name: `Tenant ${tenant}` },
    });

    const logBody = [
      "2026-04-08T17:21:00Z ERROR checkout-service HTTP 500 payment failed",
      "Traceback: coupon parser raised exception",
      "environment=production",
    ].join("\n");

    const submitRes = await request.post(`${API_BASE_URL}/api/incidents/submit`, {
      multipart: {
        tenant_id: tenant,
        reporter_email: reporter,
        description: "Customer checkout is failing after coupon apply.",
        attachment: {
          name: "incident.log",
          mimeType: "text/plain",
          buffer: Buffer.from(logBody, "utf-8"),
        },
      },
    });

    expect(submitRes.ok()).toBeTruthy();
    const queued = await submitRes.json();
    const incident = await pollIncident(request, queued.incident_id);
    expect(incident.attachment.attachment_filename).toBe("incident.log");
    expect(incident.attachment.attachment_used).toBeTruthy();
    expect(incident.triage.attachment_used).toBeTruthy();
    expect(incident.triage.attachment_summary.toLowerCase()).toContain("checkout-service");
    expect(incident.triage.evidence_from_attachment.join(" ").toLowerCase()).toContain("500");
    expect(incident.triage.target_team).toMatch(/payments|checkout backend|platform\/sre/i);
    expect(Number(incident.triage.description_score)).toBeGreaterThan(0);
    expect(Array.isArray(incident.triage.rag_evidence)).toBeTruthy();
    expect(String(incident.triage.triage_mode || "").length).toBeGreaterThan(0);
    expect(incident.ticket.description.toLowerCase()).toContain("attachment evidence");
    expect(incident.ticket.description.toLowerCase()).toContain("triage mode");
  });

  test("submit with valid image uses extracted screenshot evidence", async ({ request }) => {
    const tenant = uniqueTenant("api-image");
    const reporter = `${tenant}@demo.com`;

    await request.post(`${API_BASE_URL}/api/tenants/register`, {
      data: { tenant_id: tenant, name: `Tenant ${tenant}` },
    });

    const image = buildPngWithText("Payment failed HTTP 500 checkout-service");
    const submitRes = await request.post(`${API_BASE_URL}/api/incidents/submit`, {
      multipart: {
        tenant_id: tenant,
        reporter_email: reporter,
        description: "User uploaded screenshot for checkout issue.",
        attachment: {
          name: "checkout-error.png",
          mimeType: "image/png",
          buffer: image,
        },
      },
    });

    expect(submitRes.ok()).toBeTruthy();
    const queued = await submitRes.json();
    const incident = await pollIncident(request, queued.incident_id);
    expect(incident.attachment.attachment_type).toBe("image");
    expect(incident.triage.attachment_used).toBeTruthy();
    expect(incident.triage.attachment_summary.toLowerCase()).toContain("screenshot");
    expect(incident.triage.evidence_from_attachment.join(" ").toLowerCase()).toContain("checkout-service");
    expect(incident.triage.attachment_score).toBeGreaterThan(0);
    expect(String(incident.triage.scope_assessment || "").length).toBeGreaterThan(0);
  });

  test("invalid attachment type is rejected", async ({ request }) => {
    const tenant = uniqueTenant("api-invalid");
    const reporter = `${tenant}@demo.com`;

    const submitRes = await request.post(`${API_BASE_URL}/api/incidents/submit`, {
      multipart: {
        tenant_id: tenant,
        reporter_email: reporter,
        description: "Invalid attachment test.",
        attachment: {
          name: "malware.exe",
          mimeType: "application/octet-stream",
          buffer: Buffer.from("evil"),
        },
      },
    });

    expect(submitRes.status()).toBe(400);
  });

  test("oversized attachment is rejected", async ({ request }) => {
    const tenant = uniqueTenant("api-large");
    const reporter = `${tenant}@demo.com`;

    const bigBuffer = Buffer.alloc(5 * 1024 * 1024 + 1024, "a");
    const submitRes = await request.post(`${API_BASE_URL}/api/incidents/submit`, {
      multipart: {
        tenant_id: tenant,
        reporter_email: reporter,
        description: "Oversized attachment test.",
        attachment: {
          name: "huge.log",
          mimeType: "text/plain",
          buffer: bigBuffer,
        },
      },
    });

    expect(submitRes.status()).toBe(400);
  });

  test("metrics expose attachment processing counters", async ({ request }) => {
    const tenant = uniqueTenant("api-metrics");
    const reporter = `${tenant}@demo.com`;

    await request.post(`${API_BASE_URL}/api/tenants/register`, {
      data: { tenant_id: tenant, name: `Tenant ${tenant}` },
    });

    await request.post(`${API_BASE_URL}/api/incidents/submit`, {
      multipart: {
        tenant_id: tenant,
        reporter_email: reporter,
        description: "Checkout screenshot with failure evidence.",
        attachment: {
          name: "checkout.png",
          mimeType: "image/png",
          buffer: buildPngWithText("Payment failed HTTP 500 checkout-service"),
        },
      },
    });

    const metricsRes = await request.get(`${API_BASE_URL}/metrics`);
    expect(metricsRes.ok()).toBeTruthy();
    const metrics = await metricsRes.json();
    expect(Number(metrics.attachments_received_total)).toBeGreaterThanOrEqual(1);
    expect(Number(metrics.attachments_processed_total)).toBeGreaterThanOrEqual(1);
    expect(Number(metrics.attachment_used_in_triage_total)).toBeGreaterThanOrEqual(1);
  });

  test("deduplication and tenant isolation remain intact with attachments", async ({ request }) => {
    const tenantA = uniqueTenant("api-a");
    const tenantB = uniqueTenant("api-b");
    const description = "Checkout coupon flow returns 500.";

    await request.post(`${API_BASE_URL}/api/tenants/register`, {
      data: { tenant_id: tenantA, name: `Tenant ${tenantA}` },
    });
    await request.post(`${API_BASE_URL}/api/tenants/register`, {
      data: { tenant_id: tenantB, name: `Tenant ${tenantB}` },
    });

    const first = await request.post(`${API_BASE_URL}/api/incidents/submit`, {
      multipart: {
        tenant_id: tenantA,
        reporter_email: `${tenantA}@demo.com`,
        description,
        attachment: {
          name: "incident.log",
          mimeType: "text/plain",
          buffer: Buffer.from("checkout-service HTTP 500 payment failed", "utf-8"),
        },
      },
    });
    expect(first.ok()).toBeTruthy();
    const second = await request.post(`${API_BASE_URL}/api/incidents/submit`, {
      multipart: {
        tenant_id: tenantA,
        reporter_email: `${tenantA}@demo.com`,
        description,
        attachment: {
          name: "incident.log",
          mimeType: "text/plain",
          buffer: Buffer.from("checkout-service HTTP 500 payment failed", "utf-8"),
        },
      },
    });
    const dedupQueued = await second.json();
    const dedup = await pollIncident(request, dedupQueued.incident_id);
    expect(dedup.triage.is_duplicate).toBeTruthy();

    await request.post(`${API_BASE_URL}/api/incidents/submit`, {
      multipart: {
        tenant_id: tenantB,
        reporter_email: `${tenantB}@demo.com`,
        description,
        attachment: {
          name: "incident.log",
          mimeType: "text/plain",
          buffer: Buffer.from("checkout-service HTTP 500 payment failed", "utf-8"),
        },
      },
    });

    const listARes = await request.get(`${API_BASE_URL}/api/incidents?tenant_id=${encodeURIComponent(tenantA)}`);
    const listA = await listARes.json();
    const listBRes = await request.get(`${API_BASE_URL}/api/incidents?tenant_id=${encodeURIComponent(tenantB)}`);
    const listB = await listBRes.json();

    expect(listA.every((item) => item.tenant_id === tenantA)).toBeTruthy();
    expect(listB.every((item) => item.tenant_id === tenantB)).toBeTruthy();
  });

  test("multi-ticket intelligence links related incidents and detects recurrence", async ({ request }) => {
    const tenant = uniqueTenant("api-mti");
    await request.post(`${API_BASE_URL}/api/tenants/register`, {
      data: { tenant_id: tenant, name: `Tenant ${tenant}` },
    });

    const reporter = `${tenant}@demo.com`;
    const descriptions = [
      "Customers cannot complete payment in checkout. HTTP 500 after clicking pay.",
      "Payment failed in checkout with 500 from checkout-service.",
      "Users report checkout payment timeout and internal server error.",
    ];

    const incidents = [];
    for (const description of descriptions) {
      const res = await request.post(`${API_BASE_URL}/api/incidents/submit`, {
        multipart: {
          tenant_id: tenant,
          reporter_email: reporter,
          description,
          attachment: {
            name: "incident.log",
            mimeType: "text/plain",
            buffer: Buffer.from("checkout-service payment failed HTTP 500 timeout", "utf-8"),
          },
        },
      });
      expect(res.ok()).toBeTruthy();
      const queued = await res.json();
      incidents.push(await pollIncident(request, queued.incident_id));
    }

    const latest = incidents[2];
    expect(Array.isArray(latest.triage.related_incident_ids)).toBeTruthy();
    expect(latest.triage.related_incident_ids.length).toBeGreaterThan(0);
    expect(Number(latest.triage.recurrence_count_30d)).toBeGreaterThan(0);
    expect(String(latest.triage.multi_ticket_influence_reasoning || "").length).toBeGreaterThan(0);
  });
});
