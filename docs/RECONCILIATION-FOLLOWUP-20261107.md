# Reconciliation follow-up — 7 November 2026 (UTC)

**Status: engineering baseline verified; privileged SHADOW deployment NOT performed.**
This dated report complements [the original reconciliation](RECONCILIATION-20261107.md).
It is not a current-service-status authority or a scientific qualification.
All data and local artifacts below are owner-private unless already in Git.

## Exact compatible engineering baseline

| Authority | Approved revision | Canonical development checkout at inspection |
| --- | --- | --- |
| `copytrade-pm` | `b1dc9fd9493b28d56385400708e7547f74b173fe` | `main@c663b8b396fc14e24093ac2365095a5fe3cd19e8` |
| `trading-connector` | `2db29b50af301741821781dedf64e4d8194fc125` | `main@5f7664b51988e9f48b3ff3a07876a136c2d97de8` |
| `prop-production` | `baf067ec8a9d6fec1ec5a6f38a7745e02a8e8c05` | `feat/account-guardian-program@baf067e` |

All three canonical Git checkouts were clean and matched the corresponding
remote branch. The application's sole compatibility manifest binds the first two
revisions, `SHADOW`, `trading_authorized=false`, and
`FIXED_K_NATIVE_QUANTITY` (leader whole-account NAV **optional** for this
policy). Its compatibility digest is
`a5ef88eb42d7b18d0bce965675ab6114121c4a681741e23bfd795e63960ec783`.

From the clean application checkout, with `PROP_RESEARCH_ROOT` at the exact
research pin and `PROP_CONNECTOR_ROOT` at the exact connector pin,
`bash scripts/verify-local.sh all` returned `LOCAL_VERIFY_PASS`:

- Application Python 3.13: **140 passed, 1 skipped**; Python 3.14:
  **140 passed, 1 skipped**; Ruff, mypy, builds and smoke passed.
- Connector: **303 passed, 1 skipped**; native Propr gateway **2 passed**;
  native Bybit Demo checks **15 passed**.
- Research: **1,378 passed**; Ruff, build and 110 native capability checks
  passed with **zero capability errors**.

The single connector skip is the separately unmerged optional Combo2 capture
module. These are engineering tests, not production attestation or alpha.

## Corrected stash audit — all three Git parents

The original preservation stash is Git object
`b895d0b3fa92e091e4507a5ebb4949284f4904fb` (414 changed paths).
The original development branch
`archive/original-dev-20261107-before-sync` remains preserved. A stash with
untracked files has a distinct **third parent**; inspecting only the stash's
normal worktree tree misses those files. Compare `stash^3` against current
`HEAD` before any recovery or deletion.

| Disposition | Paths | Treatment |
| --- | ---: | --- |
| Exact Git object match on `main` | 252 | Already incorporated |
| Older tracked copy differing from `main` | 51 | Preserve older version; semantic review before replacing accepted code |
| Older untracked copy now present with different bytes | 3 | Retain legacy version; current tracked copy governs |
| Local Vike skills | 47 | Preserve outside reviewed application path |
| Historical private CSV/compressed tables | 38 | Preserve privately; do not commit |
| Historical research reports/decisions | 19 | Preserve as historical evidence; not current policy |
| Historical read-only scripts | 3 | Preserve; do not promote unqualified scripts |
| Local skill lock | 1 | Preserve local configuration |

**414/414 paths have an object-level disposition**, but the 51 divergent
tracked copies are not independently requalified for merging. The original
base branch also contains the standalone hourly `pm_wallet_intent` and
two-wallet `pm_wave_c` research modules and their tests. They remain
historical, not accepted live fixed-k or native SQLite authorities.
No stash entry, private data or archive object was dropped.

The full path inventory is at
`copytrade-pm/.workspace/reconciliation-20261107-stash-disposition.json`
and its independently verified snapshot is under
`~/.local/share/copytrade/reconciliation/20261107-final`.
These are **private**, ignored recovery materials.

## Worktrees and PRs

The previous verified cleanup removed **25** redundant worktrees. At this
inspection, **75** remained before the temporary isolated repair worktree:
3 canonical, 56 with documented earlier preservation reasons, 4 newly active
DevSpace checkouts, 9 dirty/unique worktrees, 2 locked release checkouts and
1 historical research checkout. None of the earlier 24 eligible clean
ancestors remained; no additional deletion passed the ownership/evidence
test. The private per-worktree disposition is at
`copytrade-pm/.workspace/reconciliation-20261107-worktrees-disposition.json`.

All ten current open `copytrade-pm` PR diffs and metadata were inspected:
**#7, #15, #24, #25, #74, #98, #107, #120 and #122** remain draft research.
**#26** remains `BLOCKED_WITH_EVIDENCE` because the prospective Combo2
source and follower-finance gates are not complete. No experimental or
unqualified science was merged. No open connector or application PR was
returned at inspection. A private per-PR disposition is at
`copytrade-pm/.workspace/reconciliation-20261107-pr-disposition.json`.

## Actual VPS deployment and observer evidence

The registry reader at `b1dc9fd` verified
`ACTIVE_READ_ONLY_VERIFIED`. Private SQLite schema version 8 had
`database_integrity=VERIFIED`,
`research_selection_integrity=VERIFIED` and inventory SHA
`694bc121f43bc618fc35693e935724a210c57d8a98a0a9de34b9c9b464aaec06`.
Registered financial paper runs remained zero.

Six `prop-production` services were observed active with the **older**
root-owned installation `1d7a530df06f2dad753f1615ff2c22af64879d41`.
No activation of `baf067e` or privileged protected-journal inspection
occurred. An installer invocation through the available execution interface
was blocked before the privileged installer ran; it was **not bypassed**.
The code-compatible release is therefore **ENGINEERING_VERIFIED, NOT DEPLOYED**.

The existing P1/P14 bounded observer remained active on
`27b7a6912c18f50eadb1e3fe08010dd0b42fce9a`.
Read-only health reported `DEGRADED_OBSERVER_ONLY`: 5/5 selected source
aliases had receipts, but all **29 indexed market-quote tapes** were stale or
missing under the current freshness contract. Running processes do not
establish continuous current quotes or financial paper eligibility.

The separate continuous `--shadow-report` option previously raised
`sqlite3.OperationalError` when given this legacy bounded journal.
A regression now reports `BLOCKED_INCOMPATIBLE_JOURNAL` and
`CONTINUOUS_STREAM_SCHEMA_NOT_PRESENT` without fabricating elapsed witness
time, stream integrity or financial rows. This diagnostic improvement **does
not** convert the legacy observer into a continuous feed or admit financial
paper trading.

## Remaining independent gates

1. Privileged, rollback-protected installation of the exact approved
   `prop-production` bundle by an authorized OS operator, following the
   owning `prop-production/docs/DEPLOYMENT-RUNBOOK.md` and companion commit pins.
   Verify real `systemd` identities, fresh role heartbeats and journal state.
2. Full source/market capture and measured shared-IP subscriptions for the
   public continuous observer (#135), followed by separately authorized
   cutover (#142); preserve genuine long-duration soak evidence (#141)
   without making it a universal read-only collection prerequisite.
3. Independently matched quote-side follower economics and account-bound
   broker reconciliation before any financial paper admission or demo/live
   authorization. No source-NAV demand is permitted under approved fixed-k.

No broker order, release cutover, source/portfolio reseal, research promotion,
or financial journal mutation was performed as part of this follow-up.
