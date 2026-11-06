# Persistent observer program #129: execution and evidence

## Verified starting point

Inspected 2026-11-06. The primary checkout was main at
b560db3628bb8dbe6f41932b3731918925ee9640 with substantial staged, modified
and untracked work. It remains untouched. Remote main was
58dc8ee1490238fb6f066fb3e27c548d75962c70.

The active public observer was pinned to
27b7a6912c18f50eadb1e3fe08010dd0b42fce9a, PID 438441, zero systemd restarts.
It used 2-second account/market windows and a 120-second inter-cycle pause.
Independent health returned DEGRADED_OBSERVER_ONLY, five source tapes,
29 market tapes and five collateral tapes, with stale/missing quotes.
This is a sampled baseline, not a continuous-health claim.

The candidate starts from PR #118 at
0062d06d1c29d6ea6efc4d4213f5006896dbe5e1, which includes current main.
PR #126 at c8b5ccc9d3905cf2fc48c706d8b87273e1e70e13 also incorporates
protected standby operations; those services are outside this program.
The candidate selectively reuses the explicit real-source admission guard,
as-of readiness correction, and public error redaction from that integration.
The only cherry-pick conflict was documentation; both independent corrections
were retained.

The initial focused observer/public-trade/readiness/source/cache suite passed
61 tests. The native registry doctor failed; investigate and preserve its
signed-selection gate before any new portfolio-bound live capture.
No registry or existing service was changed.

## Module ownership

| Responsibility | Existing owner / lineage | Candidate treatment |
| --- | --- | --- |
| Wallets and frozen portfolios | wallet_registry, main | Read-only; native doctor plus sealed definitions |
| Account schema | pm_e4_prospective / pm_forward_source_observation, main | Reuse strict all-DEX parser |
| Source receipt tape | PaperJournal.source_receipts, main | Add atomic stream-checkpoint hook |
| L2 and rolling cache | pm_forward_ccxt_market / pm_forward_ccxt_trades, main | Retain client, transactional state publication |
| Public wallet candidates | pm_forward_public_trades, PR #118 | Reuse native normalization and existing receipt table |
| Lifecycle / resource planning | New pm_forward_continuous responsibility | Orchestration only; no competing registry or ledger |
| Independent health | pm_forward_observer_health, main | Extend existing public surface |
| Financial state | PM-03/PM-04, main | Existing admission and synthetic consumer contracts |

## Dependency order

#130 preflight → #131/#132/#133 acquisition → #134 account families →
#135 required markets → #136 atomic progress → #137 reconciliation →
#138 health → #139 consumer compatibility → #140 full verification →
#141 real 72-hour shadow → #142 separately authorized public cutover.

Atomic persistence is designed alongside acquisition so no intermediate
runtime can treat uncommitted input as accepted progress. Tickets are not
closed until their applicable acceptance evidence is recorded.

## Evidence and operating boundaries

The native shared-IP limits checked against official documentation are
10 sockets, 10 unique user-specific subscriptions, 1000 subscriptions,
30 new connections/minute and 2000 sent messages/minute. Existing services
share those limits. Reservations must cover the whole IP, including rotating
source-ABC users; a low instantaneous socket count is insufficient proof.

Host sample: approximately 12.9 GiB available memory and 58 GiB free disk.
These measurements are transient. Disk, queue, connection and account limits
must be enforced at runtime. No inference of source NAV, complete trade volume,
account orderability, or financial admission follows from healthy capture.

The actual 72-hour gate cannot be shortened. Public cutover requires separate
operator authorization and accepted shadow evidence. No independent judge
tool is exposed in this session; deterministic checks and the recorded
self-review must not be represented as an independent signed review.

## Engineering outcome at 2026-11-06 13:57 UTC

