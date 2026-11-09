# Pydantic-native engineering acceptance — #228

**Accepted code:** `a9c4de264ba6f2b929f169b64393df59ed5d4983` on 2026-11-09. This receipt is engineering evidence prepared before the final integration PR; its merge receipt belongs to [issue #228](https://github.com/hzminhzz/copytrade-pm/issues/228). No service was installed, restarted, cut over or repinned.

**Result:** 28/28 original families have exactly one evidenced disposition, and CF01–CF13 all executed through their existing authority seams. Final clean code passed **1,570 core tests / 34 explicit skips**, **1,781 all-extras tests / zero skips**, **47 separate companion tests**, Ruff, formatting, wheel/sdist build and capability validation. No actual provider, forward financial or scientific unknown is relabeled PASS.

## Baseline, scope and original documents

The authoritative inspected starting code was `175d54dec4fcda88ccf6bea885d172646aa63e4e`, independently verified against the prepared worktree and preflight. It is the before-revision for every family below. The common after-revision is `a9c4de264ba6f2b929f169b64393df59ed5d4983`; the migration history identifies the precise implementation commits. Original source witnesses, raw hashes, first-known clocks and runtime inventories remain in private preflight evidence.

The prepared implementation checkout was reused. No second copytrade implementation worktree was created. All 16 preserved architecture/design documents were compared by SHA-256 with the original dirty design worktree and remain byte-identical. Its uncommitted documents and modified index were left untouched. The original acceptance and combined-fault matrices remain historical design documents with their original NOT RUN wording; this new receipt records the results.

Verification applies to existing observer, source journal/spool, portfolio paper owners, registry, research and operator interfaces. No duplicate financial ledger, event store, global WalletState or protected authority was introduced. Tests use temporary keys and synthetic private journals except the explicitly preserved private replay witnesses. Test fixtures cannot establish new-program forward observations.

## Final integration repairs and failure evidence

CF02 exposed two additional real failures after #227: PaperJournal used permission for new risk as permission for every simulated fill, blocking an otherwise valid HALT reduction, and risk reclassification could overwrite the original halt reason. New `risk_semantics_version=3` resolves these for future events while retaining exact v1/v2 replay.

PaperJournal permits the classified reduction only when the account is already HALTed, is **not contractually breached**, and the current classifier's only reason is `PERSISTENT_HALT`. The existing classifier still clips per-pod reductions and prevents an increase in net exposure; quote, capacity, cost, instrument and unknown-order checks remain. The breached-account negative stays blocked with its actual inventory unresolved. No risk threshold changed.

The final audit reproduced two more reason-overwrite paths (unknown MARK and later HALT): **2 failed / 1 passed** on `dddc0faca26b4daddb5d0d4a2269ecabecc51933`. Existing PM03/04 owners now call one version-aware `Account.latch_halt`. The first restriction survives; event results and risk reasons retain operational diagnostics. Existing authenticated/protected authority was not expanded. Only the existing reset path clears the reason. The resulting focused replay/risk suite passed 35 cases, including original journals and explicit midnight/restart checks.

A strict dependency sync also exposed five optional-import collection errors and nine Polars-dependent chart failures previously hidden by an all-extras development environment. Tests now explicitly declare those optional requirements. Core finance/readiness tests remain active; all-extras plus the real companion source executes every required case with **zero skips**. README commands now explicitly sync each environment, preventing an inexact environment from being called a core-only gate.

## Exact reproducible gates

Run in the prepared candidate checkout at the accepted code SHA:

```bash
git rev-parse HEAD
git status --porcelain
uv sync --frozen --group dev
uv run --no-sync pytest -q tests
uv sync --frozen --all-extras --group dev
PYTHONPATH=/home/quant/.devspace/worktrees/prop-production-f12542b4/src:/home/quant/.devspace/worktrees/prop-production-f12542b4/tests uv run --no-sync pytest -q -rs tests
uv run --no-sync pytest -q -s tests/test_pydantic_baseline.py
uv run --no-sync ruff check .
uv run --no-sync ruff format --check .
uv build --offline
uv run --no-sync copytrade-pm capabilities validate
git diff --check
git status --porcelain
```

| Gate | Final observed result |
| --- | --- |
| Clean committed core | 1,570 passed, 34 skipped, 29.89 s |
| Clean committed all-extras with reviewed companion source/tests | 1,781 passed, zero skipped, 45.10 s |
| Explicit CF selection on preceding integration commit | 28 passed, 1,750 deselected, 2.16 s; the same cases also execute in the final 1,781-test gate |
| Native source/paper benchmark | 3 passed, 0.37 s |
| Ruff / format | Passed; 554 Python files formatted |
| Build | Wheel and source distribution built successfully offline |
| Capabilities | 113 capabilities, 40 CLIs, errors=[] |
| Git state | Clean before and after the committed gates; diff check passed |
| Separate V4 companion against final candidate | 47 passed, 0.80 s |

The 34 core skips explicitly concern absent optional NumPy/Polars/HTTP/WebSocket/CCXT dependencies or required companion source. They are **not waived acceptance**: the final all-extras environment with the real companion source has zero skips. The private opportunity, Combo2 and pre-fix risk-v2 archive tests all ran there; a portable checkout missing those witnesses must not count their skips as acceptance.

The explicit combined-fault selection was:

```bash
PYTHONPATH=/home/quant/.devspace/worktrees/prop-production-f12542b4/src:/home/quant/.devspace/worktrees/prop-production-f12542b4/tests uv run --no-sync pytest -q -rs tests -k 'cf01 or cf02 or cf03 or cf04 or cf05 or cf06 or cf07 or cf08 or cf09 or cf10 or cf11 or cf12 or cf13'
```

In the existing reviewed companion V4 checkout, with the candidate producer and existing connector pin:

```bash
PROP_RESEARCH_ROOT=/home/quant/dev/copytrade-pydantic-0911 PYTHONPATH=/home/quant/.devspace/worktrees/trading-connector-41b116aa uv run --frozen --extra connector --group dev pytest -q tests/test_v4_crosstree_integration.py tests/test_v4_source_spool_crosstree.py tests/test_v4_timing.py tests/test_v4_guardian_shadow.py tests/test_v4_source_receiver.py tests/test_v4_source_handoff.py tests/test_v4_shared_source.py tests/test_v4_market_identity.py tests/test_native_gateway.py tests/test_bybit_gateway.py tests/test_bybit_observer.py
```

The separate [#227 compatibility receipt](PYDANTIC-CROSS-REPOSITORY-COMPATIBILITY-20261109.md) records exact companion revisions, full pinned all-repository verification on Python 3.13/3.14, baseline skips and existing deprecation warning. Candidate contracts reject unknown financial schemas/fields, identity/scope/clock/signature damage; optional NAV diagnostics leave fixed-k unchanged. The existing runtime verifier deliberately rejects the candidate as **unpinned**. No compatibility manifest or protected trust floor changed.

## 28-family disposition matrix

Every row uses the common exact before/after SHAs above. Test paths below are under `tests/` unless explicitly stated. Their SHA-256 artifact bindings follow the matrix. Running the all-extras command executes the named public-interface oracles and broader regressions.

| ID | Final disposition | Change | Existing owner / reachability | Exact evidence | Observed positive and negative behavior | Rollback risk |
| --- | --- | --- | --- | --- | --- | --- |
| 01 | FIXED | #216 | PersistentAccount.observe / pm_source_contracts, official complete selected books | test_pydantic_source.py::test_formatting_change_has_distinct_raw_evidence_but_no_transition; test_unknown_or_ambiguous_critical_semantics_fail_closed | 20/20.0 keeps one economic state; 20→21 creates one transition. NaN, duplicate markets, booleans, unknown critical fields and raw-wire drift reject without rewriting evidence. | R1 |
| 02 | FIXED | #215, #228 | Account, PaperJournal, ShadowRun and existing PM03/04 reducers | test_pydantic_halt.py; test_pydantic_combined_authorities.py::test_cf02_loss_halt_funding_stale_exit_restart_reduction_or_unresolved; test_pydantic_halt_origins.py | Loss/HALT then missing funding, stale quote, unknown mark, repeated HALT, UTC reset and restart retain restriction and first cause. Valid non-breached reduction can fill; contractual breach retains unresolved inventory; new risk and unauthorized reset reject. | R2 |
| 03 | FIXED | #220–#221 | ObservedP1Paper, PM04 paper lifecycle and existing follower exit owner | test_pydantic_opportunity.py::test_verified_flat_exit_releases_obsolete_quote_requirement; test_pydantic_opportunity_replay.py::test_cancel_late_fill_stale_snapshot_cannot_clear_target_or_reservation | Only independently reconciled flat exposure clears obsolete routed targets. Unknown orders, stale snapshots and unpriceable held exposure remain unresolved; no inferred close. | R2 |
| 04 | FIXED | #218, #228 | v4_source_spool.capture_once and real separate SourcePacketReceiver | test_pydantic_publication.py; test_pydantic_combined_protected.py::test_cf04_spool_crash_then_consumer_commit_lost_ack_is_idempotent | Seven real publisher crash cuts retain complete signed final files before cursor advance. Consumer commit/lost ACK and duplicate packets produce one eligibility action; original packet bytes stay exact. | R3 |
| 05 | EXPLICIT-AND-VERIFIED | #221, #228 | pm04_broker through ShadowRun.record; no real broker | test_pydantic_opportunity_replay.py::test_cancel_late_fill_stale_snapshot_cannot_clear_target_or_reservation; test_pydantic_combined_authorities.py::test_cf03_cancel_late_fill_writer_cancellation_restart_duplicate_snapshot | Cancel ACK cannot release unproven remainder. Late partial, stale account snapshot and duplicate delivery retain reservation and HALT without counting modeled cash or fees twice. | R2 |
| 06 | FIXED | #217, #228 | PersistentAccount.reconfigure and separate ObservedP1Paper P14/P16 owners | test_pydantic_continuity.py::test_targeted_scope_generation_does_not_reset_independent_account; test_pydantic_combined_scope.py | A's changed HIP-3 scope fences both dependents, including the offline consumer on recovery. Actual held A inventory remains. Unchanged B retains its epoch and executes a later valid fill with independent sizing/cash. | R1, R2 |
| 07 | FIXED | #217 | PersistentAccount.begin/observe/gap and source journal checkpoint | test_pydantic_continuity.py::test_cf01_malformed_pending_then_reconnect_cannot_resurrect_old_t0; test_same_clock_conflict_is_per_dex_even_if_another_dex_advances | Reconnect ACK and recovery baseline do not recreate T0. Duplicate or cosmetic frames do not enter; malformed economics and regressed/same-clock conflicting native state fence continuity. | R1 |
| 08 | EXPLICIT-AND-VERIFIED | #226 | Retained CCXT quote/trade adapters, market CLI and observed-paper callers | test_pm_forward_ccxt_market.py::test_feed_reconnect_rebaseline_and_no_private_calls; test_pm_forward_ccxt_trades.py; test_pydantic_combined_authorities.py::test_cf06_retrospective_recovery_cannot_repair_official_gap_or_pm02 | Reachability audit found required current callers; no retirement. Reconnect requires baseline, stale/crossed/spoofed ticks reject, initial trade cache is retrospective and cannot repair official-source continuity. | R1 |
| 09 | EXPLICIT-AND-VERIFIED | #217, #228 | Retained public-trade collector and PaperJournal public-wallet tape | test_pm_forward_public_trades.py; test_pydantic_continuity.py::test_optional_public_trade_gap_cannot_repair_or_break_official_continuity; test_pydantic_combined_authorities.py::test_cf12_numeric_equivalence_conflict_late_correction_and_native_regression | Catch-up, duplicate, late correction and public gaps stay observable and retrospective. They cannot replace official selected-position proof or set its first-known clock. | R1, R5 |
| 10 | EXPLICIT-AND-VERIFIED | #228 | pm_vike_selected_fills.open_selected_journal/apply_frame/record_event | test_pm_vike_selected_fills.py::test_gap_remains_latched_and_cannot_be_explained_away; test_retroactive_rest_does_not_manufacture_prospective_known_time; test_pydantic_combined_authorities.py::test_cf06_retrospective_recovery_cannot_repair_official_gap_or_pm02 | Cursor advance and REST recovered fills do not clear the historical gap; duplicate payload drift fails before checkpoint advance. Recovery remains prospective=false. | R1 |
| 11 | FIXED | #218, #228 | SerialWriter.submit and existing owner commit/close paths | test_pydantic_publication.py::test_repeated_submitter_cancellation_drains_admitted_commit; test_cancel_before_admission_has_no_effect; test_pydantic_combined_authorities.py::test_cf03_cancel_late_fill_writer_cancellation_restart_duplicate_snapshot | Cancellation before admission has no effect. Repeated cancellation after admission/commit drains the write before returning cancellation; restart does not duplicate the durable event. | R3 |
| 12 | EXPLICIT-AND-VERIFIED | #223, #228 | PaperJournal.observed_utc_net_delta / persist_observed_utc_bucket | test_pydantic_bucket_cache_recovery.py; test_pm_forward_public_trades.py::test_sqlite_first_known_idempotent_and_utc_net_with_roundtrip | Duplicate cannot alter the persisted aggregate. Late data is excluded from the original interval and a conflicting correction is rejected. The actual owner has an immutable provisional seal, not a scientifically final bucket; no fictitious final-state transition is claimed. | R5 |
| 13 | FIXED | #225 | Existing Grafana production start path and grafana_health.assess | test_pydantic_operator_health.py::test_live_grafana_with_dead_publisher_reports_degraded_without_restart; test_fresh_synthetic_fixture_cannot_pass_authentic_health | A running container with a dead/stale publisher reports DEGRADED without a restart. Fresh synthetic fixtures cannot establish authentic finance health. | R4 |
| 14 | EXPLICIT-AND-VERIFIED | #222, #228 | Existing registry release lock, signed release pointer and verify reader | test_pydantic_registry_release_readers.py; test_pydantic_combined_registry_science.py | Concurrent supported reader blocks during pointer/metadata switch; post-commit restart retains the coherent new generation. No mixed release, silent reseal or metadata rollback is admitted. | R3 |
| 15 | EXPLICIT-AND-VERIFIED | #215, #228 | Protected standby/watchdog public APIs and independent companion Guardian fixtures | test_pm_forward_protected_ops.py::test_actual_sigkill_then_restart_never_auto_resets_halt; test_pydantic_halt_origins.py::test_standby_recovery_across_utc_midnight_keeps_existing_halt_and_no_finance; test_pydantic_combined_protected.py::test_cf13_packet_selection_repin_restart_cannot_clear_independent_guardian_halt | Worker recovery, UTC rollover, alternate process epoch and consumer restart cannot clear the persistent latch. Standby creates no financial journal. Guardian rejects reservation independently of source success. | R2, R4 |
| 16 | FIXED | #225 | Existing notifications process_once/acknowledge/dashboard_status | test_pydantic_operator_health.py::test_cf08_stale_publisher_ack_and_target_disconnect_remain_independent | Failed delivery remains RETRY and incident stays active after local ACK. A recovered publisher or browser state cannot clear financial HALT; account-scoped incident ownership remains. | R4 |
| 17 | EXPLICIT-AND-VERIFIED | #224, #228 | Existing prospective ledger/audit/maturity and strict readiness projection | test_pydantic_scientific_truth.py::test_receipt_audit_signature_maturity_and_economics_remain_independent; test_pydantic_combined_registry_science.py | Missing independent audit, immature outcome and forged signer reject independently. One valid matured outcome still reports NOT_SCIENTIFICALLY_QUALIFIED without an independent predeclared holdout. | R5 |
| 18 | FIXED | #222, #228 | Native cohort artifact publisher and existing registry SQLite metadata | test_pydantic_registry_lifecycle.py; test_pydantic_combined_registry_science.py | File and directory durability precede SQL adoption. Real crashes leave an identifiable immutable orphan or coherent metadata; conflicting/private-mode-invalid archives cannot promote selection. | R3 |
| 19 | FIXED | #226 | Retained copytrade-pm-combo2-paper CLI and historical Combo2 projector | test_pydantic_retained_lifecycles.py::test_stress_frozen_display_blocks_new_risk_after_restart; test_prechange_combo2_archive_replays_without_rewriting | Reachable CLI/archive remain supported. New semantics enforce FROZEN/HALT through reversal and opening legs. Prechange v1 archive remains exact; no installed consumer was removed. | R2 |
| 20 | FIXED | #226 | Retained ForwardBatch public planner; no production caller outside module found in source/scripts/ops audit | test_pydantic_retained_lifecycles.py::test_due_is_revoked_by_gap_even_with_a_numeric_follower_mark; test_recovery_baseline_cannot_revive_old_due_or_invent_new_t0 | GAP revokes DUE and old clock. Recovery/unchanged baseline cannot resurrect the signal; only a later real delta can create another due time. Retained API, not an unsupported retirement claim. | R1, R2 |
| 21 | FIXED | #224 | Historical fill replay/book owner plus strict retrospective provenance view | test_pydantic_scientific_truth.py::test_cf10_partial_episodes_and_past_payout_do_not_mean_current_funded; test_readiness_view_cannot_launder_positive_or_invalid_evidence | Historical fill-only reconstruction explicitly stays retrospective and incomplete where scope is missing. It cannot supply official prospective SourceBook identity, T0 or financial authorization. | R5 |
| 22 | FIXED | #224 | Existing episode reconstruction plus evidence projection | test_pydantic_scientific_truth.py::test_cf10_partial_episodes_and_past_payout_do_not_mean_current_funded | Partial-fill flat-to-flat episodes retain estimated/uncertain coverage. Missing start position does not become complete PIT account proof or executable follower PnL. | R5 |
| 23 | FIXED | #224 | Existing challenge simulation and strict stage/payout/current-active view | test_pydantic_scientific_truth.py::test_cf10_partial_episodes_and_past_payout_do_not_mean_current_funded | Past funded stage/payout remains valid history; currently inactive cannot be displayed as currently funded. No past payout is promoted into current forward evidence. | R5 |
| 24 | FIXED | #223, #228 | Existing E4/HyperX acquisition and generation-bound paired-page readers | test_pydantic_acquisition_generations.py; test_pydantic_bucket_cache_recovery.py | Missing/shuffled/foreign raw pairs, provider SHA conflicts, generation reuse and replaced complete pairs reject. Restart preserves original raw and first-known clocks; legacy v1 is read-only, not resumable generation proof. | R3, R5 |
| 25 | FIXED | #223, #228 | ImmutableCache publish/load through existing cache authority | test_pydantic_research_cache.py; test_pydantic_bucket_cache_recovery.py | Bytes returned are the exact verified bytes. Corrupt partial data, ambiguous manifest and wrong generation cannot qualify research. Rebuild uses a new generation and retains corrupt evidence. | R3, R5 |
| 26 | EXPLICIT-AND-VERIFIED | #219, #228 | Existing source fanout, each PaperJournal transaction and each V4 ShadowRun ledger | test_pydantic_consumer_recovery.py; test_pydantic_combined_scope.py; test_pydantic_combined_protected.py | One consumer's durable commit/lost ACK cannot advance another offline consumer. Each resumes its own cursor/effect once, retains separate finance, and refuses to backdate late first admission. No cross-database exactly-once claim. | R2, R3 |
| 27 | EXPLICIT-AND-VERIFIED | #226, #228 | Retained PM02 rank/fallback CLI and historical PM01/02 readers | test_pydantic_combined_authorities.py::test_cf06_retrospective_recovery_cannot_repair_official_gap_or_pm02; existing PM02 qualification suites in the full gate | Reachability audit retained the historical API. Profitable historical fallback with absent qualification yields zero qualified managers and EMPTY seats, live_trading_authorized=false; it cannot admit current paper. | R5 |
| 28 | FIXED | #225 | Existing obscura CDP Browser and bounded cleanup | test_pydantic_operator_health.py::test_cf08_stale_publisher_ack_and_target_disconnect_remain_independent; tests/test_obscura_cdp.py in the full gate | Destroyed/detached target and timeout invalidate the session; a second command cannot reuse it. Browser evidence remains separate from source, finance and trading authority. | R4 |

Disposition totals: FIXED=18, EXPLICIT-AND-VERIFIED=10. No family is declared retired. The four audited legacy families remain reachable or preserve required historical/public interfaces.

### Rollback risks referenced above

- **R1 — Source semantics:** retain readers for committed source semantics v2 and original raw/receipt hashes. Never turn recovery into a new first-known transition, replace a source identity, clear scope gaps, or normalize stored historic wire bytes.
- **R2 — Financial/paper semantics:** retain readers for risk v1/v2/v3, paper v1/v2 and Combo2 v1/v2 where present. An older binary may not understand new events. Do not truncate, rewrite, clear HALT, release unknown reservations or infer flat to make rollback succeed. Existing protected Guardian remains independently pinned.
- **R3 — Durable publication/metadata:** retain committed signed packets, cursors, SQL history, generation artifacts and identifiable orphans. Roll back only to a coherent verified release, never one side of a pointer/metadata pair. No global transaction across independent portfolio databases is claimed.
- **R4 — Operator diagnostics:** preserve acknowledgement/delivery/activity distinctions and persistent watchdog latches. Incompatible/absent health data becomes UNKNOWN/DEGRADED. A browser restart, heartbeat or container status cannot authorize finance.
- **R5 — Research/history:** preserve original historical files, provisional seals and provenance. Corrupt cache remains unqualified and a rebuild gets a new generation. Retrospective or test evidence cannot become prospective or scientifically qualified through rollback.

## All 13 combined-fault results

All are **PASS for their stated engineering invariant**, with no waiver of CF01/02/03/04/05/13. Parameterized crash and breach variants account for 28 executed cases in the focused CF run.

| Case | Exact test entry point | Observed combined outcome |
| --- | --- | --- |
| CF01 | test_pydantic_continuity.py::test_cf01_malformed_pending_then_reconnect_cannot_resurrect_old_t0 | Malformed economics during a pending delay, followed by reconnect after due, cancels the original intent without inventing T0 or closing held inventory. |
| CF02 | test_pydantic_combined_authorities.py::test_cf02_loss_halt_funding_stale_exit_restart_reduction_or_unresolved | Two loss/HALT cases combine funding uncertainty, stale exit, restart and source reduction. Valid non-breached reduction fills under the same HALT; contractual breach stays unresolved. Broker route rejects. |
| CF03 | test_pydantic_combined_authorities.py::test_cf03_cancel_late_fill_writer_cancellation_restart_duplicate_snapshot | Cancel ACK → late partial → repeated writer cancellation after durable append → restore/duplicate stale snapshot. Remaining reservation is 2; one committed late-fill event and unchanged cash/costs on replay. |
| CF04 | test_pydantic_combined_protected.py::test_cf04_spool_crash_then_consumer_commit_lost_ack_is_idempotent; test_pydantic_publication.py::test_cf04_real_process_crashes_never_publish_partial_or_skip_event | Seven publisher cuts plus a real consumer process exit after commit/before ACK. Exact signed files survive; no early due action, exactly one at T+300, none after another restart. Financial once-only effects are separately exercised by family26's real journal crashes. |
| CF05 | test_pydantic_combined_scope.py::test_cf05_shared_scope_change_offline_portfolio_and_independent_held_finance | Shared A held by two portfolios changes HIP-3 scope with one consumer offline. Both fence A on their own recovery, retain their actual A holdings; unchanged B later fills independently. |
| CF06 | test_pydantic_combined_authorities.py::test_cf06_retrospective_recovery_cannot_repair_official_gap_or_pm02 | Official pending intent enters GAP while CCXT cache, public trades, Vike REST recovery and historical PM02 fallback provide retrospective data. No official rebaseline, first-known replacement or paper entry results. |
| CF07 | test_pydantic_bucket_cache_recovery.py::test_cf07_late_seal_crash_and_corrupt_cache | Two cache-manifest crash positions combine foreign complete acquisition pairs and delayed UTC correction. Generation mismatch rejects, original sealed aggregate stays exact, corrupt cache never becomes valid science. |
| CF08 | test_pydantic_operator_health.py::test_cf08_stale_publisher_ack_and_target_disconnect_remain_independent | Live container/dead publisher, failed notification with local ACK and destroyed CDP target. Health DEGRADED, incident active/RETRY, browser invalidated, original finance observation unchanged. |
| CF09 | test_pydantic_combined_registry_science.py::test_cf09_artifact_crash_release_reader_and_scientific_predicates | Real native artifact process crash precedes SQL; concurrent release switch blocks mixed reader. During the switch, missing audit, immature outcome and forged signer each reject. Valid matured outcome remains scientifically unqualified. |
| CF10 | test_pydantic_scientific_truth.py::test_cf10_partial_episodes_and_past_payout_do_not_mean_current_funded | Partial historical episode and past payout from an inactive challenge retain approximation/history labels; current funded and forward scientific qualification remain false. |
| CF11 | test_pydantic_retained_lifecycles.py::test_cf11_frozen_flat_target_gap_due_and_expired_quote_cannot_open | FROZEN/flat routed target, rejected-source stale DUE and expired follower quote cannot open new risk. Proven flat can clear obsolete routing without fabricating a current mark. |
| CF12 | test_pydantic_combined_authorities.py::test_cf12_numeric_equivalence_conflict_late_correction_and_native_regression | Equivalent 20/20.0 retains one intent; same-clock 21 conflicts, late trade correction and old native frame reject. Official position history remains and paper stays canceled. |
| CF13 | test_pydantic_combined_protected.py::test_cf13_packet_selection_repin_restart_cannot_clear_independent_guardian_halt | Actual signed producer packet meets a proposed changed release and alias rebind, then consumer and finance restart. Pin drift and alias drift reject; original packet replays once, independent Guardian HALT blocks reserve, no FakeBroker dispatch. |

CF09 uses real OS locking, file publication, processes and SQLite owners. Its installed-doctor/source-health dependencies are controlled fixture responses so the test does not operate installed services. This limitation does not replace the independent audit/signature/maturity checks, which execute their actual owners.

The separately pinned V4 consumer opens a SQLite handle before rejecting a changed-release constructor. CF13 retains and closes those **test-owned** handles around the expected failure; no warnings are suppressed and no companion authority code is modified. This is a known cleanup limitation in the external negative-construction path, not a waiver of pin rejection or financial HALT.

## Performance and actual-evidence limits

The same 100-frame synthetic PersistentAccount/PaperJournal benchmark used by #214 measured:

| Metric | Original baseline | Final accepted candidate |
| --- | --- | --- |
| Source journal p50 | 1.383 ms | 1.726 ms |
| Source journal p95 | 1.720 ms | 2.168 ms |
| Frames per second | 732.67 | 575.70 |
| Final process peak RSS | Baseline receipt retained separately | 58,128 KiB |
| Final process CPU for 100 frames | Baseline receipt retained separately | 0.172 s |
| Network source connections | 0 | 0 |
| Order route | NONE | NONE |

Final p95 is approximately 26.0% higher and throughput 21.4% lower than the initial single-run baseline. Both remain within the predeclared investigation thresholds (p95 >5 ms or throughput <250 frames/s). These are measurements on synthetic offline inputs; workload variance is not isolated, so the difference is not attributed solely to Pydantic. The intent retains exact first-known+300 eligibility and the test deliberately attempts at +301; **real scheduler jitter is UNMEASURED**.

The existing Grafana UI was separately exercised in #225 across 15 page/viewport combinations and six acceptance renders, with no overflow. That operator result does not establish authentic protected finance or installation of this candidate.

## Historical replay and privacy

The required private prechange witnesses contain seven opportunity events, four Combo2 events and six risk-v2 events. Replay compares original journal bytes, heads, cursor and state; subsequent valid changes are new versioned events. A historical exact duplicate remains idempotent; an attempted new legacy-version write rejects. The original v1 HALT regression reader is also retained.

Private source witnesses and full serialized financial archives are not published. Public test generators and SHA bindings below are sufficient to inspect the engineering mechanism without disclosing raw private source or runtime inventory. Public-trade alias/privacy tests, restricted-file access tests, fail-closed unknown-schema tests and no-broker-route tests execute in the final full gate.

## Public test artifact SHA-256 bindings

These hashes identify the test artifacts at the accepted code SHA. They are not hashes of private source or financial witnesses.

| Artifact | SHA-256 |
| --- | --- |
| tests/test_pm_forward_ccxt_market.py | `a76c791d28fc77aa3b1bf069c322d7f4ef19c39752fe27b2a28ba06ab18ee669` |
| tests/test_pm_forward_ccxt_trades.py | `e4323b8be95366d18bdcc064d41b4336e6bfb4ce85902dc5b452765266981356` |
| tests/test_pm_forward_heartbeat.py | `cff4c0e813fe0cc00ec75e69fdaf8768a6225de2dd80d27756ba99f3cc3f9180` |
| tests/test_pm_forward_protected_ops.py | `b84cd1ded4eb38698c2ee9e30722ebbea65a289d77cf0f669957511123b2f932` |
| tests/test_pm_forward_public_trades.py | `7eb02519ffc8f8c8cadbfa7e138e36a35595d897c7bd751e316ddd3ceed57bf0` |
| tests/test_pm_vike_selected_fills.py | `24dad3e5190aeb20ffbc7da68b0b798281a759cfae0349cbe8ada323f1a38137` |
| tests/test_pydantic_acquisition_generations.py | `96b43085274d2732bea76836fd545ef0bf2ea9cec701cb25fabd118ea2a4d795` |
| tests/test_pydantic_baseline.py | `ad5c3eceab342a9e645860f0a656dca7a514a032924006a7bcccfee137db903d` |
| tests/test_pydantic_bucket_cache_recovery.py | `c833f689ff1d1a5948d4abf94303f4e971dd7acf10d28b7d4e5d90ed765e93f9` |
| tests/test_pydantic_combined_authorities.py | `dcdd1e8cca2578040f137a7114ec79dc32b39f893280b35c065c0942b437cbf1` |
| tests/test_pydantic_combined_protected.py | `f17a7ef148fa613699c5fd90edc362b7d5f6fafaca1dec88e07d2b45ea835f0a` |
| tests/test_pydantic_combined_registry_science.py | `4a451d7d2f19604b751b80a7f4fffeb0fdd6d71510a865233839caf8e8d23443` |
| tests/test_pydantic_combined_scope.py | `4ff77e6ff27ee7b37a4e8d546c1bd11aff81cf1f7bb9bdba5c949d931b7b61e9` |
| tests/test_pydantic_consumer_recovery.py | `cceca54c54d416eaf9aa5f56ac3a2fe92a14f5968574f724b1da191f0bc862d4` |
| tests/test_pydantic_continuity.py | `b0d4316c49cce16383a9c301a1d9411fdc9121470e073a004f855a7579dcaa36` |
| tests/test_pydantic_crossrepo_contracts.py | `3056b307fd0c3d96c9941f3cb0723d3ffff6d6e068fa74f6c5b954ee67dc2e71` |
| tests/test_pydantic_halt_origins.py | `63e669485361ffd8c8cc798bed6ce8358e2fb6d7f1ec8f62eb095948c159c8df` |
| tests/test_pydantic_halt.py | `6da4621b6c1a9538ab2ec06dc5438fca9d8695efa4c90530cc5b64faec9eed19` |
| tests/test_pydantic_operator_health.py | `814a85d6d2b6353e5d1b84150590ebc22b3fd35c9b5a9fddbec5bae12bd95dae` |
| tests/test_pydantic_opportunity_replay.py | `6f6808e16f5ba7d3a2f786cb0f53c6f7fe513af5e0a4c0a26fa4de824beaf84d` |
| tests/test_pydantic_opportunity.py | `ef2a9e96d63ba23d3a2e389a7de948a2332e64c5f42ab531e9c40d8cf2162ffc` |
| tests/test_pydantic_publication.py | `9db80d7b4df50aa51f69adfbecc8634b07bf330fb5f56a82a4c23a0fcbe3534b` |
| tests/test_pydantic_registry_lifecycle.py | `80d3f5927bde3ac897173998089a474559cf4e2a1aee644eb2a446b2c8bda3f6` |
| tests/test_pydantic_registry_release_readers.py | `4d793053b3f3f437dc3200289c31fac08252f7f79342fe6acb8a3d128a161f25` |
| tests/test_pydantic_research_cache.py | `1438a7fdb0fff1d690bd36a336e83402725fbbb0259dac199cac9d2c72472653` |
| tests/test_pydantic_retained_lifecycles.py | `da99693971d72bf1bac1cc94b60bfe380daee1ffc9a8cbd8155282993c4beb74` |
| tests/test_pydantic_risk_v3_replay.py | `63a076f42cdc67588da9b05a72a83e59115d80ef2c0fb914f754580b40462408` |
| tests/test_pydantic_scientific_truth.py | `b283513d46e8004efa41f79c46868d0f9da827abd8bf1f9b060933384e1b6bea` |
| tests/test_pydantic_source.py | `276196c9cdaebe3a785f8795fa1edd402782cfcc9ba7fba1dc592b2dde9abfc1` |

## Migration history and integration record

| Ticket | Implementation commit | Integrated PR |
| --- | --- | --- |
| #214 | `453a44069aa1f67f8c59ffdcec69302539aa0184` | [#232](https://github.com/hzminhzz/copytrade-pm/pull/232) |
| #215 | `5c2b917757fa63347c36e64b638324d535c70855` | [#231](https://github.com/hzminhzz/copytrade-pm/pull/231) |
| #216 | `f9da2bdf6df181e13e31f2d75e9f27bca42bf57f` | [#233](https://github.com/hzminhzz/copytrade-pm/pull/233) |
| #217 | `7974ecd6104f39df3a89990f810df327036701bb` | [#234](https://github.com/hzminhzz/copytrade-pm/pull/234) |
| #218 | `54cfde70898dcbc35e877108f933839f086e2c91` | [#235](https://github.com/hzminhzz/copytrade-pm/pull/235) |
| #219 | `9ef3e25a8a9052d46c71d5045ad881fbee2e91ee` | [#236](https://github.com/hzminhzz/copytrade-pm/pull/236) |
| #220–221 | `986470fb37fcaf3ec2091e78d3b3ccfc677892bf` | [#237](https://github.com/hzminhzz/copytrade-pm/pull/237) |
| #222 | `242490316d2155a794237acdc67ca235660f7cf6` | [#238](https://github.com/hzminhzz/copytrade-pm/pull/238) |
| #223 | `f15504799fad47c391b96010add9599851bc57c0` | [#239](https://github.com/hzminhzz/copytrade-pm/pull/239) |
| #224 | `e2289f230b619917d4df296dbfd3065d57ddd671` | [#240](https://github.com/hzminhzz/copytrade-pm/pull/240) |
| #225 | `a765bd778ac584e0afa7733659999232cc4b0747` | [#241](https://github.com/hzminhzz/copytrade-pm/pull/241) |
| #226 | `be4808c03420166cf482abc2db99810b2ebf23c8` | [#242](https://github.com/hzminhzz/copytrade-pm/pull/242) |
| #227 | `5ad4d700ce5eaf3a6ed0455edd9dd66bbfd93ba9` | [#243](https://github.com/hzminhzz/copytrade-pm/pull/243) |
| #228 combined-fault and risk v3 | `dddc0faca26b4daddb5d0d4a2269ecabecc51933` | Final acceptance PR |
| #228 original HALT cause / UTC coverage | `a9c4de264ba6f2b929f169b64393df59ed5d4983` | Final acceptance PR |

The final evidence-only commit may follow the accepted code commit without changing executable artifacts. Exact final PR/merge SHA and issue closure are recorded in #228 after GitHub confirms integration.

## Status boundary and #229 handoff

| Status | Evidence at this engineering acceptance |
| --- | --- |
| IMPLEMENTED | Core #214–#228 code at the accepted SHA; all 28 dispositions resolved |
| ENGINEERING VERIFIED | Commands/results above; 13 combined scenarios; real separate consumer compatibility |
| MERGED | #214–#227 confirmed by linked PRs; #228 requires the final integration receipt in its issue |
| DEPLOYED | No new-program installation, restart, cutover or repin |
| FORWARD OBSERVED | New-program authentic lifecycle not observed; FORWARD_EXIT_NOT_YET_OBSERVED |
| SCIENTIFICALLY QUALIFIED | Not established; no follower alpha or independently qualified forward economics |
| TRADING AUTHORIZED | No; no funded/demo trading, orders or protected financial-policy permission |

#229 remains open for **separate explicit deployment authorization naming exact services, OS user and scope**. Before any authorized installation, recheck the exact candidate and compatibility pins, signed selected scope/source identities, current service reality, backup and rollback. Then require an authentic complete baseline and later real source change, original T0/T+300 and actual decision/attempt result, quote/source provenance, restart replay and independent portfolio/HALT behavior. If no real exit occurs, keep FORWARD_EXIT_NOT_YET_OBSERVED. Expanding to 16 portfolios requires its own exact authorized rollout scope.

Optional #230 is isolated research work. Its result cannot alter this engineering receipt, selection, financial authority or scientific qualification.
