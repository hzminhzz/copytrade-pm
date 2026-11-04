# Autonomous blocker recovery — operator protocol

**Trigger:** A requested research or engineering objective encounters `BLOCKED`, a data/API/tool error, failed tests, missing dependencies, an unavailable judge, inconsistent evidence, or an invalid hypothesis. This is a **work-continuation procedure**, not permission to weaken any qualification, source-integrity, or authorization gate.

## RECOVER: execute the loop, not a status-only response

1. **Keep the original objective.** Identify the failing stage, exact error/verdict, evidence path, frozen input IDs, source SHA, decision clock, and any active unrelated work. Preserve dirty worktrees and immutable raw artifacts.
2. **Classify and diagnose.** Reproduce with the narrowest safe check; determine whether the cause is engineering, source/data, scientific non-identifiability, external permission/availability, or genuine falsification. Inspect actual source/code/docs and available authorized tools rather than guessing.
3. **Select a remedy.** Compare at least the feasible native repair, independent source/contract-compatible alternative, and a scoped prospective or unaffected-work path. Prefer the smallest reversible, evidence-preserving change. Respect provider quotas, costs, explicit owner permissions and affected source authority.
4. **Act, then verify.** Implement or acquire on a new auditable lineage. Test the failure case and regressions, re-run the relevant audit, verify SHA/as-of/fill/cost contracts and inspect the diff. A new provider generation is not an edit to a frozen source.
5. **Resume the original workflow** from the blocked dependency. If that path is proven unrecoverable, mark the *affected result* blocked with reasons, continue independent eligible subwork, and pursue the authorized prospective or alternative campaign. Never relabel the original failed window as qualified.
6. **Close against the requested objective**, not against an intermediate fix: capture objective outcome, evidence, actual tests, unresolved constraints and exact next external action. An active automation may resume later; a normal chat session cannot claim unattended continuation once it ends.

Do not run identical retries indefinitely. Bound attempts and spend; after repeated same-cause failures change diagnosis or route. Save durable evidence before switching paths. Resolve routine build, code, dependency, local permissions, data-catalog and documentation problems without requesting another approval when already within the approved scope.

## Failure routes and what to do next

| Route | Mandatory next action | Status that may remain |
| --- | --- | --- |
| Broken code, test, package, stale command, local file layout | Inspect the real interface and state; repair, test, and resume | `ENGINEERING_BLOCKED` only if safely unrecoverable |
| Missing HyperX source pages, account book/equity, native 1m day, funding/position chain | Verify native owner/provider; try bounded, authorized new source generation and independent SHA audit; isolate unavailable wallet/window; activate prospective collection where justified | `BLOCKED_SOURCE` / `BLOCKED_PIT` for that exact historical window |
| Vendor timeout, quota, auth, judge or tool unavailable | Classify timeout vs exhausted quota vs credentials vs missing integration; bounded retry/backoff or preauthorized alternative; continue offline independent work | `EXTERNAL_BLOCKED` only for the dependent action |
| Corrupt/tampered chain, irreconcilable broker state, stale or uncertain risk evidence | Quarantine affected evidence, investigate independently and repair upstream; preserve HALT and zero new risk | `HALT` / `BLOCKED_INTEGRITY` until independently repaired |
| Valid scientific test rejects a thesis | Record the falsification and selection count; move to the next distinct approved candidate if the wider program continues | `FALSIFIED` for that hypothesis |
| Insufficient prospective matched follower outcomes | Capture real independent first-known receipts and mature follower/control economics going forward; retain no-trade decision | `NOT_SCIENTIFICALLY_QUALIFIED` |

**Fail closed on an affected result; keep the wider research program moving.** Historical event timestamps cannot recover a follower's past first-known time. Missing hedge/book/collateral cannot be zero-filled. A provider proxy cannot masquerade as native executable evidence. A blocked or invalid historical study may remain terminal while safe prospective collection and other eligible studies continue.

## Decision authority and missing independent review

Routine exploration, screening, data queries, tests and already-authorized engineering do not call the judge. Classify **protected decisions**, not chat turns: consult [governance gates](GOVERNANCE-GATES.md) at explicit PR/signoff boundaries for material scientific-policy changes, frozen roster promotion/deletion or other irreversible decisions. Existing deterministic PIT/source/risk gates are mandatory regardless of the review verdict.

If a review integration is unavailable, record `JUDGE_UNAVAILABLE` for that protected decision and preserve its pending status. Continue all independently valid reversible work; do not simulate or invent a review. A valid review is evidence of review only, not owner approval, scientific qualification or trading permission. Explicit approval covers only its authorized scope; protected holdout access, live orders, contract rewrites and production deployment still require their separate authority.

## Source of truth and memory checkpoints

- For **instructions**: platform/safety constraints and explicit current user authority apply first, then applicable repository contracts/agent guidance; where they conflict, choose the safer compliant action and disclose any genuine conflict.
- For **facts**: current source code, immutable raw evidence, signed contracts, current Git/service state and independently verifiable observations outrank dated docs; docs outrank remembered summaries. OptMem and ChatGPT memory are recall aids, not evidence or execution authorization.
- Run mandatory OptMem `wake`/`note`/`nap` as specified by `AGENTS.md`. Finish requested compression, then return to the interrupted step; memory maintenance never counts as the task's completion. On a memo error, diagnose and recover its integrity state rather than directly editing `~/.optmem/memory`.
- Before closing or handing off, persist any durable architectural decision and the evidence/next-step pointer, without duplicating transient status or secrets.

## Closeout criteria

An objective is **DONE** only when its stated acceptance and relevant engineering/scientific/authorization gates actually pass. A distinct hypothesis can be **FALSIFIED** without ending an ongoing discovery campaign. The workflow is **EXTERNALLY BLOCKED** only when all safe, authorized alternatives for the required dependency have been examined, and the response identifies the precise user-only or external action. No qualification, deployment or live-trading claim without separately verified evidence.
