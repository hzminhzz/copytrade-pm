# copytrade-pm execution contract

## 1. Scope and authority

- **Research / shadow only:** no broker credentials, real orders, live-risk promotion, or trading authorization; every observer remains `NO_TRADE`.
- Never change or deploy `hyperliquid-expert-ensemble` as a side effect.
- GitHub owns reviewed source; verify the default branch and exact commit SHA, not the assumed checkout.
- The private SQLite registry owns wallet identities, aliases, cohorts, exclusions and versioned portfolio selections; private immutable evidence owns original source/market observations.
- PM-03/PM-04 own research simulation finance; `prop-production` Guardian exclusively owns protected follower finance, permits and durable production intents.
- `trading-connector` owns provider REST/WS transport and normalization, not a second Guardian; do not duplicate registry, replay, qualification, broker routes or existing PM-03/PM-04 owners.
- Installed revision, contract pins and service identity come from deployed metadata and OS evidence; OptMem is navigation, never operational truth.
- Before adding a capability, run `copytrade-pm capabilities list`, `copytrade-pm capabilities show <id>` and `copytrade-pm capabilities validate`; follow [agent operations](docs/AGENT-NATIVE-OPERATIONS.md).
- Agent-performance claims require independently exported, externally key-pinned host events; fixtures do not qualify as agent traces. See [trace evidence](docs/AGENT-TRACE-EVAL-20261105.md).

## 2. Session evidence and preservation

- ChatGPT executes directly; do not delegate coding unless explicitly requested.
- Inspect actual Git status, branch, worktrees, GitHub and relevant VPS runtime before claiming state; preserve staged, unstaged, untracked, stashed and local-only work.
- Use an isolated worktree when the primary checkout is dirty or another session owns it; never reset, clean, overwrite or discard unreviewed work.
- Run `~/.optmem/memo wake` at startup and complete its pagination; use `memo recall` / `memo zoom` for pertinent decisions.
- Record durable changes with `memo note` (maximum 280 bytes); never edit `~/.optmem/memory` directly or treat memory as Git, registry, runtime or qualification evidence.
- Read [INDEX](docs/INDEX.md), [ARCHITECTURE](docs/ARCHITECTURE.md) and the owning [RUNBOOK](docs/RUNBOOK.md), [DATA-ACQUISITION](docs/DATA-ACQUISITION.md) or [QUALIFICATION](docs/QUALIFICATION.md) before changing a boundary.
- Dated evidence reports are historical, not current policy, deployment status or acceptance.
- When auditing a stash containing untracked files, inspect its stable commit and `<stash-sha>^3` separately; compare Git object IDs before discarding anything. See [reconciliation follow-up](docs/RECONCILIATION-FOLLOWUP-20261107.md).

## 3. MANDATORY REGISTRY-FIRST workflow

- For wallets, cohorts, exclusions, portfolios, paper runs and readiness, follow [WALLET-REGISTRY-AGENT-WORKFLOW](docs/WALLET-REGISTRY-AGENT-WORKFLOW.md); [WALLET-STATUS](docs/WALLET-STATUS.md) is dated evidence, not a current count.
- From a verified checkout, inspect the registry and installed metadata without writing:

```bash
uv run --frozen --group dev copytrade-wallet-registry doctor
uv run --frozen --group dev copytrade-wallet-registry status
uv run --frozen --group dev copytrade-wallet-registry native status
uv run --frozen --group dev python scripts/registry_release.py verify
```

- **Independent checks:** physical SQLite integrity, logical `inventory_sha256`, signed selection provenance and historical `source_manifest_sha256` import lineage; never collapse one into another.
- A doctor exit 2 with physical integrity `VERIFIED` and `BLOCKED_MISSING_EXTERNAL_PROOF` means selection provenance blocked, **not** database corruption; read-only release compatibility does not admit the blocked selection.
- Public read-only observers verify only their explicitly requested SQLite portfolio seals, as-of watchlist, inventory generation, native market scope and resource budgets; unrelated missing research-priority signatures must not block that observer.
- Never admit an explicitly unverified selection; preserve the global registry doctor's blocked research-provenance result and `NO_TRADE`.
- Never manufacture signatures, reseal history, change frozen membership or use an older database to erase a provenance failure.
- Use `portfolio --current` for new research, namespace/version/as-of for fixed identities (`q3/B` differs from `gemini.phase5/B`), and `wallet --alias`, `cohort`, `paper` for targeted inspection.
- Resolve aliases only as known at the actual cutoff; a later alias resolution cannot rewrite an earlier seal. Registry membership is not worker health, finance, scientific qualification or an order permit.
- Native writes require **explicit reviewed manifests, exact inventory SHA, private permissions and verified online backups**; never run writes as an incidental diagnostic.
- `native lock --apply` fences legacy imports; `native register` appends cohorts; `native exclude` appends exclusions without inferred owner-review attestations or silent revocations.
- Follow [native registry controls](docs/SQLITE-NATIVE-LEGACY-LOCK-20261105.md) and [release/rollback](docs/WALLET-REGISTRY-RELEASE-RUNBOOK.md) before any authorized mutation.

