# copytrade-pm

Owns **market/wallet facts (`FactStore`), dynamic seat roster (`RosterStore`), source observation, PM03 virtual paper, and offline release staging**. Holds zero broker credentials, live orders, Guardian mutations, or trading authority.

Keep **IMPLEMENTED / ENGINEERING_VERIFIED / MERGED / DEPLOYED / PROSPECTIVE_PAPER_ACTIVE / ECONOMICALLY_QUALIFIED / SCIENTIFICALLY_QUALIFIED / TRADING_AUTHORIZED** strictly separate with exact supporting receipts.

## Start-of-task steps

1. **State scope & check git state:** Inspect `git status`, `git worktree list`, and open GitHub issues (`gh api repos/<owner>/<repo>/issues/<number>` when `gh issue view` fails on `projectCards` in `gh <= 2.46.0`); use an isolated worktree for edits.
2. **Discover capabilities before building:** Run `copytrade-pm capabilities list`, `copytrade-pm capabilities show <id>`, and `copytrade-pm capabilities validate`, then inspect the owner module and tests ([docs/AGENT-NATIVE-OPERATIONS.md](docs/AGENT-NATIVE-OPERATIONS.md)).
3. **Check & verify via `uv run --frozen --group dev`:** Run `bash scripts/ci_focused.sh tests/test_module.py` for quick feedback; run `scripts/ci.sh all` (or `.githooks/pre-push`) before merge/push; docs-only edits verify links, contract consistency, and diff.

## Context pointers

| Branch | Read first |
|---|---|
| Full doc map, recent Phase-D changes, domain terms, system boundaries | [docs/INDEX.md](docs/INDEX.md), [CHANGELOG.md](CHANGELOG.md), [CONTEXT.md](CONTEXT.md), [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) |
| Unified facts (`copytrade_pm.facts`, `facts.sqlite`, strict `as_of_ms` PIT; `allow_unknown_known_at=True` for undated Reservoir retrospective runs) | [docs/FACTS-STORE.md](docs/FACTS-STORE.md) |
| Dynamic seats, leases, CUSUM latches, vetoes, unsigned proposals (`copytrade_pm.roster`, `roster.sqlite`, `copytrade-pm` CLI) | [docs/ROSTER.md](docs/ROSTER.md) |
| PM03 checkpoint paper over `copytrade_kernel.step_checkpoint` (`FIXED_K_NATIVE_QUANTITY`) | [docs/CHECKPOINT-KERNEL-DECISION-PM03.md](docs/CHECKPOINT-KERNEL-DECISION-PM03.md), [docs/PM-03-shadow-account.md](docs/PM-03-shadow-account.md), [docs/RISK-BUDGETED-K-SIZING-20261106.md](docs/RISK-BUDGETED-K-SIZING-20261106.md) |
| CWSA 5m observation, Chapter 2 gates (`copytrade-pm release chapter2`), Ops Control Center | [docs/CWSA-CHAPTER2-20261112.md](docs/CWSA-CHAPTER2-20261112.md), [docs/OPS-CONTROL-CENTER-20261111.md](docs/OPS-CONTROL-CENTER-20261111.md) |
| Contract EV screening (`copytrade-pm research contracts` on matched net follower evidence) | [docs/CONTRACT-PORTFOLIO-EV-TOOL-20261105.md](docs/CONTRACT-PORTFOLIO-EV-TOOL-20261105.md) |
| Mutations, qualification, governance, blocker recovery, coding standards | [docs/RUNBOOK.md](docs/RUNBOOK.md), [docs/QUALIFICATION.md](docs/QUALIFICATION.md), [docs/GOVERNANCE-GATES.md](docs/GOVERNANCE-GATES.md), [docs/BLOCKER-RECOVERY.md](docs/BLOCKER-RECOVERY.md), [CODING_STANDARDS.md](CODING_STANDARDS.md) |
| Cross-repo companion & schema pins (sole pin authority) | `prop-production:src/prop_production/compatibility.json` |
| Agent workflows, issue tracker, triage labels, domain docs | [docs/AGENT-SYSTEM-DESIGN.md](docs/AGENT-SYSTEM-DESIGN.md), [docs/agents/issue-tracker.md](docs/agents/issue-tracker.md), [docs/agents/triage-labels.md](docs/agents/triage-labels.md), [docs/agents/domain.md](docs/agents/domain.md) |

Reserve `~/.optmem/memo recall <regex>` (`zoom <lo>-<hi>`) for cross-repo history only, and verify every fact against its current owner. When changing a contract, update the canonical owner, [docs/INDEX.md](docs/INDEX.md), affected capabilities/tests, and a scoped ADR (`docs/decisions/`).
