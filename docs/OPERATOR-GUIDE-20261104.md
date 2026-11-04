# Copytrade-PM VPS operator guide (read-only reference)

**Version:** 2026-11-04. **Verified deployment:** pinned on-demand registry at `29156de99cd2a670f48757fea283bc6a5aa109d5`. This is a dated checkpoint: always re-run live checks. For the detailed operational contract, read [the mandatory registry-first workflow](WALLET-REGISTRY-AGENT-WORKFLOW.md) and [registry release runbook](WALLET-REGISTRY-RELEASE-RUNBOOK.md). This guide adds no trading authority.

## 2026-11-05 on-demand CLI upgrade checkpoint

The agent-native read-only release controller activated main commit
`8bdaf1e352193554c052167bc8e13e6a66033a95` from a clean detached
worktree. Source generation `e2836aab5ef6ef79306e9dfe732d8768c3b1ca6af29efbda066b37f03646a18f`
remained unchanged, preactivation backup was verified, and tracker/ensemble/
Source-ABC retained their original PIDs. Current release must be reverified
on every later session. Use this installed release's new CLI with:

```bash
REG="$HOME/.local/share/copytrade/registry/release-control/current"
uv run --project "$REG" --offline --frozen --no-dev copytrade-pm capabilities validate --json
uv run --project "$REG" --offline --frozen --no-dev copytrade-pm portfolios current
uv run --project "$REG" --offline --frozen --no-dev copytrade-pm health
```

The P1 wallet/research/runtime extensions were **later** independently
merged and activated at `00a6b1e260ad9983b8497dcc35922a288f87d09b`,
with source SHA and original service PIDs unchanged (dated 2026-11-05
checkpoint). Their owner and safety boundaries are documented in
[the P1 acceptance guide](AGENT-OPERATIONS-P1-ACCEPTANCE-20261105.md).
The separate [P2 agent-trace benchmark](AGENT-TRACE-EVAL-20261105.md)
requires independently captured, signed host tool events before declaring
real LLM tool-choice effectiveness. Reverify the current pinned release
rather than treating either historical SHA as today's deployment.

## 1. One-minute read-only check

Use the **installed pinned release**, not a possibly stale or dirty developer checkout:

```bash
REG="$HOME/.local/share/copytrade/registry/release-control/current"
reg() {
  uv run --project "$REG" --offline --frozen --no-dev \
    copytrade-wallet-registry "$@"
}
reg doctor
reg status
reg portfolio --current
reg runtime
reg paper
reg qualification
```

Expected on the dated deployment: `doctor.counts_match=true` and `freshness=CURRENT`; 264 configured/subscribed wallets, 158 research wallets, 22 exclusions, 11 sealed portfolio definitions, 0 indexed paper runs. Source manifest `e2836aab5ef6ef79306e9dfe732d8768c3b1ca6af29efbda066b37f03646a18f`, observed at `2026-11-04T09:36:57.574969+00:00`. **Current counts are not static; live output overrides dated documentation.**

`runtime.recent_outbox_observation_1h` counts indexed events only. It does **not** prove independent wallet runtime admission or complete receipt health. `paper` is not a substitute for real run manifest, financial journal, worker PID and fresh signed transport/source/market heartbeat. Qualification and trading authorization are separate gates.

## 2. Wallet and portfolio discovery

With the `reg` function from Section 1:

```bash
reg portfolio                  # all saved sealed definitions
reg portfolio --current        # NEW research selection, not running papers
reg portfolio gemini.phase4/E6 # primary five-wallet research slate
reg portfolio gemini.phase4/E2 # three-wallet challenger
reg portfolio P1               # historical/Forward-Paper baseline
reg portfolio P14              # archived old challenger / FP baseline
reg portfolio q3/B             # distinct from gemini.phase5/B
reg portfolio gemini.phase5/B
reg wallet --alias W083
reg cohort research-108
reg cohort nansen-20
reg cohort hyperx-30
```

Use `reg portfolio P1 --asof 2026-11-02T17:52:22+00:00` for an as-known historical query, and `wallet --alias ... --asof ...` to resolve aliases at a specific first-known time. A vendor fill timestamp must never substitute for the time that identity became known locally. Ambiguous display names or post-seal alias matches fail closed.

At the verified V2 selection cut, `gemini.phase4/E6` consists of `ACT04`, `CM-002`, `S051-BTC`, `S053-HYPE`, `Whale_0x5f94`; `gemini.phase4/E2` consists of `ACT04`, `S051-BTC`, `S053-HYPE`. These are **research-only selections**; `P1` and `P14` remain separate sealed financial experiments. Neither selection nor Gemini `k` values authorize paper enrollment or broker orders.

## 3. What is actually operating

```bash
systemctl --user show copytrade-tracker.service \
  copytrade-ensemble.service copytrade-source-abc.service \
  copytrade-paper-p1.service copytrade-paper-p14.service \
  -p Id -p LoadState -p ActiveState -p MainPID --no-pager
```

At the deployment checkpoint: tracker, ensemble and Source-ABC collector were active on **separately pinned legacy releases**; the registry activation did **not** restart or upgrade them. Source-ABC sometimes emits unobserved subaccounts; it does not establish continuous atomic whole-wallet NAV. P1/P14/watchdog protected systemd units were **not installed**, and `PAPER_RUNNING=UNKNOWN`.

