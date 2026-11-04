# Forward-Paper engineering continuation — 2026-11-04

**Repository:** `hzminhzz/copytrade-pm` · **Draft PR:** #73 · **branch:** `feat/forward-paper-fp01-15-20261104`.

## Mainline registry v7 / FP #73 integration — 2026-11-04

The registry foundation was incorporated into **main commit `5d7b4d7` (#79)**, superseding draft WR PR #57. This FP branch now merges the *actual* new main rather than merging the older overlapping draft code. The mainline SQLite v7 `research_selections` table is the only new-study priority authority: use `copytrade-wallet-registry portfolio --current` (E6 primary, E2 challenger); old `priority` CLI and duplicate overlay module are removed. P1/P14 retain their separate frozen FP-09 contracts and do not become E6/E2 workers. The mainline standalone registry-only read-only release `5d7b4d7` is **ACTIVE_READ_ONLY_VERIFIED** with 264 configured/264 subscribed, 158 research, 22 owner exclusions, and 11 sealed definitions at observed private generation `e2836aab...`. There are still zero registered paper runs, no protected paper services and no trading authorization.

**Frozen-membership integrity finding:** mainline v7's importer originally filled NULL `wallet_id` cells in historical P1/P14 version-2 membership rows when later Phase-4 aliases became available. The production read-only registry now contains those assignments; no rollback/database restoration was performed here. This branch fixes future imports by leaving sealed historical rows untouched and using as-of `wallet_aliases` lookup, with a red/green regression. FP's independently read-only identity audit now refuses the retrofilled IDs as original sealed identity evidence because those alias observations were only known **after** the 2026-11-02 selection clocks. Against actual live registry P1 3/3 and P14 5/5 addresses match, but **all 3/5 post-seal bindings remain BLOCKED** (`source_wallet_equity_attested=false`, `paper_admitted=false`). Future paper enrollment needs a newly versioned, source-known identity decision and complete account books. This is not a retroactive PIT repair or permission to mutate frozen v2 in production.

The **current approved new-research priority** in merged Gemini V2 is E6 primary and E2 challenger, P1 an incumbent historical baseline and P14 archived from the new-selection queue. The preexisting FP-09 implementation in this PR remains a distinct **sealed P1/P14 engineering trial** ($10k each, $600 total nominal risk), not an E6/E2 deployment. The research priority does not authorize remapping a current P1 or P14 run's wallets, equity denominator, historical SHA, effective time or separate private virtual account. `PaperPortfolioView.register()` now refuses any unsealed portfolio or changed P1/P14 membership even if the new name/budget form a valid `FrozenPaperPortfolio`. It cannot silently register E6/E2 without their own reviewed, newly versioned WR+FP contracts.

The independently checked WR PR #57 registry P1/P14 v2 seals are `0862c6dd3e19...` / `079c7c6f3751...`; the **distinct** FP manifest frozen portfolio hashes are `14c0b3611453...` / `fe50ebdafd4c...`. A read-only cross-branch smoke uses the *real* VPS private registry and official private source locators to verify seal version, source document SHA, selection-known timestamp, exact roster, no mutation and the existing synthetic HALT/status boundary: **P1 3/3 aliases; P14 5/5 aliases** match. Both remain **0 independently resolved frozen wallet IDs and 0 verified whole-wallet source-equity books**; neither PR may promote that into paper admission or a healthy worker. The superseding mainline WR v7 `portfolio --current` projection is separate from the seven original source-sealed selection definitions and does not authorize or change this FP trial. No service was started or real financial state changed by the compatibility checks.

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
