# Forward-paper real-input readiness and cost stress — 2026-11-04

**Policy update 2026-11-06 (supersedes NAV veto, not this historical audit):** [Approved fixed-k policy](RISK-BUDGETED-K-SIZING-20261106.md) makes missing **leader** whole-account NAV a diagnostic, not an admission blocker. The CLI now defaults to `FIXED_K_NATIVE_QUANTITY` (selected parent perps only); use `--sizing-policy ALLOCATION_OVER_LIVE_NAV` to reproduce this report's historical whole-wallet NAV/fidelity blockers. P1/P14 remain `BLOCKED_NO_TRADE` for unresolved pinned identities, stale/incomplete independent source/market observations, protected paper worker and risk/financial authorization. Historical table below remains a dated observation, not the current policy.

**Decision: BLOCKED_NO_TRADE for P1 and P14.** This report is based on bounded, true first-local public observations. It is *not* a paper trade, a backtest, a production service, or scientific qualification.

## Point-in-time audit correction (2026-11-06; code awaiting separate release)

The read-only readiness CLI accepts `--as-of`, but previously chose the
**newest** source-account receipt, collateral diagnostic and market quote
even when those records were known **after** the requested cutoff. The
financial gate still blocked every run, but historical reports could leak
future portfolio exposures and apparent quote/collateral availability.

The corrected audit validates each entire SHA chain first, then projects the
as-known prefix: sources require both `first_known_at` and local
`captured_at` by the requested cutoff, collateral diagnostic records require
all observed response clocks by that cutoff, and market quotes require
`first_known_at` by the cutoff. After a later/future collateral record,
no subsequent record is treated as a causally valid earlier prefix.
Independent observer-health callers omit the cutoff and continue validating
the full latest chain. Missing or future records remain `BLOCKED`, never
filled with a current-price/NAV proxy.

Synthetic fault tests cover a source receipt known before but captured
**after** a historical cutoff, a later position/hedge market that must not
appear in the required-market inventory, a later diagnostic collateral
scope, and a later native quote. This is a read-model integrity correction,
not retroactively obtained source NAV, signed operator approval or executable
market capacity. The deployed observer remains on its independently pinned
release; this change is not deployed by creating a pull request.

## Source admission mode boundary (2026-11-06 engineering correction)

The whole-book validator `admit_source_book` now rejects **all real-source
inputs by default**, including a self-declared `synthetic_fixture=true`
inside a valid-looking source JSON. A source's own flags, SHA digest, position
marks or reported NAV do not authenticate the provider or prove atomic
parent/subaccount collateral.

Only explicitly labeled PM-03/PM-04 **synthetic fixture** call sites opt in
using `allow_synthetic_fixture=True`. They must still pass every whole-book,
causal-clock, risk and source-hash check; such a simulation remains
`FORWARD_PAPER_SIMULATED_v1`, `order_route=NONE`, and cannot be counted as
independent prospective execution or alpha. Live source observation and
read-only readiness do **not** opt in. No real-source attestation mechanism is
implemented by this change; `INDEPENDENT_REAL_BOOK_ATTESTATION_UNAVAILABLE`
remains the correct live reason.

### Official Hyperliquid collateral-accounting constraint

