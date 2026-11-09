# Pydantic-native implicit-state acceptance matrix — ALL 28 families

**Date:** 2026-11-09
**Status:** Q18/Q37 **APPROVED ENGINEERING ACCEPTANCE DESIGN** for all 28 families; **NOT TESTED, NOT IMPLEMENTED, NOT AUTHORIZED FOR DEPLOYMENT**. This is a test specification, not evidence of PASS.
**Base:** `copytrade-pm` `175d54d` as inspected; previously catalogued audit findings in [the state ledger](PYDANTIC-NATIVE-STATE-GRILL-20261109.md). Revalidate on implementation branch, deployed pins and real source data rather than assuming static names remain current.
**Binding semantics:** [Q3–Q24 ADRs](decisions/2026-11-09-pydantic-native-validation-runtime.md), [Q25–Q29 sequencing](decisions/2026-11-09-pydantic-native-sequencing-ecosystem.md), [Q30–Q34 domain interfaces](decisions/2026-11-09-pydantic-native-domain-interfaces.md), [Q35–Q39 failure and specification readiness](decisions/2026-11-09-pydantic-native-failure-and-spec-readiness.md), [V4 official-source T+300](decisions/2026-11-08-position-first-t300.md). Companion [13-case combined fault matrix](PYDANTIC-NATIVE-COMBINED-FAULT-MATRIX-20261109.md) covers interactions across all 28 families; neither matrix has been run.
**Status for EVERY row:** `OPEN_ENGINEERING`. Design/acceptance obligations have been approved; no tests or reachability proofs have yet been executed. Codes are audit IDs, not issue numbers, and proposed resolutions are not completed dispositions.

## Cross-family invariant oracles

- **I1 — Evidence:** Source raw bytes, SHA/signatures, historic versioned hash algorithms and stored original clocks remain untouched by new Pydantic model serialization.
- **I2 — Causality:** Only a verified, continuous, official, complete, selected-account economic state change **after baseline** can create a new T0; T+300 is exact from first-known T0; mid-delay updates do not reset it.
- **I3 — Scope:** Selected account and DEX identity remain exact, scope changes fence only affected dependent intents, gaps cannot fabricate flat or reset existing follower holdings.
- **I4 — Finance:** HALT is monotonic until authorized reset; pod/global risk, fixed k, unknown orders, existing inventory, daily/trailing floors and protective reductions remain enforced.
- **I5 — Delivery:** Persist local events atomically; publish complete signed files before cursor advance; consumer replay idempotent; never assert global exactly-once without a transaction authority.
- **I6 — Authority:** Research source `NO_TRADE`; simulated paper is not Guardian permission; unsigned/unsupported schemas cannot create order permits.
- **I7 — Science:** Correct engineering and valid input do not qualify leader edge or executable follower PnL; retrospective reconstruction is labeled retrospective.
- **I8 — Recovery:** Failed or restarted processes cannot create fresh first-known signals or silently clear leases, HALT, unresolved effects or published evidence.

## Risk categories and stages

`H` high-consequence source/financial, `D` durable/provenance, `R` retrospective or governance, `O` operator-only, `L` legacy retirement. These govern **test depth**, not whether a bug already exists.

`S1` canonical official state and durable observations; `S2` financial/PaperRun lifecycle; `S3` research/metadata durability; `S4` operator diagnostics; `S5` legacy retirement/compatibility. Preliminary build stages, not approved deployment order.

## 28/28 concrete behavioral acceptance cases

