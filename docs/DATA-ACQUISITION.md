# Wallet data acquisition and provenance

## Public market-wide trade capture (experimental, 2026-11-05)

[Native public trade first-known receipt and UTC net-delta contract](FORWARD-PAPER-PUBLIC-TRADES-20261105.md) implements an opt-in bounded `trades` WS filter for sealed, SQLite-resolved public wallets, with buyer/seller signatures, per-session baseline exclusion, stream-gap evidence and provisional immutable journals. It supports explicit multi-pair capture via a versioned market allowlist: ≤128 native perp/HIP-3 instruments, ≤8 per WS shard and ≤5 concurrent shards, with per-market observed frames and no silent market omissions. See [the non-authoritative 13-market example](FORWARD-PAPER-MARKET-EXAMPLE-20261105.json), and the [exact user-selected 40-market five-shard configuration and test evidence](FORWARD-PAPER-TOP40-FIVE-SHARD-20261105.md). It is not an authenticated whole-wallet account ledger; a disconnected stream is not a complete timeline, and reported quantities are not PM-03 follower orders. Owner-private address lists are read from SQLite, not from Markdown. Requires independent `userFills`, TWAP, position/NAV and L2-capacity reconciliation before any financial paper admission.

**Use this for “get wallet fills,” “new wallet,” “fix gaps,” “get 1m OHLCV,” or “start forward capture.”** Read [INDEX](INDEX.md) and [ARCHITECTURE](ARCHITECTURE.md) first. No commands in this guide authorize orders. Offline auditing is distinct from vendor/SDK downloads. Live source snapshot inspected 2026-10-31; private paths can change.

## Official Hyperliquid public API as the forward source (2026-11-05)

**ADOPTED for prospective account observations, NOT independently reconciled
whole-wallet NAV.** The existing `pm_forward_source_stream` uses
`wss://api.hyperliquid.xyz/ws` (`allDexsClearinghouseState`) for each observed
parent/subaccount to acquire the full *per-account* perpetual position set and
DEX margin diagnostics, retaining source event clocks and separately measured
first-local-known receipt clocks in the private SHA-chained `PaperJournal`.
The official `/info` API provides `perpDexs` (DEX census), `subAccounts`
(account discovery), `spotClearinghouseState` (collateral evidence) and
`userAbstraction` (account collateral/margin mode). The legacy, wider
`userVaultEquities` diagnostic remains available only when explicitly requested;
the approved forward portfolio's **perpetuals-only** account-family observer
**does not query vault equities**. Public observations do not
require a private key or a HyperX vendor subscription.

The `userAbstraction` response is a scalar JSON string, one of `disabled`,
`default`, `dexAbstraction`, `unifiedAccount`, `portfolioMargin`. The collector
validates the exact response, SHA and local receipt clock, stores it in the
existing collateral diagnostic chain, and leaves `source_equity=null` and
`order_route=NONE`. An unknown/unavailable mode is blocked, never assumed to
mean standard. `unifiedAccount` and `portfolioMargin` cannot use independent
perp-DEX account values as an additive whole-wallet denominator; `default` and
`dexAbstraction` also require separate accounting interpretation. The
read-only readiness join explicitly reports these mode blockers and missing
or unmatched discovered subaccount position receipts. No account mode, amount,
market price or vendor record is promoted to a financial execution gate.

### Approved perpetuals-only capture (2026-11-05)

Follower scope = `PERPETUALS_ONLY`. Source positions cover *all* open native
perpetual DEX markets, including HIP-3 and hedges, for each known parent and
linked subaccount. No spot position, spot trade, vault deposit or staking event
is a copy instruction. The public spot-state request is retained **only** to
read quote collateral for unified-margin perpetuals: the diagnostic retains
USDC/USDH `total` and `hold` values with their original response SHA and
first-local timestamp, and counts other spot assets without turning them into
follower signals or making assumptions about their collateral value.

The existing SQLite collateral journal retains its legacy two-slot layout for
readers: the excluded vault slot is explicitly marked
`OUT_OF_SCOPE_PERPETUALS_ONLY` with null timestamps/amounts, **not** a failed
API acquisition or a fabricated zero balance. New diagnostics carry
`copy_scope=PERPETUALS_ONLY` and
`status=BLOCKED_PERPETUAL_COLLATERAL_RECONCILIATION`. Legacy SHA-chained
receipts are accepted unchanged and retain their earlier scope. The readiness
audit does not require vault freshness in perp-only mode, but still requires
timely public spot collateral/mode evidence and a whole-wallet reconciled
sizing denominator. Unified/portfolio-margin accounts cannot use their
individual perp-DEX `accountValue` as equity. Do not replace missing source
NAV with native quote balances, a fixed source leverage, or retrospective
HyperX funding/PnL. Asynchronous account books are not atomic.

The additional `userAbstraction` `/info` call is subject to documented provider
weight (general `info` weight 20); keep account-family captures bounded and
monitor provider errors/rate limits before expanding beyond the existing
observer. One WebSocket frame per subject is **not** an atomic parent/child
and spot/vault snapshot. Per-account DEX values cannot be summed into whole
wallet equity without mode-specific settlement and collateral reconciliation.
The observer and current frozen P1/P14 deployment remain distinct from the
current research selection E6/E2; no protected paper-worker activation or
wallet roster change is implied.

