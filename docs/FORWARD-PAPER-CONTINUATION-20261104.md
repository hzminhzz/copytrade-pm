# Forward-Paper engineering continuation — 2026-11-04

**Repository:** `hzminhzz/copytrade-pm` · **Draft PR:** #73 · **branch:** `feat/forward-paper-fp01-15-20261104`.

## Latest engineering continuation (2026-11-04, HEAD `f40ef4c`)

This section supersedes the **older snapshots below**; earlier counts and service statements remain time-scoped. New commits after `7b9bae2`: `79ba0d1`, `b985664`, `6ecb12f`, `cbcfb00`, `61825e0`, `f40ef4c`. The branch is still draft, not merged or deployed.

- **Actual read-only observer:** One source census/version check captures the P1/P14 union of five unique wallets (3 shared) via official Hyperliquid public all-DEX parent/subaccount, spot and vault observations. A single bounded CLI cycle recorded first-known receipts for all five parents, then scanned the 22 *observed* native P14 position instruments in three CCXT Pro L2/trade shards. Live read-only readiness found P1 **7/8** and P14 **21/22** bounded L2 quotes; `para/ANSEM` blocked on unchanged spread gate, 0/22 execution volume completeness verified, HIP-3 sessions not independently attested. These are finite non-synchronized receipts, not a future-PIT study or executable fill evidence.
- **Observer supervision:** explicit missing native markets, failed channels, reconnect gaps, five-wallet source capture gaps, WAL observer lease, actual second-process refusal/SIGKILL lease recovery, optionally bounded long-running observer-only loop (`--epochs 0`) with hard cycle timeout/SIGTERM cancellation. No unattended service was installed or left running. Local SHA-linked PID/boot/start-tick plus verified source/market/collateral head heartbeat and separate mode=ro inspector never report protected `PAPER_RUNNING`; live standalone bounded canary inspector accurately returned `UNKNOWN` (no ongoing heartbeat).
- **Physical financial isolation seam:** `pm_forward_source_fanout.fanout_one_portfolio_receipts` reads canonical observer receipts through SQLite `mode=ro`, verifies causal clocks/hashes/complete local prefixes, and writes **one** destination P1 *or* P14 account journal only. Each protected OS identity would write its own account database; the two-journal helper is offline fixture-only. Verified one-account fault recovery, canonical/local tamper, idempotent replay and two separate $10k synthetic PM-04/PM-03 account calculations. A separate negative real-format five-wallet end-to-end test proves actual public partial account books cause **zero** financial effects, leave independent $10k cash intact and preserve source financial cursors across restart.
- **Verification:** `uv run --group dev python -m pytest -q tests` **744 passed**; native-market extra **744 passed**; CCXT-enabled extra **744 passed**. Ruff check, Ruff format, `uv build` wheel+sdist and `git diff --check` passed at `f40ef4c`. GitGuardian success; CI #130 still running at the initial 2026-11-04 inspection, confirm latest SHA independently.
- **Unresolved:** No authentic combined source NAV/hedge/collateral and position marks, frozen registry v2 `wallet_id` mapping (P1 0/3, P14 0/5), complete executable traded volume, verified HIP-3 session, authorized protected OS service identities, immutable installed release or independent watchdog, genuine paper financial observations or real follower/control economic qualification. P1/P14 user/system units are not installed and external cutover signoff is absent. Neither 72h pilot nor 24h 50-account soak has elapsed. All issues #58–#72 remain open until actual acceptance passes.

## Earlier verified source state and protected boundaries

- Wallet-registry PR #57 already implements a read-only FP journal consumer with a correct dual-SHA P1/P14 identity bridge; registry HEAD `ee7baf8` was inspected without modifying that branch. Cross-branch P1 and P14 smoke scripts passed against FP `fd6a673`; both returned NOT_RUNNING, read-only source unchanged and registry not mutated.
- Production `copytrade-tracker`, `copytrade-source-abc` and `copytrade-ensemble` user services remained active. Their sources are **not** evidence of an admitted atomic, complete P1/P14 wallet book or live market execution quotes.
- No broker orders, provider subscriptions, service restarts, deployed worker or production data paths were changed in this continuation.

## New implementations after baseline checkpoint

| Area | Actual implementation | Remaining acceptance gap |
| --- | --- | --- |
| FP-02/06 | `a6d354c`: one SQLite transaction seals SHA-matched source receipt consumption, account event, run-specific cursor and PM03 snapshot; exact replay and rollback/adversarial tests | Real source transport, gap recovery, 24h replay scale |
| FP-05/09 | `fd6a673`: existing native PM04 processes synthetic complete-book P1/P14 targets with immutable 300s batching/netting, PM03 fills and unfillable reductions. Follow-on sizing audit uses native `pm_exposure_sizing` source signed notional/source equity and separately known follower quote (including unequal-price regression), **not** a blind source-quantity ratio | Real independently admitted source books, full costs/contract/prospective execution |
| FP-02/11/13 | `799b8d8`: OS SIGKILL before/after commit and file-size-failure tests; read-only finance report with explicitly UNKNOWN prospective coverage; status cannot claim healthy from caller-supplied PID | Protected worker, watchdog, real independent source/complete trade-capacity/funding and matched OOS reports |
| FP-07 live public market-data slice | Optional pinned CCXT Pro Hyperliquid websocket L2 with main/HIP-3 native identity, SHA-chained private market tape, actual BTC/xyz:BRENTOIL one-shot read-only canary; see [market evidence](FORWARD-PAPER-CCXT-PRO-MARKET-20261104.md) | No source-account NAV, no complete traded volume or venue session for HIP-3; no real paper fills, service or broker |
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

**Sizing correction during review:** source mark and follower mark need not be equal. All admitted nonzero native source legs must include a SHA-bound positive source mark. The pure planner refuses a due quantity without follower marks. The PM04 adapter and fixture worker reuse `calculate_weights` + `target_from_weights`; an independently tested 2 BTC source position at source mark $110, source equity $20,000, and $3,000 follower allocation at follower mark $100 yields 0.33 BTC, not 0.30 BTC. See [equity-normalized exposure](EQUITY-WEIGHT-SIZING.md). This is engineering fidelity only; genuine source-account equity and first-known marks remain unproven.

**No background execution or protected cutover was started during this interactive continuation.**
