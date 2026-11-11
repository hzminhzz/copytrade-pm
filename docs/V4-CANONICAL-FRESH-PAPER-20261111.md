# V4 canonical 16-portfolio fresh paper campaign — 2026-11-11

**Transport distinction:** [Vike-first wallet ingestion](decisions/2026-11-11-vike-first-wallet-source.md) is an approved future design, not an installed replacement for the current official complete-position source. Keep this campaign's selected-account official proof, T+300, frozen k, PM03/PM04 and immutable financial journal requirements unchanged until separate engineering, reconciliation and runtime admission. The 7-of-14 source coverage in this document is a dated deployment snapshot; verify current GAP/coverage from original journals and OS evidence.

## Scope and outcome

This work restores one **research-only** 16-portfolio paper consumer on a single immutable Git release. The original 0811 P1/P14/P16 and two 0911 sixteen-portfolio journals are historical evidence. Never overwrite them, reuse their state roots, migrate old paper positions or retroactively reprice outcomes.

The canonical implementation is the common current `pm_forward_single_shot.py` + PM03/PM04 reducer, with source recovery reconciled from PR #306 and the merged PR #307 signed-source/effect contracts. **Do not change T+300 semantics**: initial official first-known leader position change starts an exact 300-second wait with a 30-second grace. Later revisions coalesce without restarting the clock. Verified source reductions and independent protective risk latches request prompt exits. Missing quotes, source gaps, or unresolved inventory do not imply a trade.

## Risk assumptions

New runs use `--paper-risk-profile CHALLENGE_TRAILING_8PCT` and an independently named `--run-label canonical_20261111`. Each virtual account begins at $10,000 and models $500 fixed daily allowance plus an **uncapped** $800 peak-to-trough trailing loss allowance. The legacy `LEGACY_STATIC_10PCT` is default and unchanged for historical/replay use. This is a research scenario, **not a confirmed prop-firm contract**; daily loss reset definition, trailing cap/profit-locking and provider-specific rules must be verified before interpreting challenge pass/fail. No funded trade permit is inferred.

Each new ledger fixes its rulebook source and `pm02_sha`. Restarting with another risk profile fails closed. Old journal bytes and accounts remain immutable.

## Source coverage qualification

Hyperliquid's shared-IP distinct-user budget constrains the deployed 0911 official observer to a fixed, continuously subscribed **7-parent** cohort while 0811 has three parent subscriptions. Seven other original selected parents remain a durable `GAP`. The 16-portfolio paper service is therefore an experimental comparison with **DEGRADED_SOURCE_COVERAGE**, not an unbiased sixteen-portfolio ranking. Missing exposure may not be filled from past events or from Vike fills. Only a genuinely observed post-start official state transition can open a fresh T+300 intent. True full 16-way comparison needs independently qualified complete coverage; never fabricate it.

The 0911 source remains running during paper cutover. Shared Vike minute market data remains running. Guardian, brokers, production wallets, k releases and prop-production are untouched.

## Required operational sequence

1. Review PR, tests and main SHA. Inventory all five original paper service names, unit pins and ledgers and check original finance replay, source stream and selected portfolio identity. Preserve read-only receipts and backup metadata. Stage a new exact-Git-SHA release outside the primary mutable worktree. Validate source and market snapshots and private campaign SHA.
2. Stop and disable **only** these five paper consumers: `copytrade-v4-paper-p1-0811`, `copytrade-v4-paper-p14-0811`, `copytrade-v4-paper-p16-0811`, `copytrade-v4-sixteen-paper-0911`, `copytrade-pydnative-v4-sixteen-paper-0911`. Do not stop `copytrade-v4-sixteen-source-0911`, `copytrade-v4-selected-positions-0811`, or `copytrade-v4-minute-0811`. Verify paper PIDs are zero and capture the final event-chain and PM03 account heads, then leave journals in place and set old consumer enablement to disabled.
3. Run a one-shot canary against a **new** owner-only state root such as `~/.local/share/copytrade/prospective/v4-canonical-sixteen-1111/` using `--once --run-label canonical_20261111 --paper-risk-profile CHALLENGE_TRAILING_8PCT`. Verify 16 distinct ledgers, $10k, $500 daily, $800 trailing, no static floor, no imported positions, no old signal replay, no broker operations, source GAP handling, and no new WAL/CPU growth.
4. Install one owner-only pinned systemd service `copytrade-v4-canonical-sixteen-1111.service` with its own state root, `MemoryMax`, `CPUQuota`, source/price dependencies and `NO_TRADE` operator permission. Start the service. Verify the actual PID, `/proc/PID/cwd`, exact Git SHA, ledger heads, 16-run admission, first post-start transitions and zero real broker fills. Monitor source GAPs, quote-age errors, unresolved exits, WAL and disk growth.
5. Rollback = stop the new paper consumer while preserving its new journals. Do not automatically reenable older campaigns and mix their experimental evidence. Original old units and all original journals remain available for a separately authorized recovery. No source reset, WAL truncation, registry write, or funded order.

## Operator commands (only after reviewed merge)

All commands run from the exact verified checkout, with the full immutable 40-character Git revision in `RELEASE_SHA`:

```sh
uv run --frozen --group dev python scripts/v4_canonical_paper_release.py --phase plan --expected-sha "$RELEASE_SHA"
uv run --frozen --group dev python scripts/v4_canonical_paper_release.py --phase stage --expected-sha "$RELEASE_SHA" --apply
uv run --frozen --group dev python scripts/v4_canonical_paper_release.py --phase cutover --expected-sha "$RELEASE_SHA" --apply
uv run --frozen --group dev python scripts/v4_canonical_paper_release.py --phase verify --expected-sha "$RELEASE_SHA"
```

The release operator stages tracked source into a private exact-SHA copy, installs locked dependencies, stops/disables the five old paper services only, creates a 35-ledger final head SHA receipt, runs a one-shot fresh-ledger canary, installs a bounded systemd user service and verifies PID. If any cutover step fails, old journals are preserved and old paper remains stopped (fail-closed); no broker/order/funded action occurs. Rollback is an explicit `--phase rollback --expected-sha "$RELEASE_SHA" --apply`, which stops canonical paper but never deletes its journal nor implicitly restarts old experiments.

## Acceptance interpretation

- **ENGINEERING VERIFIED:** both legacy and new risk profiles create/restart with immutable manifest SHA and causal ledger chain; T+300, risk exits, source protection and resume tests pass.
- **OPERATIONS VERIFIED:** unit reports an exact committed revision, 16 independent fresh accounts, no actor submitting broker orders, and bounded WAL/storage at observed sampling times.
- **SCIENTIFICALLY QUALIFIED:** requires enough independent, full-source, prospective opportunities, actual cost/coverage evidence and correct prop rules; not guaranteed by this cutover.
- **TRADING AUTHORIZED:** **NO**.
