# ADR: Retire V4 first-known T0+300 operational policy

**Date:** 2026-11-14
**Status:** Owner-approved retirement; VPS legacy observer shutdown verified; repository fail-closed changes pending review and merge.
**Scope:** `copytrade-pm` source observation and virtual paper. This ADR is not a Guardian, broker or production trading authorization.

## Decision

The former first-known position-transition T0+300 source policy is retired **before** ANOS real-world E2E workflows. CWSA's canonical five-minute complete-position REST checkpoint policy is the only forward-looking source policy and the ANOS E2E target. Do not operate the old V4 streaming observer or sixteen-portfolio T0+300 paper engine, use them as a new research admission policy, or present their historical results as CWSA financial evidence.

On 2026-11-14, `copytrade-v4-selected-positions-0811.service` and `copytrade-v4-minute-0811.service` were stopped and disabled. Both active CWSA Chapter 2 user services were independently checked still running. The V4 Vike-minute observer had a V4 label and historical consumers; it is not the CWSA REST source.

## Compatibility and proof boundaries

- The active CWSA source service still launches `copytrade_pm.pm_v4_selected_positions --source-mode CHECKPOINT_REST_V3`. Its module name is historical, not its timing semantics. Deleting the module before moving that shared checkpoint implementation would interrupt CWSA.
- The former V4 `LEGACY_WS` service mode and V4 sixteen-portfolio paper CLI must reject new starts in the next merged release. Historically named shared evidence, source, identity, recovery and research helpers are retained where independently used. They are not permission to resume the retired policy.
- Keep original V4 journals, source receipts, signed releases, protection/reconciliation evidence and historical tests available for read-only interpretation. Do not erase unsettled follower obligations or replay them as new CWSA opportunities.
- The CWSA source collector is running and collecting authentic observations. Its financial admission may remain `BLOCKED_EVIDENCE`, economic fields nullable, and protected trading unauthorized. The retirement decision does not promote any of these states.
- ANOS real-world E2E cases should use authentic CWSA checkpoints, scoped gaps, recovery baselines, source-to-paper blocker projection, and UI/CLI parity. Retired V4 behavior is historical context only; no performance comparison or model benchmark.

## Migration follow-up

A separate verified source-module extraction can move the checkpoint CLI and `selected_parents`/shared evidence adapters to CWSA-named modules; update source service units and runtime process-proof catalog in the same release. Remove old V4-only deployment scripts and tests only after their executable consumers and historical/replay obligations are explicitly classified. This cleanup does not block starting CWSA real-data E2E after the legacy services are stopped.