Implementation is **ENGINEERING VERIFIED** at
`5eeb57dfb2ae17169c6ab16dd3ede9b0d802c35f` on
`feat/persistent-observer-129-20261106`.
[PR #144](https://github.com/hzminhzz/copytrade-pm/pull/144) is open and ready
for review. It is not merged. The actual 72-hour portfolio shadow is
**BLOCKED / NOT STARTED**. The active public observer is **NOT CUT OVER**.

The implementation commits are:

- `0ebb1cde0175495795d0578fe34c4afa249b6c59`: continuous acquisition,
  atomic stream progress, recovery, health, compatibility and operating interfaces.
- `f97ebae816987fd4c27452c6d6dbae8a93fff1c8`: inclusive native millisecond
  REST reconciliation and deterministic wheel-test ZIP metadata.
- `5eeb57dfb2ae17169c6ab16dd3ede9b0d802c35f`: capture the returned CCXT cache and its ingress clocks
  before the supervisor yields; record the verified rollback reader constraint.

The later evidence-document commit does not change the executable source,
tests, dependency lock or the release tested below.

### Ticket disposition

Every ticket remains open while integration/operational gates remain unmet.
The statuses below distinguish the implemented mechanism from actual live scope.

| Issue | Implemented and verified evidence | Remaining gate |
| --- | --- | --- |
| #130 | Reconciled base and preserved dirty work; isolated candidate; native registry, exclusions, path/lease/resource preflight and no-side-effect rejection | Actual portfolio startup fails signed-selection/exclusion gates |
| #131 | Persistent native account owner; full all-DEX census, exact ACK, epochs, snapshot baselines, distinct native child identities and clocks | Live portfolio-source coverage not observed in this program |
| #132 | Persistent pinned CCXT client; coherent raw ingress clocks, rolling-cache overlap/deduplication; actual BTC L2/trade probe | Full-universe throughput and 72-hour reliability unqualified |
| #133 | Native public frames and immutable wallet-side candidate identities; snapshots excluded, raw wire SHA and canonical deduplication | Real probe selected zero wallets; live P1/P14 matches UNKNOWN |
| #134 | One parent/child family census and shared P1/P14 source projection, independent per-account state, unknown children retain hedge requirements | Actual portfolio startup gate |
| #135 | Configured union held native markets; unsupported siblings remain explicit; exact 157-market display-snapshot parity | Shared-IP allocation and live full-scope capacity |
| #136 | Atomic legacy receipt plus stream checkpoint/CAS; cancelled submitters await commit; SIGKILL before/after COMMIT; live backup/reopen | No host reboot performed |
| #137 | Later REST audit-only reconciliation; original clocks and deadlines preserved; millisecond-boundary regression | No live watched-wallet reconciliation in market-only probe |
| #138 | Separate watchdog, process/revision/head verification, per-feed ACK/freshness, bounded queue/disk metrics, real elapsed witness audit | No accepted 72-hour portfolio witness |
| #139 | Existing PM-03/PM-04 and FIRST_SIGNAL_PLUS_5M regressions pass; parent/child fanout, replay and independent portfolio fixtures | Financial/source evidence gates remain unchanged |
| #140 | Full core/market/all-extras matrix, build, lint, capabilities, fault tests, isolated systemd rehearsal and real BTC probe | Enforced hosted CI cannot start because of billing lock |
| #141 | Pinned release, private configs, uninstalled collector/watchdog units and audit workflow prepared | BLOCKED_NOT_STARTED; 0 hours of qualifying portfolio shadow |
| #142 | Isolated failed-launch/bad-health/restart and compatible reader/journal recovery verified; release staged | Accepted real72h, trusted release/review and separate public-cutover authorization absent |

### Exact-commit verification

All commands below ran against `5eeb57dfb2ae17169c6ab16dd3ede9b0d802c35f`, with a clean
candidate checkout. Dependency variants were actually synchronized between runs.

| Verification | Exact command / preparation | Result |
| --- | --- | --- |
| All extras | `uv run --frozen --all-extras --group dev python -m pytest -q tests` | **1232 passed**, 27.33 s |
| Core | `uv sync --quiet --frozen --group dev`, then `uv run --frozen --group dev python -m pytest -q tests` | **1113 passed, 15 skipped**, 17.77 s |
| Market | `uv sync --quiet --frozen --extra market --group dev`, then `uv run --frozen --extra market --group dev python -m pytest -q tests` | **1231 passed, 1 skipped**, 24.04 s |
| Ruff | `uv run --frozen --all-extras --group dev ruff check src tests` | PASS |
| Formatting | `uv run --frozen --all-extras --group dev ruff format --check src tests` | 302 files already formatted |
| Native catalog | `uv run --frozen --all-extras --group dev copytrade-pm capabilities validate` | 94 capabilities, 32 CLI, 44 module-only, errors empty |
| Package | `uv build --offline` | Wheel and sdist built |
| Working tree | `git status --short` | Empty after source commit |

The all-extras environment was restored after the matrix. The native/CCXT
instrumentation tests use the installed pinned CCXT 4.5.91 Client dispatch;
they do not manufacture a network result. Process crash tests send real
SIGKILL to isolated subprocesses. No shared VPS reboot was attempted.

### Defects reproduced and corrected

The work did not stop at the first green suite. Verification exposed and fixed:

- Raw native frame SHA accidentally shadowed by an individual-trade SHA.
- Cancellation returning while a queued write could still commit, allowing a
  replacement projection to reopen an old head.
- SQLite WAL transition contention and a disappearing WAL/SHM size-check race.
  The integrated lifecycle test passed 15 independent repetitions after repair.
- Fatal storage cleanup abandoning later sibling transports after the first
  exception; the fault test now proves every client/socket closes.
- REST requests truncate to inclusive integer milliseconds, while validation
  used microsecond caller bounds. A valid boundary fill was rejected. The
  regression failed before repair; the native request bounds are now retained
  and used for both candidate and official-row comparison.
- A release test regenerated its supposedly identical wheel with a different
  ZIP timestamp. Its fixture metadata is now deterministic.
- A real BTC probe raised one cache-gap guard. A deterministic event-loop
  regression then proved that a newer raw callback could be paired with an
  older already-resolved CCXT cache. Both quote and trade cases failed before
  repair. Data, stamp and per-trade clocks are now copied before yielding.
  The genuine cache-loss guard remains active.

An initial high-rate fake-feed rehearsal at 30% CPU produced explicit native
queue-overflow gaps and degraded watchdog samples. Its journal still verified
and financial rows remained zero. This is retained failure evidence, not a
throughput pass. The corrected, paced isolated rehearsal subsequently produced
current-feed observations without the false REST-window error.

## Actual bounded public market observation

The final real probe used the existing native command from the clean pinned
release, one BTC perpetual, two sockets, zero selected source wallets and no
credentials. The configured capture duration was 135 seconds. Total measured
process interval, including setup/cleanup, was **143.19126372016035 seconds**:

- Start: **2026-11-06T13:49:22.001054+00:00**.
- Stop: **2026-11-06T13:51:45.192287+00:00**.
- Systemd process exit: 0; main PID 0 after completion.
- SQLite integrity: `ok`; independent stream/reference verification: VERIFIED.
- The report's stream-head SHA matched the independently computed stream head.
- Live journal: 2,146,304 bytes at verification.

| Feed | Post-baseline observations | Baselines | Epochs | Recorded gaps |
| --- | ---: | ---: | ---: | --- |
| BTC CCXT L2 | 25 quote observations | 1 | 1 | Startup and orderly stop only |
| BTC CCXT trades | 205 rolling-cache batches | 1 | 1 | Startup and orderly stop only |
| BTC native public trades | 214 frames | 1 | 1 | Startup and orderly stop only |

These are frames/batches, not 205 or 214 independently matched wallet fills.
There were **zero unexpected gap markers during this bounded probe**. This
does not establish exchange-wide losslessness or full-universe coverage.

Measured source-to-first-known latency for persisted post-baseline frames:

| Feed | Samples | p50 ms | p95 ms | p99 ms |
| --- | ---: | ---: | ---: | ---: |
| CCXT L2 | 25 | 518.697 | 894.270 | 1111.080 |
| Native public trades | 214 | 456.038 | 1120.318 | 1245.146 |

Percentiles select the ordered sample at floor((N-1)q). This small BTC sample
does not qualify portfolio latency or 157-market capacity.

The earlier `f97ebae` probe lasted 143.8531130058691 seconds and retained one
`CCXT_NATIVE_CACHE_DROPPED_OBSERVED_TRADE` guard event. Its evidence was not
rewritten after the scheduler-race repair.

Final probe stream head:
`f9a7417123b978c6121b7f5627364a92682934edc101d8fd0b55d9ed386d25fc`.

The live journal was backed up and reopened independently. Both originals and
copy had that stream head. The old `27b7a69` reader accepted this additive
market-only schema and agreed with the current reader on legacy head digest
`85971ab8a1c8003e45ea9ec2aeb3d97f7d8fd61f33e6d922dc619358fb9947e3`.

**Claim boundary:** source coverage NOT_REQUESTED_MARKET_TRANSPORT_PROBE;
watched wallets 0; matched wallet fills 0; financial runs 0; financial events 0;
order_route NONE. No financial paper, scientific qualification or trading
authorization follows.

## Isolated operational and rollback rehearsal

Separate transient systemd units exercised deterministic fake account/BTC/HIP-3
feeds with `RestrictAddressFamilies=AF_UNIX`, private state and CPU/memory/task
limits. They could not reach the exchange.

The separate watchdog observed all eight required fixture feeds. On the final
restored revision, its sealed history recorded **10 CURRENT_FEEDS_OBSERVED**
samples, followed by an orderly-stop/degraded sample. A deliberately incorrect
expected revision returned `OBSERVER_RELEASE_REVISION_MISMATCH`. A deliberately
missing module produced an actual failed-launch process exit 1. The restored
collector exited 0 and reported every fake client/socket closed.

All **13** saved pre-restart stream prefixes remained at their original sequence
numbers and SHAs after subsequent runs. Source and quote progress continued
without rewriting the old tape. Financial runs/events remained zero.

A read-only SQLite backup of the existing public journal was created privately,
without changing its producer. The old pinned `27b7a69` reader ran in a separate
bounded systemd unit and verified **3893 source receipts, 29 quote tapes and five
collateral tapes**. Both reader generations agreed on digest
`10b4d8d1117b2c919a18566535a737cbb7e2da9a1c0bbedac518f233a55d7d92`.

**Reader compatibility limitation:** the old release rejects new
`BLOCKED_PERPETUAL_COLLATERAL_RECONCILIATION` diagnostics. It must roll back
with its preserved legacy journal. The new reader accepts the old journal;
the old reader also accepts new additive market-only tapes. No diagnostic
was rewritten to force compatibility.

This verifies isolated process failure/readiness/restart and matched
release/journal recovery. It is not an authorized active-service rollback,
nor a live portfolio-source rehearsal. The mixed-revision fake witness log
contains intentional stops and long gaps; none of its elapsed time counts
toward #141.

## Prepared release and exact blockers

The pinned source environment is:

`/home/quant/.local/share/copytrade/releases/5eeb57dfb2ae17169c6ab16dd3ede9b0d802c35f`

Its ignored private `dist/` directory contains:

- `continuous-shadow-blocked.json`: complete 157-market configuration with
  conservative shared-IP reservations; deliberately fails current capacity.
- `continuous-preflight-registry.json`: minimal read-only diagnostic config.
- `copytrade-continuous-shadow.service` and
  `copytrade-continuous-shadow-watchdog.service`: uninstalled, verified with
  `systemd-analyze --user verify`.
- `prepared-shadow-units.json`: native unit hashes and unsigned wheel report.
- `program-evidence.json`: machine-readable test, probe, release and gate evidence.
- `isolated_observer_rehearsal.py`: explicit fake-feed process reproducer.

The prepared full-shadow state root was **not created**. Both actual CLI
preflight attempts exited 2 before journal/network creation. Full scope returned
`STREAM_CONNECTION_BUDGET_EXCEEDED`; the minimal diagnostic reached and rejected
native registry provenance.

The unsigned wheel is 590060 bytes, SHA
`b89302cda3ea393c5fc4e92535717c89da678db23fc72311f23f322bf573c63e`.
It is staged under the native `candidate-` content-addressed release directory.
Manifest SHA:
`2550a6ce0a03367a95c3639867a9133339d3534f85a5a1ba5cffc887e17a247f`.
Its verified status is **UNPROTECTED_UNSIGNED_CANDIDATE_VERIFIED**.
Independent signature, immutable release, independent build attestation and
operator-cutover authorization remain false.

### Registry gate, rechecked at 13:57:14 UTC

SQLite integrity is VERIFIED. Inventory SHA remains
`b2e5ea14fc3f1b71778bc78f4a568b0e7ee711802e2ab3ebfd72ef282cbdb855`.

The latest research-selection source
`a899f0f6a4331c246307189f3ab75d87e1a515b84a2e926073ce33ff994ce9eb`,
known at `2026-11-05T18:18:46.324642+00:00`, has **zero selection proofs**.
The native status/doctor gate reports `unverified research selection provenance`.
An independent P1/P14 watchlist query rejects
`PUBLIC_TRADE_WALLET_PROPFIRM_EXCLUDED`.

These are provenance/exclusion failures, not missing NAV. No registry proof,
frozen definition, exclusion or qualification was changed to pass them.

### Scope and shared-IP gate

The exact external display snapshot verified SHA
`1a6cd762634d4f05e88577be1a43a5cf2dede643bf724ab743cf7a278e20179b`.
The configured native universe is **157**, grouped **8/88/61**.
This is display/configuration parity, not account orderability.

An offline plan for five parent accounts requires five additional sockets
and 476 subscriptions before discovering additional children/hedges.
The prepared config reserves eight existing/headroom sockets, ten rotating
user identities and 350 subscriptions. It cannot fit the full candidate.

Installed code inspection bounds the tracker to one socket, source-ABC to four,
and the legacy public observer to one at a time. The two-socket BTC probe added
no user-specific subscription. TCP counts were not mislabeled as WebSocket
counts. The full candidate still needs a deliberate allocation that preserves
existing consumers, plus measured sustained CPU/disk/watchdog adequacy.
No 157-market rate or 72-hour storage projection is qualified by the BTC probe.

### Merge and review gate

Remote main remains `58dc8ee1490238fb6f066fb3e27c548d75962c70` and is an
ancestor of the candidate. PR #144 has no merge conflict, but GitHub reports
`mergeable_state=blocked`.

At the exact code commit, required checks `verify (core)` and
`verify (market)` failed **before starting**. GitHub's annotation states the
account is locked due to a billing issue. Both checks are strict branch
requirements with admin enforcement. The approved local VPS evidence does not
override that enforceable protection. No bypass or merge was attempted.
GitGuardian completed successfully.

Actual-diff self-review covered raw clocks, rollback, queue cancellation,
atomic publication, immutable recovery, credential/order exclusion and resource
bounds. **JUDGE_UNAVAILABLE**: no independent review tool was exposed. Self-review
and passing tests are not an independent signed release approval.

## Continuation and preserved runtime

The remaining sequence is:

1. Resolve signed-selection provenance and allowed watchlist identity through the
   owning authorized registry workflow; preserve frozen history and exclusions.
2. Allocate shared-IP capacity and verify full-scope resource adequacy.
3. Restore required hosted CI and complete applicable review/release trust gates.
4. Re-run exact native preflight, then install the separately supervised private
   collector/watchdog only if those gates pass.
5. Collect and independently audit **72 actual hours**; review coverage,
   discrepancies, restarts, latency and storage without relabeling gaps.
6. Obtain the separate scoped public-cutover authorization; only then change the
   public observer with the preserved compatible rollback pair.

The collector/watchdog units for #141 remained **not-found/inactive** at final
inspection. Bounded probe and rehearsal processes were stopped; no unattended
72-hour portfolio collector is claimed.

Final protected/legacy service observations matched the starting PIDs and
restart counts: public observer 438441/0; tracker 2050126/0; source-ABC
2180745/0; ensemble 707716/1. The public unit still points to
`27b7a6912c18f50eadb1e3fe08010dd0b42fce9a`.
The primary dirty checkout remains at `b560db3`; its work was not edited,
reset, stashed, cleaned or force-pushed by this program.

No broker mutation was invoked. New observation journals contain zero financial
runs/events. No financial paper observation, scientific qualification, source
NAV attestation, broker orderability or trading authorization was granted.
