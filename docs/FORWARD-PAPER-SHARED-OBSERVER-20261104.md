# Shared P1/P14 read-only source and market observer — 2026-11-04

**Status: engineering-only, no protected worker or paper execution.** This is a bounded public-data acquisition and diagnostic bridge for draft PR #73, not an executable portfolio or an unattended scientific pilot.

## What runs

`pm_forward_source_campaign.observe_shared_frozen_sources_readonly` verifies P1/P14 registry version parity and the three common native address hashes **before opening a socket**. It subscribes once to the **five unique** P14 wallets (including their discovered subaccounts) and maps the same three public receipts to P1. It does **not** subscribe separately per portfolio, modify the registry, or infer complete source equity.

`pm_forward_observer.capture_shared_observer_cycle` uses that source capture and the existing SQLite journal to validate per-account SHA-linked receipts. It requests every observed signed native exposure across parent and subaccounts, including hedges, not just the headline coin. Its **observed native market list is a lower bound**: missing parent receipts, account reconciliation, market marks, spot/vault state, margin and funding remain unknown. The latest parent for each frozen member is checked against the native account-address hash, so a later child receipt cannot masquerade as parent.

Requested markets are partitioned into independent at-most-10-instrument CCXT Pro public L2/trade sessions with explicit HIP-3 DEX discovery. A failing shard is isolated; it never creates a fictitious quote, resumes a trade cache, or treats standing L2 depth as executed volume. The finite supervisor distinguishes `DEGRADED_OBSERVER_FAILURE` (cycle exception), `DEGRADED_OBSERVER_EVIDENCE` (partial source/market capture), and a non-executable `BLOCKED_NO_TRADE` cycle. Lack of a new source account-book frame is reported separately from proven transport disconnection; a quiet wallet is not assumed offline. Every new session starts its own trade baseline. The existing `pm_forward_readiness.audit_live_paper_readiness` is called in read-only mode on the same private journal to report P1 and P14 blockers.

`pm_forward_observer.run_readonly_observer_epochs` runs up to 20 finite cycles, with bounded pauses, explicit fault and reconnect-gap reports. Restarts do **not** establish elapsed continuous coverage. It does not install a service, produce independently signed health, or mutate financial-account ledger state. The canonical `PaperJournal` persists the observed source/quote/trade/collateral tapes; full source/market replay is verified by existing read-only receipt validators and backup integrity checks.

## Example bounded source + market canary

```bash
uv run --extra source --extra market-stream --group dev copytrade-pm-paper-observe \
  --registry /home/quant/.local/share/copytrade/registry/wallet_registry.sqlite \
  --primary-dir /home/quant/dev/copytrade-pm/data/wallet_fills_90d \
  --secondary-dir /home/quant/dev/copytrade-pm/data/nansen_smart_money_fills_90d \
  --state-root /home/quant/dev/copytrade-pm/data/private/p1p14_shared_observer_20261104 \
  --epochs 1 --seconds-per-account 2 --max-source-frames 2 \
  --market-duration-seconds 2 --max-market-updates 3 --market-shard-size 8
```

An optional engineering-only `--epochs 0 --service-cadence-seconds 60 --service-cycle-timeout-seconds 600` mode loops without accumulating unbounded in-memory reports, emits one JSON status line per epoch to stdout for an external service-log consumer, and handles SIGINT/SIGTERM. At each epoch it atomically fsyncs a private local observer heartbeat bound to Linux PID, process start ticks/boot ID and verified SQLite source/quote/collateral journal heads. A failed heartbeat write terminates the service; the epoch output is never silently used as healthy worker evidence. Each capture has a hard timeout, faults produce a negative `DEGRADED_OBSERVER_FAILURE` record, and a failed stdout/report sink terminates the loop. A shutdown signal races the active capture with an explicit cancellation path: a hung websocket task is cancelled and the interrupted epoch records `DEGRADED_OBSERVER_STOPPED`, never a successful source/quote window. Tests cover the hung-task cancellation and timeout paths without waiting out an actual service cadence. This is **not a protected release or an independently signed paper-worker heartbeat**, and it was not started as an unattended VPS service. The minimum cadence is 30 seconds and the cycle timeout must be 30–3600 seconds. Crash recovery relies on SHA-linked private tapes and a fresh source/CCXT trade-cache epoch, not an invented continuous window.

The command is opt-in. It takes an exclusive, mode-0600, no-symlink process lease at `paper-observer.lock` under the private journal root. A second process targeting the same journal is refused before it opens any source/market connection; the lease releases on normal return or process death. This **does not** establish a privileged protected service identity. Store private market/account observations outside Git and protected by Linux 0700 directories and 0600 database files. The CLI can open public WebSockets and persistent local journal files, but has **no broker client, order/cancel route, private credentials, or service manager calls**. Do not run concurrent writers for the same journal. The independent release preflight remains `BLOCKED`.

## Real bounded canary evidence — 2026-11-04

