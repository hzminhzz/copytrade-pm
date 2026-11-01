# E4 A/B/C prospective source collection — 2026-11-01 UTC

Scope: read-only official Hyperliquid public API observations. No live orders, no promotion, no historical Q3 first-known reconstruction. Private wallet address mappings and original payloads remain outside Git.

## Runtime and safety

Existing C service `copytrade-e4-source-capture.service` remains unchanged, active (PID 3824555, NRestarts=0 at inspection). Its ExecStart uses the pinned release `/home/quant/.local/share/copytrade/releases/copytrade-e4-source`, not this development worktree. This change does not restart or replace it.

The same `pm_e4_stream` code now accepts `--portfolio A|B|C` (default C). It discovers master and official subaccounts afresh each session, validates original owner association, hashes private identities, discovers all DEXes, subscribes to all five account channels, records original raw bytes, SHA256 and local receipt times. Observed subaccounts are *separate accounts*, not assumed manager strategy constituents. Failed discovery, missing coverage or source errors block qualification. To respect the provider cap (observed error: `Cannot track more than 15 total users.`), subscriptions are sharded across WebSocket connections, each at most 15 subscriptions. Session rotation and reconnects do not demonstrate continuous books.

## Verified bounded observations

| Portfolio | Masters | Subaccounts observed | Accounts checkpointed | Received/persisted frames | Latest generation SHA256 | Source result |
| --- | --- | ---: | ---: | ---: | --- | --- |
| A | W028 W042 W030 | 7 (all W028) | 10 | 120 / 90 | `5ee899b4fcbca825b40b49d5d95fcc8472552f71c6e94ee7d29476ae828d87f1` | Bounded session no source errors |
| B | W044 CA-005 W031 | 0 | 3 | 31 / 27 | `38f683235ce4974c8e17cb169705ef90e351de074009334c75d317fe23e019d9` | Bounded session no source errors |
| C | CO-001 W015 VS066 | 8 | 11 in last completed audited session | 65 persisted in that session | `bb116442b97cf68c5294f1fb230eb81d20726c6096d6495c935213e1b10b38d7` | Existing pinned service active; inter-session gaps fail closed |

A original single-connection experiments returned provider errors; their immutable generations were **not deleted**. The later sharded session succeeded. Independent `pm_e4_source_readiness` checks raw frame SHA256, channel attribution, first-known local timezone, raw/meta cardinality, session reports and the account/subaccount census. Earlier failed sessions and intentional gaps remain explicitly BLOCKED, including gaps between bounded trial sessions. The independent C store audit also checked completed generations; a current in-progress generation had no finalized session report and was classified INVALID_REPORT at scan time (not evidence of corrupt stored bytes). They cannot be relabeled continuous by the successful latest sessions.

## Reproduce without trading

```bash
uv run --group dev --extra market --with websockets==15.0.1 python -m copytrade_pm.pm_e4_stream --research-root /home/quant/.local/share/copytrade/reports/five-pod-20261029-research --store /home/quant/.local/share/copytrade/reports/pm-e4-ab-20261101/portfolio-a --portfolio A --session-seconds 15 --sample-seconds 60
uv run --group dev python -m copytrade_pm.pm_e4_source_readiness --store /home/quant/.local/share/copytrade/reports/pm-e4-ab-20261101/portfolio-a --portfolio A
uv run --group dev python -m copytrade_pm.pm_e4_source_readiness --store /home/quant/.local/share/copytrade/reports/pm-e4-ab-20261101/portfolio-b --portfolio B
```

## Qualification gaps, still fail closed

- Bounded snapshots and event streams are not a lossless continuous event census. No prospective maturity window has passed.
- Original receipt time is available only from local reception onward; historical Q3 2026 first-known timing remains unknowable.
- Complete all-DEX collateral, spot, funding, transfers and subaccount equity have not been independently matched into reconciled whole-wallet equity; historical HyperX account snapshots cannot substitute.
- Existing E4 reconcile logic explicitly declines full equity denominator eligibility. A/B collector smoke passes are **not** equity reconciliations, sizing fidelity or scientific trading qualification.
- New A/B services are **not deployed**; collector code is in the E4 research worktree pending review/pinning. Existing C service remains as-is.

Stages: A/B **IMPLEMENTED and bounded source observed**; C **preexisting running capture**. A/B/C **NOT FULL-BOOK QUALIFIED**, **NOT SCIENTIFICALLY QUALIFIED**, **NOT TRADING AUTHORIZED**.
