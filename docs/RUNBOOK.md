# Research operator runbook — verified CLI sequence

**Scope:** the installed `copytrade-pm/main` commands checked against source/`--help` on 2026-10-31. Operations are offline by default; explicitly flagged acquisition commands can call paid/rate-limited vendors. **No live trading authority.** Begin with [INDEX](INDEX.md); for wallet fill acquisition and exact market sources read [DATA-ACQUISITION](DATA-ACQUISITION.md).

## 0. Preflight, source of truth, safe worktree

Do not change a dirty branch or another session's feature worktree. The primary checkout at `/home/quant/dev/copytrade-pm` may lag behind `origin/main`, and draft PR #7 has separate changes. Choose a clean isolated worktree based on fetched `origin/main` before editing docs/code.

```bash
git status --short --branch
git worktree list
git fetch origin main
git log -1 --oneline origin/main
gh pr list -R hzminhzz/copytrade-pm --state open
gh issue list -R hzminhzz/copytrade-pm --state open

uv sync --frozen --group dev --extra market
uv run --frozen --group dev --extra market python -m pytest -q tests
uv run --frozen --group dev ruff check src tests
uv run --frozen --group dev ruff format --check src tests
uv build
```

On the frozen `c3e9ccf` baseline: **219 tests passed**, Ruff checks and wheel/sdist passed. Rerun and report the actual current result; do not repeat that number as a new test without executing it.

Set these pre-existing **owner-private** paths as a convenience (replace if the actual environment differs):

```bash
ROOT=/home/quant/.local/share/copytrade/reports/five-pod-20261029-research
MARKET=/home/quant/dev/quant/ml4t-data/.data/store
OUT=/home/quant/.local/share/copytrade/reports/pm01-36-shadow
test -d "$ROOT" && test -d "$MARKET" && test -d "$OUT"
```

Never print the contents of `PRIVATE_*`, vendor raw pages, env files or account tokens in a log/PR. Do not use `find ... | tail -1` to guess the “latest” evidence: all source outputs are content addressed, and several incompatible schemas have the same filename prefix.

## 1. Read-only PM-01 source and native market audit

```bash
# Local cache diagnostics (offline).
uv run --frozen --group dev --extra market python -m copytrade_pm.pm_fill_diagnostics \
  --research-root "$ROOT" --summary

# Independent 36-wallet pages + selected market-defect audit (offline).
uv run --frozen --group dev --extra market python -m copytrade_pm.pm_source_audit \
  --research-root "$ROOT" --market-root "$MARKET" --out "$OUT"

# Whole cohort native 1m instrument-day inventory, source SHA and gaps (offline).
uv run --frozen --group dev --extra market copytrade-pm-market-audit \
  --research-root "$ROOT" --market-root "$MARKET" --out "$OUT"
```

Every CLI prints an output `evidence_path`/`evidence_file` and SHA. Record those values with the **schema and code commit**. `SOURCE_DAY_SHA_VERIFIED` proves integrity of the native day bytes, not executable minute capacity, actual bid/ask, a valid Propr order ID or a whole source account.

To restrict further native-day acquisition to relevant Propr **display** markets, run `copytrade-pm-scope` with **the exact market-audit output** from the previous command:

```bash
# This file was independently confirmed on the VPS at the dated baseline.
# For a new audit, replace it with that command's exact evidence_path.
AUDIT="$OUT/pm01-36-wallets-fcb98de61ca43cdeeed0.json"
test -f "$AUDIT" || exit 1
uv run --frozen --group dev --extra market copytrade-pm-scope \
  --research-root "$ROOT" --market-audit "$AUDIT" --out "$OUT"
```

Those Propr terms and market display snapshots are **dated research metadata**; market-day coverage is not order permission. See [source acquisition](DATA-ACQUISITION.md) before any optional CryptoHFTData request.

## 2. Frozen PM-01 36 × 5/15/60-minute replay

