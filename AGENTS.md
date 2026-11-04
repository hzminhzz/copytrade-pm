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

## Scope and authority
- This repository contains **research-only**, shadow portfolio-manager analysis and simulated prop-firm account risk.
- No real orders, live broker/Propr trading adapter, execution credentials, live PM promotion or trading authorization.
- Never modify or deploy the production `hyperliquid-expert-ensemble` service from here.
- Changes to contractual Propr assumptions require dated official evidence and versioned frozen rule snapshots.

## Data and science
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
- For wallet counts, cohort membership, exclusion evidence, monitoring configuration, and research portfolio status, read [the dated wallet status](docs/WALLET-STATUS.md) and [SQLite wallet-registry checkpoint](docs/WALLET-REGISTRY-STATUS-20261104.md) **after** checking its source cut and `doctor` freshness. Registry rollout remains PARTIAL while WR-01–WR-12 issues #44–#55 are open. A research selection is NEVER a running account; only the documented independent paper-run manifest/status/heartbeat contract can produce a read-only `PAPER_RUNNING_OBSERVED`, and that does not imply economic qualification or trading authorization. See [registry-to-paper boundary](docs/WALLET-REGISTRY-PAPER-CONTRACT-20261104.md) and [pinned on-demand release/rollback](docs/WALLET-REGISTRY-RELEASE-RUNBOOK.md).
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
