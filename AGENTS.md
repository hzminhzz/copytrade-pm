# copytrade-pm execution contract

**Observer proof isolation (2026-11-07):** For a public read-only observer, verify the explicitly requested SQLite portfolio seals, as-of resolved watchlist, inventory generation, native market scope and resource budgets. Missing signatures for unrelated current research priorities must not block this observer. Never admit an explicitly unverified selection; the global registry doctor still reports its research provenance as blocked. All observers remain `NO_TRADE`.


## Start with live evidence

ChatGPT is the direct executor. Do not delegate coding to another agent unless
the user explicitly asks. Preserve staged, unstaged, untracked and local-only
work; inspect GitHub and the VPS before claiming current state. Use an isolated
worktree when the primary checkout is dirty or another session owns it.

Run `~/.optmem/memo wake` at session startup and complete its pagination.
Use `memo recall` / `memo zoom` for relevant durable decisions. Memory is a
navigation aid, never current Git, SQLite, service or qualification truth.
Record concise durable changes with `memo note` (maximum 280 bytes); complete
requested compression. Never edit `~/.optmem/memory` directly. Avoid transient
counts or execution state as durable policy.

Read [the handbook](docs/INDEX.md), [architecture](docs/ARCHITECTURE.md), and the
owning [runbook](docs/RUNBOOK.md), [data guide](docs/DATA-ACQUISITION.md), or
[qualification contract](docs/QUALIFICATION.md) before changing their boundary.
Dated reports preserve historical evidence; they do not override current policy.
When auditing a Git stash that included untracked files, inspect the stable stash
commit **and its third parent** (`<stash-sha>^3`) independently. The ordinary
stash tree alone omits those untracked contents; compare full Git object IDs
against current main before classifying changes or deleting preserved work.
Read the [dated follow-up audit](docs/RECONCILIATION-FOLLOWUP-20261107.md)
for the preservation disposition, not as a live runtime status.

## Authority and repository ownership

| Authority | Owner |
| --- | --- |
| Reviewed source and change history | GitHub; verify default branch and exact SHA |
| Wallets, aliases, cohorts, exclusions, versioned portfolios | Private SQLite registry |
| Original observed source and market records | Private immutable source evidence |
| Research simulation accounting and target contracts | PM-03 / PM-04 in this repository |
| Protected follower finance, permits, durable production intents | Guardian in prop-production |
| Provider REST/WS transport and native normalization | trading-connector |
| Running revision, contract pins and service identity | Verified deployment metadata and OS evidence |
| Durable preferences and navigation | OptMem |

This repository is research / shadow only: no broker credentials, real orders,
live-risk promotion, or trading authorization. Do not change or deploy
`hyperliquid-expert-ensemble` as a side effect. The connector stays a
multi-provider library with optional ML4T bridges, not a second Guardian.

Before adding functionality, run `copytrade-pm capabilities list`,
`capabilities show <id>` and `capabilities validate`. Reuse native owners;
do not recreate the registry, PM-03 finance, replay, qualification, or broker routes.
See [agent-native operations](docs/AGENT-NATIVE-OPERATIONS.md).
Only independently exported, externally key-pinned host events qualify an
[agent trace](docs/AGENT-TRACE-EVAL-20261105.md); fixtures do not prove agent performance.

## Default sizing: FIXED_K_NATIVE_QUANTITY

Follower target notional = signed per-pod `k * leader_native_quantity * source_mark`;
convert at an independent follower quote. Leader whole-account NAV, unified
collateral, unrelated child-account NAV, spot and vault balances are optional
diagnostics. Missing leader NAV must not interrupt valid fixed-k work.

`ALLOCATION_OVER_LIVE_NAV` is explicit legacy opt-in and still requires authentic
point-in-time leader NAV. Preserve old E0 / equity-relative studies and claims.

Always require authentic selected account identity, complete positions within
that selected perp scope, DEX/market census, exits, causal receipts, valid signed k,
verified follower equity/headroom/inventory, broker reconciliation, fresh markets,
lot/margin/capacity constraints, concentration/gross limits, pod losses,
daily/trailing floors, durable HALT and separate order authorization.
A $200 stop is a trigger, not a guaranteed maximum loss under gaps or slippage.
See [the binding sizing policy](docs/RISK-BUDGETED-K-SIZING-20261106.md).

## MANDATORY REGISTRY-FIRST workflow

For wallets, cohorts, exclusions, portfolios, paper runs or readiness, follow
[WALLET-REGISTRY-AGENT-WORKFLOW](docs/WALLET-REGISTRY-AGENT-WORKFLOW.md).
[WALLET-STATUS](docs/WALLET-STATUS.md) retains dated source evidence; verify the
current registry before treating any of its counts as current.
From a verified checkout, begin with:

```bash
uv run --frozen --group dev copytrade-wallet-registry doctor
uv run --frozen --group dev copytrade-wallet-registry status
uv run --frozen --group dev copytrade-wallet-registry native status
uv run --frozen --group dev python scripts/registry_release.py verify
```

