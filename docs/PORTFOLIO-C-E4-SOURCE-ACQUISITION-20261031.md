# E4 source acquisition and reconciliation — October 31, 2026

**Scope:** Three previously approved Portfolio C wallets (`CO-001`, `W015`, `VS066`) and their independently discovered Hyperliquid subaccounts. Read-only acquisition; zero trading orders, zero promotion/qualification. This report describes newly collected evidence, **not Q3 first-known wallet-account snapshots**.

## Providers, transport, original evidence

1. **HyperX authenticated Data API** using the existing read-only key on the VPS. The pinned 36-wallet cohort resolved the three private addresses. The bounded `pm_hyperx_account_triage` collector requested `POST /wallet_analysis/`, `GET /market/trader-funding/`, and `GET /market/trader-margin-timeline/` per wallet. All **nine responses** saved as raw immutable owner-private files. The first two wallets' report write was blocked by output-parent permissions after their six raw responses had already been saved; permissions were corrected without overwriting those bytes, and the independent reconciliation subsequently revalidated all nine. Third-wallet triage report SHA: `84781f08049a3be26d07220745c9db761cad93a5bcb5439f98872c2d48c22101`. HyperX provides retrospective wallet metrics, historical leverage samples, 7-day margin points and a paged funding feed — **not** an independently attested complete all-DEX signed-position history.
2. **Official public Hyperliquid API** (no exchange auth, no trading keys): `POST /info` for `perpDexs`, `portfolio`, `spotClearinghouseState`, `subAccounts`, `userFunding`, `userNonFundingLedgerUpdates`; `wss://api.hyperliquid.xyz/ws` for `allDexsClearinghouseState`, fills, fundings, ledger updates, user events. Local receive times and original raw-frame SHA-256 hashes stored for every accepted frame. Dex catalog has **11** scopes, matched exactly by each per-wallet and per-subaccount official full-DEX response.
3. **First official prospective run:** `ge4live20261031first`, 45 raw WS frames, three parent-wallet 7-snapshot observations plus 15 official info responses; raw summary SHA `5ebde8780d327868ea372dae510f0db2f4854130e1ebde71f7d434b85b72dce2`. One `subAccounts` info response was `null`, subsequently handled correctly as zero registered subaccounts.
4. **Second official prospective run:** `ge4live20261031subaccounts`, **110 raw WS frames**, including **78 full-Dex state frames across 11 subjects**, 23 acknowledged subscriptions and nine initial fills/funding/ledger snapshot frames; zero capture errors. Raw report SHA `723b243ca59a9abe4c8f4d94dcda20f4041ac163a58c136e9247bf1156b93992`. Received October 31, 2026 at approximately **16:03 UTC**.
5. **Independent cross-provider SHA reconciliation:** `ge4reconcile20261031v2/reconciliation.json`, SHA `f01a24cade9b05d5cf01e4dabd236d68b416037fee6123450f3ede3fd34b106b`. Replays each original raw WS frame, checks the local receipt metadata and independently recomputes exact 11-Dex positions; HyperX identity and source shapes verified. Comparison to the official recent portfolio account-value series is an **asynchronous partial consistency check**, not a cash/collateral full ledger proof.
6. **Retrospective official 2026Q3 funding / nonfunding source pages:** `ge4q3ledgers20261031a/backfill-report.json`, SHA `f38058229e0b4819b6f86b7a13ae08b8fd4a6c2eafff292adf21f0e1ebd72341`. Ten bounded public calls; per-source time-range pagination reached the end without recorded timestamp-boundary ambiguity. Raw pages are immutable and separately stamped with **October 31 receipt time**, not Q3 local knowledge.

All private source payloads are in **`/home/quant/.local/share/copytrade/reports/pm-e4-hyperx-20261031/`**. They are not committed to GitHub. The `ops/systemd/copytrade-e4-source-capture.service` file and `pm_e4_stream` receiver are code deliverables, not an order gateway.

## Current master wallets and subaccounts

| Field | CO-001 | W015 | VS066 |
|---|---:|---:|---:|
| Current master nonzero perp positions | **7** | **7** | **14** |
| Subaccounts confirmed by official `subAccounts` | **7** | **0** | **1** |
| Additional nonzero subaccount perp positions | **48** | **0** | **1** |
| Perpetual DEXs checked per subject | 11 | 11 | 11 |
| Master perp account-value *sum* at receipt (USD) | 74,367.51 | 123,967.17 | 57,162.02 |
| Master gross perp notional proxy (USD) | 321,369.40 | 440,470.30 | 555,189.38 |
| Official asynchronous equity difference (USD) | 0.00 | -2.28 | +8.64 |
| Independently reconciled full-wallet capital denominator | **NO** | **NO** | **NO** |

**Important:** Master wallet and subaccounts are distinct exchange account namespaces. The additional subaccount exposures are real and source-observed but their inclusion in each *manager strategy* is **unknown**. Do not silently add their balances, flatten their exposure or exclude them without an explicit source-scope decision. Spot, vault and withdrawal flows are separate; parent-vs-subaccount transfers may double count if aggregated naively. The close asynchronous comparison demonstrates consistency **for recent master perps only** and cannot prove account equity, funding or collateral at every Q3 decision.

## Completed historical records retrieved

