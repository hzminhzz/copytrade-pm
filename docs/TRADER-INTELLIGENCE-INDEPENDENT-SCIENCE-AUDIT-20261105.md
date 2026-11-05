# Trader Intelligence #31-#33: independent science gate audit (2026-11-05)

**Inspection cut:** 2026-11-05 11:39 UTC. **Baseline:** `origin/main` `58dc8ee1490238fb6f066fb3e27c548d75962c70`. **Status:** `BLOCKED_INDEPENDENT_ECONOMICS`, research-only. This is a read-only operational inspection, **not** a protected study activation, science result, or trading approval.

## Reproducible observations

- `git merge-base --is-ancestor 2479365 origin/main` and the same check for `ba2716d` both returned 0: the requested PR #75/#76 baseline is included.
- The original `/home/quant/dev/copytrade-pm` main checkout was six commits ahead, 50 behind, and dirty. The audit/tests ran in a separate clean DevSpace worktree based on `origin/main`. Original files and production services were not altered.
- `copytrade-wallet-registry doctor`: SQLite integrity `VERIFIED`, schema v8, inventory SHA `3217b46450dcd4fe7b23c17079bf50eb99d585546002610e2e189779ef0f4bf8`. Generation freshness `STALE`; runtime admission `UNKNOWN`; scientific qualification false.
- `copytrade-wallet-registry status`: `registered_paper_runs=0`, `paper_running_observed=0`, `qualification_integrity=FAIL_CLOSED`, `scientifically_qualified=NOT_ESTABLISHED`, `trading_authorized=NOT_ESTABLISHED`. This is a registry observation, not proof that a source observer is absent.
- `copytrade-pm health` returned `DEGRADED`, `trading_authorized=false`, `scientifically_qualified=false`, `paper_running=UNKNOWN`. It must not be converted into a healthy protected paper worker claim.
- `systemctl --user show`: `copytrade-public-observer-p1p14.service` active/running (PID 438441; entered 2026-11-05 04:44:52 CET), and `copytrade-source-abc.service` active (PID 2180745). These are source-observation processes, not independent follower settlement or order authorization.
- `copytrade-pm capabilities validate`: 87 available capabilities, 0 errors. No new replay/economics subsystem is warranted by this result.
- Github issues #31/#32/#33 all OPEN. Recent CI has startup failures, and PR #118's two CI verification jobs failed; therefore do not use GitHub status as an independent economic attestation.

## Engineering verification on this baseline

| Check | Observed result |
| --- | --- |
| TI qualification, walk-forward, economics, rank focused tests | 27 passed |
| Core tests | 1,028 passed, 14 skipped |
| Native market tests | 1,146 passed |
| `ruff check src tests` | Passed |
| `ruff format --check src tests` | Baseline failed on two pre-existing mainline files: `src/copytrade_pm/pm_forward_portfolios.py` and `tests/test_pm_forward_portfolios.py`; mechanically repaired on this audit branch, pending rerun |
| `uv build` | Wheel and sdist built |

Passing these tests demonstrates deterministic engineering behavior only, not real matched follower/control PnL.

## Required evidence for each issue

**#31:** Need independently verifiable first-known receipt continuity and complete main/HIP-3 perp source books, account-mode-aware NAV/equity including collateral and subaccounts, and resolved hedges. Need native SHA-pinned minute quotes/volume and executable 300-second follower and matched controls measured with fee, spread, slippage, funding and capacity evidence. Historical vendor fills and modeled OHLCV outcomes are not independent execution proof. `trader_intelligence_research` produces explicitly hypothetical labels; `trader_intelligence_qualification` cannot establish economic truth from signature alone.

**#32:** Existing shrinkage/ranker tests are engineering verified but calibration against independent mature follower net-R labels cannot be established. Keep C/X = 0R; do not call a historical A/B provisional result prospectively validated.

**#33:** Frozen design `docs/specs/trader-intelligence/frozen-future-pit-design-20261103-v1.md` is `DESIGN_FROZEN_NOT_ACTIVATED`; its original November 4 UTC start was missed without independent preregistration. Do not backdate it. A later protected activation must happen *before* first cut, with independent auditor/collector keys and an immutable identity/selection/economic-protocol SHA. The comparison family consists of five policies for P1 and P14 (10 tests); require equal candidate exposures, 60-minute-or-longer embargo, multiplicity-adjusted block uncertainty, 2x executable cost, 600-second delay and tail/failure stress. Existing `walkforward_diagnostic` is exploratory only.

## Decision and unchanged prohibitions

No issue closed; no scientific promotion, order, protected paper activation, risk-policy change or production deployment. Continue observation and independent attestation, then repeat the read-only eligibility audit. No extrapolation from 27 focused tests, a signed synthetic fixture, public observer heartbeat or source-vendor timestamps to live execution economics.