```bash
# Offline historical-oracle scenario with a 1% gross-notional cap.
uv run --frozen --group dev --extra market copytrade-pm-replay \
  --research-root "$ROOT" --market-root "$MARKET" \
  --out "$OUT" --risk-budget 0.01

# Separate 10%-gross-notional stress/coverage comparison. BLOCKED is valid.
uv run --frozen --group dev --extra market copytrade-pm-replay \
  --research-root "$ROOT" --market-root "$MARKET" \
  --out "$OUT" --risk-budget 0.10

# Historical source-position tape; no real first-known clocks or actionable targets.
uv run --frozen --group dev --extra market python -m copytrade_pm.pm_fill_tape \
  --research-root "$ROOT" --out "$OUT"
```

**What to capture:** each report's raw SHA-256/path, code HEAD, frozen cutoff, source manifest SHAs, `risk_budget_fraction_of_initial_capital`, 36 aliases, 108 latency rows, native market day SHAs, blocked-reason counts and matched-control incremental economics. `pnl=None` in a blocked scenario means **UNKNOWN**, not $0. A completed synthetic 5-minute row is not a real follower trade.

If using authenticated page supplements, **first audit a new independent generation** with `pm_hyperx_overlay_audit`, then pass the same `--hyperx-generations` paths to both replay and tape. Never splice records into original caches. See [DATA-ACQUISITION §5](DATA-ACQUISITION.md).

## 3. PM-02 ranking: frozen historical vs independently audited forward

The CLI reads an **exact** `pm01_fill_only_replay_v2` SHA-addressed JSON file (not source-audit or PM-01 market coverage JSON):

```bash
# This previously verified private fixture was present at inspection time.
REPLAY=/home/quant/.local/share/copytrade/reports/pm01-36-shadow/pm01-36-wallets-33f95784345e79ca5b1f.json
PM02_OUT=/home/quant/.local/share/copytrade/reports/pm02-extraction-target-parity
test -f "$REPLAY" && test -d "$PM02_OUT"

# Read-only consumer, writes an immutable research-only decision artifact.
uv run --frozen --group dev --extra market copytrade-pm-rank \
  --pm01 "$REPLAY" --asof 2026-10-31T00:00:00+00:00 --out "$PM02_OUT"
```

With this specific frozen PM-01 input and as-of, previous parity verification yielded PM-02 digest `7bf28ee5ad53cdac9212bb0222ae1b3e0ef020eee5faae9972c53028e4b60f4f` (36 historical-only cards; 0 qualified; five EMPTY; 0 actionable R). **Recompute from the actual source and compare before claiming parity.** The `--asof` must not precede the PM-01 frozen `study_cutoff`. For a later decision, `--previous` accepts a signed/canonical `pm02-<fullsha>.json`, monotonic as-of, unchanged frozen source and the same 36-wallet cohort.

When genuine independently signed outcomes exist, add **all three** opt-in flags:

```bash
# Only after a real owner-private ledger and independent auditor public key exist:
# uv run --frozen --group dev copytrade-pm-rank \
#   --pm01 "$REPLAY" --asof 2026-11-01T00:00:00+00:00 \
#   --out "$PM02_OUT" --prospective-ledger "$LEDGER" \
#   --research-root "$ROOT" --auditor-public-key "$AUDITOR_PUBLIC_KEY"
```

See [ledger contract](PM-01-prospective-ledger.md). A new WS receipt **without an audited and mature economic outcome** must still produce no verified prospective episode. No synthetic user-generated signature is proof of real-world follower returns.

## 4. PM-01/PM-02 to PM-03 evidence handoff (offline)

`copytrade-pm-handoff` is a strict historical contract verifier. It requires all three **matching** sealed artifacts: PM-01 v2 replay, PM-01 observed-book tape, and PM-02 governance output. They must share source manifests, cutoff, cohort and PM-01 digest. **Do not pick “latest” tape and replay independently**, or mix overlay/non-overlay generations.