| ID | Stage / class | Minimum adversarial test input or sequence | Required result / evidence |
|---|---|---|---|
| **01** | S1 / H | Two complete same-scope official books, quantity `"20"` then `"20.0"`; second case genuine `20→21`; third NaN/duplicate market | Numeric formatting only: **UNCHANGED** and no new intent; genuine delta: one transition and original T0; invalid book rejected with original raw SHA still auditable |
| **02** | S2 / H | HALT after equity breach; then stale quote, unknown funding, failed execution and process restart | HALT and reasons remain latched, no new risk; a separately valid reduction is not mistaken for risk admission; reset requires an explicit authenticated event |
| **03** | S2 / H | Open + routed exposure → verified terminal exit → quotes for old instrument expire | Actual flat/reconciled book no longer requires stale routed target quotes; still-open or uncertain inventory **does** retain required market/risk checks |
| **04** | S1 / D | Interrupt signed spool during staged write, rename, directory fsync and cursor update; restart each crash point | No consumer sees partial final packet; no cursor may pass unavailable durable evidence; staged leftovers recover safely; duplicates are signature-checked and idempotent |
| **05** | S2 / H | Broker cancel ACK races with late partial fill; new account snapshot older than cancel then independently later | Cancel ACK alone does not release reservation; position/account snapshot after both source and local event clocks resolves only proven remainder |
| **06** | S1 / H | Selected child/account DEX scope changes while another selected account remains unchanged and paper follower has holdings | Changed scope begins new generation and fences all dependent new-risk intents; unrelated account remains eligible if its proof is valid; held follower inventory persists |
| **07** | S1 / H | WS disconnected → reconnect ACK → baseline → duplicate frame → real post-baseline transition | No entry for reconnect or duplicate; only continuous later change creates new T0; epoch and subscription state agree with committed journal |
| **08** | S5 / L | Enumerate CCXT CLI, installed units, all callers and archival replay; if still active, inject reconnect + stale quote | Retire only with **no required consumer** and preserved historical interface; otherwise quarantine bad ticks/epochs and block fallback to unofficial V4 market identity |
| **09** | S1 / H | Native public-trade feed loses cursor, catches up retrospectively and replays duplicate | Recorded gaps and catch-up are observable but never promote historical trades to verified prospective selected-position transitions |
| **10** | S1 / D | Vike selected-fill feed gap at cursor N, later N+1, duplicate and REST recovery | Historic gap flag remains until explicitly proven recovery semantics; forward qualification never resumes solely because cursor advanced; recovered fills remain retrospective |
| **11** | S1 / D | Cancel writer task between queue admission, journal commit and delivery acknowledgment; shutdown/restart | Single serialized write authority; complete committed events replay once semantically; uncommitted events not claimed; tasks/leases drain or recover deterministically |
| **12** | S3 / D | UTC bucket late trade, duplicate, correction after provisional seal and after final seal | No silent alteration of sealed historic evidence; explicit correction/version where supported or quarantine; duplicate cannot alter aggregate |
| **13** | S4 / O | Grafana container running but projection stale/publisher stopped; fixture data looks fresh | Health report distinguishes container liveness, authentic data freshness and publisher progress; synthetic fixture cannot represent authentic operational readiness |
| **14** | S3 / D | Registry release crash before/after file staging, pointer update and metadata commit; concurrent read | Reader never admits mixed inventory/policy generations; recover prior known release or fail closed; no silent reseal/reversion of signed selection |
| **15** | S2 / H | Protected standby HALT → midnight/restart/reconnect; alternative process epoch appears | Durable HALT survives; restarting public source/watchdog never grants Guardian finance authority; standby is not active broker |
| **16** | S4 / O | Incident active, delivery fails, local ACK recorded, condition persists, delivery recovers | Incident activity, acknowledgement and delivery result remain separate; ACK does not clear active alert or Guardian HALT |
| **17** | S3 / R | Signed receipt present; audit missing; outcome immature; forged signer; finally independently matured outcome | Each predicate remains independently gated; no synthetic/forged/immature outcome receives scientific qualification |
| **18** | S3 / D | Native metadata file hard-link/staging crash before SQL commit, after commit and during recovery | Metadata and artifact hashes cannot diverge into a trusted release; orphan files identifiable; read-only fallback fails closed pending recovery |
| **19** | S5 / H/L | Legacy Combo2 marked FROZEN while direct new-risk admission attempted; inspect installed callers | If retained, admission denies new risk regardless of display flags and risk exits remain separately possible; if retired, prove no relevant consumers |
| **20** | S5 / H/L | Legacy ForwardBatch marked DUE, then source GAP, reconnect baseline, expired reason flag | If retained, GAP revokes old DUE and cannot recreate T0; no stale reason resurrection; if retired, prove no active consumers |
| **21** | S3 / R | Historical fill-only book with incomplete account scope; attempt to use it as prospective complete SourceBook | Research tape remains retrospective; cannot supply genuine first-known selected-account position proof or trading authorization |
| **22** | S3 / R | Flat-to-flat episode reconstructed from partial fills with missing startPosition/gap | Episode marked estimated/uncertain, coverage caveats retained; no claim of complete PIT source position or follower entry evidence |
| **23** | S3 / R | Challenge `ever_funded=True` with `currently_active=False` and payout history | Valid history retained without claiming presently funded/live state; stage math and payout result remain distinct |
| **24** | S3 / D | Two acquisition generations, shuffled/missing paired raw pages, replay from prior generation | Never pair content across generations or accept mismatched digest; stable recovery/rejection, no silent duplicate fresh receipt |
| **25** | S3 / D | Cached market/research artifact modified, partially written or wrong generation; rerun | Digest/schema mismatch fails verification and never silently qualifies science; fresh cache generation can be built without rewriting old evidence |
| **26** | S1 / D | One source event consumed by two downstream paper portfolio readers; one crashes after commit before cursor ACK | Each consumer tracks independent durable progress; restart replays safely without duplicating source or modeled financial effects; no event silently skipped |
| **27** | S5 / L | Enumerate PM-02 legacy decision/fallback CLI and installed consumers; if still active force missing qualification | Retire only after proving non-reachability; otherwise deterministic `NO_TRADE` when qualification/evidence absent; archived PM-01/02 outputs remain interpretable |
| **28** | S4 / O | CDP connection loses target, browser session closes, reconnect uses new target/viewport | No stale session/target reused; errors fail predictably and browser acceptance does not become financial evidence |

## Cross-repository acceptance case (not a 29th family)

Pin a producer release that adds an unrecognized **financial** field/version to a signed source contract. Guardian must reject protected admission unless compatible and trust-root pinned. Separately prove that an explicitly optional *nonfinancial diagnostic* field cannot affect order, identity, timing or risk semantics. Verify companion commit pins and rollback. Do not equate connector/Guardian local checkout revisions with currently deployed processes.

## Required evidence receipt per row at execution time

Every closure record must contain: audit ID; exact pre/post commit; actual affected consumer/OS scope; final disposition; reproducible test invocation and test identifiers; positive and **negative** input; observed result; artifact SHA; regression risk and rollback note. For `RETIRED-NOT-REACHABLE`, include call graph, CLI and release/service pin inspection. For `DOCUMENTED-INTENTIONAL`, include the valid state example and actual test. For `FIXED`, show failure reproduction before change or a controlled external evidence block, plus post-change evidence. A one-line assertion or green CI badge does not meet the contract.

## Research, permission and runtime caveats

- Recorded official-shaped fixtures establish engineering semantics, not independent prospective provider completeness.
- Actual forward paper must retain genuine first-known, price provenance and modeled fees/slippage; engineering success does not demonstrate positive net follower PnL.
- No row permits production live trading or modifying root-owned Guardian. Deployment is separately authorized.
- Tests, source hashes, actual service state and installed releases have **not** been executed/verified for this design document. All 28 remain **OPEN**.
