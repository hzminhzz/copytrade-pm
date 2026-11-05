# Research operator runbook — verified CLI sequence

## 2026-11-05 opt-in public wallet trade canary and UTC scheduler

Follow [public market-wide trade acquisition, first-known receipt, UTC policy, and blocked paper execution](FORWARD-PAPER-PUBLIC-TRADES-20261105.md) for `copytrade-pm-public-trades --mode observe` and `--mode plan` examples. The new capability is `source.public_trades`; query `copytrade-pm capabilities show source.public_trades` and registry `doctor` first. To test other pairs use repeated `--instrument` or the example `--market-file docs/FORWARD-PAPER-MARKET-EXAMPLE-20261105.json` (13 native/HIP-3 markets), with bounded `--parallel-shards 2` and per-market receipt diagnostics. Up to 128 explicit symbols are partitioned into shards of eight; all-market coverage remains UNKNOWN until independently reconciled. The CLI writes **only a new owner-private research journal**, not the installed observer, production tracker, or PM-03 financial events. Run the documented tests and preserve the existing protected P1/P14 NO_TRADE state.

## Authoritative SQLite metadata inventory (2026-11-05)

Use `copytrade-wallet-registry doctor` for `authority=SQLITE`,
`database_integrity=VERIFIED` and `inventory_sha256`. Query any registered
cohort, including SQLite-only `ml4t-top6`, with
`copytrade-wallet-registry cohort ml4t-top6`. The older files can be audited
using `copytrade-wallet-registry doctor --legacy-audit` but are not roster
or deployment authority. The six-wallet cohort's old provenance label remains
unverified. See [release/rollback contract](WALLET-REGISTRY-RELEASE-RUNBOOK.md).



## Portfolio x prop contract EV comparison (research only)

Use the existing native capability `research.contract_selector`, exposed as
`copytrade-pm contracts rules` and `copytrade-pm contracts compare`. This
read-only tool consults the actual sealed portfolio registry and requires a
complete joint **net follower MTM** per-pod PnL tape. E6/E2 without such
independent evidence correctly return `BLOCKED` rather than speculative EV.
See [the full tool input, CLI, stage-risk and limitation contract](CONTRACT-PORTFOLIO-EV-TOOL-20261105.md).


## Public P1/P14 observer-only collection (not financial paper)

The 2026-11-05 [pinned public observer guide](FORWARD-PAPER-PUBLIC-OBSERVER-SERVICE-20261105.md)
records the bounded five-wallet first-local canary and the independent
`DEGRADED_OBSERVER_ONLY` heartbeat. Use the existing native
`copytrade-pm-paper-observe` for source/market receipts, or the separate
`copytrade-pm-public-observer-unit` for a conservatively verified user-unit
install. The latter's explicit `--apply` changes only an unprotected observer
unit file; it does not start a service. P1/P14 financial paper-worker cutover
remains `BLOCKED_NO_TRADE` and requires separate protected review.

## Agent-native discovery and operator read

For new engineering work run `copytrade-pm capabilities list`,
`copytrade-pm capabilities show portfolio.current`, and
`copytrade-pm capabilities validate` before adding a module. The
[agent-native guide](AGENT-NATIVE-OPERATIONS.md) documents scope,
examples, failure semantics and protected boundaries. The `copytrade-pm`
CLI provides read-only wallet, portfolio, paper and aggregate status adapters;
research enumeration remains explicitly unknown without an authoritative run
catalog. Original commands remain the owners.

The 5 November extension supports *scoped* research discovery using the actual
immutable job cache, plus private wallet inventory and independent release/
paper-unit inspection; use `copytrade-pm wallets list --cohort research-108`,
`copytrade-pm research list --cache-root PRIVATE_CACHE` and `copytrade-pm
health`. The research listing is NOT a global all-study catalog. See
[the acceptance record](AGENT-OPERATIONS-P1-ACCEPTANCE-20261105.md) and
[operator guide](AGENT-NATIVE-OPERATIONS.md).

