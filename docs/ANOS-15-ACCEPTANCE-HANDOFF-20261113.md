# ANOS-15 Eight-Scenario Engineering Acceptance Handoff (2026-11-13)

- **Tracking issue:** `#349` (`[ANOS-15] Verify eight end-to-end agent tasks and publish handoff evidence`), verifying `#334` scenarios `S1`–`S8` against the authoritative **ANOS-12** Ops Control Center surface (`ops/control-center/`, `scripts/dashboard_server.py`, `copytrade-pm cwsa chapter2 site-view`).
- **T02 frozen baseline SHA:** `1c4ac38e76dc7ed31e3421273269750b2f03e086` ([ANOS-02 baseline](ANOS-02-AGENT-EVAL-BASELINE-20261113.md))
- **T15 starting `origin/main` SHA:** `0eab42c8ae578d0c18e30432dc1772bd1c8c7be1`
- **Candidate branch / worktree:** `feat/anos-15-eight-scenario-acceptance` (`/home/quant/.devspace/worktrees/copytrade-anos-15`)
- **Live running Ops Control Center & observer release:** `49731332ea24803a7141a48d07e74c3ee490ca30` (explicitly untouched during engineering verification; `DEPLOYED != MERGED`)

## Claim State Separation

| Layer | Status | Basis |
| --- | --- | --- |
| `IMPLEMENTED` | Yes | Production fixes (`pm_k_recalibration.py`, `ops/control-center/src/globals.css`), E2E & Playwright parity suites (`tests/test_anos_15_eight_scenarios.py`, `ops/control-center/tests/owner_parity.cjs`), and handoff docs (`docs/INDEX.md`, this file) |
| `ENGINEERING_VERIFIED` | Verified per PR HEAD commit | Deterministic pytest (`S1`–`S8` positive + falsifier), Playwright unmocked Chromium parity + `browser.cjs`, and exact-commit `bash scripts/ci.sh all` SHA-bound receipt recorded on final HEAD (prior pre-polish commit `899484ed12c5a00d418b7da73f8799eaaebe7ab9` passed CI: adversarial 83 passed, core 2116 passed / 48 skipped, market 2285 passed / 20 skipped, frontend Vite build clean) |
| `MERGED` | Pending PR completion | Merges only after exact-commit CI and dual `code-review` pass on final HEAD |
| `DEPLOYED` / `RUNNING_OBSERVED` | Separate (`49731332ea24803a7141a48d07e74c3ee490ca30`) | Installed ops unit `/api/health` returns `200` on `49731332ea24803a7141a48d07e74c3ee490ca30`, whereas `/api/owner-view` returns `404` because `49731332ea24` predates T12 (`#346`) and also omits `COPYTRADE_OPS_OWNER_PYTHON` (`dashboard_server.py` on T12 returns `503` fail-closed when unset) |
| `EMPIRICALLY_MEASURED` (`#101`) | `BLOCKED_EVIDENCE` (`BLOCKED_NO_INDEPENDENT_HOST_TRACE`) | No independently host-captured, externally Ed25519-signed tool transcript (`pm_agent_trace_eval` fail-closed `UNVERIFIED_TOOL_TRACE`) |
| `SCIENTIFICALLY_QUALIFIED` / `TRADING_AUTHORIZED` | `NOT_AUTHORIZED` (`#313`) | Chapter 2 readiness remains `BLOCKED_EVIDENCE`; no K recalibration, mandate promotion, or Guardian live authorization |

## Candidate vs. T02 Frozen Baseline Comparison

| Metric / Surface | T02 Baseline (`1c4ac38e76dc7ed31e3421273269750b2f03e086`) | Candidate (`0eab42c8ae578d0c18e30432dc1772bd1c8c7be1` + ANOS-15 fixes) | Delta / Evidence Posture |
| --- | --- | --- | --- |
| Registry validation (`capabilities validate --json`) | `114` total, `41` CLI, `48` module-only, `0` errors | `156` total, `41` CLI, `49` module-only, `0` errors | `+42` validated capabilities (`+1` module-only), `0` schema errors |
| Eval task fixture catalog (`pm_agent_trace_eval --list-tasks`) | `13` deterministic tasks (`copytrade_agent_tasks_v1`) | `13` deterministic tasks (`copytrade_agent_tasks_v1`) | `0` drift; synthetic replay does not establish LLM behavior |
| Engineering eval / agent-native suite | `33 passed` (`test_pm_agent_trace_eval.py`, `test_pm_agent_native.py`) | `47 passed` (adds `test_pm_agent_eval_baseline.py`) | Deterministic contract coverage expanded; empirical speedup unverified |
| ANOS-15 Ops Control Center parity (`S1`–`S8`) | Not yet delivered at T02 | Unmocked HTTP `/api/owner-view` <-> CLI `site-view` <-> Chromium DOM (`1440x900`, `390x844`) + fail-closed `400`/`403`/`503` + tampered `trading_authorized=true` UI check + `browser.cjs` (`768x1024`) | Engineering parity established cleanly via isolated fixture DBs and subprocess server |
| Live LLM host trace evidence (`#101`) | `UNVERIFIED_TOOL_TRACE` (`bytes_read=None`, `wall_time_ms=None`, `context_tokens=None`) | `BLOCKED_NO_INDEPENDENT_HOST_TRACE` | External Ed25519 host-signed capture remains open under `#101` |

