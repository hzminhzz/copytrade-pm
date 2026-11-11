/* Reproducible, hostile browser audit of the built read-only control center. */
const { chromium } = require("/home/quant/.hermes/node/lib/node_modules/playwright");
const { spawn } = require("node:child_process");
const path = require("node:path");
const assert = require("node:assert/strict");

const project = path.resolve(__dirname, "../../..");
const serverScript = path.join(project, "scripts/dashboard_server.py");
const port = Number(process.env.PORT || "18989");
const base = process.env.TARGET_URL || `http://127.0.0.1:${port}`;
const hasExternalServer = Boolean(process.env.TARGET_URL);
const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));

async function waitForService(proc) {
  for (let i = 0; i < 60; i++) {
    if (proc && proc.exitCode !== null) throw new Error(`server exited ${proc.exitCode}`);
    try { if ((await fetch(base + "/api/health")).ok) return; } catch { /* starting */ }
    await sleep(100);
  }
  throw new Error("Dashboard server did not become healthy");
}
async function main() {
  const subprocess = hasExternalServer ? null : spawn(process.env.PYTHON || "python3", [serverScript, "--port", String(port)], {
    cwd: project, env: process.env, stdio: ["ignore", "pipe", "pipe"],
  });
  let stderr = "";
  if (subprocess) subprocess.stderr.on("data", data => { stderr += data.toString(); });
  let browser = null;
  try {
    await waitForService(subprocess);
    const response = await fetch(base + "/api/state");
    assert.equal(response.status, 200);
    const expected = await response.json();
    assert.equal(expected.runtime.observerMode, "NO_TRADE");
    assert.equal(expected.registrySync.latestAccepted, null);
    assert.equal(expected.portfolios.every(p => p.totalRiskUsd === null), true);
    const post = await fetch(base + "/api/records", { method: "POST", headers: { "content-type": "application/json" }, body: '{"status":"approved"}' });
    assert.equal(post.status, 403);
    const patch = await fetch(base + "/api/records/seed", { method: "PATCH", body: "{}" });
    assert.equal(patch.status, 403);
    browser = await chromium.launch({
      executablePath: "/home/quant/.cache/ms-playwright/chromium-1254/chrome-linux64/chrome",
      headless: true, args: ["--no-sandbox", "--disable-setuid-sandbox"],
    });
    for (const [width, height] of [[1440, 900], [768, 1024], [390, 844]]) {
      const context = await browser.newContext({ viewport: { width, height }, colorScheme: "dark" });
      const page = await context.newPage();
      const errors = [];
      page.on("pageerror", err => errors.push("pageerror: " + err.message));
      page.on("console", msg => { if (msg.type() === "error") errors.push("console: " + msg.text()); });
      const load = await page.goto(base, { waitUntil: "networkidle" });
      assert.equal(load.status(), 200);
      await page.locator(".stat-card").first().waitFor();
      await page.waitForFunction(n => document.querySelectorAll(".stat-card")[0]?.textContent?.includes(String(n)), expected.wallets.length);
      const overflow = await page.evaluate(() => document.documentElement.scrollWidth > innerWidth + 2);
      assert.equal(overflow, false, `document overflow at ${width}`);
      assert.deepEqual(errors, [], `browser errors at ${width}`);
      const statTexts = await page.locator(".stat-card").allTextContents();
      assert.ok(statTexts.some(t => t.includes(String(expected.wallets.length))));
      assert.ok(statTexts.some(t => t.includes(String(expected.portfolios.length))));
      assert.equal(await page.getByRole("button", { name: "Record decision" }).count(), 0);
      assert.equal(await page.getByRole("button", { name: "Record execution evidence" }).count(), 0);

      if (width === 1440) {
        await page.getByRole("button", { name: "Wallet health" }).click();
        assert.equal(await page.locator("tbody tr").count(), expected.wallets.length);
        const search = page.getByPlaceholder("Search wallet alias");
        await search.fill("Whale_0x5f94");
        assert.ok((await page.locator("tbody tr").count()) <= 1);
        await search.fill("");
        await page.getByRole("button", { name: "Portfolios" }).click();
        assert.equal(await page.locator("tbody tr").count(), expected.portfolios.length);
        await page.getByLabel("First portfolio").selectOption({ index: 1 });
        await page.getByLabel("Second portfolio").selectOption({ index: 2 });
        assert.equal(await page.locator(".compare-column").count(), 2);
        await page.getByRole("button", { name: "Paper & execution" }).click();
        assert.equal(await page.locator(".execution-card").count(), 4);
        assert.equal(await page.locator('select[aria-label^="Update"]').count(), 0);
        await page.getByRole("button", { name: "Gates & blockers" }).click();
        assert.equal(await page.getByRole("button", { name: "Add gate" }).count(), 0);
        await page.getByRole("button", { name: "Overview" }).click();
        await page.getByLabel("Switch to light mode").click();
        assert.equal(await page.locator(".app-shell").getAttribute("data-theme"), "light");
        await page.getByLabel("Switch to dark mode").click();
        assert.equal(await page.locator(".app-shell").getAttribute("data-theme"), "dark");
      }
      if (width === 390) {
        assert.equal(await page.locator(".mobile-menu").isVisible(), true);
        await page.locator(".mobile-menu").click();
        assert.equal(await page.locator(".sidebar-open").isVisible(), true);
        await page.locator(".mobile-close").click();
        assert.equal(await page.locator(".sidebar-open").count(), 0);
      }
      assert.deepEqual(errors, [], `browser errors after interactions ${width}`);
      const source = await page.locator("body").innerText();
      for (const marker of ["NaN", "[object Object]"]) assert.equal(source.includes(marker), false);
      console.log(`PASS ${width}x${height} responsive, no JS errors, read-only UI`);
      await context.close();
    }
  } finally {
    if (browser) await browser.close();
    if (subprocess) {
      subprocess.kill("SIGTERM");
      await Promise.race([new Promise(resolve => subprocess.once("exit", resolve)), sleep(2000)]);
    }
    if (stderr && process.env.VERBOSE) console.log(stderr.slice(-4000));
  }
}
main().catch(error => { console.error("FAIL", error.stack || error); process.exitCode = 1; });
