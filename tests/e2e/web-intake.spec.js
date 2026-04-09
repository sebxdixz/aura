const { test, expect } = require("@playwright/test");

const describeWeb = process.env.RUN_WEB_E2E === "true" ? test.describe : test.describe.skip;
const WEB_BASE_URL = process.env.WEB_BASE_URL || "http://127.0.0.1:3000";
const DASHBOARD_BASE_URL = process.env.DASHBOARD_BASE_URL || WEB_BASE_URL;
const ADMIN_KEY = process.env.WEB_ADMIN_KEY || process.env.TENANT_ADMIN_KEY || "hackathon2024";
const WEB_SUBMIT_TIMEOUT_MS = Number(process.env.WEB_SUBMIT_TIMEOUT_MS || 180000);
const WEB_RESOLVE_TIMEOUT_MS = Number(process.env.WEB_RESOLVE_TIMEOUT_MS || 60000);
const WEB_DASHBOARD_LOAD_TIMEOUT_MS = Number(process.env.WEB_DASHBOARD_LOAD_TIMEOUT_MS || 60000);

function uniqueTenant(prefix = "pw-web") {
  const now = Date.now();
  const rand = Math.floor(Math.random() * 10000);
  return `${prefix}-${now}-${rand}`;
}

describeWeb("AURA web separation", () => {
  test("welcome + public intake + tenant dashboard flow works end-to-end", async ({ page, context }) => {
    test.setTimeout(180000);
    const tenant = uniqueTenant("tenant-ui");
    const reporter = `${tenant}@demo.com`;
    const tenantUpper = tenant.toUpperCase();

    await page.goto(`${DASHBOARD_BASE_URL}/`, { waitUntil: "domcontentloaded" });
    await expect(page.locator("body")).toContainText("Welcome", { timeout: 30000 });
    await expect(page.locator('a[href="/dashboard"]').first()).toBeVisible();

    await page.goto(`${WEB_BASE_URL}/intake/${tenant}`);
    await expect(page.locator("#incidentForm")).toBeVisible();

    await page.fill("#reporter_name", "Test Reporter");
    await page.fill("#reporter_email", reporter);
    await page.selectOption("#issue_type", "checkout");
    await page.fill("#description", "Checkout returns 500 when coupon is applied.");
    await page.click("#submitBtn");

    await expect(page).toHaveURL(new RegExp("/thanks"), { timeout: WEB_SUBMIT_TIMEOUT_MS });
    await expect(page.locator("#thanksView")).toBeVisible();
    await expect(page.locator("#thanksView")).toContainText("Report Received");

    const dashboard = await context.newPage();
    await dashboard.goto(`${DASHBOARD_BASE_URL}/dashboard`);
    await dashboard.fill("#l_tenant", tenant);
    await dashboard.fill("#l_key", ADMIN_KEY);
    await dashboard.click('#loginForm button[type="submit"]');

    await expect(dashboard.locator("#tenantChipLabel")).toContainText(tenantUpper, {
      timeout: WEB_DASHBOARD_LOAD_TIMEOUT_MS
    });
    await expect
      .poll(
        async () => {
          const raw = await dashboard.locator("#stat-total").innerText();
          return Number(raw.replace(/[^\d.-]/g, ""));
        },
        { timeout: WEB_DASHBOARD_LOAD_TIMEOUT_MS }
      )
      .toBeGreaterThanOrEqual(1);

    await dashboard.click("#nav-incidents");
    const resolveBtn = dashboard.locator("button", { hasText: /resolve/i }).first();
    await expect(resolveBtn).toBeVisible();
    dashboard.once("dialog", (dialog) =>
      dialog.accept("Applied remediation, deployed fix, and verified recovery in production.")
    );
    await resolveBtn.click();
    await expect(dashboard.locator(".status-resolved").first()).toContainText("RESOLVED", {
      timeout: WEB_RESOLVE_TIMEOUT_MS
    });
  });
});