```bash
# First set REPLAY, TAPE and PM02 to exact content-addressed,
# matching, validated paths from the same frozen source campaign.
# uv run --frozen --group dev copytrade-pm-handoff \
#   --pm01 "$REPLAY" --tape "$TAPE" --pm02 "$PM02" \
#   --out "$OUT"
```

A valid historical handoff returns `RESEARCH_ENGINEERING_CONTRACT_VALID_PROSPECTIVE_BLOCKED` and `account_backtest_ready=false` **by design**. It does not approve PMs, reconstruct external Propr positions or open a live account.

`pm03_bridge.inspect_pm02` separately enforces decision SHA and as-of, while `require_external_targets` refuses to translate PM-02 budget **R** directly into source quantities. A realistic multi-wallet prop pass-probability estimator requires independently known positions, broker costs/capacity, account and Propr constraints and credible prospective history; this is **not** provided by the existing synthetic CLI.

## 5. PM-03 — safe demonstration of the account supervisor

```bash
uv run --frozen --group dev copytrade-pm-shadow \
  --input examples/pm03_synthetic.json \
  --output-dir /tmp/copytrade-pm03-shadow-demo
```

The checked-in fixture is fabricated, and the CLI works entirely offline. `pm03_cli_input_v1` supports `compare` (only `RESEARCH_SYNTHETIC`) or `replay` with versioned input events and SHA manifest. Inspect report fields, financial residuals, contractual floor breaches, GREEN/YELLOW/ORANGE/RED/HALT, partial/unfilled orders, unchanged input SHA and three policies. Do not label a synthetic pass a challenge pass probability. The Propr public rule factory is **`confirmed=False`**, intentionally blocking real-input fills. Detailed formulas: [PM-03 model](PM-03-shadow-account.md).

## 5a. PM-04 synthetic three-pod research only

[PM-04 contract](PM-04-shadow-hardening.md) extends the existing `copytrade-pm-shadow` CLI with action `compare_pm04` and the `pm04_compare_input_v1` JSON schema. Verified offline example: `uv run --group dev copytrade-pm-shadow --input examples/pm04_synthetic_comparison.json --output-dir /tmp/copytrade-pm04-shadow-demo-issue12`. The fixture is invented, not actual wallet signals. The reproducible schema builder is in `tests/test_pm04_compare.py`; use only named synthetic fixtures. It runs identical signed-target research input under `IMMEDIATE`, `BATCHED`, `ASYMMETRIC` execution policies using the sole PM-03 replay engine. `PM04_BROKER` receipts are read-only; they cannot become real fills by setting a flag. All real provider observations and signed snapshots remain **unverified**, so `broker_required=True` blocks new-risk simulation without independently supplied reconciled evidence. Never supply broker credentials. Incomplete immutable output should be preserved; replay into a new private output directory instead of overwriting it.

## 6. Complete entry-point map

| Invocation | Safe network class | Purpose |
| --- | --- | --- |
| `copytrade-pm-replay` | Offline | Frozen 36-wallet historical fill replay; native market marks |
| `copytrade-pm-market-audit` | Offline | 1m native instrument-day SHA coverage |
| `copytrade-pm-scope` | Offline | Frozen public Propr **display** market scope vs audit |
| `copytrade-pm-rank` | Offline | PM-02 36-card manager research, optional sealed forward evidence |
| `copytrade-pm-handoff` | Offline | Strict three-artifact dependency verdict |
| `copytrade-pm-receipts` | Offline | Immutable receipt ingestion and external signed audits |
| `copytrade-pm-shadow` | Offline | PM-03 synthetic account replay/comparison |
| `copytrade-pm-research` | Offline, requires separate Rust ledger | Legacy independent observation-path study |
| `python -m copytrade_pm.pm_source_audit` | Offline | Raw vendor cache SHA/source consistency |
| `python -m copytrade_pm.pm_fill_diagnostics` | Offline | Existing fill-cache status diagnostics |
| `python -m copytrade_pm.pm_fill_tape` | Offline | Observed historical signed-book tape |
| `python -m copytrade_pm.pm_hyperx_overlay_audit` | Offline | Additional page generation reconciliation |
| `python -m copytrade_pm.pm_hyperx_gap_recovery` | **Network when invoked** | Bounded authenticated vendor gap resnapshot |
| `python -m copytrade_pm.pm_hyperx_rest_forward` | **Network when invoked** | Bounded recent REST first-local receipt capture |
| `python -m copytrade_pm.pm_hyperx_forward` | **Network when invoked** | Bounded WS first-local receipt capture |
| `python -m copytrade_pm.pm_hyperx_account_triage` | **Network when invoked** | Vendor funding/margin/account state triangulation |
| `python -m copytrade_pm.pm_chd_target_1m` / `pm_chd_hip3_1m` | **Network + external market writes** | Strict gated native minute-day acquisition in ml4t-data |

