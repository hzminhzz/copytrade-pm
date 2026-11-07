# Dextrabot DEX-71 and DEX-02 — approved research advancement (2026-11-07)

**Decision:** Owner approved advancing **DEX-71** (first priority) and **DEX-02** (second priority) into detailed follower-replay/source-reconciliation and prospective shadow-paper research. This is **not** a portfolio seal, source subscription, change to the current TriadA/TriadChop research selection, trading authorization, or permission to place an order.

**Evidence scope:** Original Dextrabot snapshot 2026-11-07; Vike historical fill tape 2026-07-01 through 2026-11-07 07:43 UTC; independent read-only local 30-day window 2026-10-08 00:00 through 2026-11-07 00:00 UTC; source/market artifact SHA audit from `research/0711`. The selection was made *after seeing vendor historical performance*. Treat all prior history as **discovery**, not unseen out-of-sample performance.

## Registry, privacy and source identity

- Private SQLite `dextra_wallet` cohort v1 contains both aliases with bound identities; neither is currently excluded or a current portfolio member.
- Registry physical integrity `VERIFIED`, inventory SHA-256 `6553b8b7a725474b73a3924fcce63c198e42656d8064c82144816240ca0a762d` at audit. Source last legacy import dated 2026-11-04, **not** a fresh wallet observation.
- Private original raw files, account addresses and the full diagnostic JSON stay **outside Git**:
  `/home/quant/.local/share/copytrade/reports/dextra-candidates-0711-20261107/diagnostics.json`.
- Source `DEX-71`: 11,152 historical fills, SHA-256 `4aa6539877a2ff965bcb759aaabcc1e505a0815addc1324042d7ce1abfa49d72`. Source `DEX-02`: 6,879 historical fills, SHA-256 `c5c3574ba16e21c336b8eb2439be6e82ca2a6434dbc008979c6e01d6608dbb04`. Recomputed hashes match the private acquisition manifest.

## Predeclared follow-up research design

**Primary question:** after five-minute signal batching and fully realistic taker costs, is copying the *complete selected-scope source position vector* feasible and preferable to no trade / a matched market control? Use existing PM-03/PM-04 and native cost/market authorities rather than a second financial simulator.

1. Establish authentic selected perps account and all-DEX/HIP-3 census with first-observed position snapshots and causal source-event/receipt clocks. Classify opaque `@` asset IDs as spot/non-perp where independently verified; keep spot activity outside an explicitly selected perp-only mirror. Map any unresolved namespace before it can enter the selected perp set. Separate pre-window inventory from missing fills; don't assume flatness or reconstruct missing transactions.
2. Reconcile each selected-scope official position vector against fill deltas, closures, rollbacks, session restarts and any vendor source gaps. Freeze the exact trusted, timestamped opening state *before* reporting whole-position episodes or holding durations. Report unresolved episodes as blocked.
3. For the matching native instruments/dates, require exact native source-day SHA and minute completeness; ensure viable orderable follower market coverage and lot precision. Reject unsupported legs instead of silently dropping hedges.
4. Under the native `FIXED_K_NATIVE_QUANTITY` contract, use 5-minute batching, signed pod k, **real follower equity and headroom**, a $200 nominal pod-loss stop for the illustrative $10k challenge, gross/concentration caps, fees, spread, slippage, funding and margin. Never infer k from the vendor source equity snapshot. Benchmark 0/5/15-minute diagnostics as sensitivity *without selecting a winning lag retrospectively*. Matched follower PnL needs actual prospective first-known decision timing; historical Vike fills are an **oracle upper-bound/timing screen only**.
5. Open an untouched future forward window **after** this decision, retain failures and stale/gap intervals, and compare source/market/actual paper broker outcomes over matching intervals. Only separately reviewed source authenticity, portfolio seal, observer capacity, Guardian account risk and financial reconciliation can grant later paper execution authority.

## Audited 30-day diagnostics

