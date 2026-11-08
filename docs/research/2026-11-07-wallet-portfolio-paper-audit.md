# Copytrade research audit — 2026-11-07

**Scope:** Read-only evidence inspection from isolated `research/0711`; no production changes, no full replay, no paid API acquisition.

**Research source commit:** `28bda4f23175a8d2b5f644ee157e8dc732dae7f3`
**Authority:** SQLite inventory `6553b8b7a725474b73a3924fcce63c198e42656d8064c82144816240ca0a762d`; native updated at `2026-11-07T07:34:06Z`.
**Observed during audit:** 2026-11-07 approximately 10:23 UTC. Verify again before any decision.
**Evidence classes:** VERIFIED = direct live read; HISTORICAL = dated artifact; UNKNOWN = authority unavailable.

## A. System status

VERIFIED: SQLite physical integrity and current research selection signatures pass on schema v8. Registry has 502 canonical wallet identities in total, 284 distinct research cohort members, 264 configured and 264 subscribed (not a receipt-health attestation), 32 distinctly owner-excluded wallets, and one research/exclusion intersection. The research cohort breakdown is research-108=108, nansen-20=20, hyperx-30=30, ml4t-top6=6, ml4t-strict-66=66, dextra_wallet=73; these overlap. 158 wallet-coverage records describe 108 `UNKNOWN_PARTIAL` and 50 `VENDOR_COIN_CENSUS_RECONCILED`, with account-book and first-known coverage both `UNKNOWN`. Thus **no evidence-backed number of copy-qualified wallets is established**.

The registry status reports 13 sealed definitions while doctor reports 15 and direct SQLite contains 22 version rows. These denominators refer to different objects/filters and must not be presented as interchangeable. Dated legacy import clock 2026-11-04 is stale; native update 2026-11-07 is current relative to the audit, but does not attest new source receipts or wallet fills.

Installed registry-only release `b1dc9fd9493b28d56385400708e7547f74b173fe` verified. Actual user public observer PID 438441 uses prior independent release and is `DEGRADED_OBSERVER_ONLY`; its process is running, not a financial worker. Source-ABC also running. Separate prop-production Guardian and Bybit read-only observer system services are active, but protected Guardian account journals under `/var/lib/prop-production` were inaccessible to user `quant`, and are **not financially attested in this audit**.

## B. Wallet universe and quality

| Classification | Finding |
| --- | --- |
| Registered research universe | **284** distinct; do not call all usable |
| Total canonical metadata identities | **502** (not a research-candidate count) |
| Monitored / subscribed | **264 / 264**, not evidence of healthy current observation |
| Owner exclusions | **32 unique**, across 33 exclusion records |
| Exclusion reasons by record | 14 truncated Nansen; 11 inactive 30d; 5 underwater bagholder; 3 passive maker |
| Research overlap with exclusions | **1** |
| Coverage records | 158; 108 unknown partial, 50 vendor-census reconciled |
| Independently provable 180-day history / continuous fills | **UNKNOWN** without per-wallet original source audit |
| Independently provable qualified wallet count | **UNKNOWN**, not zero |
| Evidence-grounded A/B/C per-wallet grades | **UNAVAILABLE** on this inspection; never use vendor PF as qualification |

The local 90-day source folders and 2026-11-05 ML4T collections exist, but the file presence and vendor pagination census alone do not validate 180 days of complete episode history, first-known timing, full source book or executable follower economics. No wallet earns a positive A research grade by assumption. Prior archived candidate rankings remain historical hypotheses pending exact as-of data and prospective evidence. Avoid extracting wallet addresses into reports.

## C. Portfolio inventory (SQLite authoritative)

| Portfolio | Members | Version | Sizing contract | State | Verified finance |
| --- | --- | --- | --- | --- | --- |
| regime.macro/TriadA | ACT04 / ACT08 / ACT09 | 2 | NON_EXECUTABLE_SIGNED_RESEARCH | **Current primary** research selection | UNKNOWN |
| regime.macro/TriadChop | ACT04 / ACT09 / ACT10 | 2 | NON_EXECUTABLE_SIGNED_RESEARCH | **Current challenger** | UNKNOWN |
| P1 | S035-ENA / S051-BTC / S053-HYPE | 2 | Virtual $10k, nominal loss budget $600 | Frozen prior paper research | NOT VERIFIED |
| P14 | P1 + S064-xyz:BRENTOIL / Whale_0x5f94 | 2 | Virtual $10k, nominal loss budget $600 | Frozen challenger | NOT VERIFIED |
| Combo2 | CA-008 / W015 / W028 | 2 | Virtual $5k, NOT broker | Research experiment | NOT VERIFIED |
| gemini.phase4/E6 | ACT04 / CM-002 / S051-BTC / S053-HYPE / Whale_0x5f94 | 1 | Non-executable reference k | Prior research | NOT VERIFIED |
| q3/B | CA-005 / W031 / W044 | 2 | Q3 illustrative $10k | Historical only | NOT VERIFIED |

Current research selection signature `e3460d5357c7cdc5995334256ef536d081ef8c4cdab6cd0a162eebc2503f6f10`; as-known `2026-11-07T01:08:46.706481Z`. Both Triads' wallet aliases resolve in current registry. This does not prove source identity at their historical selection or running worker status. Older P1/P14 original-selection binding was documented as post-seal (see `docs/SELECTED-OBSERVER-P0-EXECUTION-20261107.md`); do not backdate current aliases.