| Source wallet | Q3 official funding events | Q3 official nonfunding cashflow/transfer events | Pagination status |
|---|---:|---:|---|
| CO-001 | 1,051 | 33 | Complete for queried source date interval |
| W015 | 166 | 0 | Complete for queried source date interval |
| VS066 | 1,443 | 2 | Complete for queried source date interval |
| **Total** | **2,660** | **35** | No recorded ambiguous source cursor |

These are *main-account queried historical official API rows*, not all-subaccount funding/cashflow records and not independently matched to every HyperX fill/fee. The initial **latest-seven-day** official `userFunding` requests returned exactly 500 rows each and were correctly flagged **truncated**; the dedicated Q3 range query uses explicit start/end times and bounded inclusive-cursor pagination to avoid that trap. No retroactive point-in-time knowledge is claimed.

## First-known continuous collection and health

- `pm_e4_prospective`: bounded synchronous observation session with the official 11-DEX catalog, primary wallet and subaccount census, raw official frames + metadata, retrospective funding/margin/spot comparisons. It keeps all snapshots, preserving receipt timestamps.
- `pm_e4_stream`: read-only continuous WebSocket event observation, persistent local first-receive timestamps for fills, funding, ledger and user events. Every signed **position change** is recorded immediately; unchanged account states are sampled at **5-minute** checkpoints; reconnect/rotation produces an explicit gap rather than inferred events. Source rediscovery every 15-minute stream session enumerates current subaccounts and DEXs. Streams **3 masters and 8 subaccounts** as of the acquired snapshot. Session raw bytes capped at 100 MB; streamer refuses to start below 10 GiB free disk.
- Initial **14-second smoke** on the real official WebSocket recorded **76 frames received, 43 persisted**, 11 account checkpoints, nine event-channel frames, no recorded errors, and session SHA `290f3a61815ac8234a476702e2e0615e8a001d7838fe34c2a2e22f8dd506eb5a`. Counts do not show proven market fills during the window: initial snapshots cannot be reinterpreted as post-connection events.
- Service status and deployed version must be checked in the live VPS; this document's counts are *dated evidence*, not timeless health claims.

## Exact on-VPS commands

```bash
cd /home/quant/.devspace/worktrees/copytrade-pm-80b822d4
BASE=/home/quant/.local/share/copytrade/reports/pm-e4-hyperx-20261031
RESEARCH=/home/quant/.local/share/copytrade/reports/five-pod-20261029-research

# Read-only official all-DEX + subaccount prospective capture:
uv run --frozen --group dev --extra market --with websockets==15.0.1 \
  python -m copytrade_pm.pm_e4_prospective --research-root "$RESEARCH" \
  --generation "$BASE/gE4uniqueNewCapture" --duration 30

# Historical Q3 official funding/nonfunding (never first-known Q3):
uv run --frozen --group dev --extra market \
  python -m copytrade_pm.pm_e4_backfill --research-root "$RESEARCH" \
  --generation "$BASE/gE4uniqueNewLedgerBackfill" --pages-per-series 35

# Independently reconcile immutable HyperX data with official account receipts:
uv run --frozen --group dev --extra market \
  python -m copytrade_pm.pm_e4_reconcile --research-root "$RESEARCH" \
  --hyperx-root "$BASE" --official-generation "$BASE/ge4live20261031subaccounts" \
  --out "$BASE/gE4uniqueReconciliation"

# One-shot real WebSocket ingestion/health test, or --forever in the
# separate read-only user service. This never places orders.
uv run --frozen --group dev --extra market --with websockets==15.0.1 \
  python -m copytrade_pm.pm_e4_stream --research-root "$RESEARCH" \
  --store "$BASE/stream" --session-seconds 15 --sample-seconds 30
```

**Pinned release/runtime:** The enabled research-only service runs from a locked detached Git worktree at `/home/quant/.local/share/copytrade/releases/copytrade-e4-source` rather than the transient DevSpace checkout. Do not remove this locked worktree or alter the pinned commit without an explicit service stop, reproducible build/test, and restart/health verification. After deployment, check the actual `systemctl --user show ...` values; the live session is not proof of uninterrupted 24-hour receipt coverage.

**Service operational commands:** `systemctl --user status copytrade-e4-source-capture.service`, `journalctl --user -u copytrade-e4-source-capture.service --since '1 hour ago'`, and `systemctl --user stop copytrade-e4-source-capture.service` for immediate cessation. Never attach broker credentials. Audit reports before asserting healthy recurring capture; active systemd status alone does not prove source continuity.

## Research disposition

**VERIFIED**: HyperX nine raw account responses; official current master/subaccount position snapshots across all 11 DEXs; locally received timestamps and immutable raw SHA links; Q3 main-account funding/nonfunding historical date-interval pages; synthetic E4 mathematical adapter.

**UNKNOWN/BLOCKED**: Historical Q3 simultaneous complete source position+equity history; source subaccount **strategy membership**; all-subaccount historical funding/collateral and external transfers; independently matched source+follower execution and actual Propr broker symbol permissions; continuous 24/7 no-gap stream history; honest historical Q3 first-known times (cannot be recovered).

**E4 historical qualification** remains **BLOCKED_E4_SOURCE_EVIDENCE**. The new first-known source observation period can begin October 31; the 2026Q3 backtest remains censored. **No new portfolio-sizing win, deployable live strategy or capital authorization** is claimed.
