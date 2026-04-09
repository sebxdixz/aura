const { test, expect } = require("@playwright/test");

const describeWeb = process.env.RUN_WEB_E2E === "true" ? test.describe : test.describe.skip;
const DASHBOARD_BASE_URL = process.env.DASHBOARD_BASE_URL || "http://127.0.0.1:3001";
const WEB_SUBMIT_TIMEOUT_MS = Number(process.env.WEB_SUBMIT_TIMEOUT_MS || 90000);
const WEB_RESOLVE_TIMEOUT_MS = Number(process.env.WEB_RESOLVE_TIMEOUT_MS || 60000);
const WEB_DASHBOARD_LOAD_TIMEOUT_MS = Number(process.env.WEB_DASHBOARD_LOAD_TIMEOUT_MS || 60000);

function uniqueTenant(prefix = "pw-web") {
  const now = Date.now();
  const rand = Math.floor(Math.random() * 10000);
  return `${prefix}-${now}-${rand}`;
}

describeWeb("AURA web separation", () => {
  test("public report portal shows attachment evidence end-to-end", async ({ page, context }) => {
    const tenant = uniqueTenant("tenant-ui");
    const reporter = `${tenant}@demo.com`;

    await page.goto(`/intake/${tenant}`);
    await expect(page.locator("#incidentForm")).toBeVisible();

    await page.fill("#reporter_name", "Test Reporter");
    await page.fill("#reporter_email", reporter);
    await page.selectOption("#issue_type", "checkout");
    await page.fill("#description", "Checkout returns 500 when coupon is applied.");
    await page.locator("#attachment").setInputFiles({
      name: "incident.log",
      mimeType: "text/plain",
      buffer: Buffer.from("2026-04-08T17:21:00Z ERROR checkout-service HTTP 500 payment failed", "utf-8"),
    });

    await page.click("#submitBtn");

    await expect(page.locator("#outStatus")).toContainText("COMPLETED", { timeout: WEB_SUBMIT_TIMEOUT_MS });
    await expect(page.locator("#resAttachment")).toContainText("checkout", { timeout: WEB_SUBMIT_TIMEOUT_MS });
    await expect(page.locator("#resInfluence")).toContainText("Attachment evidence", { timeout: WEB_SUBMIT_TIMEOUT_MS });

    const dashboard = await context.newPage();
    await dashboard.goto(`${DASHBOARD_BASE_URL}/?tenant_id=${encodeURIComponent(tenant)}`);
    await dashboard.click("#loadWorkspaceBtn");

    await expect(dashboard.locator("#statusMsg")).toContainText(`workspace loaded: ${tenant}`, {
      timeout: WEB_DASHBOARD_LOAD_TIMEOUT_MS,
    });
    await expect(dashboard.locator("tbody")).toContainText("incident.log", { timeout: WEB_DASHBOARD_LOAD_TIMEOUT_MS });
    await expect(dashboard.locator("tbody")).toContainText("checkout", { timeout: WEB_DASHBOARD_LOAD_TIMEOUT_MS });

    const resolveBtn = dashboard.locator("button[data-incident-id]").first();
    await expect(resolveBtn).toBeVisible();
    const incidentId = await resolveBtn.getAttribute("data-incident-id");
    await resolveBtn.click();
    await expect(dashboard.locator(`#status-${incidentId}`)).toContainText("RESOLVED", { timeout: WEB_RESOLVE_TIMEOUT_MS });
  });
});
