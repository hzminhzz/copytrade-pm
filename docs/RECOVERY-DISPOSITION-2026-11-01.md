# Recovery disposition — 2026-11-01

This is a dated engineering and evidence record for the execution of PR17's
Diagnose → Choose remedy → Implement → Verify → Resume protocol. It is not a
scientific approval, an independent judge verdict, or an execution authorization.

## Authoritative baseline and preserved work

PR17 is present on authoritative remote main at
`d3e0ce916c2f0b64ad36593f55b261607ec0cbdd`.
PR18 merged the complementary E0/E4 infrastructure at
`7a8be42dbee374f7ce3d5702f98dadc638853f4a`; its reviewed implementation commit is
`4d6dc6e934155ffbb398ca0f42e28e7a3ee39f1a`.
This follow-up is the `recovery/evidence-governance` branch based on that merge.

The primary checkout at `b560db3628bb8dbe6f41932b3731918925ee9640` retained its six
local commits and uncommitted AGENTS change. Other research worktrees and the dirty
trading-connector and ml4t-data source checkouts were not reset, stashed, cleaned
or overwritten. Existing research artifacts remain immutable. New data artifacts
have separate content-addressed lineage in the owner-private recovery directory.

Mandatory AGENTS, OptMem wake, architecture, data, runbook, qualification and blocker
recovery initialization was completed. OptMem supplied context; actual Git, code,
provider metadata and service observations supplied evidence. No implementation was
delegated. JUDGE_UNAVAILABLE applies to the new changes; no external verdict is invented.

## Disposition by dependency

| Work item | Engineering disposition | Scientific / authority disposition | Remaining dependency |
| --- | --- | --- | --- |
| PM04 / Issue12 | Existing PR13 offline accounting and 18-case/adversarial acceptance reverified; no replacement financial engine | No actual broker evidence or live authority | EXTERNAL account, signer/transport, native clock and contract approval; PM01/PM02 qualification |
| E0/E4 / PR7,15,16 | Complementary complete-book, one-scale sizing, native identity, tracking and source modules integrated through PR18 | Q3 complete-wallet economics not established | EXTERNAL complete source capital/continuous account evidence; TEMPORAL prospective accumulation |
| PM01 / Issue4 | Source overlay reconciled; bounded native-market recovery and durable A/B/C collector operational | Zero independently qualified wallets | EXTERNAL remaining source/market/account/auditor inputs; TEMPORAL mature real outcomes |
| PM02 / Issue5 | Immutable code-pinned OOS campaign, v2 whole-account gates, fixed-look lifecycle and conservative risk verified | Zero qualified, five EMPTY, zero R on actual inputs | Independent review and economic attestation; future OOS windows and matched dependence history |
| ML4T / Issue14 | Source-grounded specification and pure offline identity/reconciliation oracle verified | No production adapter, broker credentials or route | EXTERNAL account contract, executable adapter review and separate implementation/authorization |

COMPLETE applies to the stated offline engineering, not to the open scientific or
account-specific acceptance. Missing evidence is not FALSIFIED. Known provider gaps
remain explicit; a failed scientific path does not block independent engineering.

## PM04 acceptance evidence

