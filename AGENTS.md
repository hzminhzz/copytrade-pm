## Mandatory native-first capability discovery

Before implementing new functionality, query `copytrade-pm capabilities list`,
`copytrade-pm capabilities show <id>` and `copytrade-pm capabilities validate`.
Read the owning module/contracts before adding another implementation; reuse or
extend the existing native interface. For measuring **actual agent choices**,
use [the host-trace evaluation contract](docs/AGENT-TRACE-EVAL-20261105.md):
only independently exported and externally key-pinned host tool events may
qualify. Synthetic, manual and transcript-reconstructed traces remain
`UNVERIFIED_TOOL_TRACE`; do not assert an empirical agent pass from CLI tests.
Do not recreate Wallet Registry, PM-03 finance, research replay, evidence
qualification or broker routes. Follow
[the agent-native operator guide](docs/AGENT-NATIVE-OPERATIONS.md), its
mechanical catalog checks and the registry-first workflow for wallet/portfolio
questions. A missing service must remain `UNKNOWN` or `NOT_RUNNING`, never
inferred as healthy from Git or tests. Native `wallets list` uses a private
address-redacted registry view; `research list/show --cache-root` verifies
only canonical SHA-sealed job reports from that explicit root. `health` verifies
the installed registry release separately from Git and checks scoped protected
paper OS units; a PID or public quote receipt never proves a healthy worker,
whole-wallet economics, or market-provider readiness. See
[the operator contract](docs/AGENT-NATIVE-OPERATIONS.md).

## Memory

Your memory is OptMem:
- The tool is `~/.optmem/memo`
- Your memories are in `~/.optmem/memory`

OptMem outlives every session, compaction, model and vendor change.
Without it you do not know who you are, or what was decided and tried.

### At startup: activating OptMem (mandatory)

Run `~/.optmem/memo wake` before any other tool call, in every session, and
then do exactly what it prints, to the end of its output.

### While working: register memories (mandatory)

Call `~/.optmem/memo note "<1 line, max 280 bytes>"` whenever you learn
something new, or something worth keeping happens. That covers a task
worth real effort, a fact or insight the user teaches you, anything you
learn about their life (even indirectly), any event of lasting effect.

Do not register redundant memories.

If `~/.optmem/memo note` asks a compression: do it before your next action.

Never edit or delete anything under `~/.optmem/memory`: the tool manages it.

### When you need an old memory: search, or navigate

`~/.optmem/memo recall <regex>` searches every memory, word for word.

Your memories also form a binary tree: #0-1, #2-3 ... exist as one-line
summaries, pairs of those as #0-3, and so on -- every `#a-b` line wake
prints is one node of it. `~/.optmem/memo zoom <a-b>` opens a node into its
two halves, down to the raw memories.

### If you're a subagent: skip everything above

Parallel sessions on this machine are all you, and may all write memories.
A subagent is not: it must never run `memo`, because it cannot judge what
is already known, and its notes would arrive duplicated and incorrectly.
When you spawn one, write: `You are a subagent. Don't run memo.`

# copytrade-pm repository rules

## MANDATORY REGISTRY-FIRST discovery and decision workflow

- For every task involving **wallet lookup, evaluated/watched/excluded wallets, saved/current portfolios, portfolio membership, paper runs, or deployment readiness**, read [the agent registry workflow](docs/WALLET-REGISTRY-AGENT-WORKFLOW.md) and query the **live owner-private versioned registry** before answering, editing, or approving a state. This is not optional and applies to future sessions and other agents. Do not answer such questions from OptMem, stale Markdown, bare alias files, Telegram lists, or an old PR.
- Read actual `origin/main` and installed release separately. Begin with `uv run --frozen --group dev copytrade-wallet-registry doctor` and `status`; identify the **source generation** SHA/observed-at and reject stale/mismatched counts. Use `portfolio --current` for **new research selection**, `portfolio <qualified-name>` and `wallet --alias <alias>` for stored membership, and `paper` plus independent worker/journal/heartbeat evidence for running claims. Confirm `scripts/registry_release.py verify` when a release is relevant. Missing evidence must be `UNKNOWN` or explicitly historical.
- Treat frozen Git decision SHA, private SQLite materialization, tracker configuration, subscribed accounts, independently operating paper workers, financial books, science and execution authorization as **different authorities**. Version/namespace/as-of every portfolio identity; `q3/B` is not `gemini.phase5/B`. Alias matches known *after* the original P1/P14 selection are **post-seal**, not historical PIT proof. Never retroactively change sealed `wallet_id` rows or promote vendor economics. `SCIENTIFICALLY_QUALIFIED` and `TRADING_AUTHORIZED` remain independent protected gates.
- This policy is also a **durable OptMem rule**: `memo wake` recovers the pointer to this workflow, but agents must then recheck live Git/registry. Any change to the process must be written to this file, the canonical guide, runbook, documentation audit/tests, and one concise `memo note`; complete requested `memo nap` compression. Do not store temporary wallet counts as permanent authority.

