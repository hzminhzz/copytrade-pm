# Trader Intelligence milestone checkpoint — 2026-11-02

## Repository authority and versions

- Primary scope: [Issue #27](https://github.com/hzminhzz/copytrade-pm/issues/27), Issues #28–#35. Draft primary PR #36 on `feat/trader-intelligence-foundation-20261102`. The initial foundation commit was `7a181f9`; check PR HEAD for later commits.
- Cross-repository source: `hyperliquid-expert-ensemble` feature branch `feat/expert-wallet-execution-correctness-prospective-research`, observed HEAD `e5af40b`. Its `copy_board.py`, `copy_digest.py` and journal are **not** in ensemble `main` `ef8d7c1`. Grade overlay changes must target the feature branch in a separate, isolated worktree/PR.
- Existing systemd services and hourly Telegram timer were inspected read-only. No production unit, .env, broker connector or account policy was modified.
- This documentation describes engineering on an unmerged branch, **not a production release**.

## Engineering implemented (research-only)

| Area | Code | Contract |
| --- | --- | --- |
| TI-01 | `trader_intelligence.py` | Pure `evaluate(snapshot, decision_at)`; schema v1, hash-stable as-of identity, exact instrument, C/X default, evidence/unknowns, research R tiers and no-order authority |
| TI-02 | `trader_intelligence_intake.py` | Arbitrary 1/36/94+ rosters, read-only SQLite journal, first-known versus vendor clocks, coalesced changes, invalidation/barrier, explicit HyperX/public fill schemas |
| TI-03 | `trader_intelligence_book.py` | Explicit coherent all-DEX source book/equity/chain/spot/parent-cluster evidence; reduce/exit/reversal semantics, basket/carry/unknown veto |
| TI-04 | `trader_intelligence_research.py` | 300s follower minimum, native 1m next-open proxy, prior completed-minute capacity, taker/spread/slippage/funding assumptions, fixed-horizon versus conservative OHLC stop, missing-mark refusal |
| TI-05 | `trader_intelligence.py` and `trader_intelligence_research.py` | Sparse-history shrinkage by episode group; diagnostic C/X `ResearchRank` with parent-first dependence collapse, strict matured outcome clocks, policy/horizon comparability, failed-episode and conflicting-ID guards, explicit `UNATTESTED_DIAGNOSTIC_ONLY` provenance; **no positive calibrated A/B assignment** without independently attested outcomes |
| TI-06 | `trader_intelligence_research.py` | Exploratory same-cut five-policy comparisons, optional matched market controls with exact policy SHA, null missing controls; always `NOT_QUALIFIED` |
| TI-07 | `ensemble/trader_grade_adapter.py` plus optional `copy_digest.py` kwargs | Strict model/policy/source/time/namespace/grade validation, bounded escaped research appendix, descriptive-only by default, no CLI activation or new sends |
| TI-08 | Tests and this checkpoint | Independent integration test, source/restart/adversarial fixtures; full signoff and release still pending |

## Read-only real dataset smoke

The stored `/home/quant/dev/copytrade-pm/data/wallet_fills_90d` contains 19 JSON wallet files at inspection. A deterministic, read-only **sample** of 250 BTC public-API fill records for an existing roster alias was converted by explicit `HYPERLIQUID_PUBLIC` schema: 12 OPEN, 117 ADD, 110 REDUCE and 11 EXIT. Original local source-file SHA256: `bb3e2596c2369238c9689058a737bc07c24f632825285a5138f6379f9bc0ff39`. The sample is historical vendor events; **0 first-local-receipt clocks or account-level equity attestations are inferred**. Do not extrapolate this sample to the complete 94-wallet inventory.

### Existing real as-known journal (read-only, no trade)

At inspection the live `copy-opportunities-live.db` contained **74,148** durable first decisions, **138,417** updates and **66** coverage barriers. The intake was corrected to query a bounded **4-hour** decision window under a single read-only SQLite WAL transaction; it refuses truncation rather than blindly taking the earliest 50,000 records. A live read-only interface smoke tested five wallet IDs selected solely for schema validation and returned **28 as-of event rows and six research assessments**. All six were **C/X with no order authority** and all events' missing whole-book equity remained NULL. These five IDs are a convenience sample, **not** an independently known-at/predeclared roster. This is not scientific qualification.

## Verification at local working state (before final commit)

- Primary core: `uv run --group dev python -m pytest -q tests` → **529 passed** (after final as-of bounded journal and candidate binding regressions).
- Primary native market: `uv run --extra market --group dev python -m pytest -q tests` → **529 passed**.
- Primary lint and Ruff formatting → PASS; `uv build` wheel and sdist → PASS.
- Ensemble full tests `uv run --group dev python -m pytest -q tests` → **276 passed**; Ruff lint and build → PASS. Ensemble-wide `ruff format --check src tests` fails on 73 **pre-existing** files; changed grade adapter/test files are formatted, and an unrelated project-wide format rewrite was deliberately avoided.
- Real cross-repository in-process contract test, from PM `assessment_document_for_board` to ensemble `inspect_grade_artifact`: **PASS**, no risk/order authority; source board SHA `f0dd4d11a99dec70ec68ca931a7f66fa38a5a7eff20f0b179aef4620a9cbca99` (synthetic board fixture).
- Tests are engineering evidence. Recheck GitHub CI for each pushed commit before any merge.

## Research ranker integrity — continuation after handoff

`rank_research_opportunities(...)` is a read-only **watch-order**, not a calibrated trader-skill estimate. The retained as-of source hash must match the evaluator's decision cut. Parent-linked subaccounts collapse before explicit cluster labels; unverified independence contributes no independent score. Episode identity conflicts, incomparable policies/horizons and matured failed follower episodes fail closed. A rank can be derived from hypothetical labels, including retrospective proxies, so **every** output carries `evidence_class=UNATTESTED_DIAGNOSTIC_ONLY` and `UNATTESTED_REPLAY_NOT_FOLLOWER_PROOF`; no A/B or account risk can be assigned. The episode-history digest now covers the full label payload rather than only IDs. Outcome clocks are checked before the shrinkage step and a future first-local receipt cannot improve an earlier rank.

2026-11-03 local acceptance for this incremental ranker: both core and native-market suites **538 passed** each, Ruff lint/format and wheel/sdist build passed. This is engineering verification only; no independent signed economic evidence or OOS qualification was produced.

## 2026-11-03 signed economic evidence continuation

The optional `trader_intelligence_qualification.py` read-only audit and `trader_intelligence_qualification_cli.py` now verify the **existing** prospective ledger's full SHA chain and external Ed25519 signatures before counting eligible whole-account v2 observations. They require an exact selection-plan SHA and future evaluation window, preserve as-of sealing, reject older v1/incorrect-plan outcomes and missing matched 5/15/60m horizons, and report per-source-event conservative follower-minus-control net R only from fully matched groups. No new mutable ledger, signer or order gateway was added. **The audit deliberately never issues A/B or scientific qualification:** a signed assertion does not establish economic truth, pre-registration, independent follower fills or statistical OOS skill. The future [study proposal](TRADER-INTELLIGENCE-PROSPECTIVE-STUDY-20261103.md) is not an active registered holdout.

In the inspected private PM-01 forward reports, no signed whole-account outcome ledger manifest was located. A separate [2026-11-03 P1 real-journal audit](TRADER-INTELLIGENCE-P1-EXPLORATORY-AUDIT-20261103.md), using the existing ensemble validator rather than a new simulator, found 712 P1 first decisions, mixed 5m/15m/1h hypothetical net results, largely unverified source coverage, and no positive Holm-corrected 1h alpha evidence. Its SHA-pinned 217-wallet report is private, not a newly protected holdout. The existing systemd `copytrade-source-abc.service` and `copytrade-tracker.service` were observed **active**, but active observation services are not independent matched economic producers. No service was changed. Historical/private accounts and evidence remain off Git.

## Current P1 source-acquisition recovery

A [read-only native P1 capture](TRADER-INTELLIGENCE-P1-NATIVE-SOURCE-20261103.md) now documents the official HTTP/WS 422 endpoint distinction and a successful 40-request, 3-parent, 11-DEX-per-account source snapshot with immutable private SHA receipts. It is a **non-atomic** present-state snapshot and cannot establish continuous prospective matched account NAV, nor follower profitability. No service or financial account was modified. All current grades remain C/X at 0R.

## Scientific and release limitations

1. **No qualified A/B edge.** A user-provided follower estimate or a syntactically plausible calibration is insufficient to confer A/B. The in-repo default remains C/X at 0R; positive-grading needs independent receipt/outcome attestation and frozen OOS calibration.
2. **Retrospective roster selection.** The 90-day fill inventory was selected with hindsight; it is not an unbiased historical holdout. Need first-known roster registration/coverage and an independent later period. Historical fills are not prospective receipts.
3. **Follower execution is hypothetical.** Native 1m OHLCV fixed-horizon, conservative intrabar stop and prior-minute notional capacity are research proxies. No observed bid/ask quote, queue, matched Propr order fills or executable account-specific stop. Funding is a configured constant proxy, not a verified historical funding event stream.
4. **No signed matched outcomes attached.** Existing PM prospective ledger separately verifies independent Ed25519 receipts/mature follower and market-control records. Integrate that verified maturity gate before actual A/B research or prospective economic claims. Never equate crypto signatures alone with independent economic truth.
5. **No complete walk-forward campaign.** The benchmark scaffold shows method parity and nullable controls only, not predeclared PIT roster, purged group splits, calendar return/drawdown, calibrated interval, rank stability or inference superiority. Negative/insufficient results are valid.
6. **No account or Telegram activation.** The ensemble consumer defaults to original descriptive-only message, and optional experimental grade rendering is not CLI or service activated. Any production display requires separately reviewed release/rollback and tested operator health.
7. **Issues #28–#35 remain open until each exact GitHub acceptance is satisfied.** Do not close the milestone or PR based only on fixture tests.

## Engineering follow-through

- Review PR diffs and CI. Verify core/market/PIT/frozen report parity; source/Telegram integrity and crash/restart after integration.
- Establish standalone, provenance-safe prospective grade production with a pinned PIT roster and signed mature follower/control metrics, not a speculative class result.
- Freeze prospective evaluation windows and model family budgets; run actual matched independent OOS benchmark with null/negative results.
- Only then review positive calibration and consider distinct Telegram research-display release; no trading is authorized.
