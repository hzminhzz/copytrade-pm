# copytrade-pm

Research, public observation and deterministic shadow accounting for wallet
copytrading. This package does not hold broker credentials, submit real orders
or authorize trading.

Start with [AGENTS.md](AGENTS.md), [INDEX](docs/INDEX.md) and the [domain glossary](CONTEXT.md), then the owning source module and public behavioral tests. [Architecture](docs/ARCHITECTURE.md) explains the connected system; [Agent system design](docs/AGENT-SYSTEM-DESIGN.md) owns the proposed interaction model and staged plan. For source work, select the actual policy: [V4 official complete-position T0+300](docs/decisions/2026-11-08-position-first-t300.md) and [CWSA sampled five-minute checkpoints](docs/CWSA-CHAPTER2-20261112.md) have distinct source/timing contracts. [Vike-first](docs/decisions/2026-11-11-vike-first-wallet-source.md) is a separate future transport direction. Dated studies retain their original assumptions; recheck the owning evidence for current state, and distinguish merged/released revisions from edited or untracked worktrees.

## System ownership

| Repository / authority | Responsibility |
| --- | --- |
| copytrade-pm | Private wallet/portfolio metadata, source evidence, research, public observation, PM-03/PM-04 shadow simulation |
| trading-connector | Independent provider transports, normalization and optional ML4T bridges |
| prop-production | Guardian follower finance, risk permits, durable production intents and SHADOW services |
| Private source records and financial journals | Actual observations and account state; never inferred from Git |
| Deployment evidence | Configured/installed revision, independently bound application-process identity and contract pins; each may differ from development HEAD |

The source baseline is reviewed GitHub `main`. Fetch before comparison; preserve
dirty primary checkouts and other sessions. Use a clean isolated checkout for
verification. The three-repository compatibility pins are owned by
`prop-production/src/prop_production/compatibility.json`; its local acceptance
runner records the containing application commit and companion revisions.

## Sizing and evidence

The default is **FIXED_K_NATIVE_QUANTITY**: signed k × selected leader native
position quantity × source mark gives target notional, converted at an independent
follower quote. Leader NAV is optional. Follower equity, selected source scope,
causal receipts, reconciliation, market evidence and risk remain mandatory.

Explicit `ALLOCATION_OVER_LIVE_NAV` retains its legacy leader-NAV requirement.
See [sizing policy](docs/RISK-BUDGETED-K-SIZING-20261106.md),
[production handoff](docs/PRODUCTION-HANDOFF.md) and
[scientific qualification](docs/QUALIFICATION.md).
Synthetic tests, retrospective vendor PnL and public heartbeats do not establish
executable follower economics or trading permission.

## Quickstart and local verification

Requires Python 3.14 and uv. Commands below use synthetic/offline test inputs.

```bash
uv sync --frozen --group dev
uv run --no-sync pytest -q -rs tests
uv sync --frozen --all-extras --group dev
uv run --no-sync pytest -q -rs tests
uv run --no-sync ruff check .
uv run --no-sync ruff format --check .
uv build --no-sources
uv run --no-sync copytrade-pm capabilities validate
```

Explicit sync removes previously installed optional packages from the core gate.
Optional chart, dashboard and source tests skip only when their dependencies are
absent; they are mandatory in the all-extras gate. Required companion-consumer
and private archival replay checks are recorded separately in the program's
[acceptance receipt](docs/PYDANTIC-NATIVE-ACCEPTANCE-RESULTS-20261109.md), and a
portable-checkout skip is not acceptance evidence.

GitHub Actions is optional for this program. Respect actual branch protections
and record clean commit-bound local results. Run `scripts/ci.sh all` locally
(core and `--extra market` legs); the committed `.githooks/pre-push` enforces it
when `core.hooksPath` is `.githooks`. Cross-repository acceptance uses
`bash scripts/verify-local.sh all` in prop-production with the pinned companion
checkouts. Passing tests proves engineering behavior, not economic qualification.

For wallet/portfolio questions, follow the
[registry-first workflow](docs/WALLET-REGISTRY-AGENT-WORKFLOW.md).
Use native `doctor` and the scoped metadata reader for the requested identity;
add `native status` for writer-lock/native-state questions. Aggregate status and
release/process/financial checks apply only to their corresponding claims.
Read the [known facade limitations](docs/AGENT-NATIVE-OPERATIONS.md) before using
unified status. A physically valid SQLite database can contain blocked unsigned
selection proof; preserve those separate dimensions and historical evidence.

For source acquisition and bounded public observation, follow
[DATA-ACQUISITION](docs/DATA-ACQUISITION.md) and
[the continuous observer runbook](docs/FORWARD-PAPER-CONTINUOUS-OBSERVER.md).
For private registry release and recovery use
[the release runbook](docs/WALLET-REGISTRY-RELEASE-RUNBOOK.md).

## Historical contracts

PM-01 reconstructs sealed historical source books and hypothetical followers.
PM-02 owns manager evidence and research governance. PM-03/PM-04 own this
repository's deterministic shadow accounting and target policy contracts.
Preserve the original frozen 36-wallet PM-01 cohort and replay-v2 interface;
new cohorts do not silently alter historical evidence.

The filtered 12-commit PM-only source ancestry is documented in
[PROVENANCE](docs/PROVENANCE.md). The legacy ensemble service remains owned and
deployed independently by hyperliquid-expert-ensemble.
