# Milestone #2 engineering acceptance vs scientific qualification

**Decision:** Owner approved **Option A**, 2026-11-04. This supplements
[specification #78](https://github.com/hzminhzz/copytrade-pm/issues/78)
and [Milestone #2](https://github.com/hzminhzz/copytrade-pm/milestone/2).
It **does not** relax PIT, financial integrity, loss-floor, missing-data,
risk, or immutable provenance requirements. PR #92 remains draft; no merge
or deployment is authorized.

## Two independent evidence gates

**ENGINEERING VERIFIED** is reached when the offline software can consume a
versioned, sealed, independently supplied, *complete fixture* in one
manifest-to-result invocation; compile per-fill clocks and native
minute evidence; use the **existing PM-03 Decimal account** for all
chronological money/risk transitions; produce immutable, restart-safe
scenario/ledger hashes; and correctly return typed `BLOCKED`,
`UNKNOWN` and `AMBIGUOUS` for incomplete or impossible inputs.
Fixtures must test positive and negative paths including full book,
source equity, explicit synthetic funding completeness (never inferred zero), margin, daily/trailing floor, pending residual,
partial execution, odd source timestamps, multiple DEXes, and exact
inclusive thresholds. Tests/CI, native-market optional deps, security
and compatibility checks, build and benchmark evidence are required.
A green test suite alone is **insufficient** if the public end-to-end
contract remains incomplete.

**SCIENTIFICALLY QUALIFIED** additionally requires genuine independent
prospective first-known receipts, complete historically as-of source
book/NAV/funding, matched executable follower/control economics, costs,
out-of-sample/future holdouts, uncertainty and contractual rulebook
attestation. A historical vendor timestamp is **never** a prospective
first-known timestamp. Current source files do **not** prove these
conditions. No genuine real-portfolio PASS/BREACH or alpha claim may
be generated from `HISTORICAL_ORACLE` matching, synthetic fixtures
or Float64 screening.

Engineering-accepted artifacts may show `ENGINEERING_VERIFIED` with
`scientifically_qualified: false`. These are **independent state
dimensions**, not progressive confidence labels. Missing historical
evidence must never be manufactured or made a build-time blocker for
unrelated deterministic processing; it remains a **reported result
blocker** for the affected real scenario.

## Issue-by-issue engineering exit tests

| Issue | Engineering acceptance (testable; original constraints preserved) | Independent real-world evidence still missing |
| --- | --- | --- |
| #80 | Frozen comparable synthetic/real-source benchmark input and result SHA, CPU/RSS/I/O/disk measurements, PM01 and PM03 parity fixtures | Matched full historical account performance |
| #81 | One manifest-to-report CLI with typed INVALID/BLOCKED, SHA/policy/provenance checks, complete/partial result semantics, safe paths | Independently attested full real study input |
| #82 | Source account/DEX whole-book/equity typed importer, deterministic signed position chains, as-of/freshness tests and independent source provenance requirements | Real complete atomic books and timestamped NAV |
| #83 | All five per-fill delays, strict next bar, independent receipt vs oracle distinction, streaming/in-memory canonical SHA, prefix invariant | Prospective first-known on past source fills |
| #84 | SHA verified exact native 1m match, prior completed minute capacity, no future volume, explicit market gaps/partial days and DEX namespace checks | Market gaps, L2 execution validation |
| #85 | Immutable source/equity/tape/market/scenario cache boundaries, lineage/invalidation, crash/restart, read-only source and bounded resource use | Source coverage; large certified financial panel |
| #86 | Valid fixture source & marks through one real PM03 chronological account, whole-book faithful sizing, gross/net/pod risk, funding/fees, partials and daily/MTM/HALT; exact ledger parity; no second simulator | Real sufficient source equity/funding/hedges |
| #87 | Screen-only never certifies; exact Decimal fixture PASS/BREACH/UNKNOWN/AMBIGUOUS and inclusive floor/day/margin/restart tests, certified-path evidence gates | Validated real account terms, first-known/mark path |
| #88 | One manifest launches 3- and 5-wallet five-delay cost/stress matrix, stable statuses and SHAs across workers/input order/restart, completed vs partial publication | Real prospective portfolio performance |
| #89 | Reproducible cold/warm comparable input timings, p50/p95 where feasible, CPU/RSS/disk/spill, new and baseline policy distinction, profile-guided optimization | Comparable full historic PM03 portfolio data |
| #90 | Main and market CI, lint/format/build, end-to-end golden/differential proof, frozen PM01 and FP/registry no-order compatibility, docs and PR review | Scientific approval and production authorization |

**Closing rule:** Close each GitHub issue only when its corresponding
engineering acceptance is supported by an exact commit, test commands,
results and reviewed diff. `BLOCKED` or `UNKNOWN` on deliberately
incomplete *real-world* inputs is correct behavior **only if a positive
complete-evidence fixture and an adversarial negative fixture both pass**.
Never close issues by merely writing a blocker note.

## Persistent invariants

- `eligible_at = independently_first_known_at + delay`; retrospective
  oracle experiments must be labeled `HISTORICAL_ORACLE`. Forward-paper
  first-event non-resetting T+300s is not this policy.
- PM-03 is the only authority for chronological cash, NAV, positions,
  realization, funding, fees, daily resets, gross, drawdown and HALT.
- Exact Decimal or independently proven fixed-point is mandatory for
  final financial verdicts. Float OHLCV volume is merely screening.
- Source equity/hedge/funding/market/day gaps are unknown, not zero.
  Blocked exits and partial fills are not fictitious flat positions.
- Frozen 36-wallet PM01 v2 contract and active Forward-Paper/registry
  ownership remain unchanged.
- Source and native day files are immutable. No network source
  acquisition, broker order, demo trade, service cutover, merge, or
  protected deployment is authorized by this milestone.

## Reporting

On every PR update show separately: IMPLEMENTED, ENGINEERING VERIFIED,
REAL DATA BLOCKED/UNKNOWN, SCIENTIFICALLY QUALIFIED, AUTHORIZED, DEPLOYED.
Only the first two can be achieved by this approved engineering program
without new independent observational evidence.