## Scope and authority
- This repository contains **research-only**, shadow portfolio-manager analysis and simulated prop-firm account risk.
- No real orders, live broker/Propr trading adapter, execution credentials, live PM promotion or trading authorization.
- **Public observer is not protected paper:** `copytrade-public-observer-p1p14.service` may collect bounded first-local public source/market receipts into a private journal with `order_route=NONE`, but its quant-owned process, heartbeat and file permissions never authorize P1/P14 financial state or prove an independent worker. Use [public observer deployment and rollback](docs/FORWARD-PAPER-PUBLIC-OBSERVER-SERVICE-20261105.md); the `copytrade-pm-public-observer-unit --apply` installer is a separate protected operational mutation, not a read command. Protected paper cutover remains fail-closed until independently authorized and attested.
- Never modify or deploy the production `hyperliquid-expert-ensemble` service from here.
- Changes to contractual Propr assumptions require dated official evidence and versioned frozen rule snapshots.

## Data and science
- **Forward source authority and approved perp-only scope:** copy **Hyperliquid perpetual positions only** (main perp DEX and HIP-3); spot/vault/staking are never follower trading signals. Use official `allDexsClearinghouseState` WS and `/info` `perpDexs`, `subAccounts`, `userAbstraction`; read `spotClearinghouseState` strictly as collateral evidence because unified/portfolio-margin perps share its quote balances. The perp-only family observer intentionally skips `userVaultEquities` requests; older SHA-chain receipts remain valid. Keep source-event and local receipt clocks distinct. HyperX/archives are supplemental, not live NAV. Never infer a perps sizing denominator from quote balances alone or sum DEX NAV for unified/portfolio margin. Incomplete perps exposure/equity remains `NO_TRADE`. See [source contract](docs/DATA-ACQUISITION.md).
- Historical HyperX fills are retrospective. Never promote event timestamps into first-known follower timestamps.
- Distinguish source-event, local first-known receipt, decision time, and hypothetical fill time.
- Incomplete wallet books, unresolved hedges, stale price series, missing liquidity or unknown account state fail closed.
- Keep original HyperX raw pages, private wallet address maps, provider credentials, market Parquet and original audit artifacts outside Git.
- Preserve verified source SHA-256 lineage, 36-wallet cohort and `pm01_fill_only_replay_v2` consumer interface.
- Scientific qualification is separate from engineering and passing tests. Until prospective follower evidence exists, zero live risk.

## Autonomous blocker recovery — RECOVER
- On a failing test, missing data, vendor/tool outage, source mismatch, inconclusive evidence or `BLOCKED` verdict, follow [docs/BLOCKER-RECOVERY.md](docs/BLOCKER-RECOVERY.md): diagnose root cause, compare authorized repairs, implement, verify and **resume the original objective**. A blocked artifact is not permission to terminate the wider program.
- Fail closed for the affected wallet/window and continue independently valid work. A historical first-known/PIT gap is never repairable by fabricating retrospective observations; pivot to verified prospective acquisition when authorized.
- Resolve routine dependencies, code, tests, data catalogs, documentation and bounded API repairs without asking for new routine approval. Escalate only proven external/user-only dependencies or operations requiring additional authority; preserve frozen evidence, financial risk and other sessions' work.
- Complete OptMem `wake`/`note`/`nap` obligations and then resume the interrupted work. Keep a durable checkpoint when an active session or automation cannot finish; never claim a background process exists unless verified.