PR13 merged at `8dd0c97971b41cd8d1c0e177050ed4cb059f30ec`; its final reviewed
head was `35c02b0198c9cb1b2d8944d30c5efd6ff9988c00`. Review comment
[6541125379](https://github.com/hzminhzz/copytrade-pm/pull/13#issuecomment-6541125379)
recorded offline PASS with 285 tests and CI run 41184087466. The prior judge verdict
in that PR was limited to its original offline scope and is not reused as a verdict
on this recovery.

Reverification covered shared PM03 authority, separate pod losses, exact opposing
+3/-2 netting, virtual attribution, non-resetting 300-second increases, gross and
concentration guards including pending/in-flight risk, suspended exits, cancel/fill
races, source-clock freshness, replay/reconnect and persistent HALT. The two actual
comparison CLI runs reproduced:
`f17d3048875b57b6e99ce452cd1ce3f54200c548247d74d36feed8291555bb42`.

Issue12 remains open for the explicitly retained external and scientific gates.
Synthetic broker-observation acceptance does not authenticate a real broker.

## Research branch reconciliation

- PR7 at `f931376ac2882a7e365fdc7576519b81b5024bcc` remains a historical draft.
  Its independent simulator is not merged as a competing financial authority.
  Historical model results are preserved and do not establish forward economics.
- PR15 at `6f4138d7c649fda445b24d7974abd9942e607475` supplied complementary
  E4 source/backfill/reconciliation work integrated through PR18. Its historical
  artifacts and unresolved scientific work remain separately identified.
- PR16 at `ee25379c7f5e473dcc33c6c1c808624bb886bf0c` supplied E0 complete-book
  portfolio A/B/C fidelity. PR18 resolves the useful integration against current
  PM03/PM04; merging the old branch is unnecessary.
- Complete source positions/hedges and independently established equity are required.
  One explicit proportional scalar preserves each wallet's intent. Missing hedges
  and unknown starting capital are rejection conditions, not normalization inputs.
  Source intent, risk-approved exposure and executed exposure remain distinct.

See [integration and operational procedures](RECOVERY-INTEGRATION.md).

## PM01 source and market evidence

The 36-wallet HyperX audit covered 941 pages and 104,051 raw fills:
`4d0000010fd8a1244e7b1189aa3c3392e2b6710cb4e0fd92db5db4337a17d988`.

Reauditing four existing bounded HyperX recovery generations added 2,229 unique
pre-cutoff fills (W019 2,121; VS083 108), with no in-window additions. Their exhausted
pages and nonconflicting overlaps reduced 27 position discontinuities to 15.
The merged diagnostic overlay is
`4883b71b366ed3cf2be9035d799b87233a2219999b9e1cab0cd25eff3e199f12`.
No new HyperX request spending was needed to reconcile that already acquired evidence.
Neither source timestamps nor the additional fills recreate historical first receipt
or unknown initial equity.

The initial native-market audit was 1,536/2,433 source instrument-days:
`fcb98de61ca43cdeeed0b27826593a288c3f7f3ea43299907f6a3cb1222ff758`.
The initial strict Propr display-match subset was 1,036/1,289 (80.3724%); the
strict-plus-tentative candidate subset was 1,522/1,990.
The bounded canonical candle writer publishes only new partitions with native
Hyperliquid futures/DEX identity, source metadata and content hashes. Existing
partitions are not overwritten.

The SDK adapter was repaired to use the documented read-only key transport
(`use_jwt=False`) and the required identity on both transports. A regression test
checks transport selection without real credentials. A metadata probe made from the
wrong working directory failed before a provider call; it was corrected to use the
existing data project's authorized key loader. A separate ad hoc probe accidentally
used the wrong exchange selector. Its artifact
`f5884d7d5c7d8f735ef58f8a68286c67819f4feed8d9991d2a600d75e27e62ef`
is invalid coverage evidence. The corrected exact futures-selector probe supersedes it:
`dca6107f06aed5427d66821796fbf8a9c1f682946e981c654dd6ec6be084d99b`.

The strict milestone passed at 1,161/1,289 SHA-covered days (90.0698%), scope hash
`03f58ab7c6c9812d9919ec83dc12bdcb3e96b540065f6703ccc7a1279103cb11`.
This explicitly is not minute execution/capacity proof or historical Propr listing.
Many provider candle bounds end during October 14–15. The alternate trade builder
was inspected and not used: it forward-fills intervals without observed trades,
which cannot resolve missing-minute evidence under this recovery's constraints.

Two initially acquired partial days were preserved:
MET 2026-10-15, 230 bars, hash
`0762403b8c5f500f37a735cdde946b61161e7b70e53a44d791cda8284a86d52f`;
ATOM 2026-10-14, 1,175 bars, hash
`e354340b4496bc22b4b0ee63fe2bc20b83e65accfb61413b2be712ad472bade9`.
Partial observations cannot become a complete minute path.

Final recovery published **260 new canonical native-candle partitions**:
258 full UTC minute grids and two partial days. Independent parquet inspection
verified all content hashes, native/DEX partition identity, exact UTC minute
alignment, uniqueness and OHLCV values. It found 372,925 observed minutes and
1,475 explicitly missing minutes across those new partitions; no zero fill or
existing-partition overwrite was used. Minute audit:
`44f71d53a419d150da9eedcc46cdbad6fbd5ab0e87f2e378df0950fb73d51ded`.

The final 36-wallet market audit is 1,796/2,433 SHA-covered days:
`e07fded1dbba640e5aebd76661db7182eed71a84f8303fdae68a26b048bc1465`.
Final display-scope evidence:
`aaa2ae86c03db7273834bad33110a01003233f7d21dcd3a42ee7379d3ae421bb`.

| Scope | SHA-covered instrument-days | Fraction | Meaning |
| --- | --- | --- | --- |
| Strict native display match | 1,198 / 1,289 | 92.9403% | Data acquisition milestone passed; not broker eligibility |
| Strict plus tentative native xyz | 1,782 / 1,990 | 89.5477% | Nine more covered days needed for the stated 90% day metric |
| Outside permitted display scope | 14 / 443 | 3.1603% | No scope expansion or ticker proxy used |

The remaining permitted queue contains 206 absent days plus the two existing
partial leaves. Exact provider metadata classifies 181 absent days outside published
candle bounds, 18 intersecting only partial published intervals, and seven with
unresolved native `kPEPE` provider identity. No further fully covered missing day
was identified through this approved candle path. Partial intervals were not fetched
merely to turn a day-count target green. Disposition evidence:
`b2d27297db6a7078574571d499e7307c53b08a1ffaab31d6f1dc7f4ef5dc7d55`.

A long tool request timed out after the final 43 writes. Process inspection and
partition hashes showed completion; those requests were not repeated. The
independent minute audit also includes those batches. The canonical data-project
readiness audit was regenerated at 2026-11-01T13:25:43.812983Z:
`362b56b4488bf8c7ff4bb2acec2f2a3d3d54153bc8a7548167a6309e08ac9310`.
Its overall multi-asset research-ready flag remains false; neither that catalog nor
the candle day metric establishes copytrade economics.

## Durable read-only source collection

The release at 4d6dc6e is detached and clean, with its locked source dependencies.
`copytrade-source-abc.service` is enabled and active, and the user has linger enabled.
Its controlled restart changed PID 2168800 to 2180745; successful prior generations
remained present and hash-verifiable. The over-limit legacy E4 observer was disabled;
its files and evidence were preserved.

Final snapshot at 2026-11-01T13:26:04.183251Z:
`59dcf2a9f16c2fb1b9cdb08fdf56b03d13917ca644adcacdd247dbfaa3a5ad32`.
The service remains active/enabled with PID 2180745, zero automatic restarts and
linger=yes. This v2 snapshot corrects only the release-commit field label of its
preserved v1 record; the observed clocks and raw integrity audits are unchanged.

| Portfolio | Discovered accounts observed in recent windows | Latest complete generation integrity |
| --- | --- | --- |
| A | 10 | PASS |
| B | 3 | PASS |
| C | 11, in a ten-account and one-account window | PASS |

The shared provider/IP limit is ten user-specific subscriptions. Sequential bounded
windows preserve all discovered scope over a cycle, but do not establish continuous
full-book coverage of 24 accounts. No IP-limit evasion or fabricated continuity was
used. Raw first application receipt, source clocks, census/catalog provenance,
private permissions and immutable hashes are audited. Incomplete/interrupted
generations and rotation gaps remain visible. A's all-generation flag remains false
because an interrupted generation is retained; its latest completed generation
passes. B and C pass both the latest-complete and all-generation checks at this snapshot. Capital reconciliation, continuous
book proof, scientific qualification and order authorization remain false.

Tracker, ensemble, recorder and their existing observation/outcome timers were
inspected without modification. The separate December 2 forward-assessment timer
had not run; its protected outcome data was not opened. A timer's enablement is not
an observed future result.

## PM02 campaign, economics and lifecycle

[PM02 evidence gates](PM-02-EVIDENCE-GATES.md) specify the new independently signed
whole-account v2 outcome contract and immutable selection history. Statistical
qualification uses separately scored 5/15/60-minute horizons, a declared multiplicity
family, effective sample sizes, fixed PIT cutoffs, independent uncertainty review
and a complete episode census. Earlier valid primary outcomes can support paired
risk history only as known at their original fixed looks. Missing returns remain
missing. Worst-day absolute exposure envelopes prevent quiet-day or reversal
averaging from hiding concentration.

All eight lifecycle states have durable reasons. Reusing a window cannot advance
state; RETIRED is terminal; missing evidence never counts as scientific rejection.
Actual source, follower and control outcomes remain separate; real audited evidence
is required before proposals can qualify. PM03 remains the financial authority.

The unchanged historical-only CLI output reproduced exactly:
`7bf28ee5ad53cdac9212bb0222ae1b3e0ef020eee5faae9972c53028e4b60f4f`.
Its PM01 raw source file is
`33f95784345e79ca5b1fd9e870d0882ea0e4c37e634ff316da49ab76a961e1c5`;
canonical source hash
`0797e4eb12a7501b1f0ad3280fa6ef2d9af8d1778c83648dd8f93541e6ba204b`.

The active local research campaign is
`df3b986e8f25a6ab6149451cb9293dd4ec6eb70b5278f15230fedcc1db038a6e`,
registered at 2026-11-01T13:18:04.110841Z, before the November 2 start. Four disjoint
30-day windows, 36 frozen wallets and three horizons declare 432 hypotheses.
The first possible fixed look is **2026-12-02T01:00:00Z**. No outcome has matured.
Independent review of plan custody, the global experiment family and economics
is still required; the date alone cannot qualify a wallet.

An earlier same-session registration
`6dba894b256f6cdf18de47ff9d2e000cb6a3e8d5b7e3faddd122590e0dac1f79`
was superseded before OOS after a regression exposed acceptance of as-of clocks
preceding plan registration. The guard is fixed. Cohort, source, thresholds and
windows did not change. Both files remain immutable; supersession evidence:
`6cbb41235251e21f878b34948d3b0a88de1296ac97a3fe7089d80aa08fe67a42`.
The old code pin is deliberately rejected by current code, not silently rewritten.

Actual pre-OOS CLI output under the active campaign:
`b6c1d59ea4a3a042a020891420f88f5429adf89061ff2895056b86bbe150f8d7`.
It reports **zero qualified wallets, five EMPTY seats and zero R**.

## ML4T specification and tests

[The precise specification](ML4T-PROPR-INTEGRATION.md) pins installed ml4t-live 0.1.2
and actual dirty connector file hashes. It records shadow reconciliation bypass,
lossy pending-order fingerprints, BTC/BTC-USDC alias collisions, fallback clocks,
unproven idempotency and generic floor differences. The new pure offline oracle
checks native identity, lossless decimals, order multiplicity, source/receipt
freshness, mandatory mismatch veto and retained HALT without importing a broker.

Account terms, authentic native observations, signer authority and a future
executable differential adapter remain separately required. Public Propr rule
ambiguities about payout/leverage were not resolved by invention. No trading key,
broker object, order route, challenge purchase or production execution was used.

## Verification and continuation

PR18 passed 363 tests in each suite and CI run 41305783047.
This follow-up passed the following complete local gate on 2026-11-01:

| Check | Result |
| --- | --- |
| Core pytest | 398 passed |
| Market-enabled pytest | 398 passed |
| Ruff lint | PASS |
| Ruff format | 106 files already formatted |
| uv build | sdist and wheel built |
| git diff --check | PASS |
| Historical PM02 CLI parity | Exact 7bf28ee5… match |
| Active campaign pre-OOS CLI | Zero qualified; five EMPTY; zero R |
| PM04 comparison/replay | Same f17d3048… digest in both runs |

New fixtures are synthetic engineering tests only. No fixture signature is used as
real economic evidence. Full diff review covered secrets, PIT, native identity,
evidence lineage and financial authority. CI and actual reviewer findings are
checked at the PR's actual head before merge.

Next dependencies are measurable: independently reconcile complete capital and
source scope; fill only genuinely available market/source gaps; obtain independent
receipt and v2 economic attestations; accumulate the predeclared windows and paired
risk history; evaluate only at their fixed clocks. Continue recording real gaps.
No scientific issue should close merely because these engineering gates pass.