## Eight Acceptance Scenarios (`S1`–`S8`) & Verification Matrix

Implemented in [tests/test_anos_15_eight_scenarios.py](../tests/test_anos_15_eight_scenarios.py) and [ops/control-center/tests/owner_parity.cjs](../ops/control-center/tests/owner_parity.cjs):

1. **S1 — Fresh agent task discovery (`<= 2` doc hops + capability validation):**
   - *Positive:* Every Markdown doc referenced up to 2 hops from [AGENTS.md](../AGENTS.md) -> [docs/INDEX.md](INDEX.md) (including this handoff) resolves cleanly; `capabilities validate --json` returns `VERIFIED` (`156` capabilities, `41` CLI, `49` module-only, `0` errors); `portfolios show q3/B`, `gemini.phase5/B`, and `wallets show W083` succeed without triggering finance/paper/projection scans or leaking raw `0x` addresses.
   - *Falsifier:* Bare `B` collision fails closed with exit `2` (`REGISTRY_READ_FAILED`), and stale Markdown docs never override sealed SQLite `current` (`gemini.phase4/E6`).
2. **S2 — ANOS-12 Ops Control Center parity (`GET /api/owner-view` vs `site-view`):**
   - *Positive:* On a fresh completed 5-minute grid (`A` has `source_observation: OBSERVE_READY`, `new_risk_source_status: SOURCE_SCOPE_READY`, `missing_or_stale_members: []`, `affected_portfolios: []`, `paper_finance: BLOCKED_EVIDENCE`), live `scripts/dashboard_server.py` `/api/owner-view` matches `copytrade-pm cwsa chapter2 site-view --json` (`cwsa_chapter2_site_owner_view_v1`) verbatim for both `evidence` and `metadata`, and headless Chromium (`owner_parity.cjs` at `1440x900` and `390x844` + `browser.cjs`, GET-only) renders the exact owner states and 4 `UNKNOWN` null-economics cells without raw `0x` leakage.
   - *Falsifiers:* Healthy service with empty paper journals stays `BLOCKED_EVIDENCE`; write methods (`POST`/`DELETE`) return `403` (`403`/`405`/`501`); bad queries return `400`; unset `COPYTRADE_OPS_OWNER_PYTHON` returns `503` and `"UNKNOWN — owner evidence unavailable."`; route-intercepted `trading_authorized: true` fails closed in Chromium UI (`"UNKNOWN — owner evidence unavailable."`).
3. **S3 — Configured, installed, and running release identity separation:**
   - *Positive:* `deployment-status`, `assess_release_admission`, and `/api/health` keep candidate SHA, installed release SHA, observer unit identity, and running PID proof distinct across Chapter 2 (`A`/`B`/`C` have `3`/`3`/`3` members in `six_paper.PORTFOLIO_CONFIGS`) without equating process liveness to trading permission.
   - *Falsifiers:* Missing `/proc` liveness or unrelated PID mismatches block process-proof admission and fail closed instead of certifying an unverified runtime.
4. **S4 — Track C offline recalibration bounds, preflight, & Guardian/mandate safety:**
   - *Positive:* `evaluate_k()` yields `INSUFFICIENT_EVIDENCE` without authorization; `offline_preflight()` verifies real SQLite `portfolio_seals` cleanly (fixing an unclosed `sqlite3.connect` leak), leaving `T+300` pending `k` frozen; generation-2 `activate_copy_mandate` preserves active `HALT` journal state.
   - *Falsifiers:* Out-of-bounds `k` (`0`, `-0.01`, `10.1`) and non-HOLD candidates fail `ValidationError` (`RELEASE_PROPOSAL_SCOPE_OR_EVIDENCE_INVALID`), and tampered SQLite seals trigger `SQLITE_PORTFOLIO_SEAL_MISMATCH`.
5. **S5 — Per-wallet source gap & mixed policy epoch isolation (`B` without blocking `A`):**
   - *Positive:* Injecting a gap on `W031` and mixed policy epoch on `CA-005` isolates blockers to `B` (`SOURCE_POLICY_EPOCHS_MIXED`, `MIXED`) while `A` remains `OBSERVE_READY` / `SOURCE_SCOPE_READY` (`"A"` in `unaffected_source_portfolios`) and `CO-001` / `W028` / `W030` per-wallet clocks remain preserved verbatim.
   - *Falsifiers:* `B` surfaces `COVERAGE_GAP` / `UNAVAILABLE` without coercing to flat or poisoning `A`.
