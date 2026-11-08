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

## Dashboard V1 phase boundary

Phase 2 source implementations and fail-closed owner-capture consumer are
independently tested; do not confuse source merge with live capture permission,
installed release, signed pod budget, broker PnL or trading authorization.
See `docs/DASHBOARD-PHASE2.md` and prop-production's owner projection contract.
Phase 3 implements independent dry-run incident delivery, mobile navigation,
security regression tests and *disposable staging-only* packaging; see
`docs/DASHBOARD-PHASE3.md`. The approved single-app topology uses
`pages/dashboard.py` as the **only** run-only Marimo ASGI mount; the eight
existing view notebooks are lazy embedded presentation modules under native
`mo.routes()` hash navigation. Never reintroduce independent notebook mounts,
server-side routing state or a global eager reactive query graph. The exact
same-origin, authenticated, bounded Marimo UI POST allowlist is
`function_call` and `set_ui_element_value` only; do not enable arbitrary
kernel execution or filesystem mutation routes.
The notification backend is NOT_CONFIGURED for external distribution; local ACK never clears Guardian HALT. URL portfolio/UTC
scope is display-navigation context, never production selection. Browser and
source tests cannot qualify live Guardian cadence, protected ACL, private ingress,
source finance or a pinned installed runtime. TD-13 requires independent
noninterference/performance evidence; TD-14 needs separately authorized pinned
reversible installation. Never grant Marimo journal access or activate protected
capture/Guardian services as a shortcut.

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
