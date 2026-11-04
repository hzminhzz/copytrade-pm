# Forward-Paper engineering continuation — 2026-11-04

**Repository:** `hzminhzz/copytrade-pm` · **Draft PR:** #73 · **branch:** `feat/forward-paper-fp01-15-20261104`.

## Verified source state and protected boundaries

- Wallet-registry PR #57 already implements a read-only FP journal consumer with a correct dual-SHA P1/P14 identity bridge; registry HEAD `ee7baf8` was inspected without modifying that branch. Cross-branch P1 and P14 smoke scripts passed against FP `fd6a673`; both returned NOT_RUNNING, read-only source unchanged and registry not mutated.
- Production `copytrade-tracker`, `copytrade-source-abc` and `copytrade-ensemble` user services remained active. Their sources are **not** evidence of an admitted atomic, complete P1/P14 wallet book or live market execution quotes.
- No broker orders, provider subscriptions, service restarts, deployed worker or production data paths were changed in this continuation.

## New implementations after baseline checkpoint

| Area | Actual implementation | Remaining acceptance gap |
| --- | --- | --- |
| FP-02/06 | `a6d354c`: one SQLite transaction seals SHA-matched source receipt consumption, account event, run-specific cursor and PM03 snapshot; exact replay and rollback/adversarial tests | Real source transport, gap recovery, 24h replay scale |
| FP-05/09 | `fd6a673`: existing native PM04 processes synthetic whole-book source-equity scaled P1/P14 targets, immutable 300s batching, netting, PM03 fills and unfillable reductions | Real independently admitted source books, full costs/contract/prospective execution |
| FP-02/11/13 | `799b8d8`: OS SIGKILL before/after commit and file-size-failure tests; read-only finance report with explicitly UNKNOWN prospective coverage; status cannot claim healthy from caller-supplied PID | Protected worker, watchdog, live source/quote/funding and matched OOS reports |
| FP-09/11 | `FixturePaperWorker`: a test-only one-shot library consuming previously captured SHA-verified synthetic full books from the shared private journal. P1 remains blocked until all 3 books exist, P14 until all 5; across fixture tests both recover independently, share a source receipt once, preserve source cursors, and produce only simulated account effects | No live producer, source provider auth or long-running supervised service |
| FP-12 | `copytrade-pm-paper-preflight` read-only OS and path check, never installs/restarts anything; blocks on unverified privilege separation and cutover authority | Separate protected runtime OS identities, immutable release, signed review/cutover and rollback |
| FP-15 | Synthetic ext4 one-shot 50-account fixture, full account mark/funding accounting and 2x sequential mark burst, see [load probe](FORWARD-PAPER-SYNTHETIC-BENCHMARK-20261104.md) | 72h+24h actual time windows, real feed burst and true due-event lag SLA |

## Local ext4 release blocker (read-only inspection)

`quant` effective UID is **1001**. Existing generic copytrade release directory is owner `quant:quant` mode `700`. Existing generic reports directory is `quant:quant` mode `775`. Neither provides a separate protected paper financial-state identity. The read-only preflight returns **BLOCKED** for same OS identity, coding user write permission, group/world access to reports, and unverified sudo/docker/service authority. Never place durable paper account SQLite in those currently writable locations as a supposed protected release. The destination, permissions and service unit need explicit controlled operator preparation and proof of isolation; no changes were made.

## Verification and evidence tiers

Run on this FP branch:

```bash
uv run --group dev python -m pytest -q tests
uv run --extra market --group dev python -m pytest -q tests
uv run --group dev ruff check src tests scripts/bench_forward_paper.py
uv run --group dev ruff format --check src tests scripts/bench_forward_paper.py
uv run --group dev python scripts/bench_forward_paper.py --accounts 50 --marks 20 --burst-multiplier 2
uv build
```

Verified fixtures only; no systemd protected pilot launched. `ENGINEERED` may advance, but `PAPER_OBSERVED`, `SCIENTIFICALLY_QUALIFIED`, `BROKER_AUTHORIZED`, `DEPLOYED` remain **false/UNKNOWN**. P1/P14 sequential 11-DEX historical/REST snapshots cannot be retro-labeled as atomic full-book first-known observations. The owner-approved total nominal research risk of $600 does not override PM03 contractual daily floor or prove a funded $600 independent stop budget.

## Next authorized steps

1. Establish a true independently verified source-book/market/receipt producer (not an old A/B/C rotating observer or retrospective vendor timestamp). Prove P1/P14 wallet alias-to-account identity, parent/subaccount/DEX census, collateral/equity and allowed native markets; keep ineligible wallets explicitly BLOCKED.
2. Create a distinct dedicated OS paper runtime identity, immutable releases and owner-private state outside writable Git and generic mode-775 reports. Stage and rollback without affecting production services.
3. Implement supervised workers, signed/secure heartbeat, read-only registry FP-10 status admission and independent alert watchdog. Test transport loss, watchdog failure, process kill, market/quote continuity and unique state recovery.
4. Only after verified protected cutover authority, observe an actual 72h pilot then 24h 50-account soak with real event feed, queue lag, economics and disk headroom. These elapsed evidence intervals cannot be substituted with short fixture tests.
5. Produce P1/P14 matched forward reporting at equal total risk, model cost sensitivity and independent source/market quality, then review CI and merge only genuinely accepted gates.

**No background execution or protected cutover was started during this interactive continuation.**
