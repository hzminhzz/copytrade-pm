# Trader Intelligence TI-04/05/06 — causal research engineering continuation

**Verified research inspection:** 2026-11-04 UTC. **Scope:** issues #31–#33, read-only analysis. This document supplements, and does not supersede, the immutable [future PIT design](specs/trader-intelligence/frozen-future-pit-design-20261103-v1.md). No financial order, broker/account mutation, Telegram send or source-ledger rewrite occurred.

## Engineering contracts implemented

The native minute path (`trader_intelligence_native.py`) delegates day identity, source-sidecar SHA, DEX and venue validation to the existing `pm_shadow.VerifiedHyperliquidMinuteSource`. It rechecks raw Parquet bytes for a mid-read SHA change, converts complete UTC minute OHLCV to the existing `trader_intelligence_research.MinuteBar`, and refuses gaps, duplicate minutes, unsupported market identities, an unclosed final minute or a window longer than three days. Source day SHA and input window SHA are retained. A verified open/volume is **not** an executable quote or fill, and neither available volume nor OHLCV authenticates funding, spread, whole-wallet positions or actual Propr costs.

The existing `follower_replay` is unchanged in risk/size ownership. Its additional source hygiene rejects a missing first actionable minute instead of moving the order arbitrarily into a later candle, and detects UTC-equivalent duplicate market bars. `trader_intelligence_stress.replay_follower_sensitivities` runs the **same input event census** through the existing engine under fixed-horizon 300s base, 2× nonnegative fees/slippage/spread (signed funding unchanged so short credits cannot masquerade as adverse costs), 600s delay and conservative stop/horizon; missing exposures/marks remain NULL, not $0. Every scenario has its own policy SHA and deterministic report digest; these are hypothetical simulated follower outcomes.

The research benchmark's `MatchedMarketControl` now requires the exact source episode, candidate cut, instrument, direction, horizon, hypothetical entry/exit, cost R and policy SHA. Both `matched_benchmark` **v2** and `walkforward_diagnostic` **v2** apply the same identity/maturity validator and reject duplicate candidates. This is an intentional *versioned research diagnostic contract* change; it is not a frozen PM-01 or PM-02 schema migration. No signed independent economic control is produced by this module.

The privacy-safe source preflight (`trader_intelligence_source_preflight.py`) reads the **existing** ensemble `opportunity_decisions`/barrier journal and the private owner alias files; it makes no new journal or subscription and prints only SHA-hashed identities, never addresses. An operator-declared `--registered-at` is explicitly `OPERATOR_DECLARED_UNATTESTED`, **not independent registration**; omission is `UNREGISTERED_DYNAMIC_INSPECTION`. It inspects bounded native 1m coverage even when real source barriers veto directional entry, but never counts market marks as eligible follower trades. `--output` is a single owner-private **O_EXCL** SHA-stamped report, refusing overwritten evidence. There is no new scheduler or background process.

## Real current read-only P1 assessment (NOT an eligible future study)

- Alias cohort: **S035-ENA / S051-BTC / S053-HYPE**, existing P1 historical selection, **not** a newly independently registered roster.
- Recorded source cut: **2026-11-04 07:27 UTC**; existing journal last 24h contained **141** P1 opportunity rows, **0** eligible directional transitions, **0** verified coherent source books/equity and **0** signed matched executable follower/control outcomes. Future-window/independent registration unavailable.
- The journal had **98** accumulated coverage barriers: 49 `SUBSCRIBED_HISTORY_UNVERIFIED`, 45 `DISCONNECTED_GAP_UNVERIFIED`, 4 `STARTUP_GAP_UNVERIFIED`; latest **2026-11-04 06:32:20 UTC**, after inspected P1 first decisions. These barriers correctly invalidate source promotion: do **not** clear by assigning a synthetic current clock or backfilling vendor fills.
- Across the **141** inspected event-time windows, **99** exact SHA-verified native minute entry+5/15/60m mark checks passed and **42** were blocked on missing market-day data. These checks are *historical diagnostic source availability*, not verified follower execution or all-market coverage for P1.
- Immutable private evidence (existing signed records untouched): `/home/quant/.local/share/copytrade/reports/gTI_20261104_P1_source_readiness_0731_v1/audit.json`, SHA-256 `68cff5ebcc2975d1fd0c73320e8de2be0de1629c0e1df4b802bb38821d3ecda6`, directory 0700/file 0600; `economic_evidence_attested=false`.
- Additional actually loaded real native **62** contiguous BTC minutes, 2026-11-03 12:00–13:01 UTC, SHA-verified input window `b8aa5c0a84d9fbc92b98f710349034d2982633d4d8c1b52c4f0b51ce65006b7b`, **not** a real signed follower.
- Full engineering integration exercised **131** real native BTC 1m bars 2026-11-03 12:00–14:10 UTC, SHA-verified input window `6271c2d53c59b1c288cead0c1d54b88b6dd8511f766e60ecad13af8ec6665b57`, joined with an explicitly **synthetic** open event for 5/15/60m × four model policies = **12/12** hypothetical episodes with `status=OK` (no real-wallet trade). Hypothetical report SHA `0e19ea5b446a6b729424c58f6171da4bc195bc1480b2d51d4a315ef5942bbe6f`, `UNATTESTED_HYPOTHETICAL_RESEARCH_ONLY`.

