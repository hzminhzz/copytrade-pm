# Forward-paper synthetic ext4 load probe — 2026-11-04

**Classification: ENGINEERING LOAD PROBE ONLY.** This does **not** establish a 24-hour unattended soak, independent live-source/market evidence, per-due-event p99 SLA or paper alpha.

## Reproduction

Ran on VPS `/dev/sda1` **ext4**. Branch: `feat/forward-paper-fp01-15-20261104`; script was in the worktree during the run and is committed alongside this report.

```bash
uv run --group dev python scripts/bench_forward_paper.py --accounts 50 --marks 20 --burst-multiplier 2
```

This is a **single sequential synthetic burst**: 50 independently sealed $10,000 PM-03 accounts, one shared synthetic SHA-bound source, one costed hypothetical fill, 40 synthetic marks, and one synthetic funding event per account. It exercises account-level SQLite WAL/FULL financial effects, full replay checks and source cursors. It does not measure real websocket ingestion or PM-04 eligible due-event queue latency.

| Metric | Observed |
| --- | ---: |
| Virtual accounts | 50 |
| Committed effects, total | 2,100 / 2,100 expected |
| Simulated 2x mark burst | 40 mark events per account |
| Complete financial replay/account checks | 50 / 50 |
| Account-level event processing latency p50 | 6.837 ms |
| Account-level event processing latency p99 | 13.212 ms |
| Maximum account-level event processing | 23.418 ms |
| Total wall duration | 15.032 s |
| User CPU / system CPU | 13.910 s / 1.108 s |
| Peak process RSS | 29,268 KiB |
| Final SQLite DB + WAL/SHM footprint | 1,568,768 bytes |
| Broker/network mutations | None in benchmark source |
| Actual 24-hour uninterrupted evidence | **NOT RUN** |
| p99 eligible due-event lag below 5 s with real queue + feed | **NOT MEASURED** |
| Live source, quote and funding coverage | **NOT ESTABLISHED** |
| Scientifically qualified | **NO** |

Measured values are a one-shot sample, not production guarantees. The script deletes its scratch private SQLite directory after checking all accounts. No existing tracker/source/ensemble service was restarted or modified. A real 50-account prospective workload and externally observed periods remain required for FP-15 #72.