| Field | DEX-71 | DEX-02 |
| --- | ---: | ---: |
| Dextrabot account-value snapshot (USD) | 215,133 | 25,261 |
| Vendor copy score | 79.06 | 61.49 |
| Verified historical file fills / fills in 30-day window | 11,152 / 5,512 | 6,879 / 3,143 |
| Distinct source order-side-market groups over 30 days | 160 | 401 |
| Active observed UTC trading days | 25 | 29 |
| Median time between observed order groups | 41.66 min | 10.84 min |
| Consecutive groups separated by <=5 min | 23.9% | 37.5% |
| Taker (not maker) fraction of fills | 94% | 85% |
| Main traded-notional concentration | BTC 43.5%, ETH 19.7%, ZEC 18.3%, HYPE 16.0% | ZEC 88.9%, xyz:SKHX 6.5%, XMR 3.4% |
| Native traded symbol-days: full verified SHA / partial / unresolved IDs | 53 / 1 / 0 | 42 / 0 / 7 |
| Reported liquidations in available historical audit | 0 | 0 |

The gaps between **order groups** are **not** position holding times; neither episode-count nor follower costs/PnL can be inferred from them. The historical 30-day vendor source closed-PnL values, if consulted, are not independently valued follower returns and omit important causal/account context. Source snapshots were at times before some latest fills.

## Position reconciliation — cannot advance to economic replay yet

A naive flat-start sum of fills before the vendor's `portfolio_at` snapshot does **not** reconcile. This is a diagnostic **unexplained opening-position offset**, **not proof** of a wrong current snapshot: the historical window starts July 1 and does not establish an opening book.

- **DEX-71:** snapshot reports −100 ZEC; cumulative signed fills up to snapshot imply −50 ZEC *assuming flat at window start*, leaving −50 ZEC as an unexplained opening/scope offset. `@107` also has a +0.88 residual unresolved by the visible snapshot.
- **DEX-02:** snapshot lists no open positions, but before-snapshot signed fills under a hypothetical flat opening imply +13,000 XRP and residual `@142`, `@151`, `@156` quantities. Later XRP fills reverse the +13,000; do not infer true flat historical inventory from that reversal.
- The official atomic scoped account positions, HIP-3 token mapping, original opening balances, and authentic first-known receipt clocks are not yet established. These specific missing facts block a faithful **whole-position** follower replay. They **do not** block continuing independent data repair and forward research.

## Final evidence classification

- **REGISTERED / HISTORICALLY ACTIVE / snapshot account value >$1,000:** Verified for both within the specified snapshots; not a current real-time equity guarantee.
- **ADVANCED FOR RESEARCH:** Approved DEX-71 then DEX-02, with versioned observations and explicit blockers.
- **HISTORICAL FOLLOWER PNL:** **UNKNOWN**. No 5-minute financial result or risk-adjusted follower edge has been computed.
- **PROSPECTIVE PAPER_RUNNING, SCIENTIFICALLY_QUALIFIED, TRADING_AUTHORIZED:** **NOT ESTABLISHED**.
- No registry mutation, subscription, deployment, Guardian financial action, or real order accompanies this record.

## Reproduction

From `/home/quant/dev/copytrade-0711`, with `uv run --frozen --group dev`:

```bash
copytrade-wallet-registry doctor
copytrade-wallet-registry wallet --alias DEX-71
copytrade-wallet-registry wallet --alias DEX-02
copytrade-wallet-registry portfolio --current
copytrade-wallet-registry paper
python /home/quant/.local/share/copytrade/reports/dextra-candidates-0711-20261107/audit.py
```

Run commands within the repository's `uv run --frozen --group dev` environment if using the native executable aliases. The private report and script are permissioned to the `quant` account. The script performs read-only source and native-market file inspections and writes only a private derived report. It does **not** simulate trades or alter the registry.

## Independent post-screen validation — 2026-11-07 11:23 UTC

