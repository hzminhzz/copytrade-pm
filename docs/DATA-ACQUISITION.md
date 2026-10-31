# Wallet data acquisition and provenance

**Use this for “get wallet fills,” “new wallet,” “fix gaps,” “get 1m OHLCV,” or “start forward capture.”** Read [INDEX](INDEX.md) and [ARCHITECTURE](ARCHITECTURE.md) first. No commands in this guide authorize orders. Offline auditing is distinct from vendor/SDK downloads. Live source snapshot inspected 2026-10-31; private paths can change.

## 1. The three different data problems

| Request | Actual source and writer | What it establishes | What it cannot establish |
| --- | --- | --- | --- |
| Historical wallet fills | Authenticated **HyperX Data API** source pages in a frozen private research cache; `pm_hyperx_gap_recovery` can create additional audited page generations | Historical vendor-listed fills, source event time, position-before/after chains, candidate symbols | Complete account census, funding/collateral, first-known follower time |
| Historical 1m trade/price bars | *ml4t-data* canonical native Hyperliquid lake; optional CryptoHFTData market-day acquisition modules | SHA-checked venue-specific OHLCV and minute bars | HyperX wallet fills, real quotes/depth, guaranteed Propr execution |
| Forward observed wallet actions | `pm_hyperx_forward` bounded WS or `pm_hyperx_rest_forward` bounded REST, then signed local ledger | Newly *locally observed* receipt with conservative knowledge clock | Real executable follower book or PnL without independent signed evidence |

HyperX is a **vendor**, not proof that every exchange position/collateral event has been captured. The Propr display universe is **not** a signed account-specific executable order-ID allowlist. Never substitute Binance prices for Hyperliquid markets or erase an off-universe hedge to make the source book look eligible.

## 2. Verified VPS layout (paths contain private data; do not commit)

| Owner | VPS path | Interpretation |
| --- | --- | --- |
| Frozen wallet research | `/home/quant/.local/share/copytrade/reports/five-pod-20261029-research` | 36-wallet sources, Wave A/B frozen manifests, private hashed/address alias maps, vendor page cache, Propr public snapshots |
| Native market data | `/home/quant/dev/quant/ml4t-data/.data/store` | *ml4t-data*-owned Hyperliquid minute parquet + metadata/SHAs |
| Historical PM-01 reports | `/home/quant/.local/share/copytrade/reports/pm01-36-shadow` | Multiple **separately labeled** content-addressed reports; do not pick by newest filename alone |
| Additional vendor generations | `/home/quant/.local/share/copytrade/reports/pm01-hyperx-gaps` | Repair pages with independent generation and source SHA |
| WS probe receipts | `/home/quant/.local/share/copytrade/reports/pm01-hyperx-prospective/receipts` | Local observation files; not yet economically verified |
| REST probe generations | `/home/quant/.local/share/copytrade/reports/pm01-hyperx-rest-forward` | Fresh, bounded vendor pages and `first_local_receipts` subdirectories |
| Private PM-02 parity | `/home/quant/.local/share/copytrade/reports/pm02-extraction-target-parity` | Dated frozen replay result, not current live manager ranking |

These directories were verified to exist on the VPS at the inspection snapshot. Private output directories must be **0700** and files **0600**. No raw address pages, provider credentials, vendor responses, private mapping or market Parquet in Git. Never print the HyperX key or dump private JSON to a PR.

The frozen identity loader is `pm_sources.load_cohort`: **6 original, 10 Wave 1, 20 Wave 2**, exact aliases and private source-SHA manifests. It checks vendor pagination and post-cutoff exclusions, including special W019/LIT generation; do not modify those manifests to accommodate an arbitrary new wallet.

## 3. Acquiring a *new* wallet vs repairing the frozen 36

**There is no new-wallet registration workflow in `copytrade-pm/main`.** Discovery and initial full-history pagination happened upstream in private HyperX wallet research, not through a generic package command. A helper exists at `$ROOT/slow_pod_hyperx_cache.py`, but it is **private and pinned by SHA** in `pm_hyperx_gap_recovery`; its cohort cutoff and cache locations are frozen. Use it for understanding historical lineage, **not for casually enrolling a 37th wallet or rewriting frozen data**.