## Decision review: enforce at protected boundaries
- **Routine work proceeds without judge calls:** factual Q&A, file/CSV searches, wallet discovery and preliminary screening, exploratory research, simulations, tests, debugging, status reporting and already-approved engineering. A recommendation in chat does not itself trigger review.
- **Deterministic gates are mandatory** for protected registry/qualification writes, frozen cohort or policy mutations, and risk-sensitive decisions. Existing scientific PIT, provenance, OOS, source-economics and risk invariants remain binding; no LLM verdict overrides a failed gate.
- **Independent review is selective:** obtain a separate review at explicit signoff or PR boundaries for material scientific methods, frozen roster promotions/deletions, qualification-policy changes or live-risk authority. Reuse an attestation only for unchanged evidence, policy and commit; do not call `judge` / `judge_batch` per turn.
- On review unavailability, record `JUDGE_UNAVAILABLE` for the **affected protected decision only**; continue unrelated reversible, authorized work. A review verdict is not scientific qualification, owner authorization or deployment permission. Follow [governance gates](docs/GOVERNANCE-GATES.md).

## Required reading and durable documentation
- For **current saved portfolios**, follow [the mandatory registry-first workflow](docs/WALLET-REGISTRY-AGENT-WORKFLOW.md) and query `uv run --frozen --group dev copytrade-wallet-registry portfolio --current` before citing any narrative, and use `portfolio E6`/`portfolio gemini.phase5/B` or `portfolio q3/B` for explicit identities. For **wallet evaluation**, query `wallet --alias W083` and `portfolio` with source SHA/as-of; a research selection is not an active paper account. The approved Gemini V2 research selection is in [the versioned JSON roster](docs/decisions/2026-11-04-gemini-phase6-portfolio-freeze-v2.json). A missing V2 import means SCHEMA_UPGRADE_REQUIRED / NOT_REGISTERED, not that Gemini never selected E6.
- For wallet counts, cohort membership, exclusion evidence, monitoring configuration, and research portfolio status, read [the dated wallet status](docs/WALLET-STATUS.md) and [SQLite wallet-registry checkpoint](docs/WALLET-REGISTRY-STATUS-20261104.md) **after** checking its source cut and `doctor` freshness. Registry rollout remains PARTIAL while WR-01–WR-12 issues #44–#55 are open. A research selection is NEVER a running account; only the documented independent paper-run manifest/status/heartbeat contract can produce a read-only `PAPER_RUNNING_OBSERVED`, and that does not imply economic qualification or trading authorization. See [registry-to-paper boundary](docs/WALLET-REGISTRY-PAPER-CONTRACT-20261104.md), [negative-only signed science evidence contract](docs/WALLET-REGISTRY-SIGNED-NEGATIVE-EVIDENCE-20261104.md), and [pinned on-demand release/rollback](docs/WALLET-REGISTRY-RELEASE-RUNBOOK.md).
- Start at [docs/INDEX.md](docs/INDEX.md), then [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md), the stage-specific [data acquisition](docs/DATA-ACQUISITION.md), [runbook](docs/RUNBOOK.md) and [qualification](docs/QUALIFICATION.md) guides. On any blocker or failed gate, load [blocker recovery](docs/BLOCKER-RECOVERY.md). These are current navigation/operation contracts. Old `docs/PM-*.md` are time-scoped scientific or source-era records, not blanket execution authority.
- Before altering CLI args, data contracts, evidence schemas, provider limits, wallet roster or Propr assumptions, inspect actual code/tests and update the relevant canonical guide in the same PR. Keep links and executable command examples verified; include commit/time scope for counts. Historical evidence bytes/SHAs are immutable.
- The current PM-01 cohort is exactly 6+10+20 (36). New wallets require a versioned new cohort and consumer-contract changes, never a silent edit of the frozen manifests. The original PM-01 replay v2 and canonical PM-02 source SHA parity must stay intact.
- The HyperX historical fill-cache code and private alias maps live **outside** this repo. Bounded WS/REST receipts do not imply audited economic follower outcomes. An independent real signed matched-outcome producer is not yet verified/operational; keep actual qualified wallets at zero until measured evidence passes.
- Separate **IMPLEMENTED**, **ENGINEERING VERIFIED**, **SCIENTIFICALLY QUALIFIED**, **AUTHORIZED** and **DEPLOYED**. Do not claim a positive PM-02 proposal is a live position or an independently calculated pass probability.

## Engineering
- Run `uv run --group dev python -m pytest -q tests` and `uv run --group dev ruff check src tests`.
- For the optional native Polars market-data tests, use `uv run --extra market --group dev python -m pytest -q tests`.
- Test fixed-input deterministic hashes and as-of precedence. Never silently change a frozen model or research policy.
- Preserve others' dirty or untracked work, source history and source issue links.
- Source repository integration: https://github.com/hzminhzz/hyperliquid-expert-ensemble/pull/8