[Hyperliquid's account-abstraction documentation](https://hyperliquid.gitbook.io/hyperliquid-docs/trading/account-abstraction-modes)
states that unified-account and portfolio-margin balances and holds reside in
the spot clearinghouse state; individual perp-DEX user state balances are **not
meaningful standalone NAV**. Shared USDC/USDH or portfolio collateral must not
be counted once per DEX. The [official portfolio-margin documentation](https://hyperliquid.gitbook.io/hyperliquid-docs/trading/portfolio-margin)
also describes offsets between eligible spot and perpetual holdings, so simply
adding quoted balances and perp margin values cannot recover account equity.

**Observed private read-only P14 diagnostic (2026-11-06 check):** four of five
wallets returned `unifiedAccount`, one returned `disabled` from the official
`userAbstraction` endpoint. The remaining `disabled` mode does **not**
establish full cross-DEX/parent/subaccount collateral/position coverage.
Even a complete per-DEX public snapshot or a sequential REST poll cannot
independently attest an atomic source-equity denominator. Continue to report
`BLOCKED_NO_TRADE` until actual source NAV/positions and execution capacity
can be reconciled with provider-level provenance.

## Evidence and actual admission gaps

The read-only `copytrade-pm-paper-readiness` command joins three separate authorities without modifying any of them: (1) sealed WR-06 portfolio identity + owner-private historical address locator (identity only), (2) official all-DEX per-parent Hyperliquid source receipts and (3) CCXT Pro first-local L2 quote receipts.

| Portfolio | Frozen version | Wallet identities resolved in membership | Source accounts with live per-parent observations | Independently complete wallet NAV | Required **native** markets from signed observed inventory | Markets with bounded L2 receipt | Status |
| --- | --- | --- | --- | --- | ---: | ---: | --- |
| P1 | 2 | **0/3** | 3/3 (3 receipts each) | **0/3** | 9 | 8 | BLOCKED_NO_TRADE |
| P14 | 2 | **0/5** | 5/5 (S064: 3, Whale: 2) | **0/5** | 23 | 22 | BLOCKED_NO_TRADE |

All five native account addresses are found in the registry's wallet table, but frozen portfolio membership `wallet_id` is NULL, therefore paper source activation cannot be inferred from matching files. Independent parent/subaccount/spot/vault NAV, collateral denominator, source position marks, complete trade volume, quoted market session and protected worker identity remain unavailable. The observed portfolio inventory includes hedges/cross-pairs: selecting only ENA/BTC/HYPE or the headline coin would silently omit exposures.

The read-only source-tape adapter now keeps the latest authenticated receipt **per account identity** within a wallet alias, using the frozen registry identity to select the parent account for its own freshness and admission checks. A newer subaccount receipt cannot replace its parent or trigger a false parent identity mismatch. Independently observed subaccount exposures are unioned into the required native market inventory, while an explicit `NON_ATOMIC_SUBACCOUNT_OBSERVATIONS` blocker prevents treating asynchronous parent/child receipts as a combined wallet NAV. A regression verifies parent remains selected with a later child receipt containing an additional HIP-3 hedge.

The read-only readiness adapter now verifies optional SHA-chained `source_scope_receipts` by registry-matched account address hash. It reports per-wallet diagnostic cursor, chain head, separate first-known spot/vault clocks and freshness. Missing, stale or tampered receipts fail closed. Valid diagnostic coverage **never** changes `BLOCKED_NO_TRADE` into source admission or infers a combined NAV. The latest private bounded P1/P14 source capture recorded collateral diagnostic chain cursors 2/2/2 for shared S035/S051/S053 and 1/1 for S064/Whale. At the subsequent read-only audit all five remained blocked; the current partial observed instrument set was 8 for P1 and 22 for P14. The earlier table's 9/23 figures refer to the separately dated earlier observation, not a permanent membership scope.

Public L2 expansion scanned current native inventory in bounded shards of 5–6 per client, using official Hyperliquid symbols from live captured source positions. The only market not accepted as an L2 quote was `hyperliquid/mainnet:perp:para/ANSEM`: the observed book spread exceeded the safety threshold (`CCXT_BOOK_SPREAD_TOO_WIDE`). The code **did not relax that threshold**. A new one-shot read-only `para/ANSEM` quote on **2026-11-04 08:05:41 UTC** was accepted at a **78.59885 bps** spread under the unchanged **100 bps** maximum, and SHA-chained to a separate private canary journal. This is a different first-known market state from the earlier rejected wide quote. The new quote still has `supported=false`, `session_trust=UNKNOWN_HIP3_SESSION` and `volume_base=null`. A successful short quote **does not** prove continuously acceptable spread or executable capacity. HIP-3 `para`/`xyz` quote availability never proves trading-session authorization, and earlier short bounded quotes turn STALE after the freshness window. Full 24-hour continuity, exchange fill capacity and source equity remain UNKNOWN.

### New full native exposure L2 shard sweep (2026-11-04)

A separate read-only canary used the **22 distinct native instruments in the latest observed P14 signed-position tape**, not a static headline list, in five CCXT Pro Hyperliquid public-client shards of 5/5/5/5/2 instruments. The private market receipt root is `data/private/p1p14_market_refresh_20261104`. **21/22** instruments produced independently time-stamped, SHA-chained L2 receipts at their specific observation times. The remaining `para/ANSEM` again failed `CCXT_BOOK_SPREAD_TOO_WIDE` at that observation, despite the independently dated 78.6 bps accepted quote above. This confirms variable quote quality, not a reason to weaken the 100 bps gate. The `xyz/ANT` and `xyz/MU` market quotes were two-sided but HIP-3 session trust remains `UNKNOWN_HIP3_SESSION`. All 21 accepted quotes explicitly retain `UNKNOWN_BOOK_DEPTH_NOT_TRADED_VOLUME`; **0/22** markets have proven complete executed volume, continuous live coverage, or authoritative order session capacity. This scan was finite and time-staggered, not a synchronized 22-market execution observation. No broker orders, source subscriptions or protected workers were initiated.

## Reproduction — no trading permissions

```bash
uv run --group dev copytrade-pm-paper-readiness \
  --portfolio P1 \
  --registry /home/quant/.local/share/copytrade/registry/wallet_registry.sqlite \
  --primary-dir /home/quant/dev/copytrade-pm/data/wallet_fills_90d \
  --secondary-dir /home/quant/dev/copytrade-pm/data/nansen_smart_money_fills_90d \
  --source-db /home/quant/dev/copytrade-pm/data/private/paper_scope_observations_20261104/paper-events.sqlite3 \
  --market-db /home/quant/dev/copytrade-pm/data/private/p1p14_market_observation_20261104/paper-events.sqlite3
```

Use `--portfolio P14` for the challenger. All database connections use SQLite URI `mode=ro`, `query_only=ON`; source and market SHA chains are verified with independent financial-tape rules and do not create new receipts. A source identity mismatch, broken SHA chain or invalid market frame fails closed. The sample counts reflect the bounded 2026-11-04 canary, not a continuously updating production feed.

## Forward-paper 1x/2x/3x modeled execution costs

`copytrade-pm-paper-report ... --cost-stress` optionally replays committed **synthetic** PM-03/PM-04 event decisions with cost assumptions at 2× and 3× (model fees, full spread, slippage, impact); it reprices the same as-known events under the existing PM-03/04 accounting authority and rehashes modeled market cost contracts within the **read-only report process**. For sealed P1/P14 run IDs with exact frozen portfolio definition SHA matches, the same read-only report now includes `matched_model_comparison`: final equity/P&L and drawdown differences, optional 2×/3× modeled cost differences and (only for exactly aligned event grids) an unannualized synthetic per-event return-difference dispersion in bps. It never imputes missing timestamps: unaligned grids return `null` dispersion. All values are explicitly `FORWARD_PAPER_SIMULATED_v1`; actual tracking error remains `NOT_ESTIMABLE_WITHOUT_MATCHED_PROSPECTIVE_PAPER`. It does **not** rewrite the original journal, rerun Gemini research, create new paper runs or claim predictive alpha. If no modeled execution evidence exists, the scenario explicitly reports `NO_MODELED_EXECUTION_EVIDENCE`. This is a diagnostic cost stress only, not a separate validated strategy.

## Remaining gates

1. WR-06 must authoritatively seal wallet ID links in a new owner-approved registry version, without overwriting frozen version 2.
2. Live producer must independently establish full parent/subaccount/spot/vault position + equity/mark and collateral coverage; a single all-DEX parent WS cannot satisfy this.
3. Native market quote and complete execution-capacity continuity must cover every signed open/hedging market; `para/ANSEM` remains unsupported by observed spread and HIP-3 session status requires separate attestation.
4. Dedicated OS users, immutable paper releases and supervised worker/watchdog identity must pass protected preflight.
5. Then a separate authorized 72h real paper pilot and a 24h 50-account soak may begin; no previous fixture can replace elapsed observations.