For agent behavior measurement (not financial qualification), list the 13
fixed model tool-choice tasks with `copytrade-pm-agent-eval --list-tasks` and
inspect only independently captured host event traces. See
[the P2 evidence contract](AGENT-TRACE-EVAL-20261105.md); synthetic/self
transcribed traces cannot qualify as empirical agent performance.


## Offline Polars 2.x Milestone #2 public job (owner-approved engineering Option A, 2026-11-04)

[Two-track engineering vs science acceptance](OFFLINE-MILESTONE2-ENGINEERING-ACCEPTANCE-20261104.md)
is authoritative for the draft [PR #92](https://github.com/hzminhzz/copytrade-pm/pull/92).
The new **single manifest-to-results** CLI is:

```bash
uv run --extra market --group dev python -m copytrade_pm.pm_offline_job \
  docs/OFFLINE-HL94-ORACLE-JOB-20261104.json \
  --input-root docs \
  --source-root /home/quant/dev/copytrade-pm/data \
  --market-root /home/quant/dev/quant/ml4t-data/.data/store \
  --cache-root /home/quant/.cache/copytrade-polars-oracle-dev-20261104
```

The above concrete 90-day **real local source** invocation was run, not just documented:
450,172 supported historical fills, 377,130 five-delay batch observations,
322,970 SHA-native 1m prior-volume matches, and immutable report
`3141e4acb2df842025f880403d9dd4be2702c6811917bcb7949546dbdc6cbd1a`.
It intentionally returns `COMPLETE_HISTORICAL_ORACLE_SCREEN_ONLY`,
`financial_status=BLOCKED_MISSING_ATOMIC_BOOK_ASOF_NAV_AND_REAL_FIRST_KNOWN`,
`scientifically_qualified=false`. It **never** asserts actual historical
follower P&L or prospective first-known event clocks.

For account finance, use a **sealed synthetic fixture** as the nested manifest
with `kind=SEALED_SYNTHETIC_PM03` plus exact `study_manifest_sha256`,
`delays_minutes=[0,1,2,5,10]`, `clock_basis` and a stable `study_id`.
The nested study must pin book/equity/receipt (if prospective fixture),
rulebook/cost/risk and native-day `data.parquet` and `source.json` hashes. It also requires explicit `synthetic_funding_evidence_complete: true|false` to distinguish a frozen zero-funding fixture assumption from an unknown funding path. `false` forces UNKNOWN for target certification.
Valid independently specified *non-flat* opening books are accepted if fully
priced and source NAV is actually as-of; unpriced hedge legs are **BLOCKED**.
One manager without admission blocks only its scenario; independent scenarios
return their separate completed hashes. The CLI report's `financial_status`
remains `SYNTHETIC_PM03_FIXTURE_ONLY`; a fixture contract PASS/BREACH is not
real prop performance. Both routes use a single immutable, private cache.

Run the full suite before issue closure:

```bash
uv run --group dev python -m pytest -q tests
uv run --extra market --group dev python -m pytest -q tests
uv run --group dev ruff check src tests
uv run --group dev ruff format --check src tests
uv build --offline
```

Optional **read-only hot native 7-day numeric panel**, for research worker
memory mapping when full SHA-verified daily Parquet exists:

```bash
uv run --extra market --group dev python -m copytrade_pm.pm_offline_hot_market \
  --market-root /home/quant/dev/quant/ml4t-data/.data/store \
  --cache-root /home/quant/.cache/copytrade-polars-hot-week-20261104 \
  --instrument hyperliquid:mainnet:perp:default:BTC \
  --week-start 2026-10-19T00:00:00+00:00
```

A valid week has exactly **10,080 UTC minute bars**. It requires all
seven independently SHA-valid native days and returns a private, read-only
`numpy.memmap` with Float64 OHLCV and Int64 UTC-minute timestamps.
Missing/partial native day returns BLOCKED, not interpolated data;
the first weekly minute has no in-week prior capacity. This optional
screening-only view is **not** an execution order book, fixed-point P&L
or a replacement for the default full-study native context cache.

For repeatable **Issue #89 resource profiling** of the same sealed 90-day
research job with a new private application cache, run:

```bash
uv run --extra market --group dev python -m copytrade_pm.pm_offline_benchmark \
  docs/OFFLINE-HL94-ORACLE-JOB-20261104.json \
  --input-root docs \
  --source-root /home/quant/dev/copytrade-pm/data \
  --market-root /home/quant/dev/quant/ml4t-data/.data/store \
  --cache-root /home/quant/.cache/copytrade-polars-bench-20261104-verified-v1/cache \
  --workers 2 --repeats 10
```

Use a **new** owner-private cache root when measuring initial application
cache cost; never delete or flush the canonical market lake or live
services. The benchmark reports per-run CPU, OS process I/O, application
cache bytes, peak RSS and observed p50/p95, with unknown Polars spill and
cold OS page-cache state clearly distinguished. See the
[measured 90-day results](OFFLINE-PIT-REAL-ORACLE-20261104.md).
`BLOCKED_REAL_WORKLOAD` remains the full PM-03 follower economics state.

All original wallet files, market lake partitions, frozen PM-01 36 wallets and
Forward-Paper T+300s scheduler remain unmodified. No orders, merges,
protected service restarts or deployments are authorized.


**Scope:** the installed `copytrade-pm/main` commands checked against source/`--help` on 2026-10-31. Operations are offline by default; explicitly flagged acquisition commands can call paid/rate-limited vendors. **No live trading authority.** Begin with [INDEX](INDEX.md); for wallet fill acquisition and exact market sources read [DATA-ACQUISITION](DATA-ACQUISITION.md).

## Mandatory agent lookup contract (registry-first)

Before answering or changing any wallet/portfolio/evaluation status, **MUST** follow [the registry-first agent workflow](WALLET-REGISTRY-AGENT-WORKFLOW.md). Run `copytrade-wallet-registry doctor` and `status` first, bind the result to the current source generation SHA/as-of, then query `portfolio --current`, namespace-qualified `portfolio`, `wallet --alias`, `cohort`, `paper` and independently verified worker evidence as the question requires. Inspect `scripts/registry_release.py verify` separately from `git log` or a merged PR; a merged source hotfix does not automatically update the pinned registry-only consumer. On stale/missing source or post-seal identity, fail closed without inventing a running/qualified/authorized wallet. OptMem is a pointer to this rule, not the current dataset.

## Research portfolio selection and private registry (2026-11-04)

New **research selection** follows [Gemini Phase 6 Portfolio Freeze V2](decisions/2026-11-04-gemini-phase6-portfolio-freeze-v2.md) and [V2 JSON](decisions/2026-11-04-gemini-phase6-portfolio-freeze-v2.json): E6 primary five-pod, E2 three-pod challenger, P1 baseline and P14 archived from new selections. All share $600 *nominal* model risk budget and a $10,000 virtual comparison basis. Gemini fixed `k` values are **not** executable follower sizing. Original P1/P14 FP paper experiments, PM01 frozen cohort and production runtime remain untouched; new studies require prospective registration and independent safeguards.

For the private SQLite read-only metadata registry (not execution/equity/qualification authority), from repository root:

```bash
uv run --frozen --group dev copytrade-wallet-registry status
uv run --frozen --group dev copytrade-wallet-registry doctor
uv run --frozen --group dev copytrade-wallet-registry portfolio
uv run --frozen --group dev copytrade-wallet-registry portfolio --current
uv run --frozen --group dev copytrade-wallet-registry portfolio E6
uv run --frozen --group dev copytrade-wallet-registry wallet --alias W083
uv run --frozen --group dev copytrade-wallet-registry paper
uv run --frozen --group dev copytrade-wallet-registry sync --dry-run
uv run --frozen --group dev python scripts/registry_release.py verify
```

For the reviewed seal/rollback protections and the strictly manual future signed selection importer, see [registry hardening](WALLET-REGISTRY-REVIEW-HARDENING-20261104.md). No new signed selection is automatically admitted from a report; a real externally reviewed signature and key fingerprint are required.

The canonical [wallet status](WALLET-STATUS.md), [registry checkpoint](WALLET-REGISTRY-STATUS-20261104.md), [paper boundary](WALLET-REGISTRY-PAPER-CONTRACT-20261104.md), [negative-only evidence contract](WALLET-REGISTRY-SIGNED-NEGATIVE-EVIDENCE-20261104.md) and [release runbook](WALLET-REGISTRY-RELEASE-RUNBOOK.md) describe read-only source collection and reversible private sync. `paper` reads independently owned FP SQLite in `mode=ro` and rejects unsupported legacy JSONL; without genuine PID/transport/quote and journal evidence, RUNNING is UNKNOWN. No raw addresses, broker orders, trading authorization, automatic source subscription, independent science signoff or forced paper activation is implied.

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

For registered whole-account qualification, first freeze a future [PM02 campaign](PM-02-EVIDENCE-GATES.md) with `python -m copytrade_pm.pm02_campaign --pm01 "$REPLAY" --out "$CAMPAIGN_REGISTRY" --oos-start "$FUTURE_OOS_START" --windows 4`. Registration uses the actual clock and pins the selection code bytes. It does not approve the science or permit access to another study's protected holdout.

When genuine independently signed v2 outcomes exist, supply the three ledger trust flags **and** `--campaign`:

```bash
# Only after a real owner-private ledger and independent auditor public key exist:
# uv run --frozen --group dev copytrade-pm-rank \
#   --pm01 "$REPLAY" --asof 2026-11-01T00:00:00+00:00 \
#   --out "$PM02_OUT" --prospective-ledger "$LEDGER" \
#   --research-root "$ROOT" --auditor-public-key "$AUDITOR_PUBLIC_KEY" \
#   --campaign "$CAMPAIGN_FILE"
```

See [ledger contract](PM-01-prospective-ledger.md). A new WS receipt **without an audited and mature economic outcome** must still produce no verified prospective episode. No synthetic user-generated signature is proof of real-world follower returns.

### A/B/C source operations

The pinned read-only `copytrade-source-abc.service` observes bounded A/B/C account windows. Check `systemctl --user show copytrade-source-abc.service -p ActiveState -p UnitFileState -p MainPID -p NRestarts`, the journal, and `loginctl show-user quant -p Linger`. Audit each portfolio with `python -m copytrade_pm.pm_e4_source_readiness --store "$CAPTURE_ROOT/A" --portfolio A` (repeat B/C). Preserve incomplete generations and inter-session gaps. Follow [the release and rollback procedure](RECOVERY-INTEGRATION.md); do not point the service at a dirty worktree or revive the over-limit legacy observer.

## Exploratory Q3 three-wallet historical replay (offline)

See [the corrected equity-weight sizing standard](EQUITY-WEIGHT-SIZING.md), [the actual executed sparse-NAV Q3 study](Q3-SPARSE-EQUITY-PORTFOLIO-EXECUTION-20261102.md), then [the superseded gross-normalized study](HISTORICAL-THREE-WALLET-COMPARISON.md). The strict `python -m copytrade_pm.pm_historical_combos` requires genuinely reconciled historical wallet equity; without it every scenario has null PnL and `BLOCKED_HISTORICAL_SOURCE_EQUITY`. The separate `python -m copytrade_pm.pm_sparse_equity_portfolio` executes a **clearly labeled exploratory proxy** using the last prior positive official source NAV with an 8d/16d bound and 5m delayed complete source-book target updates. It does NOT attest complete source scope, real first receipt, true intragap DD, or executable Propr fills. The opt-in `--legacy-gross-proxy` on the strict CLI is archived reproducibility **only**. For all 84 combinations and selected capacity stress, consult the dated study and the SHA-addressed private output, not hypothetical mid PnL as a ranking.

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

[PM-04 contract](PM-04-shadow-hardening.md) and [18-case/fault acceptance matrix](PM-04-acceptance.md) extend the existing `copytrade-pm-shadow` CLI with action `compare_pm04` and the `pm04_compare_input_v1` JSON schema. Verified offline example: `uv run --group dev copytrade-pm-shadow --input examples/pm04_synthetic_comparison.json --output-dir /tmp/copytrade-pm04-shadow-demo-issue12`. The fixture is invented, not actual wallet signals. The reproducible schema builder is in `tests/test_pm04_compare.py`; use only named synthetic fixtures. It runs identical signed-target research input under `IMMEDIATE`, `BATCHED`, `ASYMMETRIC` execution policies using the sole PM-03 replay engine. `PM04_BROKER` receipts are read-only; they cannot become real fills by setting a flag. All real provider observations and signed snapshots remain **unverified**, so `broker_required=True` blocks new-risk simulation without independently supplied reconciled evidence. Never supply broker credentials. Incomplete immutable output should be preserved; replay into a new private output directory instead of overwriting it. For the independent PR #13 reviewer corrections, run `uv run --extra market --group dev python -m pytest -q tests/test_pm04_review_regressions.py`: `pending_reductions` records only *broker-net* exit-to-flat, while `pending_pod_reductions` records virtual pod exposure still requiring exit even when broker net is flat. `pending_reversals` holds any opposite-net new-risk residual until a separate authorization contract; never submit that residual as a reduction or clear it on a clock tick. For broker source-clock safety, run `uv run --extra market --group dev python -m pytest -q tests/test_pm04_broker_timestamps.py`. `PM04_BROKER` evidence must keep independent source `event_at` and receipt `first_known_at`: a late receipt of an old position/balance/fee snapshot cannot establish current broker readiness, discharge a canceled-order reservation, or resolve a reconnect gap. After the broker source-state age exceeds `broker_max_age_seconds`, mark NOT READY, restore conservative order reservations, and preserve account HALT until separately authorized reset.

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

When any operation fails or returns BLOCKED, execute [RECOVER](BLOCKER-RECOVERY.md) before ending the wider task. Keep the affected artifact fail-closed; investigate a bounded repair or compatible source, verify it, then resume the original objective. If the original historical window is unrecoverable, preserve that verdict while continuing independently valid work or prospective evidence collection. Repeated identical retries without new evidence are not progress.


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

Routine research/CLI operation has **no per-turn judge call**. For material frozen-roster, policy or qualification decisions, follow the [protected governance boundary](GOVERNANCE-GATES.md) and run `copytrade-pm-review-gate --help` to inspect the read-only signature-check interface. An unavailable independent reviewer blocks only that protected decision; no current CLI confers scientific qualification or trading permission.

Before merging any non-trivial code or data-contract change: preserve dirty work, read `AGENTS.md`, inspect GitHub and real VPS sources, write behavior tests at the consumer seam, run **both** CI-equivalent dependency variants, Ruff and build, inspect diff and evidence SHA, update handbook links if CLI or source boundaries changed, push and wait for actual required checks. Do **not** confuse successful engineering with scientific qualification or deployment. Protected `main` requires `verify (core)` and `verify (market)`, strict current-base checks; no force push. Never touch production `hyperliquid-expert-ensemble` as a side effect of this repository.

## Offline Polars v2 synthetic fixture runner (2026-11-04; draft PR #92)

From a **clean isolated** project worktree, run the unit/integration contracts:

```bash
uv run --group dev python -m pytest -q tests
uv run --extra market --group dev python -m pytest -q tests
uv run --group dev ruff check src tests
uv run --group dev ruff format --check src tests
uv run --extra market --group dev python -m copytrade_pm.pm_offline_baseline --fills 120 --iterations 2
```

Inspect an owner-provided **synthetic** manifest (it must be prepared with
all source/equity/rule/risk/cost/market file SHA values):

```bash
uv run --extra market --group dev python -m copytrade_pm.pm_offline_manifest   /tmp/private-fixture/manifest.json --input-root /tmp/private-fixture/inputs

uv run --extra market --group dev python -m copytrade_pm.pm_offline_sweep   /tmp/private-fixture/manifest.json   --input-root /tmp/private-fixture/inputs   --market-root /tmp/private-fixture/inputs   --cache-root /tmp/private-fixture/cache --workers 2
```

The CLI expects **explicit `synthetic_fixture: true`**. Files for real
HyperX, forward receipts, account data or a source-only historical oracle
study are deliberately blocked in this prototype. Source-book initial
positions must be flat for this fixture harness, not guessed flat. All
scenario managers must independently enter the known state before a follower
target is admitted. Account financial results are labeled `SYNTHETIC_PM03_*`;
no PASS, broker orders, subscription changes, service restarts, real
PIT certification or copytrading permission follows from passing tests.

Deterministic integration fixtures are implemented in
`tests/test_pm_offline_sweep_pipeline.py`. Do not add private wallet
addresses, account rules, paid vendor pages or a raw market lake to Git.
The cache is private 0700/0600 with 8 MiB maximum fixture artifact,
1 GiB minimum free scratch and up to 2 workers. A corrupted/partial cache
entry is not a cache hit; a completed scenario resumes by its pinned SHA.

## Real local Polars 2.x historical timing and native-market audit (2026-11-04)

The commands below are **offline, read-only against original sources**.
They compile a `HISTORICAL_ORACLE` diagnostic, **never real financial
or scientific qualification**. Adapt `RESEARCH_ROOT` and `NATIVE_LAKE`
to the installed source paths; do not move the dirty main checkout's data
into a Git worktree, and never write to the lake.

```bash
RESEARCH_ROOT=/home/quant/dev/copytrade-pm/data
NATIVE_LAKE=/home/quant/dev/quant/ml4t-data/.data/store
PRIVATE_CACHE=/home/quant/.cache/copytrade-polars-oracle-dev-20261104
START=2026-08-05T00:00:00+00:00
END=2026-11-03T00:00:00+00:00

uv run --extra market --group dev python -m copytrade_pm.pm_offline_repository \
  --source-root "$RESEARCH_ROOT" --market-root "$NATIVE_LAKE" \
  --start "$START" --end "$END" --verify-market-sha
uv run --extra market --group dev python -m copytrade_pm.pm_offline_oracle \
  --source-root "$RESEARCH_ROOT" --cache-root "$PRIVATE_CACHE" \
  --start "$START" --end "$END" --engine streaming
uv run --extra market --group dev python -m copytrade_pm.pm_offline_oracle_market \
  --source-root "$RESEARCH_ROOT" --market-root "$NATIVE_LAKE" \
  --cache-root "$PRIVATE_CACHE" --start "$START" --end "$END"
```

The five-delay tape is a sealed, source-SHA-addressed private Parquet. Native
market joins validate Parquet-day and metadata fingerprints even on warm
cache; a changed upstream day creates a new dependent cache identity. The
full study requires up to 4,088 instrument-day scans (maximum admitted 6,000)
and initially uses hundreds of MiB of process RAM; check disk/swap
headroom before scaling. Re-run with `--instrument
hyperliquid:mainnet:perp:default:BTC` to audit a bounded subset.
No fee, follower equity, drawdown, execution or contract PASS/BREACH is
reported by these historical-only diagnostics.

Detailed counts and reproducible output hashes:
[real-data audit](OFFLINE-PIT-REAL-ORACLE-20261104.md).
