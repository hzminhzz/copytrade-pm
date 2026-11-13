/* Unmocked end-to-end browser parity audit for Chapter 2 /api/owner-view vs CLI site-view. */
const { chromium } = require("/home/quant/.hermes/node/lib/node_modules/playwright");
const { execFileSync, spawn } = require("node:child_process");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const assert = require("node:assert/strict");

const project = path.resolve(__dirname, "../../..");
const venvPython = path.join(project, ".venv", "bin", "python");
const pythonBin = process.env.PYTHON || (fs.existsSync(venvPython) ? venvPython : "python3");
const serverScript = path.join(project, "scripts", "dashboard_server.py");
const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));
const RAW_ADDRESS_RE = /0x[0-9a-fA-F]{40}\b/;

function normalizeOwnerView(view) {
  const copy = JSON.parse(JSON.stringify(view));
  for (const field of ["observed_at", "assessment_asof"]) {
    assert.equal(typeof copy[field], "string", `missing timestamp field ${field}`);
    copy[field] = "<UTC_TIMESTAMP>";
  }
  return copy;
}

function seedFixture(workDir) {
  const script = `
import json, subprocess, sys
from pathlib import Path
from hashlib import sha256
from copytrade_pm import wallet_registry_catalog as reg_cat
import tests.test_anos_15_eight_scenarios as t

reg_cat.WHALE_ADDRESS_SHA256 = sha256(t.WHALE_SYNTH.encode()).hexdigest()
root = Path(sys.argv[1])
db, _ = t._build_locked_registry(root / "reg")
alt_policy = t._policy_for("mixed-epoch")
b_ms = t._fresh_boundary_ms()
older_cp_ms = b_ms - t.GRID_MS
env = t._seed_chapter2_source_and_paper(
    root / "ch2",
    registry_db=db,
    boundary_ms=b_ms,
    gap_wallets={"W031"},
    epoch_override_wallets={"CA-005": alt_policy},
    checkpoint_ms_by_wallet={"CO-001": older_cp_ms},
    acq_offset_ms_by_wallet={"W028": 77, "W030": 101},
)
cli_views = {}
for portfolio in ("A", "B", "C"):
    out = subprocess.check_output(
        [
            sys.executable, "-m", "copytrade_pm.pm_operations",
            "cwsa", "chapter2", "site-view",
            "--portfolio", portfolio, "--inspection", "evidence",
            "--registry-db", str(env["registry_db"]),
            "--source-db", str(env["source_db"]),
            "--paper-root", str(env["paper_root"]),
            "--quote-db", str(env["quote_db"]),
            "--epoch", env["epoch"],
        ],
        text=True,
    )
    cli_views[portfolio] = json.loads(out)
meta_out = subprocess.check_output(
    [
        sys.executable, "-m", "copytrade_pm.pm_operations",
        "cwsa", "chapter2", "site-view",
        "--portfolio", "A", "--inspection", "metadata",
        "--registry-db", str(env["registry_db"]),
        "--source-db", str(env["source_db"]),
        "--paper-root", str(env["paper_root"]),
        "--quote-db", str(env["quote_db"]),
        "--epoch", env["epoch"],
    ],
    text=True,
)
print(json.dumps({
    "registry_db": str(env["registry_db"]),
    "source_db": str(env["source_db"]),
    "paper_root": str(env["paper_root"]),
    "quote_db": str(env["quote_db"]),
    "projection_db": str(root / "absent_proj.sqlite"),
    "ops_db": str(root / "absent_ops.sqlite"),
    "epoch": env["epoch"],
    "boundary_ms": b_ms,
    "older_cp_ms": older_cp_ms,
    "cli_views": cli_views,
    "cli_meta_a": json.loads(meta_out),
}))
`;
  const raw = execFileSync(pythonBin, ["-B", "-c", script, workDir], {
    cwd: project,
    env: { ...process.env, PYTHONDONTWRITEBYTECODE: "1" },
    encoding: "utf8",
  });
  return JSON.parse(raw);
}

async function startServer(port, extraEnv) {
  const proc = spawn(pythonBin, ["-B", serverScript, "--port", String(port)], {
    cwd: project,
    env: { ...process.env, PYTHONDONTWRITEBYTECODE: "1", ...extraEnv },
    stdio: ["ignore", "pipe", "pipe"],
  });
  let stderr = "";
  proc.stderr.on("data", data => { stderr += data.toString(); });
  const base = `http://127.0.0.1:${port}`;
  for (let i = 0; i < 60; i++) {
    if (proc.exitCode !== null) {
      throw new Error(`dashboard_server exited early (${proc.exitCode}): ${stderr}`);
    }
    try {
      if ((await fetch(`${base}/api/health`)).ok) {
        return { proc, base, getStderr: () => stderr };
      }
    } catch {
      /* waiting for startup */
    }
    await sleep(100);
  }
  proc.kill("SIGTERM");
  throw new Error(`dashboard_server did not become healthy: ${stderr}`);
}