Separate physical integrity, logical inventory SHA, signed selection provenance
and historical import lineage. Doctor exit 2 with physical integrity VERIFIED and
BLOCKED_MISSING_EXTERNAL_PROOF is still a blocked selection, not corruption.
Read-only metadata release compatibility never admits that selection.
Do not manufacture signatures, reseal history, change frozen membership or use
an older database to erase an unresolved provenance failure.

Use `portfolio --current` for new research selection and namespace/version/as-of
for specific identities; `q3/B` differs from `gemini.phase5/B`. Query
`wallet --alias`, `cohort`, and `paper` as needed. A later-resolved alias does
not become known at an earlier seal. SQLite research selection is not a worker,
financial account, scientific qualification or order permit.

Native writes require explicit reviewed manifests, exact inventory SHA, private
permissions and verified online backups. `native lock --apply` fences legacy
imports; `native register` appends cohorts; `native exclude` appends exclusions
without revocations or inferred owner-review attestation.
See [native registry controls](docs/SQLITE-NATIVE-LEGACY-LOCK-20261105.md) and
[release / rollback](docs/WALLET-REGISTRY-RELEASE-RUNBOOK.md).
Do not run these writes as an incidental diagnostic.

## Source, observer and paper boundaries

Copy only explicitly selected Hyperliquid perp positions, including required
main/HIP-3 DEX scope. Official allDexsClearinghouseState and the relevant official
scope census are positional evidence; collateral diagnostics cannot veto fixed-k.
Do not infer equity-relative weights from quote balances or summed DEX NAV.
Keep source event, local receipt, decision and fill clocks distinct.

Historical HyperX/Vike recovery cannot manufacture earlier first-known receipts.
Keep raw pages, private alias maps, authenticated responses, credentials, market
Parquet and original evidence outside Git. Preserve frozen PM-01 membership,
source hashes and the `pm01_fill_only_replay_v2` consumer interface.
Use [Vike recovery](docs/VIKE-DATA-RECOVERY-20261106.md) only within its explicit
bounded research contract; no automatic production ingestion or credential export.
The separate [2026-11-08 Vike read-only observer candidate](docs/FORWARD-PAPER-VIKE-MIGRATION-20261108.md)
is a commit-pinned additive source-fill and minute-price research intake:
it does not replace the official full-position owner, qualify v4 paper
execution, authorize trading or retire CCXT. Never expose the dedicated key
in Git, logs, process arguments or documentation; load only from the
quant-owned private environment file.

**Position-first V4 decision (2026-11-08):** Official complete selected-account
`allDexsClearinghouseState` transitions are the ONLY source of new desired
exposure for V4 paper. Vike fills are optional research/consistency evidence,
not a mandatory fill-to-position reconstruction or signal. Use the existing
atomic official stream/source journal, and require a linked verified
`OBSERVED_STATE_CHANGE` (not BASELINE, GAP, recovery or unverifiable flat)
before creating a non-resetting first-known T+300 entry. At due require the
latest complete valid official position book; source reductions and risk exits
remain immediate. Preserve PM-03/04 finance, frozen fixed k, separate pod
budgets, unresolved inventory and one terminal modeled attempt. No funded
authorization or service cutover. See
[the binding decision](docs/decisions/2026-11-08-position-first-t300.md).
For user-authorized V4 read-only installation and rollback, use the
[separate V4 release runbook](docs/V4-POSITION-FIRST-DEPLOY-20261108.md).
The later [16-portfolio V4 virtual-paper study](docs/V4-SIXTEEN-PAPER-20261109.md)
uses separately derived, explicitly non-qualifying private research scenarios;
preserve the original exclusion and historical selection records.

For persistent acquisition use [the continuous observer runbook](docs/FORWARD-PAPER-CONTINUOUS-OBSERVER.md).
Preflight and diagnostics do not admit startup. Measure shared-IP budgets and
selected scope; retain disconnects, excluded connection baselines and later
recovery clocks. Public observer PIDs and receipt counts are not protected finance.
Continuous public cutover retains #141/#142 evidence gates.

For protected standby, watchdog, HALT, installation and rollback use
[protected operations](docs/FORWARD-PAPER-PROTECTED-OPS-STAGING-20261105.md).
Staged units and quant-owned heartbeats cannot attest independent root-owned
financial workers. Inspect real OS identity, pinned release and financial journals.
The separate prop-production Guardian services must not be confused with these units.

## MANDATORY contract EV tool and scientific evidence

For every portfolio / prop-challenge comparison, use the native
`research.contract_selector` capability first: `copytrade-pm contracts rules`, then
`copytrade-pm contracts compare --portfolio NAMESPACE/ID --tape PRIVATE_TAPE`
with SQLite-resolved portfolios and actual net follower tapes.
Neither a passing tool result nor a synthetic estimate is permission to trade.
See [contract EV](docs/CONTRACT-PORTFOLIO-EV-TOOL-20261105.md) and
[actuary assumptions](docs/CONTRACT-ACTUARY-RESEARCH-20261105.md).
Do not build another simulator or substitute scaled leader PnL.

