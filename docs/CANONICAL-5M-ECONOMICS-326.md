# Matched T0+300 and checkpoint economics (#326)

## Boundary

`python -m copytrade_pm.pm_checkpoint_economics --spec /private/study.json --output /private/report.json` runs only from a clean, exactly pinned research checkout. `--criterion-public-key /private/reviewer.pub` optionally verifies the separate economic review authority. Output is immutable, hash-bound, non-trading research evidence. The command never starts a source, creates a financial run, places an order, changes k, or promotes a release.

The legacy reader reuses `Ledger.read_path` and `ShadowRun.replay_record`. The checkpoint reader uses a read-only SQLite snapshot and the existing `PaperJournal._verify` replay, including source/mandate original-proof checks. The small owner refactors preserve existing replay behavior. There is no new execution simulator or financial journal.

## Input contract

The JSON schema identifier is `cwsa_matched_economics_spec_v1`:

- `research_revision`: exact 40-character running Git revision.
- `window`: inclusive valuation endpoints `start_ms`, `end_ms`, and positive `step_ms`; the span must divide exactly.
- `source_roster`: unique `source_id`, native `account_sha`, sorted complete `dexes` (for example `default`). No source substitutions.
- `portfolios`: unique `portfolio_id`, exact `frozen_k` by source, and the two policy ledger pins below. A missing leg is explicitly `null` and produces no P&L.
- `legacy`: `path` to the existing ShadowRun directory, `head_sha`, `manifest_sha`, `source_journal` path, and `source_prefixes` mapping each parent to `{sequence, head_sha}`. Every retained prefix receipt is verified by the existing receipt owner. The recorded source event must link to its exact receipt, book, position, wallet identity, DEX census and causal clock. Missing linkage excludes the comparison. Original official stream proof is assessed separately; self-hashed historic receipts never become authenticated native originals.
- `checkpoint`: `path` to the existing paper SQLite journal, `run_id`, `head_sha`, `manifest_sha`.
- `reference_data`: exact `path`, file `sha256`, and `role`. `FOLLOWER_L2_QUOTES` files contain `{schema: cwsa_economics_quotes_v1, quotes: [...]}` using the existing verified L2 quote schema. Quote sides, source and first-known clocks, native market catalogue and quote hashes remain explicit. Other roles retain their original hashes; this does not authenticate their scientific claims.
- `reference_quote_max_age_ms`: mandatory study parameter; no production freshness threshold is inferred.
- `uncertainty`: mandatory `block_intervals`, `replicates`, integer `seed`, and decimal-string `confidence`.
- `extra_cost_bps`: explicit nonnegative decimal strings. These perturb costs on the recorded execution path; they do not simulate new latency, liquidity, fill, risk or sizing decisions.
- `criterion`: `null`, or the separately approved signature described below.

`tests/test_checkpoint_economics.py::matched_pair` is an executable synthetic example through both real policy owners. It is not prospective or economic qualification.

## Timing, execution and statistics

Each ledger retains its own policy. Old first-known T0+300 events are never rebased to exchange fill times or UTC checkpoint times. New baseline/unchanged/gap/recovery/missed/one-shot events retain their original semantics. Each engine supplies its actual replayed fills, executable quote sides, native lot/minimum rules, costs, source marks, targets, delayed exits and pod effects. Their original decision events and execution evidence appear in the report; nothing is refilled from common marks.

The matched curve uses the same causally known independent L2 midpoint for valuation only. Both net holdings and offsetting virtual pod liabilities require quotes. Missing quotes, incomplete ledger windows, mismatched k/cohorts, unpinned histories and rulebook stage changes cannot be repaired with later observations. Intervals need both endpoints in both policies. Gaps are never bridged; full-window P&L is null if any interval is missing. Different rulebooks are reported as a confounding review blocker.

Outputs include matched modeled net P&L and difference, maximum contiguous matched drawdown, observed worst and lower-five-percent interval tails, actual recorded opportunity counts and breaches, modeled execution notional, cumulative ledger costs, per-window modeled fill counts, raw evidence hashes and policy/ledger pins. Opportunity counts explicitly cover the complete pinned ledger; execution counts and cost perturbations use the requested window. Choose bounded ledger snapshots when exact window-specific opportunity attribution is required.

Paired moving-block bootstrap intervals preserve contiguous blocks and use the declared seed. Insufficient contiguous blocks remain unavailable. Resampling counts are never described as independent observations. These intervals condition on the recorded paths; they do not bound regime change, mark error, execution model error or live profitability. Latency, source gaps and changed risk policies require separately generated original policy ledgers; cost arithmetic does not stand in for them.

## Separate economic approval

A criterion uses signature domain `cwsa-economics-reviewer-v1` and payload schema `cwsa_economic_criterion_v1`. Required fields are `study_design_sha`, `declared_ms`, `derivation_evidence_sha`, `minimum_matched_intervals`, `minimum_delta_pnl`, `maximum_checkpoint_drawdown`, and `require_positive_lower_bound`. Numeric rules have no defaults. Its derivation must be retained as a hash-verified `ECONOMIC_CRITERION_DERIVATION` reference.

`study_design_sha(spec)` binds the frozen roster/k, prospective window, exact software revision, uncertainty, quote-age and sensitivity choices. It excludes future ledger heads and future observations. The signature's declared time must precede the window; a signature is an approval record, not an independent timestamp authority. The original signed payload and reviewer key hash are retained. Passing its arithmetic is labeled `PASS_MODELED_NUMERIC_CRITERION_ONLY`.

All reports remain `NOT_QUALIFIED`, `scientifically_qualified=false`, `trading_authorized=false`. Independent prospective review and actual native executable fill evidence are separate obligations. Historical synthetic mode labels are preserved as recorded; an observed paper run is not upgraded merely because the reader recognizes its timing policy.

## Verification and external blockers

Red tests exposed missing legacy source scope, legacy fill-schema differences, future quote exclusion and the absent signed criterion contract. The current targeted run passes 140 tests across economics and affected PM03/PM04/journal/legacy observed-paper owners; 13 cover the economics boundary directly. They include byte-preserving read-only replay, account tampering, source identity/k/pin mismatch, missing evidence, gapped matching and separately signed criteria.

The live new checkpoint campaign has not been activated and has no separately approved mandates or numeric sampling policy. There is therefore no prospective matched checkpoint ledger to scientifically compare. Source capacity tails/shared-IP headroom, separately approved economic thresholds and native broker execution qualification remain external evidence blockers. No missing result is reported as zero P&L or alpha.