Safe read-only inspection of its saved plan *for a known already-enrolled alias* (no API request, but reads private local roster):
```bash
ROOT=/home/quant/.local/share/copytrade/reports/five-pod-20261029-research
uv run --frozen --group dev --extra market python \
  "$ROOT/slow_pod_hyperx_cache.py" plan --wallets W019 --max-coins-per-wallet 1
```
That helper also has an `acquire` subcommand which **makes authenticated vendor requests and writes source cache**; it is intentionally not included as a canned operator command here. Do not run `acquire` against the frozen cache. A future intake of fresh wallets requires: new versioned cohort/campaign definition and alias/private identity map; independent authorized and bounded page acquisition to a **new** private generation; TID/delta/pagination/source-SHA audits; exact DEX/market namespace and market-data plan; updated consumer/fixture tests for cohort cardinality (rather than blindly relaxing 36), and an explicit owner-approved research scope. No backfilled vendor event time may become prospective first-known.

## 4. Read-only historical coverage audit — always before replay

From the checked-out `copytrade-pm` root:

```bash
uv sync --frozen --group dev --extra market
ROOT=/home/quant/.local/share/copytrade/reports/five-pod-20261029-research
MARKET=/home/quant/dev/quant/ml4t-data/.data/store
OUT=/home/quant/.local/share/copytrade/reports/pm01-36-shadow

uv run --frozen --group dev --extra market python -m copytrade_pm.pm_fill_diagnostics \
  --research-root "$ROOT" --summary
uv run --frozen --group dev --extra market python -m copytrade_pm.pm_source_audit \
  --research-root "$ROOT" --market-root "$MARKET" --out "$OUT"
uv run --frozen --group dev --extra market copytrade-pm-market-audit \
  --research-root "$ROOT" --market-root "$MARKET" --out "$OUT"
```

Capture each command's **actual** `evidence_file` or `evidence_path` and SHA; several independent PM-01 report types have the **same filename prefix** `pm01-36-wallets-<sha20>.json`. Inspect `schema` before passing the result to a consumer. Do not use an arbitrary wildcard or copy the sample October artifact filenames without checking their bytes.

## 5. Bounded source-fill gap repair — network, opt in

Only use when a specific **already-enrolled** wallet/coin has a demonstrated source position discontinuity, after an explicit API-budget check. This is **not** a retroactive first-known signal.

```bash
# Makes authenticated HyperX Data API requests. Pick a new unique private
# generation ID, not one already used in the evidence store.
uv run --frozen --group dev --extra market python -m copytrade_pm.pm_hyperx_gap_recovery \
  --research-root "$ROOT" \
  --out /home/quant/.local/share/copytrade/reports/pm01-hyperx-gaps/g_newaudit_20261031 \
  --aliases W035 --pairs W035/HBAR \
  --max-calls 3 --max-pages 3 --min-interval 12
```

This command is **illustrative and not executed by this documentation change**. It only accepts pairs with already observed fill-chain gaps. It uses the existing pinned private `slow_pod_hyperx_cache.py` Data API key loader; no broker API. Each fetched page is preserved separately with a gzip file, SHA sidecar and rate accounting. Default code limits: maximum **30 calls**, **4 pages per pair**, minimum **12s** between calls; use the lower proposed budget above. HTTP 500, quota exhaustion, partial pagination, same-TID payload conflict or a persistent unexplained position gap means **BLOCKED**, not interpolated fills.

Before using added rows, independently audit the *new* generation:

```bash
uv run --frozen --group dev --extra market python -m copytrade_pm.pm_hyperx_overlay_audit \
  --research-root "$ROOT" \
  --generations /home/quant/.local/share/copytrade/reports/pm01-hyperx-gaps/g_newaudit_20261031 \
  --out "$OUT"
```

Only pass `--hyperx-generations` to a **new** `pm_fill_replay`/tape run after the overlay audit accepts the source. The original generations remain immutable; conflicting or missing pages remain rejected. The [historical forensic log](PM-01-fill-only.md) records what earlier bounded recovery established and what it did not.

## 6. Native 1m acquisition — an ML4T-data operation, not a wallet-fill operation

Start with `pm_market_audit`, then gate the actual market-day queue by a **matching** public Propr display scope:

```bash
# Set to the actual newly emitted pm_market_audit SHA-verified JSON path.
# Verified example from the 2026-10-31 private audit. Replace with the new
# pm_market_audit evidence_path for any new campaign; do not infer via glob.
AUDIT="$OUT/pm01-36-wallets-fcb98de61ca43cdeeed0.json"
test -f "$AUDIT" || exit 1
uv run --frozen --group dev --extra market copytrade-pm-scope \
  --research-root "$ROOT" --market-audit "$AUDIT" --out "$OUT"
```