For read-only diagnostic logs: `journalctl --user -u copytrade-tracker.service -n 50 --no-pager`. Use the analogous source/ensemble unit as needed. Do not expose private wallet addresses, SQLite files, credentials or Telegram tokens.

## 4. Source, software and status evidence

| Question | Source of truth | Do not infer |
| --- | --- | --- |
| Which portfolio was approved at which time? | Git-pinned decision SHA + registry `portfolio --asof` | A running account |
| Which wallets are indexed? | `doctor`, `wallet`, `cohort`, `portfolio` | Independent equity or complete receipts |
| What is installed? | `registry_release.py verify` and pinned `current` | All services were upgraded |
| Is a worker operating? | Real protected worker + run/journal/heartbeat | Active tracker or synthetic status proves paper |
| Is it qualified or permitted to trade? | Independent prospective follower economics + explicit separate authorization | CI pass, Gemini PnL, historical oracle or model `k` values |

State labels matter: `ACTIVE_READ_ONLY_VERIFIED` means research metadata release integrity; `RESEARCH_SELECTION_ONLY` means a study selection; `UNKNOWN`, `NOT_ESTABLISHED` and `BLOCKED_NO_TRADE` mean no positive promotion.

## 5. Offline research is explicit and separate

The [Milestone #2 historical Polars job](OFFLINE-MILESTONE2-ENGINEERING-ACCEPTANCE-20261104.md) is **screening-only**. Its [canonical job manifest](OFFLINE-HL94-ORACLE-JOB-20261104.json) can be run explicitly from a clean current checkout using `python -m copytrade_pm.pm_offline_job` with the documented source and native 1m market roots in [RUNBOOK](RUNBOOK.md). Do not invoke large historical sweeps, paid acquisition or Gemini reruns just to answer a lookup question. Historical source fills do not prove as-of whole-account equity or real follower execution.

## 6. Forward-Paper remains blocked

Run only read-only preflight from a clean reviewed checkout:

```bash
uv run --frozen --group dev copytrade-pm-paper-preflight \
  --release-root "$HOME/.local/share/copytrade/releases" \
  --state-root "$HOME/.local/share/copytrade/reports" \
  --deployment-uid 1001 --state-uid 1001 --inspect-services
```

At the 4 November deployment, this returned `status=BLOCKED`, `order_route=NONE`, `cutover_performed=false`. The merged code's unsigned Forward-Paper wheel is **staged but not activated**. Missing gates include frozen first-known P1/P14 identity, whole parent/subaccount/spot/vault NAV/collateral/hedges, complete market capacity/session, protected OS identity, signed immutable release and independently supervised watchdog. No protected paper worker or broker route was deployed. See [live readiness](FORWARD-PAPER-READINESS-20261104.md) and [protected-service preflight](FORWARD-PAPER-PROTECTED-SERVICE-20261104.md).

## 7. Versioned release / rollback (operator action only)

**Do not run from the dirty physical checkout.** Open a clean isolated DevSpace worktree at the reviewed SHA. Confirm CI, full tests, Ruff, source doctor and service PID inventory. For a reviewed on-demand registry update only:

```bash
uv run --frozen --group dev python scripts/registry_release.py preview
# Only after review of exact SHA, source generation, backups and service state:
uv run --frozen --group dev python scripts/registry_release.py activate
uv run --frozen --group dev python scripts/registry_release.py verify
```

The activation creates a private registry-only preactivation SQLite backup; tracker, ensemble, Source-ABC, paper services, financial journals and broker are **outside** its mutation scope. `rollback` is a **state-changing pointer operation** and may fail when an older release cannot read the current v8 SQLite/source generation. It does not restore the database. `repair` is reserved for a verified interrupted pointer/state transaction. Never force either, reset an inventory, or restart protected services to satisfy a check.

`sync --dry-run` is inspection; `sync --apply`, signed-selection `--apply`, release `activate`, rollback and broker operations are **not** everyday read-only queries. Future research selections require canonical aliases, versioned namespace, separately verified signing key/approval and explicit private import; an imported decision does not create a paper run.

## 8. Failure response

| Symptom | First check | Response |
| --- | --- | --- |
| Wallet / portfolio missing | `reg doctor`, `reg portfolio`, `reg wallet --alias`, as-of/namespace | Report unresolved; do not guess |
| `doctor` stale or SHA mismatch | `reg status`, `reg sync --dry-run` | Stop writes; inspect source generation and backup |
| Active service, missing events | `systemctl --user show`, `reg runtime`, journal | Receipt health remains UNKNOWN; diagnose before restart |
| Research selection but no paper | `reg paper`, protected worker/heartbeat | Expected: no paper admission from registry |
| Paper preflight fails | Identity, whole NAV, quotes/session, protected units | Keep `BLOCKED_NO_TRADE` |
| Rollback refused | Target release doctor and schema/source compatibility | Leave active pointer intact, review migration |

**Mandatory operator rule:** Before acting on any wallet or portfolio, verify the current Git revision, registry generation SHA, selection namespace/as-of, installed release, actual worker evidence, source economics and trading authority. Missing evidence stays `UNKNOWN` or `BLOCKED`. Read [AGENTS.md](../AGENTS.md) and [the agent workflow](WALLET-REGISTRY-AGENT-WORKFLOW.md) before any automated decision.