Source-entry names for the first eight are pinned in `pyproject.toml`. The final modules are valid Python `-m` entrypoints, **not** separate project scripts. Network tools require pre-existing external client/API dependencies and separate authorization; do not assert they are fully provisioned by the core `uv.lock`.

## 7. Failure/runbook matrix

| Symptom | Meaning | Next *safe* move |
| --- | --- | --- |
| `UNSUPPORTED_PM01_REPLAY`, `UNPINNED_PM01_ARTIFACT_SHA` | Wrong schema or file SHA/filename | Inspect `schema`, byte SHA, exact output path; never rename unverified data |
| `INCOMPLETE_PM01_SCENARIOS` | Not all 36 × 5/15/60 rows | Reconstruct from exact source campaign; don't zero-fill |
| `BLOCKED_SOURCE_*`, `POSITION_DISCONTINUITY` | Missing anchor, post-anchor gap or corrupted fill chain | Inspect source audit, quarantine affected whole book, consider bounded new generation |
| `BLOCKED_MARKET_OR_EXECUTION`, `BLOCKED_TERMINAL_MARK` | Missing exact native minute/volume/mark | Audit exact market day, venue/namespace; do not assume executable fill |
| `HYPERX_ADAPTER_SHA_DRIFT` or pagination conflict | Private provider script/source changed | Stop and independently re-audit/version source, never patch around the checksum |
| HTTP 500, quota, WS tier rejection | Vendor endpoint/capacity failure | Record error category and stale horizon; no blind retries, use bounded new generation later |
| `IMMUTABLE_COHORT_MANIFEST_CONFLICT`, `PROSPECTIVE_SHA_CHAIN_BROKEN` | Alias mapping/auditor trust/root or journal tampered | Halt; read-only forensic backup and compare SHA; never rewrite chain |
| `NO_VERIFIED_PROSPECTIVE_EPISODES` / EMPTY seats | Authentic lack of independent follower outcomes | Correct **NO TRADE** / research-only response; don't relax thresholds |
| `PM02_PM01_SOURCE_ARTIFACT_CONFLICT` | Mismatched handoff campaign or source hash | Rebuild matching tape/ranking from frozen source |
| `HALT` in PM-03 | Simulated supervisor latches uncertainty/breach | Inspect immutable journal and cause; manual-only reset when permitted, no implicit flatten |
| GitHub checks red | Lint/test/build regression | Fix on branch, rerun both core + market matrix; no bypass on protected main |

## 8. Required engineering closeout

Before merging any non-trivial code or data-contract change: preserve dirty work, read `AGENTS.md`, inspect GitHub and real VPS sources, write behavior tests at the consumer seam, run **both** CI-equivalent dependency variants, Ruff and build, inspect diff and evidence SHA, update handbook links if CLI or source boundaries changed, push and wait for actual required checks. Do **not** confuse successful engineering with scientific qualification or deployment. Protected `main` requires `verify (core)` and `verify (market)`, strict current-base checks; no force push. Never touch production `hyperliquid-expert-ensemble` as a side effect of this repository.