**Official public Hyperliquid `/info` checks**, with original responses saved privately alongside the diagnostic, correct vendor accounting ambiguity:

| Observation | DEX-71 | DEX-02 |
| --- | ---: | ---: |
| Main-perps `clearinghouseState.marginSummary.accountValue` (USD) | 34,958.65 | 0.00 |
| Official main-perps position | −100 ZEC | Flat |
| Official `spotClearinghouseState` USDC balance (units) | 219,104.91575688 (25,846 on hold) | 25,261.428326 (none on hold) |
| `userAbstraction` | `unifiedAccount` | `unifiedAccount` |
| Dextrabot earlier account-value snapshot (USD) | 215,133 | 25,261 |

**Interpretation:** DEX-02 is **not** a zero-funded unified-account wallet: its independently observed spot USDC matches the previous Dextrabot balance. It is presently flat in main perps. DEX-71 has an independently confirmed funded active main-perp position. Do **not** add USDC spot balance and main-perp accountValue into fabricated aggregate NAV; these scopes may share collateral. Main-perp accountValue zero does not imply unified-account assets zero. Neither account's whole financial book has been atomically reconstructed.

The DEX-02 opaque events `@142`, `@151`, `@156` pay fees respectively in **UBTC, UETH, USOL** and closely correspond to independently observed spot assets. They should not be mistaken for unsupported *perpetual* instruments. Scope segregation is needed before episode replay. DEX-71's `@107` is still an opaque/nonselected instrument until independently mapped. The earlier residuals are therefore diagnostic consequences of unknown window-opening inventory and mixed source scopes, **not established missing-fill incidents**. DEX-02's XRP before-snapshot residual still requires genuine timestamped position reconciliation.

Vike `hl_wallet_trades` closed-round-trip diagnostics for the explicit close-time window `[2026-10-08, 2026-11-07)` give:

| Episode measure | DEX-71 | DEX-02 |
| --- | ---: | ---: |
| Vendor reconstructed closed episodes | 65 | 109 |
| Median closed episode holding time | 135 min | 32.7 min |
| Closed episodes shorter than 5 min | 1 | 11 |
| Closed episodes shorter than 15 min | 6 | 30 |
| Closed episodes shorter than 60 min | 22 | 75 |
| Closed episodes holding at least 10 hours | 15 | 3 |
| Worst vendor closed-trade realized PnL (USD; **source scale**) | −10,082.50 | −1,003.76 |

**Research consequence:** DEX-71 has materially more favorable observed episode durations under a five-minute copying policy. Nonetheless **50/65 DEX-71** and **106/109 DEX-02** closed episodes are under the previously preferred 10-hour minimum; neither deserves a slow-swing-manager label. DEX-02's 75/109 sub-hour episodes make it especially timing-sensitive. Vike reconstructed trades are not independent official position-chain proof, nor evidence of follower PnL. The actual follower's nominal $200 pod stop is not bounded by the leader's raw trade loss, and cannot be validated without the follower execution path.

**Official source raw-response SHA-256** (per account; both timestamped UTC and permissioned 0600):
- DEX-02 `clearinghouseState`: `dc4c8dfa910942928bcaa052648a1676691c2c0150c76c4a3cfa00755883d12a`; `spotClearinghouseState`: `6b5bc325e26abff4b77588c340eb3a4009f04ce143dc978c23edd9c4f356ab35`.
- DEX-71 `clearinghouseState`: `51908b354a21f9175ec21781e9a5bd32abd72763802b2b56f7fe2c04be2f4c7b`; `spotClearinghouseState`: `38f031271131f56f231aea0b47ebbd67a0723ebb7059e33bffec5a57dc948634`.

**Verdict remains:** DEX-71 and DEX-02 are **ADVANCED_RESEARCH_ONLY**, still without matched five-minute follower economics or authenticated prospective signal receipts. Current official public observations satisfy the practical $1,000 funded-account screen but are not a declaration of executable follower margin or order permission.
