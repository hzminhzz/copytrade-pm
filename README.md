# copytrade-pm

Black-box external-wallet portfolio-manager research and **shadow-only** prop-firm challenge simulation.

## Migration state
- **STAGING ONLY:** Source integration is verified, but PM-01/PM-02 have NOT yet been extracted and PM-03 is NOT implemented here.
- Source: [hyperliquid-expert-ensemble](https://github.com/hzminhzz/hyperliquid-expert-ensemble).
- Integrated source staging: [PR #8](https://github.com/hzminhzz/hyperliquid-expert-ensemble/pull/8) at `00382c6e5846b7df540f679b970a09e507750521`.
- Original research: PM-01 [Issue #3](https://github.com/hzminhzz/hyperliquid-expert-ensemble/issues/3), PM-02 [Issue #4](https://github.com/hzminhzz/hyperliquid-expert-ensemble/issues/4), PM-03 [Issue #5](https://github.com/hzminhzz/hyperliquid-expert-ensemble/issues/5).

## Intended modules
1. **PM-01:** immutable source/account observation, fail-closed whole-book reconstruction and hypothetical follower replay.
2. **PM-02:** evidence-driven manager ranking, independent risk budgets and lifecycle decisions.
3. **PM-03:** one account-level, deterministic, research-only Propr challenge simulator and risk supervisor.

## Non-negotiable boundaries
- Preserve PM-specific commit provenance and all SHA-referenced evidence lineage. Do not publish raw private HyperX sources, keys, wallet address maps, or private market data.
- Source fills are retrospective, not a prospective first-known feed. Keep source events, first-known receipt, decision, and hypothetical execution clocks distinct.
- PM-01 `pm01_fill_only_replay_v2` is the pinned compatibility seam currently consumed by PM-02.
- Zero wallets scientifically qualified; zero actionable allocation. A 90% *market-data readiness* gate is not source economics or executable follower PnL.
- No live orders, broker credentials, broker adapters, autonomous account risk increases or modifications to the legacy Telegram/ensemble runtime.
- PM-03 simulation must test daily/static/trailing drawdown, cross-PM netting, internal attribution, stale/unknown market state, rejection/partial fills, and blocked-live compliance verdict.
- Legacy `hyperliquid-expert-ensemble` should remain deployed from its own pinned release, independent of this repo.