## 4. Fixed-k sizing, official source and observer

- Default policy is `FIXED_K_NATIVE_QUANTITY`: follower target notional = signed per-pod `k * leader_native_quantity * source_mark`, converted at an independent follower quote.
- Leader whole-account NAV, unified collateral, unrelated child NAV, spot and vault balances are optional diagnostics; their absence must not block otherwise valid fixed-k research.
- `ALLOCATION_OVER_LIVE_NAV` is **explicit legacy opt-in** and requires authentic point-in-time leader NAV; preserve old E0/equity-relative studies and claims.
- Require authentic selected-account identity; complete selected-perp positions/exits and main/HIP-3 DEX/market census; causal receipts; valid signed k; fresh independent market quotes.
- Require verified **follower** equity, headroom, inventory and broker reconciliation; lot/margin/capacity, gross/concentration and pod-loss limits; daily/trailing floors, durable HALT and **separate order authorization** at the protected boundary.
- A `$200` stop is a trigger, not a guaranteed loss cap under gaps/slippage. See [binding sizing policy](docs/RISK-BUDGETED-K-SIZING-20261106.md).
- Official complete selected-account `allDexsClearinghouseState` and official scope census are positional authority; quote balances, summed DEX NAV, collateral diagnostics, Vike fills or fill-to-position reconstruction cannot replace that book.
- For V4, only a verified SHA-linked `OBSERVED_STATE_CHANGE` in the existing atomic official stream/source journal can create desired new exposure; `BASELINE`, `GAP`, unchanged, recovery and unverifiable flat cannot start an entry.
- The first genuine **local first-known** transition starts a non-resetting `T+300` timer; later source changes update targets, not T0. At due require the latest complete valid official position book.
- Source reductions and risk exits remain immediate; retain frozen k, separate pod budgets, unresolved inventory, PM-03/PM-04 finance and **one terminal modeled attempt**. No funded authorization or service cutover follows.
- Keep source-event, first-local-receipt, decision and fill clocks distinct; historical HyperX/Vike recovery never manufactures an earlier first-known receipt.
- Preserve frozen PM-01 membership, source hashes and the `pm01_fill_only_replay_v2` consumer interface.
- Keep raw pages, private alias maps, authenticated responses, credentials, market Parquet and original source evidence outside Git; read-only Vike data keys belong only in the quant-owned private environment, never Git/logs/process arguments/docs.
- Vike is bounded read-only research intake, not production ingestion, a mandatory V4 source trigger or replacement for the official book/CCXT by implication.
- Before persistent public observation, verify selected scope, shared-IP budgets, disconnect/reconnect clocks and continuous admission; preflight, PIDs or receipt counts do not prove protected finance; public cutover retains `#141/#142` evidence gates.
- Protected standby/rollback requires independent root-owned worker identity, pinned release and financial journal evidence; quant-owned heartbeat or staged unit is not Guardian proof.
- Binding docs: [V4 position-first ADR](docs/decisions/2026-11-08-position-first-t300.md), [V4 release](docs/V4-POSITION-FIRST-DEPLOY-20261108.md), [Vike research](docs/FORWARD-PAPER-VIKE-MIGRATION-20261108.md), [Vike recovery](docs/VIKE-DATA-RECOVERY-20261106.md).
- Operating docs: [continuous observer](docs/FORWARD-PAPER-CONTINUOUS-OBSERVER.md), [protected operations](docs/FORWARD-PAPER-PROTECTED-OPS-STAGING-20261105.md).

## 5. Research, contract EV and qualification

