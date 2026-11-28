# Copytrade-PM

Personal single-owner copytrade appliance. Owns FactStore, RosterStore, canonical CWSA observation, PM03 paper accounting and wallet health. Protected execution remains in independent Prop-Production accounts.

## Work sequence

1. Inspect the actual checkout, dirty files, worktrees, remote, relevant issues and running revision. Preserve concurrent work. Use an isolated worktree for code changes.
2. Run `copytrade-pm capabilities validate` and inspect the relevant CLI `--help`, owner module and behavioral tests. For runtime work, read [agent operations](docs/AGENT-NATIVE-OPERATIONS.md) and obtain `copytrade-pm appliance status --json`.
3. Make the smallest change that preserves PIT clocks, source identities, fixed-k, owner journals and risk/authority boundaries. Portfolios are configuration and data. All retained workers use one checkout, frozen environment and systemd target.
4. Run focused behavioral tests while editing. Before merging software, run `scripts/ci.sh all` on the clean committed candidate and retain its exact-SHA receipt. Review the actual diff against [coding standards](CODING_STANDARDS.md) and the accepted requirements.
5. For authorized runtime changes, use the appliance CLI. Verify actual worker identity and advancing source/quote receipts after activation. Software rollback never rewinds financial journals.

## Read by responsibility

| Task | Contract |
| --- | --- |
| Runtime, configuration, updates, recovery, Phase D adoption | [Agent operations](docs/AGENT-NATIVE-OPERATIONS.md) |
| Ownership and boundaries | [Architecture](docs/ARCHITECTURE.md), [appliance ADR](docs/decisions/2026-11-28-single-owner-appliance.md) |
| Facts and PIT research | [FactStore](docs/FACTS-STORE.md) |
| Observation membership, researched seats, leases, vetoes, proposals | [RosterStore](docs/ROSTER.md) |
| Checkpoint finance, signed fixed-k and historical replay | [Kernel decisions](docs/CHECKPOINT-KERNEL-DECISION-PM03.md), [PM03](docs/PM-03-shadow-account.md), [sizing](docs/RISK-BUDGETED-K-SIZING-20261106.md) |
| Qualification and protected execution | [Qualification](docs/QUALIFICATION.md); companion pins belong to `prop-production/src/prop_production/compatibility.json` |
| Historical studies and unresolved obligations | [Documentation index](docs/INDEX.md); inspect original evidence at its recorded revision |

Report IMPLEMENTED, VERIFIED, MERGED, DEPLOYED, SCIENTIFICALLY QUALIFIED and TRADING AUTHORIZED separately. A healthy source or passing test is not financial evidence. This repository grants no trading authority.

Update the canonical owner, relevant tests, [index](docs/INDEX.md) and a scoped ADR when changing a contract. Older rollout documents are historical evidence. Ops Control Center, Site sync, dashboards, Prefect and independent worker releases are permanently retired.