## D. Authentic forward paper performance

Direct immutable public-observer SQLite read of `/home/quant/.local/share/copytrade/prospective/p1p14-observer-20261105/paper-events.sqlite3` returned **5,929 source receipts**, **32,886 market quote receipts**, **0 financial runs**, **0 financial events**. Registry has 0 indexed paper runs. Independent observer-health CLI: `DEGRADED_OBSERVER_ONLY`, five source aliases with receipts, 29 verified quote tapes, thirteen quote-stale/missing reason codes, `paper_observed=false`, `order_route=NONE`, `protected_worker_attested=false`.

| Metric | P1 / P14 | Current TriadA / TriadChop |
| --- | --- | --- |
| Starting account equity | UNAVAILABLE | UNAVAILABLE |
| Genuine follower MTM | UNAVAILABLE | UNAVAILABLE |
| Realized / unrealized follower PnL | UNAVAILABLE | UNAVAILABLE |
| Return / max daily DD / max DD | UNAVAILABLE | UNAVAILABLE |
| Fees / funding / slippage | UNAVAILABLE | UNAVAILABLE |
| Financial journal events | 0 in inspected P1/P14 public journal | No verified financial journal |
| Paper-running state | NOT ATTESTED | UNKNOWN |

**Do not interpret unavailable performance as $0 PnL.** Public source/quote receipts cannot be interpreted as a financial execution ledger. Active separate Guardian SHADOW system service is not proof of a specific sealed Triad portfolio, actual demo fills or an authentic attributable paper PnL series. Protected journals were unreadable without privilege; no sudo escalation attempted.

## E. Historical modeled follower performance

Historical and research evidence collections exist in private reports, including `ml4t66-batch-recovery-20261105` and `barbell-20261106`, and dated documentation of historical oracle research. They were inventoried by filenames and not re-run or fully reconciled to a single PIT, executable follower outcome in this bounded investigation. **No historical return is promoted to current paper performance or qualified alpha.** The native `copytrade-pm contracts rules` lists three **USER_SUPPLIED_UNVERIFIED_ARCHETYPE** contracts, none account-trading-authorized; contract comparison requires an actual qualified private follower PnL tape. No such tape was certified in this audit, so do not manufacture a contract pass probability.

## F. Portfolio decision

- **TriadA — EXPERIMENT:** current signed research primary; requires actual prospective follower MTM and immutable source identity/quotes before any ranking by executable PnL.
- **TriadChop — EXPERIMENT:** matched challenger; compare only over co-observed source/market periods with identical risk/cost rules.
- **P1 — RETAIN baseline, SUSPEND financial-performance claims:** existing public observer remains degraded, not financial.
- **P14 — RETAIN archival comparison, SUSPEND promotion:** 5-wallet source identity/profirm exclusion and shared-IP census admission were flagged by dated P0 diagnostic.
- **Combo2 — EXPERIMENT offline:** virtual account and possible evidence in PR #26 are not deployed finance.
- **Gemini E6 and Q3 A/B/C — RETAIN historical research only:** separate past modeling from live record; do not optimize by model k with leakage.

Research decisions never authorize orders, risks, deployments or production changes.

## G. Highest-ROI next work

1. **Acquire independent AUTHENTIC follower accounting** (portfolio-bound journal, account equity, executed demo/paper fills, fees/funding/slippage, daily MTM, pod attribution, broker reconciliation), with authorized read-only access to protected Guardian accounting. Verify matching installed version and exact sealed portfolio. Do not launch or restart services.
2. **Fix observer coverage and budgets via existing issues #135/#141/#142.** Prior P0 audit measured user-slot and socket contention; public observer remains degraded and has stale quotes. Keep current service unchanged until independent canary/cutover.
3. **As-of joint quality ledger:** attach original first-known source receipt, source positions, market quote and per-wallet hold/episode completeness to the existing registry identity; do not synthesize backfilled first-known. Rank A/B/C only after those fields exist.
4. **Matched TriadA vs TriadChop prospective comparison:** predefine risk, 5-minute batching, signed native fixed-k, gross/pod caps, and costs before inspecting return; do not select best historical outcome.
5. **Reconcile historical report provenance:** per-run input hashes, sealed as-of wallet members, PIT source/quote chain, independent OOS, and execution costs. Prefer existing native replay tools. Avoid expensive grid until VPS resources and dashboard benchmark timing are independently safe.

## H. Reproduction and limits

```bash
cd /home/quant/dev/copytrade-0711
git rev-parse HEAD
uv run --frozen --group dev copytrade-wallet-registry doctor
uv run --frozen --group dev copytrade-wallet-registry status
uv run --frozen --group dev copytrade-wallet-registry portfolio --current
uv run --frozen --group dev copytrade-wallet-registry paper
uv run --frozen --group dev python scripts/registry_release.py verify
uv run --frozen --group dev copytrade-pm-paper-observer-health --state-root /home/quant/.local/share/copytrade/prospective/p1p14-observer-20261105
```

Snapshot findings are limited to the cited private original sources; private SQLite contents and addresses deliberately not copied or committed. Read-only CLI and SQL counts verified. No full replay, wallet-episode grading, privileged finance proof, statistical testing, smoke integration, or scientifically qualified follower PnL measurement performed. Other sessions' checkouts, services and data stores were not edited.