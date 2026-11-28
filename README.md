# Copytrade-PM

A personal, single-owner copytrade appliance: canonical source observation, point-in-time facts, portfolio membership, deterministic PM03 paper accounting and wallet health.

All retained workers run one software revision from one frozen uv environment. One systemd target owns their lifecycle. Portfolios are private configuration and independent journals under `~/.local/share/copytrade`.

## Start

```bash
uv sync --frozen --group dev --extra market --extra market-stream
uv run --no-sync copytrade-pm capabilities validate
uv run --no-sync copytrade-pm appliance status --json
```

Read [agent operations](docs/AGENT-NATIVE-OPERATIONS.md) for configuration, recovery and verified software updates. Read [architecture](docs/ARCHITECTURE.md) for ownership, and [AGENTS.md](AGENTS.md) before changing code.

## Preserved contracts

- FactStore keeps original clocks, causal scans and immutable provenance.
- RosterStore owns observation selections and separately researched seats, leases, vetoes and release proposals.
- CWSA preserves canonical five-minute checkpoint identity and explicit gaps.
- PM03 delegates checkpoint decisions to the pinned shared `copytrade-kernel`; each owner retains its own account, mandates, risk state and journal.
- Fixed-k, source scope, independent follower quotes, costs and protected execution authority remain mandatory.

Copytrade-PM holds no broker credentials and grants no trading permission. Prop-Production accounts remain independently owned and deployed. Historical source paths used by external consumers remain stable.

## Verification

```bash
bash scripts/ci_focused.sh tests/test_appliance.py tests/test_appliance_roster_adoption.py
scripts/ci.sh all
```

Full local CI verifies the clean committed candidate in separate core and market environments, the required financial/source/adoption adversarial tests, lint, formatting, types, CLI discovery and packaging. Its receipt is bound to the exact Git revision. Private archival skips are reported separately; they do not establish live parity or economic qualification.

Ops Control Center, Site synchronization, dashboards, Prefect, historical worker deployers and obsolete experiment engines are removed. Their Git history and original evidence are preserved. See the [appliance decision](docs/decisions/2026-11-28-single-owner-appliance.md) and [documentation index](docs/INDEX.md).