- For every portfolio/prop-challenge comparison, use native `research.contract_selector`: `copytrade-pm contracts rules`, then `copytrade-pm contracts compare --portfolio NAMESPACE/ID --tape PRIVATE_TAPE` with SQLite-resolved selections and actual net follower tapes.
- Do not build a duplicate simulator or substitute scaled leader PnL.
- Require matched point-in-time follower MTM, first-known clocks, complete execution costs/funding/capacity, source identity, frozen train/OOS decisions and authenticated account-specific rules.
- Missing real follower evidence stays `BLOCKED`; synthetic EV is `SCENARIO_ONLY`, never alpha, a funded permit, infinite-horizon LTV or a purchase recommendation.
- Never alter scientific thresholds to make an engineering gate pass; legacy leader NAV is required only when the legacy sizing contract is explicitly selected.
- See [QUALIFICATION](docs/QUALIFICATION.md), [contract EV](docs/CONTRACT-PORTFOLIO-EV-TOOL-20261105.md) and [actuarial assumptions](docs/CONTRACT-ACTUARY-RESEARCH-20261105.md).

## 6. Grafana operator surface

- **Grafana is the only operator surface; Marimo remains retired.** Never restore a Marimo mount, notebook route or second presentation authority.
- Preserve `DashboardReader` (`adapter.py`), registry/owner-capture adapters, `notifications.py`, `evidence_plane.py`, `grafana_projection.py`, `grafana_capabilities.py` and `chart_data.py`; do not conflate display code with finance authority.
- `ops/grafana-phase1/dashboards/` is presentation configuration; verify actual installed Grafana, owner-only Tailscale HTTPS `8444` and rollback before operational claims. The retired `copytrade-dashboard` / HTTPS `8443` route is not current authority.
- Out-of-sequence retirement does **not** imply `#190/#191/#192` acceptance, protected Guardian evidence, deployment health or trading authorization.
- Notification local ACK never clears Guardian HALT; URL portfolio/UTC scope is display navigation, not production selection. Browser/CSS/obscura checks alone cannot certify ACL, Guardian cadence, source finance or installed revision.
- See [dashboard retirement](docs/DASHBOARD-RETIREMENT-20261108.md) and [Grafana read model](docs/GRAFANA-OPERATIONAL-READ-MODEL-20261108.md) for procedures and dated status.

## 7. Governance, verification and closeout

- Routine authorized engineering proceeds without per-turn review; protected metadata/qualification writes, frozen policy changes and material scientific methods, roster promotions/deletions or live-risk decisions retain independent signoff and deterministic gates.
- An LLM verdict **cannot override failed evidence gates**; unavailable review blocks only the protected decision. See [GOVERNANCE-GATES](docs/GOVERNANCE-GATES.md).
- Verify the actual branch protections; GitHub Actions is optional, not substitute evidence.
- For code changes, record clean commit-bound core/all-extra test results, Ruff, package build and relevant cross-repository consumer tests; update the owning doc on CLI, schema, policy or release-boundary changes.
- The `prop-production` compatibility manifest and `bash scripts/verify-local.sh all` (run in that repository, not `copytrade-pm`) bind all three repository revisions.
- On ordinary failure, diagnose -> repair -> retest -> resume the objective and independent unblocked work; preserve negative evidence and escalate only a proven external dependency or separately protected authority. See [BLOCKER-RECOVERY](docs/BLOCKER-RECOVERY.md).
- Report **IMPLEMENTED / ENGINEERING VERIFIED / MERGED / DEPLOYED / RUNNING OBSERVED / SCIENTIFICALLY QUALIFIED / TRADING AUTHORIZED** as separate states, with evidence for each; never infer one from another.
- `IMPLEMENTED` requires inspected source/diff; `ENGINEERING VERIFIED` requires exact tested SHA, commands, results and disclosed failures; `MERGED` requires target-branch commit.
- `DEPLOYED` requires installed release metadata; `RUNNING OBSERVED` requires OS/service identity and relevant healthy operational observations, not merely a PID.
- `SCIENTIFICALLY QUALIFIED` requires independent, PIT/OOS, cost-complete follower evidence under the qualification contract; `TRADING AUTHORIZED` requires separate explicit trading authority, never supplied by this repo.
- Never infer an installed revision, healthy worker or alpha from Git history or passing tests; if evidence is missing, report the exact `BLOCKED` / `UNKNOWN` limitation.