Official references: [Info endpoint](https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api/info-endpoint), [perpetual account state](https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api/info-endpoint/perpetuals), [WebSocket subscriptions](https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api/websocket/subscriptions), [account modes](https://hyperliquid.gitbook.io/hyperliquid-docs/trading/account-abstraction-modes), and [provider rate limits](https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api/rate-limits-and-user-limits).

## Current inventory index (2026-11-04, partial release)

The owner-private SQLite [wallet registry checkpoint](WALLET-REGISTRY-STATUS-20261104.md) indexes the 158-wallet research cohort and deployed tracker configuration as **metadata only**. The `copytrade-wallet-registry doctor` command checks live source fingerprints, including the frozen 36-wallet evidence references and tracker ledger identity. It does **not** download fills, reconstruct whole-book equity, enroll trackers, change existing source files, or certify follower trading. Keep original HyperX/Parquet/ledger sources authoritative. Its deployment/acceptance remains incomplete under issues #44–#55.

## Recovery operations added 2026-11-01

[The dated disposition](RECOVERY-DISPOSITION-2026-11-01.md) pins the new evidence
hashes and acquisition counts. The bounded CHD adapter uses SDK 0.8.0's documented
read-only key transport and identifies both metadata and download sessions. Its
five-day request cap, audited target allowlist, native namespace checks and refusal
to overwrite existing partitions remain in force. No authentication material is
serialized. A partial day is retained and labeled partial, never filled with
invented returns or promoted to execution/capacity proof.

The A/B/C observer now records raw public account scope, first application receipt,
source clocks and discovery hashes in bounded windows. Follow [source operation and
audit instructions](RECOVERY-INTEGRATION.md). Ten users per provider/IP window does
not cover all 24 discovered accounts continuously. Current snapshots, source perp NAV,
and spot/vault/subaccount discovery do not reconstruct an unknown historical
starting equity or independently certify total wallet capital.

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

For a failed acquisition or incomplete source, follow [blocker recovery](BLOCKER-RECOVERY.md): diagnose, attempt only bounded authorized new generations, independently re-audit, and resume the unaffected research work. Preserve the blocked historical window when causal evidence cannot be recovered.

## Never perform these shortcuts

- Do **not** broaden acquisition to every exotic/outside-Propr pair simply to raise an arbitrary coverage percentage; preserve hedge relevance and whole-source economics first.
- Do **not** invent fill records, account balances, collateral, carry-in/out inventory, missing market bars, negative funding, or fallback zero returns.
- Do **not** copy/rewrite frozen raw pages or private alias maps into Git or another research campaign.
- Do **not** replace `locally_received_at` with historical vendor timestamp or let `verified_first_known` be set by an unaudited producer.
- Do **not** promote a downloaded day, completed page, or synthetic follower replay to a real profit-challenge pass probability.

**Next:** [RUNBOOK](RUNBOOK.md) for the exact read-only replay and PM-02/03 handoffs; [QUALIFICATION](QUALIFICATION.md) for approval gates.

## Offline source/PIT manifest boundary (2026-11-04)

No vendor acquisition was performed for Polars milestone #2 draft PR #92.
The new `pm_offline_manifest` accepts SHA-sealed source-book and equity
files, native Hyperliquid day Parquet, frozen cost/risk/contract files and an
explicit clock basis. It hashes in bounded chunks rather than reading an
entire large market day into memory. Same-millisecond position continuity,
every declared hedge leg, positive fresh source equity and exact
DEX-qualified native market identities are mandatory.

A historical HyperX event's exchange timestamp is
`HISTORICAL_ORACLE` **only**. It is not a follower decision-time receipt.
`PROSPECTIVE_FIRST_KNOWN` cannot be derived from vendor history and
requires separate immutable independently verified local receipts. Synthetic
`atomic_source_verified` and `source_verified` fixture flags are
**not independent source attestations**; the real importer and its
per-snapshot lineage are still outstanding. The currently available fixture
runner refuses all non-fixture studies, nonflat initial source books and
cross-DEX accounts without a consolidated complete-book anchor.

Native 1m open is a retrospective execution-price diagnostic; *same-bar*
realized volume is not PIT-known. Only completed preceding volume may be
used for conservative capacity estimates and even that is **not L2**,
adverse-selection or achievable fill proof. Do not import Binance/Bybit
prices as Hyperliquid native or create missing market days by interpolation.

## 90-day real offline Polars source inventory, read-only (2026-11-04)

Read [the verified historical-oracle audit](OFFLINE-PIT-REAL-ORACLE-20261104.md)
before inferring source capacity or real financial results. The owner has
94 archived original research JSON files across 19 primary, 55 broader
and 20 Nansen accounts, with 500,168 total raw fills. The stricter
2026-08-05 to 2026-11-03 UTC end-exclusive window contains 450,172
supported unique perp fills. Older rows are excluded and spot-style `@...`
coin codes are **not** substituted for perps.

Canonical native 1m Parquet is in the adjacent `ml4t-data` lake, with a
per-day SHA-256 `source.json` sidecar. 6,985 of 19,440 source-observed
instrument-days are verified complete, 90 partial, 12,365 missing; only
44/216 markets have all 90 days. Read the original files in place and
publish only sanitized SHA-bound research artifacts to a private cache.
A derived owner-private SHA-sealed numeric week may be built from seven
complete native day partitions via `pm_offline_hot_market`; this is
read-only, and missing/partial source days are BLOCKED rather than
backfilled. The hot panel stores Int64 UTC timestamps and Float64
screening OHLCV; it cannot attest executable liquidity.
A current wallet `equity` number in a source JSON is not historical
time-varying NAV or independently known-at receipt. Do not backfill,
timestamp or fabricate those missing source facts.