async function stopServer(handle) {
  if (!handle || handle.proc.exitCode !== null) return;
  handle.proc.kill("SIGTERM");
  await Promise.race([
    new Promise(resolve => handle.proc.once("exit", resolve)),
    sleep(2000),
  ]);
}

async function main() {
  const workDir = fs.mkdtempSync(path.join(os.tmpdir(), "anos15-ops-parity-"));
  const basePort = Number(process.env.PARITY_PORT || "18991");
  let liveServer = null;
  let unconfiguredServer = null;
  let browser = null;

  try {
    const fixture = seedFixture(workDir);
    const serverEnv = {
      COPYTRADE_OPS_OWNER_PYTHON: pythonBin,
      COPYTRADE_OPS_REGISTRY_DB: fixture.registry_db,
      COPYTRADE_OPS_CWSA_SOURCE_DB: fixture.source_db,
      COPYTRADE_OPS_CWSA_PAPER_ROOT: fixture.paper_root,
      COPYTRADE_OPS_CWSA_QUOTE_DB: fixture.quote_db,
      COPYTRADE_OPS_CWSA_EPOCH: fixture.epoch,
      COPYTRADE_OPS_PROJECTION_DB: fixture.projection_db,
      COPYTRADE_OPS_RECORDS_DB: fixture.ops_db,
      COPYTRADE_OPS_RELEASE_SHA: "anos15-parity-rev",
    };
    liveServer = await startServer(basePort, serverEnv);

    // Direct HTTP <-> CLI exact parity checks without any mocks.
    assert.equal(fixture.cli_views.A.dimensions.source_observation.state, "OBSERVE_READY");
    assert.equal(fixture.cli_views.A.scope.new_risk_source_status, "SOURCE_SCOPE_READY");
    assert.equal(fixture.cli_views.A.dimensions.paper_finance.state, "BLOCKED_EVIDENCE");
    assert.ok(fixture.cli_views.B.fault_isolation.unaffected_source_portfolios.includes("A"));
    for (const portfolio of ["A", "B", "C"]) {
      const resp = await fetch(`${liveServer.base}/api/owner-view?portfolio=${portfolio}&inspection=evidence`);
      assert.equal(resp.status, 200);
      const body = await resp.json();
      assert.deepEqual(normalizeOwnerView(body), normalizeOwnerView(fixture.cli_views[portfolio]));
      assert.equal(RAW_ADDRESS_RE.test(JSON.stringify(body)), false);
    }
    const metaResp = await fetch(`${liveServer.base}/api/owner-view?portfolio=A&inspection=metadata`);
    assert.equal(metaResp.status, 200);
    assert.deepEqual(normalizeOwnerView(await metaResp.json()), normalizeOwnerView(fixture.cli_meta_a));

    const badPortfolio = await fetch(`${liveServer.base}/api/owner-view?portfolio=Z&inspection=evidence`);
    assert.equal(badPortfolio.status, 400);
    const badMethod = await fetch(`${liveServer.base}/api/owner-view?portfolio=A&inspection=evidence`, {
      method: "POST",
      body: "{}",
    });
    assert.equal(badMethod.status, 403);

    browser = await chromium.launch({
      executablePath: "/home/quant/.cache/ms-playwright/chromium-1254/chrome-linux64/chrome",
      headless: true,
      args: ["--no-sandbox", "--disable-setuid-sandbox"],
    });

    for (const [width, height] of [[1440, 900], [390, 844]]) {
      const context = await browser.newContext({ viewport: { width, height }, colorScheme: "dark" });
      const page = await context.newPage();
      const errors = [];
      const allRequests = [];
      const ownerResponses = [];
      page.on("pageerror", err => errors.push("pageerror: " + err.message));
      page.on("console", msg => {
        if (msg.type() === "error") errors.push("console: " + msg.text());
      });
      page.on("request", req => {
        allRequests.push({ method: req.method(), url: req.url() });
      });
      page.on("response", async res => {
        const u = new URL(res.url());
        if (u.pathname === "/api/owner-view") {
          ownerResponses.push({
            portfolio: u.searchParams.get("portfolio"),
            inspection: u.searchParams.get("inspection"),
            status: res.status(),
            body: await res.json(),
          });
        }
      });

      const load = await page.goto(liveServer.base, { waitUntil: "networkidle" });
      assert.equal(load.status(), 200);

      const gatesNav = page.getByRole("button", { name: "Gates & blockers", exact: true });
      if (width < 768) {
        await page.locator(".mobile-menu").click();
      }
      await gatesNav.click();
      const owner = page.locator('[aria-label="Chapter 2 owner evidence"]');
      await owner.getByText(String(fixture.boundary_ms + 77)).waitFor();

      let textA = await owner.innerText();
      for (const marker of [
        String(fixture.boundary_ms + 77),
        String(fixture.boundary_ms + 78),
        "OBSERVE_READY",
        "SOURCE_SCOPE_READY",
        "BLOCKED_EVIDENCE",
        "UNKNOWN",
        "READ_ONLY",
        "evidence",
      ]) {
        assert.ok(textA.includes(marker), `Portfolio A DOM missing ${marker}`);
      }
      assert.equal(RAW_ADDRESS_RE.test(textA), false);

      // Verify null economics fail closed to UNKNOWN (never zero) in the rendered UI.
      const econCells = await owner.locator(".owner-finance .owner-cell").allTextContents();
      assert.equal(econCells.length, 4);
      assert.ok(econCells.every(c => c.includes("UNKNOWN") && !c.includes("$0")));

      // Switch to wallet-local blocked + mixed-epoch Portfolio B without mocks.
      await page.getByLabel("Chapter 2 portfolio").selectOption("B");
      await owner.getByText("SOURCE_POLICY_EPOCHS_MIXED").waitFor();
      const textB = await owner.innerText();
      assert.ok(textB.includes("MIXED"));
      assert.ok(textB.includes("BLOCKED_EVIDENCE"));
      assert.equal(RAW_ADDRESS_RE.test(textB), false);

      // Switch to Portfolio C and verify older original checkpoint clock is preserved verbatim.
      await page.getByLabel("Chapter 2 portfolio").selectOption("C");
      await owner.getByText(String(fixture.older_cp_ms)).waitFor();

      await page.getByRole("button", { name: "Refresh owner evidence" }).click();
      await owner.getByText(String(fixture.older_cp_ms)).waitFor();

      // Verify every single request triggered by the live browser session was GET-only.
      assert.ok(
        allRequests.every(r => r.method === "GET"),
        `Non-GET HTTP request detected: ${JSON.stringify(allRequests.filter(r => r.method !== "GET"))}`
      );
      assert.ok(ownerResponses.length >= 3);
      for (const item of ownerResponses) {
        assert.equal(item.status, 200);
        assert.deepEqual(
          normalizeOwnerView(item.body),
          normalizeOwnerView(fixture.cli_views[item.portfolio])
        );
      }

      const bodyText = await page.locator("body").innerText();
      assert.equal(RAW_ADDRESS_RE.test(bodyText), false);
      assert.equal(bodyText.includes("NaN"), false);
      assert.equal(bodyText.includes("[object Object]"), false);
      assert.equal(
        await page.evaluate(() => document.documentElement.scrollWidth > innerWidth + 2),
        false,
        `horizontal overflow at ${width}x${height}`
      );
      assert.deepEqual(errors, [], `browser errors at ${width}x${height}`);
      console.log(`PASS unmocked owner parity ${width}x${height}`);
      await context.close();
    }

    // Fail-closed server check: without COPYTRADE_OPS_OWNER_PYTHON UI reports UNKNOWN, never PASS.
    unconfiguredServer = await startServer(basePort + 1, {
      ...serverEnv,
      COPYTRADE_OPS_OWNER_PYTHON: "",
    });
    const ctxFail = await browser.newContext({ viewport: { width: 1440, height: 900 }, colorScheme: "dark" });
    const pageFail = await ctxFail.newPage();
    await pageFail.goto(unconfiguredServer.base, { waitUntil: "networkidle" });
    await pageFail.getByRole("button", { name: "Gates & blockers", exact: true }).click();
    const ownerFail = pageFail.locator('[aria-label="Chapter 2 owner evidence"]');
    await ownerFail.getByText("UNKNOWN — owner evidence unavailable.").waitFor();
    await ctxFail.close();
    console.log("PASS unconfigured owner python fails closed cleanly");

    // Negative permission-tamper UI falsifier: trading_authorized=true never renders ready.
    const ctxTamper = await browser.newContext({ viewport: { width: 1440, height: 900 }, colorScheme: "dark" });
    const pageTamper = await ctxTamper.newPage();
    await pageTamper.route("**/api/owner-view?*", async route => {
      const forged = { ...fixture.cli_views.A, trading_authorized: true };
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(forged),
      });
    });
    await pageTamper.goto(liveServer.base, { waitUntil: "networkidle" });
    await pageTamper.getByRole("button", { name: "Gates & blockers", exact: true }).click();
    const ownerTamper = pageTamper.locator('[aria-label="Chapter 2 owner evidence"]');
    await ownerTamper.getByText("UNKNOWN — owner evidence unavailable.").waitFor();
    await ctxTamper.close();
    console.log("PASS tampered trading_authorized=true UI fails closed cleanly");
  } finally {
    if (browser) await browser.close();
    await stopServer(liveServer);
    await stopServer(unconfiguredServer);
    fs.rmSync(workDir, { recursive: true, force: true });
  }
}

main().catch(err => {
  console.error("FAIL", err.stack || err);
  process.exitCode = 1;
});