The original P1 exploratory October/November matched midpoint study has already been inspected. Holm-adjusted p-values were 1.0 and confidence intervals crossed zero; no positive independent alpha or model calibration follows. The initially proposed Nov 4–Dec 4 PIT window **cannot be activated retroactively**. The independent first-known roster/whole-book source continuity, full venue funding, verified executable 300s follower and matched control outcomes and future protected holdout are missing. The concurrent forward-paper PR #73 may eventually supply independent *paper* observations, but is not assumed merged, live, mature or independently attested here.

## Reproducible offline/strictly read-only commands

From a checked-out copytrade-pm source with its normal dependencies:

```bash
uv run --group dev python -m pytest -q tests/test_trader_intelligence_economics.py tests/test_trader_intelligence_stress.py tests/test_trader_intelligence_native.py tests/test_trader_intelligence_source_preflight.py tests/test_trader_intelligence_benchmark.py tests/test_trader_intelligence_walkforward.py
uv run --extra market --group dev python -m pytest -q tests
uv run --group dev ruff check src tests
uv run --group dev ruff format --check src tests
uv build
```

Actual owner-private existing-journal inspection (do not overwrite the pinned generation):

```bash
uv run --extra market --group dev python -m copytrade_pm.trader_intelligence_source_preflight \
  --journal /home/quant/.local/share/copytrade/copy-opportunities-live.db \
  --private-source-files /home/quant/dev/copytrade-pm/data/wallet_fills_90d \
  --aliases S035-ENA,S051-BTC,S053-HYPE \
  --market-root /home/quant/dev/quant/ml4t-data/.data/store \
  --lookback-hours 24 --market-limit 500
```

The CLI uses current real as-of time unless explicitly passed and runs no provider or order network calls. To persist a new generation, use `--output` with a **new unique owner-private path**; it fails rather than overwrite any prior report. A hypothetical stop/cost sensitivity fixture passing is engineering correctness, not economic proof. Specifically, **2× execution cost is not a 2× financing/funding stress**: signed funding can be a short-side credit, and an adverse independent funding-event model remains a scientific requirement.

## Status and unblock conditions

| Work item | Engineering status | Scientific/independent evidence gate |
| --- | --- | --- |
| #31 causal 300s follower | Implemented, tested on frozen fixtures and native 1m storage; four cost/latency/stop model scenarios; no orders | Source continuity, full book/equity, actual first receipt and **independently settled follower/control 300s net R with costs/funding** absent |
| #32 calibrated A/B/C/X | Existing as-of shrinkage and C/X diagnostic remain safe; no positive grade | Independent mature training/OOS labels and calibration/uncertainty needed before any A/B confidence or R reference |
| #33 walk-forward falsification | Five-policy matched evaluator + folds/day-block uncertainty + strict v2 control binding | No legitimate newly activated future PIT sample or verified matched outcomes to run a scientific forward test or cost/latency stress |

**IMPLEMENTED:** research-only diagnostics. **ENGINEERING VERIFIED:** only when the current commit's full tests/CI are green. **HISTORICAL ECONOMICS:** exploratory and inconclusive/negative. **PROSPECTIVE VALIDATED:** no. **SCIENTIFICALLY QUALIFIED:** no. **DEPLOYED:** pre-existing optional Telegram C/X-only release only, unchanged. **LIVE AUTHORIZED:** no. **C/X = 0R, A/B disabled**. Do not auto-close #31–#33 merely because engineering tests pass.
