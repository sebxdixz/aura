const DEFAULT_URL = process.env.API_BASE_URL || "http://127.0.0.1:8000";
const TIMEOUT_MS = Number(process.env.API_WAIT_TIMEOUT_MS || 60000);
const INTERVAL_MS = Number(process.env.API_WAIT_INTERVAL_MS || 1500);

async function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function waitForApi() {
  const start = Date.now();
  const healthUrl = `${DEFAULT_URL}/health`;
  while (Date.now() - start < TIMEOUT_MS) {
    try {
      const res = await fetch(healthUrl);
      if (res.ok) {
        const body = await res.json().catch(() => ({}));
        if (body.status === "ok") {
          process.stdout.write(`API ready at ${healthUrl}\n`);
          return;
        }
      }
    } catch {
      // Keep retrying until timeout.
    }
    await sleep(INTERVAL_MS);
  }
  throw new Error(`API not ready after ${TIMEOUT_MS}ms (${healthUrl})`);
}

waitForApi().catch((err) => {
  process.stderr.write(`${err.message}\n`);
  process.exit(1);
});
