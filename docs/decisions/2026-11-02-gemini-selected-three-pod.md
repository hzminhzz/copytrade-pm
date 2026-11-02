# Decision: selected Gemini three-wallet portfolio

- **Decision date:** 2026-11-02 (UTC)
- **Decision owner:** user; confirmed after Gemini Phase 2 review and the subsequent copytrade-pm logical assessment
- **Repository:** `hzminhzz/copytrade-pm`
- **Status:** **SELECTED FOR DEMO/PAPER DEPLOYMENT PREPARATION** — not scientifically qualified, not deployed, and not authorization for funded/live-money trading
- **Decision scope:** the preferred **three-wallet roster** for the next copytrade portfolio implementation. This does **not** alter the frozen PM-01 cohort, existing service rosters, or the separate Combo 2 tracker.

## Locked portfolio choice

| Slot | Wallet alias | Intended portfolio role | Why selected |
| --- | --- | --- | --- |
| 1 | **S053-HYPE** | HYPE-focused trading sleeve | Concentrated trading identity with relatively high supported native-market coverage; distinct from the other two source profiles |
| 2 | **S051-BTC** | BTC / broader crypto trading sleeve | Adds a different instrument and source-trading profile from S053 |
| 3 | **S035-ENA** | Altcoin trading sleeve | Adds exposure to a different mix of altcoin opportunities |

**Canonical set:** `S053-HYPE + S051-BTC + S035-ENA`. Do not substitute another three-wallet combination simply because a historical proxy ranks higher. Do not change the selected roster without a new dated, reviewed decision and reason.

**Decision basis:** Gemini's portfolio proposal plus independent logical scrutiny. We favor different source trading profiles and avoidance of evident hidden-inventory/tail concerns. The apparent diversification is a **hypothesis**; different wallet labels do not guarantee independent PnL or crisis exposures.

### Superseded *candidate choice*, not production configuration

- Former research comparison `S048-BTC + S053-HYPE + S060-HYPE` is **not** the selected next-portfolio roster. S048's large underwater inventory and overlapping HYPE focus were material concerns.
- `S058-PUMP` is also **not** selected, given the concern that realized gains mask substantial open-position losses.
- Existing A/B/C historical portfolios and `W028 + CA-008 + W015` Combo 2 demo-paper work remain **separate**. No running account, watchlist, deployment, active paper strategy, or production config is replaced by this documentation decision.
- Gemini's preferred 5-wallet alternatives are **not** chosen for this implementation.

## What this decision does and does not establish

**Verified or source-grounded at decision time**

- Local `copytrade-pm` has the three source aliases in the broader 94-wallet fill inventory. Do not put wallet addresses or provider credentials in Git. Resolve aliases against the owner-private, SHA-pinned source mapping when implementing monitoring.
- An earlier local forensic pass reproduced Gemini's **realized net** source PnL (closed PnL less reported fees) for the three aliases to within approximately US$0.42 each. This is **not** follower PnL.
- Approximate historical turnover in the then-supported native Propr display universe was **94% S053, 72% S051, 69% S035**. These are dated research coverage fractions, not account-level permission or complete whole-wallet coverage.

**Inferred, not proven**

- Combining a HYPE-heavy wallet, a BTC/broader wallet and an altcoin wallet is a sensible starting point for source-style diversification.
- Their net positions may still be highly correlated during a broad crypto drawdown.

**Unknown / explicitly NOT established**

- Actual independent risk-adjusted follower alpha, genuine out-of-sample performance, and reliable prop challenge pass probability.
- Complete source-equity, subaccount/hedge scope, first-known position updates, broker-side fills and fee/funding economics for this specific three-wallet roster.
- That off-universe instruments or hedges can be dropped without changing the strategy.
- Executability, copying/API permission, instrument IDs, precision, margin, risk limits and contract terms for a specific Propr account.

Gemini's predicted challenge results and any October hindsight replay are **exploratory**, not an authorization criterion. **The user explicitly requested a logical selection decision, not additional portfolio optimization or another historical backtest at this stage.**

## Implementation direction for the next agent

**Objective:** make the **selected roster** observable and paper-executable through the existing system, rather than restarting wallet selection.

1. **Resolve identity and capture:** locate the canonical addresses for `S053-HYPE`, `S051-BTC`, `S035-ENA` in private local fill manifests; verify source owner, parent/subaccount and all-DEX scopes; register the new roster separately from the frozen 36 and Combo 2. Use bounded prospective **first-local** observation; preserve reconnect gaps.
2. **Preserve source behavior:** ingest complete positions/equity and source quantity changes, not isolated trade alerts. For follower sizing, use the existing **source-equity-relative whole-book intent** policy with account/pod limits; do **not** transplant Gemini's static $100k multipliers as live order sizes.
3. **Five-minute execution policy:** wait **300 seconds after the first eligible observed signal**, aggregate updates, then prepare **one market-order rebalance per net instrument** when allowed. Enforce actual first-known timestamp, lot/precision, account gross/notional, per-instrument capacity, independent pod attribution and hard drawdown/HALT controls. A missed trade changes follower inventory; do not pretend it executed.
4. **Handle Propr scope honestly:** verify account-specific executable symbol mapping, fee/funding and contract rules. If source books contain untradeable hedges/positions, mark any partial replication as a distinct strategy and block unsupported whole-book or risk claims. No silent hedge removal.
5. **Deploy progressively:** offline replay/integration assertions → read-only live wallet capture → durable local SQLite intent journal with transport-spy and crash/restart checks → explicitly authorized Propr **demo/free-trial** order canary, with broker acknowledgments, partial fills, inventory reconciliation, reduce-only emergency exit and service-health checks. Preserve the existing Combo 2 service and shared Hyperliquid subscription budget.
6. **Account separation:** the user's research target is a **$10,000 challenge account**; the previously inspected Propr trial `#JhW9` had roughly **$5,000** in equity at inspection. Never apply $10k order quantities to a $5k demo by implication. Read the current demo balance and confirmed account limits before a canary.

**Deployment authority boundary:** selecting this roster authorizes preparation, integration and shadow/demo evaluation, **not unattended trading or funded-account risk**. The user has previously authorized controlled trades on the Propr free-trial/demo account, but each execution path still requires actual venue/broker readiness, account-specific guards and no accidental production routing. Research-only `copytrade-pm` must not directly send broker orders; broker mutation belongs in the separately governed connector. Funded deployment needs new explicit authorization.

## Review triggers / supersession

Revisit **only** if verified source identity or account coverage changes, significant correlation/tail overlap emerges, venue support or limits conflict, or prospective follower economics and operational safety disqualify one wallet. Log the evidence and publish a superseding dated decision; never silently replace this roster.

## References

- Gemini Phase 2 portfolio study supplied in the conversation (source proposal, **not** validated alpha).
- [Independent Gemini methodological audit — PR #24](https://github.com/hzminhzz/copytrade-pm/pull/24).
- [Native PM03 94-wallet exploratory replay — PR #25](https://github.com/hzminhzz/copytrade-pm/pull/25).
- [Five-minute source-equity sizing design](../EQUITY-WEIGHT-SIZING.md).
- [Prospective source/economic qualification](../QUALIFICATION.md).
- [Autonomous blocker recovery](../BLOCKER-RECOVERY.md).