Require matched point-in-time follower MTM, first-known clocks, complete costs,
funding, capacity, source identity, frozen train/OOS decisions and authenticated
account-specific rules. Leader NAV is required only by the explicit legacy mode.
Missing actual follower evidence stays BLOCKED. Synthetic EV is SCENARIO_ONLY;
finite-horizon payouts are not infinite-horizon LTV or a purchase recommendation.
Never alter scientific thresholds to make an engineering gate pass.

## Dashboard: Marimo retired, Grafana is the operator surface

The Marimo operator UI was retired early at the operator's direction on
2026-11-08, **before** #190/#191 formal cutover acceptance. This is an
observed out-of-sequence deployment state, not acceptance/closure of #192.
The `copytrade-dashboard` user service is disabled, the Tailscale HTTPS 8443 route
is removed, and the presentation modules (`pages/`, `server.py`,
`navigation.py`, `views.py`, `phase2_views.py`, `release.py`) and
`ops/dashboard-quant/` are deleted. The dated `docs/DASHBOARD-*.md` records are
historical evidence; they do not describe current runtime.

Preserved deliberately: `DashboardReader` (`adapter.py`), the registry and
owner-capture adapters, `notifications.py` evidence, `evidence_plane.py`,
`grafana_projection.py`, `grafana_capabilities.py` and the Polars point
reduction in `chart_data.py`. Do not reintroduce a Marimo mount, a notebook
route or a second presentation authority.

Grafana is the only operator surface: five dashboards provisioned from
`ops/grafana-phase1/dashboards/` behind the owner-only Tailscale HTTPS 8444
ingress. Retirement does not close #190/#191. The Grafana stack is
DEPLOYED_READ_ONLY with the synthetic fixture still enabled, authentic protected
Guardian finance not admitted and full HTTPS 8443 rollback not demonstrated.
The retained Marimo wheel passed a local-only 403/boot probe on 2026-11-08. Read
retirement as neither Grafana acceptance nor trading authority.

The notification backend is NOT_CONFIGURED for external distribution; local ACK
never clears Guardian HALT. URL portfolio/UTC scope is display-navigation
context, never production selection. Browser and source tests cannot qualify
live Guardian cadence, protected ACL, private ingress, source finance or a
pinned installed runtime. Browser acceptance runs on the local obscura CDP
server; verify actual CSS viewport dimensions, because an outer window size can
silently clamp phone tests.

## Engineering merge is not runtime promotion (owner decision 2026-11-10)

Treat Git integration and operational authorization as independent decisions.
For additive, nonactivating research/read-only changes, merging requires verified
exact-head engineering, no protected side effects, compatible contracts and actual
GitHub branch/review rules. Missing future follower PnL, calibration, deployed
canary, k-release activation or trading approval **do not block that merge**.
Track them in separate open issues and never claim their status improved.

Every attempted operation still requires its own action-specific proof. Read-only
SHADOW publication needs controlled ingress/redaction and reversible release;
risk-off changes need authentic state and the risk owner; risk increases, active
k changes and real orders need original economic, financial and independent
operational approval at their actual authority seam. Git history never grants
Guardian/broker or PM03/PM04 permission. See
[the decision record](docs/decisions/2026-11-10-merge-vs-runtime-promotion.md).
Never remove a fail-closed
runtime guard merely to make a PR mergeable.

## Review, verification and continuation

Routine authorized engineering proceeds without per-turn judge calls.
Deterministic gates remain mandatory for protected metadata/qualification writes,
frozen policy changes and risk-sensitive decisions. Independent signoff remains
required for material scientific methods, roster promotions/deletions,
qualification-policy changes and live-risk authority. An LLM verdict cannot
override failed evidence gates. See [governance](docs/GOVERNANCE-GATES.md).
Review unavailability blocks only that protected decision.

GitHub Actions is optional for this program; respect actual branch protections.
Verify clean commit-bound core and all-extra suites, Ruff, package build and
relevant cross-repository consumer tests. Update the owning guide when changing
a CLI, schema, policy or release boundary. The prop-production compatibility
manifest and `bash scripts/verify-local.sh all` bind the three repository revisions.

On ordinary failures follow [blocker recovery](docs/BLOCKER-RECOVERY.md):
diagnose, repair, retest, resume the original objective and unrelated unblocked work.
Preserve historical failures and negative evidence. Escalate only proven external
dependencies or separately protected authority.

Report IMPLEMENTED, ENGINEERING VERIFIED, MERGED, DEPLOYED, RUNNING OBSERVED,
SCIENTIFICALLY QUALIFIED and TRADING AUTHORIZED separately. Never infer an
installed revision, healthy worker or alpha from Git history or passing tests.
