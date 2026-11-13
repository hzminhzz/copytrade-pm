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
        const ownerRequests = [];
        const ownerFixture = id => ({
          schema: "cwsa_chapter2_site_owner_view_v1",
          source_schema: "cwsa_chapter2_task_explanation_v1",
          observed_at: "2026-11-13T00:00:12+00:00",
          assessment_asof: "2026-11-13T00:00:12+00:00",
          scope: { portfolio: id, inspection: "evidence", epoch: "epoch-test", version: 2,
            selection_known_at: "2026-11-01T00:00:00Z",
            new_risk_source_status: id === "B" ? "SOURCE_SCOPE_READY" : "BLOCKED_EVIDENCE" },
          dimensions: {
            registry_integrity: { state: "VERIFIED", owner: "wallet_registry" },
            source_observation: { state: id === "B" ? "OBSERVE_READY" : "BLOCKED_EVIDENCE", owner: "pm_checkpoint_journal" },
            paper_finance: { state: "BLOCKED_EVIDENCE", owner: "pm03_account" },
            guardian_authorization: { state: "UNKNOWN", owner: "prop-production Guardian" },
          },
          generation_consistency: { state: id === "B" ? "UNVERIFIED" : "MIXED", reasons: ["SOURCE_POLICY_EPOCHS_MIXED"] },
          fault_isolation: { affected_portfolios: ["A", "Combo2"], unaffected_source_portfolios: ["B", "C"],
            shared_account_risk: { state: "UNKNOWN", owner: "prop-production Guardian" } },
          owner_heads: {
            registry: { inventory_sha256: "c".repeat(64) },
            portfolio_seal: { definition_sha256: "d".repeat(64) },
            source: { head_sha256: "a".repeat(64), source_heads_by_wallet: { W028: "b".repeat(64) },
              original_checkpoint_by_wallet_ms: { W028: 1794500000000 },
              receipt_first_known_ms_by_wallet: { W028: 1794500000123 },
              published_ms_by_wallet: { W028: 1794500000130 } },
          },
          economics: { realized_pnl_usd: null, total_costs_usd: null, current_equity_usd: null, drawdown_usd: null },
          blockers: [{ reason_code: "SOURCE_CHECKPOINT_STALE", owner: "source", affected_portfolio: id }],
          next_operation: { id: "operations.cwsa.chapter2.explain", effect_class: "READ_ONLY", auto_dispatched: false },
          prior_to_current: null, order_route: "NONE", trading_authorized: id === "C",
          financially_active: false, raw_private_account: "RAW_PRIVATE_0xEXPOSED",
        });
        await page.route("**/api/owner-view?*", async route => {
          const url = new URL(route.request().url());
          const id = url.searchParams.get("portfolio");
          ownerRequests.push({ id, method: route.request().method() });
          if (id === "Combo2") return route.fulfill({ status: 200, contentType: "application/json", body: '{"status":"UNKNOWN"}' });
          return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(ownerFixture(id)) });
        });
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
        const owner = page.locator('[aria-label="Chapter 2 owner evidence"]');
        await owner.getByText("1794500000123").waitFor();
        let rendered = await owner.innerText();
        for (const marker of ["SOURCE_CHECKPOINT_STALE", "MIXED", "BLOCKED_EVIDENCE", "UNKNOWN", "1794500000000", "1794500000130", "READ_ONLY"]) {
          assert.ok(rendered.includes(marker), `owner display omitted ${marker}`);
        }
        assert.equal(rendered.includes("RAW_PRIVATE_0xEXPOSED"), false);
        const economics = await owner.locator(".owner-finance .owner-cell").allTextContents();
        assert.equal(economics.length, 4);
        assert.ok(economics.every(text => text.includes("UNKNOWN")), "missing economics must not become zero");
        await page.getByLabel("Chapter 2 portfolio").selectOption("B");
        await owner.getByText("SOURCE_SCOPE_READY").waitFor();
        rendered = await owner.innerText();
        assert.ok(rendered.includes("UNKNOWN"), "source readiness must not clear Guardian risk");
        await page.getByLabel("Chapter 2 portfolio").selectOption("C");
        await owner.getByText("UNKNOWN — owner evidence unavailable.").waitFor();
        await page.getByLabel("Chapter 2 portfolio").selectOption("Combo2");
        await owner.getByText("UNKNOWN — owner evidence unavailable.").waitFor();
        assert.ok(ownerRequests.length >= 4);
        assert.ok(ownerRequests.every(entry => entry.method === "GET"), "a view interaction dispatched mutation");
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