Executed the command above, with its explicit isolated private journal root and **one epoch**. The five unique official parent source books each produced one SHA-linked account receipt and one separate first-known spot/vault diagnostic receipt. The read-only native-exposure audit required **8 P1** and **22 P14** signed-instrument markets; the CCXT Pro bounded shard scan yielded **7/8 P1** and **21/22 P14** first-local L2 quote receipts. The missing `para/ANSEM` quote did not pass the spread constraint. The source and market clients were bounded, then closed; this was not continuous feed evidence. P1 and P14 readiness both returned `BLOCKED_NO_TRADE`: frozen membership identity links remain unresolved, complete wallet equity and executable venue-volume coverage remain unverified. The observer supervisor reported zero financial events, zero broker orders, `protected_worker_attested=false` and `paper_observed=false`. The five separately timestamped source observations are not a synchronized account or market snapshot.

## Independently isolated P1/P14 financial journal source fanout

`pm_forward_source_fanout.fanout_one_portfolio_receipts` implements the missing inter-journal evidence boundary without a second source subscription or a second financial authority. Each future **independent OS-identity worker** reads the canonical observer SQLite tape with a read-only transaction, validates its own frozen portfolio's source chain, causal clocks and available account-book hashes, and checks an exact prefix before copying immutable first-known receipts into **only its own** private P1 *or* P14 `PaperJournal` database. A single production process never requires write access to both account journals. The paired `fanout_frozen_source_receipts` helper is **offline test-only** and must not be used as a privileged cross-account worker. The three shared wallet source receipts are copied as references into each isolated financial account; S064 and Whale only enter P14. It never creates PM-04 target, PM-03 fill, broker order, source-equity estimate, or cross-database atomicity claim. Each destination's existing `consume_source_effect` transaction later remains the only cursor+financial effect authority. If one destination fails after the other copied, a retry verifies the durable prefix and resumes only the missing receipts. Conflicting or tampered canonical/local chains fail closed. The function is library-only until protected private P1/P14 state identities and operator cutover are available; it has **not** been used to create live financial accounts on the VPS.

Regression `tests/test_pm_forward_source_fanout.py` covers one-portfolio-only writer isolation, first copy, cross-portfolio isolation, exact idempotent restart, canonical/local chain tamper, one-target failure/retry and separate PM-04 synthetic fixture effects. These tests verify mechanics, not real admitted source or scientifically qualified paper trading.

## Read-only observer watchdog

The separate test-only read-only inspector can be invoked without initializing any financial-account run:

```bash
uv run --group dev copytrade-pm-paper-observer-health \
  --state-root /home/quant/dev/copytrade-pm/data/private/p1p14_shared_observer_20261104
```

It verifies the locally fsynced `p1p14-public-observer.heartbeat.json`, private file modes, actual Linux PID/start ticks/boot epoch, SHA of the heartbeat envelope, and current SHA-chain heads of the existing source, market quote and spot/vault collateral tapes, using SQLite `mode=ro`. It distinguishes aliases checked from aliases actually having source receipts, separately flags stale/missing source or market observations, and rejects missing/tampered/forged/PID-reused/stale or financially divergent evidence as `UNKNOWN`. Even a valid recent heartbeat is only `DEGRADED_OBSERVER_ONLY`: the producer is coder-writable, the heartbeat is not independently signed, the provider has not attested atomic NAV/volume, and the watchdog does not prove protected OS user or unattended systemd service. No user/system service was installed by this change. The independent WR-07 and FP protected worker health gates remain blocked.

## Hard limitations

- The P1/P14 sealed v2 membership `wallet_id` links were unresolved at the last audit. A filename/address match is identity-locator evidence only, not authorization to change frozen membership.
- Public `allDexsClearinghouseState` plus sequential subaccount/spot/vault requests do not carry one atomic whole-wallet NAV. A reported zero subaccount/vault row count does not establish zero collateral or absent exposure.
- Asynchronously obtained market quotes are not executable capacity. Rolling CCXT trade caches lack a complete exchange sequence or 24-hour venue-volume guarantee, and HIP-3 sessions remain uncertain.
- `status=BLOCKED_NO_TRADE`, `paper_admitted=false`, `paper_observed=false`, `real_worker_attested=false` and `executable_volume_base=null` are enforced independent of short bounded successes.
- A new end-to-end negative integration regression feeds all five official-format public `allDexsClearinghouseState` receipts through the existing `FixturePaperWorker` P1/P14 PM-04/PM-03 seam. Both independently registered $10,000 virtual accounts preserve their financial journal heads, original cash, empty positions, unconsumed source cursors, and zero fills through deterministic restart. The worker **rejects** every live-format, incomplete NAV book; no `synthetic_fixture` flag is added to real public receipts and no modeled execution is forced. This validates refusal and replay, not a genuinely admitted source-to-fill path.
- The live worker with independently admitted source, protected release/rollback, 72-hour pilot and 24-hour 50-account soak remain **separate unfinished acceptance gates**.
