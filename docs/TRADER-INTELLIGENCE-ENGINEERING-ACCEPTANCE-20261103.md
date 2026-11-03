# Trader Intelligence engineering acceptance and scientific disposition — 2026-11-03 UTC

## Exact source and review boundaries

- `copytrade-pm` initial merged Trader Intelligence foundation **da9afcdf8285a1835b193ba5151d7efb98513e2d** (PR36).
- Matched evidence binding **5500bb3**, PIT descriptive features and matched walk-forward diagnostics **ec2003c** (PR40); reviewed merge **5456690fcacb48aea764684de57045fc9723d05f**.
- Separate `hyperliquid-expert-ensemble` Telegram research-display PR9 merged into its **feature branch**, not its production main: **e033509c943b4cb21c1d5804f5bc2105e5cec92d**. Existing digest-only pinned release: `ti-digest-ens-1c591080f5e9-pm-d72f9545f587`.
- The original main and feature working checkouts, real source journals, source snapshots, signed evidence, production ensemble/tracker services and accounts were **not modified by this verification**.

## Engineering evidence

- PM whole suite on isolated PR40 head `ec2003c`: core **564 passed**, native `--extra market` **564 passed**; Ruff lint PASS, Ruff formatting PASS (142 checked files), wheel+sdist build PASS.
- PM dependency and risk/restart focused regression selection: **95 passed** in native configuration. Included the real installed frozen 36-wallet PM02 SHA-parity fixture; `test_real_36_wallet_pm02_parity_if_owner_private_fixture_available` passed (no skip in separately rerun 33-test check). Existing frozen PM01 input and PM02 output not rewritten.
- CI PR40 run **41577349952**, GitHub verify(core), verify(market) and GitGuardian all PASS; PR40 merged **5456690**.
- Ensemble separate isolated worktree at `e033509c`: **283 tests passed**; focused adapter/digest **14 passed**, Ruff lint on `src tests` PASS, Ruff format on the four research-grade-adapter/producer/smoke files PASS, wheel+sdist build PASS. A full-tree Ruff format check remains non-passing on unrelated, pre-existing unformatted ensemble files, including `copy_digest.py`; it was **not** mass-reformatted. Existing ensemble GitHub CI **41572247290** PASS.
- No-network actual read-only release smoke on the already pinned digest: `PASS_NO_TELEGRAM_NETWORK`, **23 board coins**, **1 grade-C candidate**, `source_fingerprint_match=true`, `financial_orders=false`, **1,187 characters**, research-only.
- Actual post-release systemd digest period **2026-11-03T04:00Z**: `DELIVERED_DESCRIPTIVE_ONLY`, `grade_status=RESEARCH_CX_OVERLAY`, `coins_in_board=22`, `forward_ack_recorded=true`, source lag 0, `predictive_qualified=false`, exit 0.
- Live `copytrade-ensemble.service` active PID **279989**, `copytrade-tracker.service` active PID **279976**, both NRestarts 0 at inspection; `copytrade-flow-digest.timer` active/enabled; the digest one-shot service is normally inactive between runs (last exit 0). **No new unit activation, order, order mutation or Telegram send was triggered by the new offline smoke.**

## Issue-by-issue acceptance

| Issue | Engineering result | Scientific/remaining gate |
| --- | --- | --- |
| #29 PIT intake | COMPLETE; bounded existing journal, explicit old versus first-known clocks, sizes 1/36/94, source-gap and duplicate conflicts, frozen PM01/PM02 parity | No inference of true first-known from historical source |
| #30 trader features | COMPLETE; as-of parent/dependence, opening/reduction/reversal, lower-bound hold age, conditional exposure, unclassified carry/hedges and as-of hash | Native account books not independently reconciled for real P1 |
| #31 300s follower outcomes | Offline next-open replay, conservative costs/stops/capacity and missingness tests PASS | Real independently observed executable 300s matched follower/control and fees/funding not attested; KEEP OPEN |
| #32 ranker/grade | Historical shrinkage and C/X diagnostics PASS; parent collapse and no fabricated A/B | Calibrated skill/OOS for A/B unavailable; KEEP OPEN |
| #33 falsification | Five matched policies and PIT fold-embargo/day-block bootstrap diagnostics implemented and tested, same candidate/cost policy guards. Historical P1 uncertainty report preserved | No genuine independent future sample or independently reconciled economics; 2x fee/600s delay scientific tests not yet executable; KEEP OPEN |
| #34 digest | Optional read-only C/X real Telegram delivery observed, descriptive fallback verified; closed separately | A/B disabled; production execution unchanged |
| #35 end-to-end engineering | Actual journal-to-grade-to-render no-network smoke, separate genuine C/X Telegram acknowledgment, full both-repo engineering and core risk/fault tests, rollback steps verified against documented procedure | Only engineering acceptance is eligible; NO PROSPECTIVE QUALIFICATION |

## Scientific evidence and prospective protocol

The private historical P1 exploratory 217-wallet/11,146-paired-1h journal study is **already inspected**, with P1 adjusted p=1 and all confidence intervals crossing zero. Report digest `3c579ba06d16857f39b840d3dccdab4df7bb9bf88112f195fc3087d358c54e27`. The native 11-DEX source snapshot digest `962e36822f9adba63995cee50ca6910b935f6ba7058d679a197369cca2d4d19b` verifies raw read-only retrieval but NOT atomic complete account, equity, independent broker fills or accounting.

The [versioned future design](specs/trader-intelligence/frozen-future-pit-design-20261103-v1.md) locks P1/P14, the five comparison policies, candidate Oct–Nov exclusion, proposed Nov4–Dec4 protected window, 300s plus 600s stress, 5/15/60m matched horizons and 10 familywise tests **before the proposed future sample**. This is only `DESIGN_FROZEN_NOT_ACTIVATED`: no verified pre-start independent roster registration, mature signed matched economic producer, fee/capacity attestation, or full wallet book. The previously inspected data are excluded. Do not backdate capture, relabel retrospective data, or claim a live holdout just because a document exists.

**Disposition:**
- IMPLEMENTED — YES for specified read-only engineering components.
- ENGINEERING VERIFIED — YES for the explicit tested snapshots above.
- HISTORICAL VALIDATED (economic skill) — **NO**; exploratory study does not demonstrate alpha.
- PROSPECTIVE VALIDATED — **NO**; independent matured holdout missing.
- DEPLOYED — **YES, optional Telegram C/X digest-only**; **NO research strategy/ranker execution deployment**.
- LIVE AUTHORIZED — **NO**. C/X remains **0R** and no A/B grade may be emitted from these artifacts.

## Rollback and operational boundaries

For any future user-approved change to the *existing digest-only* overlay, consult ensemble `deploy/TRADER-INTELLIGENCE-DIGEST-RELEASE.md` and the pinned release `activation.json`. Its `rollback --apply --release <pinned release>` reverses only the managed `copytrade-flow-digest.service` drop-in and timer reload, never the continuous ensemble/tracker or signed evidence. **Rollback was not invoked** because no fault justified a production change; no claim of actually testing a live rollback is made. The existing period-level dedup and no-network dry-run protect against unintended duplicate Telegram messages. Any new scientific activation requires separately verified first-known and signed matched outcomes, no implicit order permission.
