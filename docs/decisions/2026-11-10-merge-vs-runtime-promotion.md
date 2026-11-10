# ADR 2026-11-10: Gate actions, not source-code existence

**Status:** Accepted for engineering workflow by owner decision on 2026-11-10.
**Scope:** `copytrade-pm` research/SHADOW code integration and subsequent independent operations.
**Context:** PR #290 implemented 15 nonactivating Track B v2 slices and passed exact-head tests, but a proposed Git merge was blocked on uncollected prospective economics, Track C k activation, calibration, deployment and trading authorization. These are not properties of a Git commit. PR #290 was subsequently squash-merged as `5875e4cb6f9fa21a99a20fdd1f3f5b159dd6c5ce`; #274–#288 closed.

## Decision: artifact maturity and action authority are orthogonal

A **source-code artifact** may be `PROPOSED`, `ENGINEERING_VERIFIED` or `MERGED`. This says nothing about installation, execution or economic validity.

Every **attempted action** has its own scope, authority, provenance and safety gate. Merging additive nonactivating code cannot grant a runtime capability. Never infer an action from a merged commit.

| Requested action | Minimal relevant gate | Not a prerequisite |
| --- | --- | --- |
| Review/merge additive read-only or nonactivating engineering code | Exact-head deterministic and adversarial tests, clean diff, lint/build, compatible contracts, code review, branch policy, no protected side-effect path | Positive alpha, live follower PnL, active k release, service deployment, broker approval |
| Publish read-only research SHADOW evidence | Original source/selection bindings as needed, redaction/auth, freshness, signed publication identity, pre/post proof, reversible deployed revision | Demonstrating positive strategy alpha |
| Publish *provisional* health advisory | Correct causal evidence and explicit uncertainty/unknown, no automatic capital or trading action | A calibrated false-warning target; do not label advisory calibrated |
| Reduce/disable prospective risk | Authentic current inventory, pending intent and source/finance identities, conservative risk policy, explicit deployment/rollback authorization; no retroactive resizing | Positive alpha. A risk-off action is not a new alpha claim |
| Increase k, release new risk, modify protected financial state | Independently authenticated economic evidence appropriate to the specific risk-changing action, version-pinned T0/k, signed future-only release, inventory/pending/rollback/guardian preflight and independent release approval | Git merge status alone |
| Route real broker orders | Actual account/venue terms, protected Guardian/broker controls, independently authorized risk and execution; explicit operator approval | PR merge, synthetic regression, a research label |

**Risk monotonicity:** tighten or pause risk only through existing protected operational authority. Relax limits, increase k or enable new-risk routing require stronger proofs. Do not invent an emergency override in this repository; Guardian in `prop-production` owns real risk authority.

### Merge decision

A nonactivating PR may be merged despite `SCIENTIFICALLY_QUALIFIED=false`, `DEPLOYED=false` or `TRADING_AUTHORIZED=false` when its engineering contract is verified and GitHub's actual merge rules are satisfied. Keep unresolved operational/finance/research work visible as separate issues with clear evidence collection and activation criteria.

A PR **must not** merge when it breaks original source/PM03/PM04 invariants, introduces unreviewed protected side effects, has failing relevant tests, or violates actual branch protections. Absence of genuine future outcomes is not a test failure for a correct fail-closed contract.

### Runtime enforcement

- No merged artifact changes `source_first_known`, selected SQLite authority, PM03/PM04 account ledger, HALT, Guardian/broker permission or active k without its separately authorized action.
- Maintain original proof and evidence classes: synthetic, prospective SHADOW and authentic broker fill are different; a checksum or signer identity is not economic authenticity.
- `pm_k_release.verify_cutover` remains `BLOCKED_NONACTIVATING` until its actual version-aware consumer and original proof path exist. Track C issues #267 and #268 remain open.
- Preserve pinned deployments, independent rollback, no stale/corrupt data promotion, no source GAP inference and the default `NO_TRADE` decision.

## Rejected alternative

**One global READY gate for Git, Grafana, research and brokers.** It makes harmless integration depend on unobservable future market outcomes and conflates engineering, science, deployment and financial authorization. Conversely, **removing all gates** is unacceptable because it would grant operational authority from a Git event.

## Verification and audit

Record all statuses separately: `IMPLEMENTED`, `ENGINEERING_VERIFIED`, `MERGED`, `DEPLOYED`, `RUNNING_OBSERVED`, `SOURCE_FINANCE_AUTHENTICATED`, `SCIENTIFICALLY_QUALIFIED`, `TRADING_AUTHORIZED`. A status can change only on evidence from its authoritative owner. Keep references to a specific SHA, running release and authenticated original receipts.

This ADR is workflow policy, not a deployment switch, trading permit or scientific signoff.
