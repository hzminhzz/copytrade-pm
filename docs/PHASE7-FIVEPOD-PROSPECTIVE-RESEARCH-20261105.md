# Phase 7 — approved five-pod prospective research observation (2026-11-05)

**Scope:** Owner approved prioritizing the broader five-wallet design for **prospective research only**, with the M3-preserving five-wallet design as challenger and original M3 as baseline. This is a **new, versioned Phase 7 research decision**, not a modification of the sealed E6/E2/P1/P14 portfolio definitions or their current registry research priority. No real broker execution, protected financial account, historical fill extension, risk policy update, or live trading is approved.

## Source of truth

- Versioned reviewable declaration: [2026-11-05 Phase 7 research v1 JSON](decisions/2026-11-05-phase7-fivepod-prospective-v1.json).
- Retrospective decision source: [PR #98, commit `3fd1009`](https://github.com/hzminhzz/copytrade-pm/pull/98), immutable private 90d model `phase7_best5_major4_screen_20261105_v5.json`, SHA256 `86bb03ff35d4a639c429d8a4b916496f4d210f4c0485918f7691e84d74af8614`. Its original private Phase 7 universe `phase7_universe_20261104_v2.json` SHA256 `2cef0d3a2c28de70a1991043a58de45fc226d6a8ec56b22960c5133909da45ff`. These are **retrospective, in-sample** results (the later 30d window has also been used in previous research). No new independent holdout has been established.
- Registry authority: live owner-private SQLite source generation `e2836aab5ef6ef79306e9dfe732d8768c3b1ca6af29efbda066b37f03646a18f`, observed `2026-11-04T09:36:57.574969+00:00`, 158 research wallets. Recheck `doctor`, `status`, `portfolio --current` before interpreting this note; the source generation may change. Exact canonical wallet identity is verified at runtime by *full address SHA-256 against the private Phase 7 universe and SQLite registry*, never by display-name or prefix guesses. No private 0x address is committed.

## Approved research portfolios

| Qualified research ID | Role | Members | Relationship |
| --- | --- | --- | --- |
| `phase7.fivepod/BROAD` v1 | First-priority future study | `HX04, N05, VS025, VS035, W083` | Highest modeled cost-buffer from bounded Phase 7 exploration; **selection is hindsight contaminated** |
| `phase7.fivepod/M3_PLUS_TWO` v1 | Five-pod challenger | `H02, VS002, VS035, VS057, W083` | Extends the original three wallets, keeping their common trio |
| `phase7.fivepod/M3_BASELINE` v1 | Fixed three-pod control | `H02, VS002, W083` | Original comparable baseline |

There are **eight unique source addresses**, not 13 separate public subscriptions. The research cash baseline is $10,000. The $5,000 total gross target is a **hypothetical four-coin research normalization at rebalance**, not a continuously enforced exposure cap, a source-equity-faithful copying factor, or a trading-risk allocation. `$450` daily and `$850` trailing are **illustrative reference loss levels** only. Models at 10/20/30bps do not establish actual execution costs, wallet NAV, funded-account pass probability, or trading authority.

## Native interface and first-known public evidence

The entry point `copytrade-pm-phase7-source-observe` extends the existing native source parser, bounded all-DEX account WebSocket/Info collector, and the existing **SHA-chained private `PaperJournal`**. Its **default command is entirely read-only**: it requires both pinned Phase 7 historical artifacts and validates every selected alias against the current private cohort and owner exclusions, while returning redacted full address hashes and explicit negative financial statuses.

### Read-only preflight (default)

```bash
uv run --frozen --group dev copytrade-pm-phase7-source-observe
```

Must return `RESEARCH_PRIORITY_PREPARED_OBSERVATION_NOT_YET_ATTESTED`, eight exact address bindings and `order_route=NONE`. If the registry source manifest SHA, source universe SHA, research evidence SHA, a wallet's canonical address identity, a cohort membership, or any owner exclusion mismatches, the command **fails closed before opening a provider connection or writing a journal**.

### One deliberately bounded first-known source canary (explicit approval scope)

The following command creates **only the separate private research observation journal** at the exact path below. It does not start a daemon, install a service, modify any existing P1/P14/prod journal, or acquire historical fills. The CLI requires `--capture-bounded` plus a separate path and is marked `PROTECTED_MUTATION` in capability discovery because the journal is an actual new evidence write.

```bash
uv run --frozen --group dev --extra source \
  copytrade-pm-phase7-source-observe --capture-bounded \
  --state-root /home/quant/.local/share/copytrade/prospective/phase7-fivepod-20261105 \
  --seconds-per-account 2 --max-frames 2
```

This performs **at most one bounded parent-account session per selected unique identity**, plus public `spotClearinghouseState` and `userVaultEquities` diagnostics; it is not a continuous forward observer. It explicitly does **not** subscribe to or attest separately discovered subaccounts, so parent+child, HIP-3 and cross-margin completeness remains **BLOCKED**. New position and collateral receipts are SHA-chained independently in the existing SQLite tape. A count of new source receipts is accepted only if the verified journal cursor advanced by exactly that many receipts, and only when the reported source alias/address hash matches the manifest. Rejected/invalid frame, provider outage or a mismatch produces a per-wallet `BLOCKED` status, not fabricated zeros or a profitability label.

During the bounded scan, each observed public book records its **first local receipt time**, distinct from the source economic event time. This does *not* recover unknown 2026-August through November historical receipt clocks and does not prove a follower could have executed at a recorded bar OPEN.

## How the forward evidence can become meaningful

The first objective is to obtain durable **independent, timestamped source-account state** for all eight wallets and quote evidence on the entire reported open-instrument set. This bounded canary is only a safe *first observation*, not the start of the 30-day financial paper period.

To permit meaningful new follower/control economics later, the producer must independently reconcile every parent/subaccount margin mode, opening positions, spot and vault claims, signed source equity/collateral and native marks, funding, all hedges, and complete traded volume. It must then capture actual first-known order intent and L2 orderbook/venue execution outcomes with a no-order shadow follower, record fee/spread/slippage and latency, and prove source-equity-faithful sizing and separate portfolio stop/kill behavior. Protected financial workers, dedicated OS protection, admission decisions and explicit owner trading authorization remain separate future boundaries.

The current installed `copytrade-public-observer-p1p14.service` is an existing **P1/P14** public-only service, **not** a new M5 worker. This experiment never reuses or restarts its state/service, never marks `PAPER_RUNNING`, does not write `research_selections`, and does not change the active research status returned by `portfolio --current`.

**Evidence truth:** `SCIENTIFICALLY_QUALIFIED=false`, `TRADING_AUTHORIZED=false`, `PAPER_RUNNING=false`, `FINANCIAL_EVENTS_COMMITTED=0` until independently verified evidence establishes otherwise.

## Verification and clean reversibility

Tests: `tests/test_pm_phase7_prospective.py` with synthetic registry fixtures, SHA-tamper, excluded-wallet, alias collision, false permission, financial-journal contamination, false public receipt counts and incomplete collateral.

Code: `src/copytrade_pm/pm_phase7_prospective.py`, discoverable through `copytrade-pm capabilities show paper.phase7_observe`. Running only the default preflight is safe and idempotent. To cease capture, **do not invoke further bounded commands**; no persistent process is created. Preserve immutable private receipt tapes for evaluation, not deletion. The private journal root must be independently backed up under the existing data retention policy before any migration. Any live canary counts reported below are a separately dated observation; do not infer continuity from a successful single scan.

## Actual bounded first-local canary — 2026-11-05 03:50:25 UTC

**OBSERVED and independently journal-audited:** A single bounded public Hyperliquid run with 2-second / 2-frame per-parent limits captured **8/8 distinct first-local parent all-DEX scope receipts**, exactly **one receipt per alias**, and **8/8 SHA-chained spot/vault collateral diagnostic groups**, exactly one group per alias. Source aliases: `H02`, `HX04`, `N05`, `VS002`, `VS025`, `VS035`, `VS057`, `W083`. The SHA-chain verification of the existing `PaperJournal` returned source cursors `1` and collateral-scope cursors `1` for every alias/account address hash. The independent read-only SQLite count of `runs`, `events` and `account_source_cursors` was **0/0/0**. Journal root: `/home/quant/.local/share/copytrade/prospective/phase7-fivepod-20261105/` (private; not committed). Do not treat the private database as a source-account NAV or monetary follower ledger.

All eight public source sessions returned `BOUNDED_SESSION_ENDED_NOT_CONTINUOUS`. The aggregate status is **`BLOCKED_PROSPECTIVE_PARTIAL_OBSERVER_ONLY`**, `whole_account_equity_attested=false`, `market_execution_economics_attested=false`, `paper_running=false`, `trading_authorized=false`, `order_route=NONE`. The new prospective state contains only *partial per-parent* observation, not complete parent/subaccount collateral/positions, not a continuous source tape, not executable prices, and not an independently validated matched-follower outcome. An **as-known first-local observation at this time is not retroactive evidence for historical August–November trades**.

**Independently inspected after the canary:** `copytrade-public-observer-p1p14.service` remained `active` with `MainPID=438441` and zero recorded restarts; the existing tracker, source-ABC and ensemble services remained active with their previous PIDs. The current registry still listed `gemini.phase4/E6` as its existing research priority. No source fills were extended, registry portfolio definitions changed, new worker started, or broker routes activated.