`--market-audit` must point to the **market audit schema**, not a fill replay or source-audit report with the same filename pattern. Run only when its frozen Propr public source snapshots are present. The 90% target in [dated Propr study](PM-01-propr-90pct-scope.md) is **strict native Propr market-day coverage**, not a 90% proportion of trades, minutes executable, wallet history, source account reconstruction or scientific qualification. Any HIP-3 namespace requires exact native source and actual Propr market-ID verification.

Optional, **network-affecting** one-day market fetch is implemented by `pm_chd_target_1m` (`--mode candles|trades`) and `pm_chd_hip3_1m`; it delegates canonical partition writing to *ml4t-data* and the external CryptoHFTData SDK, not to `copytrade-pm` storage. Do not run it unless a **matching source audit SHA + Propr scope**, vendor authorization, SDK dependencies and budget have been verified. Never rewrite an existing SHA-conflicting partition or downsample a different venue to disguise a missing native day. `pm_market_audit` must be rerun after each accepted batch before making a new request.

## 7. Forward receipts — network, not economic qualification

**WebSocket** probes live data when explicitly requested (max 60 seconds / 5 messages; provider tier restrictions may reject the subscription):

```bash
uv run --frozen --group dev python -m copytrade_pm.pm_hyperx_forward \
  --research-root "$ROOT" \
  --out /home/quant/.local/share/copytrade/reports/pm01-hyperx-prospective/receipts \
  --aliases W048 --duration 20 --max-messages 5
```

**REST** bounded recent-fill polling (max 5 wallet/coin pairs per call, minimum 12s between calls, `generation` must be unique):

```bash
uv run --frozen --group dev python -m copytrade_pm.pm_hyperx_rest_forward \
  --research-root "$ROOT" \
  --generation /home/quant/.local/share/copytrade/reports/pm01-hyperx-rest-forward/g_newpoll_20261031 \
  --out /home/quant/.local/share/copytrade/reports/pm01-hyperx-rest-forward \
  --pairs W048/AAVE --min-interval 12
```

Both examples **make provider calls** and are **not** executed as part of doc validation. The pinned provider dependency is external. In addition, `websockets` (WS) and `requests` (account triage) are **not declared** in the current default `pyproject.toml`: preflight the authorized source environment and dependency versions instead of claiming that `uv sync` alone fully provisions all acquisition clients. Read-only consumer CLIs need neither vendor key nor vendor network access.

The producer output uses `pm01_hyperx_first_local_receipt_v1`. A REST receipt is a **snapshot** and never eligible for signed prospective promotion. A WS receipt can be accepted for *review*, but there is no automatic follower economics or complete account-state inference. For ledger ingestion and independent signed outcomes, continue at [prospective ledger guide](PM-01-prospective-ledger.md). Its `copytrade-pm-receipts` subcommands and `copytrade-pm-rank --prospective-ledger` are **offline**.

## 8. Source/account triangulation

`pm_hyperx_account_triage` can query HyperX wallet-analysis, funding and margin timeline for up to **two** existing aliases in a fresh `g...` private generation. It may help explain missing positions/funding, but **no vendor summary is an independently reconciled historical account NAV**. A first-page `has_more` cannot be treated as complete funding. See [PM-01 direct forensic record](PM-01-2026-10-31-direct-execution.md) for the historical interpretation.

## Never perform these shortcuts

- Do **not** broaden acquisition to every exotic/outside-Propr pair simply to raise an arbitrary coverage percentage; preserve hedge relevance and whole-source economics first.
- Do **not** invent fill records, account balances, collateral, carry-in/out inventory, missing market bars, negative funding, or fallback zero returns.
- Do **not** copy/rewrite frozen raw pages or private alias maps into Git or another research campaign.
- Do **not** replace `locally_received_at` with historical vendor timestamp or let `verified_first_known` be set by an unaudited producer.
- Do **not** promote a downloaded day, completed page, or synthetic follower replay to a real profit-challenge pass probability.

**Next:** [RUNBOOK](RUNBOOK.md) for the exact read-only replay and PM-02/03 handoffs; [QUALIFICATION](QUALIFICATION.md) for approval gates.