6. **S6 — Bounded PIT acquisition planning & immutable research cache reuse:**
   - *Positive:* `predict_unit_cost()` (`row_groups` stats) and bounded acquisition planning emit `PLANNED` under strict `object_bytes=50_000`, `remote_compressed_bytes=12_000`, `disk_bytes=128` per-unit caps; `ImmutableCache` hits SHA-verified cached offline job reports without S3 reads.
   - *Falsifiers:* Tightening budgets below unit cost deterministically transitions to `BLOCKED`, and tampered cached report hashes fail closed.
7. **S7 — Interrupted paper & Guardian dispatch recovery + invalid query rejection:**
   - *Positive:* Reconciles pre-dispatch `NOT_DISPATCHED` vs ambiguous `POSSIBLY_DISPATCHED` on `PaperOpportunity`; verifies non-null sandboxed Guardian `HALT` (`UNKNOWN_OUTCOME`), reservations, and `risk_floors` (`daily_floor: 9500`) across `DISPATCHING` (`POSSIBLY_DISPATCHED`) vs `QUEUED` (`NOT_DISPATCHED`) via `cwsa chapter2 recover`, preserving `retry_authorized=False` and companion `prop-production` compatibility (`copytrade-pm` pinned at `b1dc9fd9` in `compatibility.json`).
   - *Falsifiers:* Tampered `PaperOpportunity` update binding raises `PAPER_OPPORTUNITY_UPDATE_BINDING`, expired pending never reopens (`retry_authorized=False`), missing Guardian evidence exits `2` (`EVIDENCE_UNAVAILABLE`), and malformed intent queries fail with `INVALID_GUARDIAN_INTENT_QUERY`.
8. **S8 — Baseline comparison, `#101` blocker framing, `#313` preservation & durable handoff:**
   - *Positive:* Asserts durability of this handoff document (`docs/INDEX.md` link + exact baseline/blocker SHAs), monotonic capability validation vs T02 (`>= 114/41/48`), exact `13/13` (`24` calls, `13` hops, `11` reads) deterministic trace-eval invariants, and `16` V4 vs `6` Chapter 2 portfolio separation.
   - *Falsifiers:* Missing external Ed25519 signature keeps status at `UNVERIFIED_TOOL_TRACE` (`!= INDEPENDENT_TRACE_PASS`), and mismatched CI receipt SHAs fail validation closed.

## Modified Paths (6 Files)

1. `src/copytrade_pm/pm_k_recalibration.py` — Wrapped `sqlite3.connect(...)` in `contextlib.closing(...)` inside `offline_preflight()` to prevent `ResourceWarning` SQLite handle leaks.
2. `ops/control-center/src/globals.css` — Added `min-width: 0; overflow: hidden;` on `.breadcrumbs` and text truncation on `.breadcrumbs strong` inside `@media (max-width: 760px)`, eliminating `390x844` horizontal overflow (`411 > 390`) on `Gates & blockers`.
3. `ops/control-center/tests/owner_parity.cjs` — Added unmocked HTTP `/api/owner-view` <-> CLI `site-view` <-> Chromium DOM parity test (`1440x900`, `390x844`, GET-only, `503` unconfigured server, and `trading_authorized=true` UI tamper falsifier).
4. `tests/test_anos_15_eight_scenarios.py` — Executed all eight `#334` acceptance scenarios (`S1`–`S8`) with positive and explicit falsifier assertions.
5. `docs/INDEX.md` — Linked this handoff document within 2 Markdown hops from `AGENTS.md`.
6. `docs/ANOS-15-ACCEPTANCE-HANDOFF-20261113.md` — This durable handoff record.

## Preserved `#313` Boundaries & External Dependencies (Do Not Close `#101`, `#313`, or `#334`)

- **Preserved `#313` invariants:** `16` canonical V4 portfolios, `6` provisional Chapter 2 portfolios, `T0+300` parity boundary, signed `DECISIONS.md` registry seals, pre-recalibration exposure/Guardian rules, and non-promotion of scientific qualification remain untouched.
- **Open external blockers:**
  1. **`#101` (`BLOCKED_NO_INDEPENDENT_HOST_TRACE`):** Independent host-captured, externally signed tool traces are still required before claiming any empirical LLM efficiency or accuracy gain over T02.
  2. **Ops runtime promotion (`49731332ea24803a7141a48d07e74c3ee490ca30`):** Deploying the T12/ANOS-15 Ops Control Center bundle and configuring `COPYTRADE_OPS_OWNER_PYTHON` in `copytrade-ops-center.service` remain separate operational steps outside ANOS-15 engineering scope.
  3. **`#313` scientific qualification:** Chapter 2 portfolios remain `BLOCKED_EVIDENCE` / `HOLD` pending independent live/paper evidence gates.
