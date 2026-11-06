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
