# Combo 2 — prospective Propr paper tracking (engineering preview)

**Scope:** local hypothetical shadow ledger plus strictly read-only, hash-verified receipt ingestion. **Not a live connector, not a working unattended monitor, not scientifically qualified.** Source of truth: [spec](specs/combo2-propr-paper-tracking/spec.md) and [single-issue plan](specs/combo2-propr-paper-tracking/plan.md). This document describes only what the current repository implementation establishes; external source/event services and the existing untracked Propr launcher are separate components.

## Frozen research experiment

- Three independent source managers: **W028, CA-008, W015**; nominal paper account **USD 5,000**, each with a fixed **USD 1,000** sizing reference.
- Each manager's desired signed notional is source signed position notional / **current source account equity** x USD 1,000, not fixed-dollar independent fill signals.
- Source first-receipt at T schedules a rebalance at **T+300 seconds**, with repeated observations merged. Leader book and equity at execution time must come from a coherent read-only snapshot. Never use historical vendor fill timestamps as first-known observations.
- **USD 1,250 coin gross cap** means sum of absolute manager target notionals per exact instrument **before cross-manager netting**, not signed net. The **USD 5,000 total manager gross cap** and stress rules are additional conservative *local paper* policy, not verified Propr contract terms.
- USD 10 opening threshold (AND instrument lot/minimum); reductions bypass the notional gate where executable; virtual crosses are not exchange trades; pending/unfilled and dust cannot be marked flat.
- Provisional Classic 1-Step synthetic 3% daily / 6% total paper hard floors with 80% opening freezes. Initial USD 5,000 daily paper balance means USD 120 daily soft freeze and USD 240 initial-to-equity soft freeze. UTC daily reset uses **realized paper balance**, not a real Propr account record. Hard breached stages never auto-reset.
- Real account **#JhW9** read-only monitoring, if/when connected, has a *separate accounting authority* from the paper ledger. No account API, even an SDK running in paper mode, may transmit order-create/cancel/close/replace/leverage mutations.

## Available offline command

The package exposes a fixture-only, strictly local CLI:

~~~bash
uv run --group dev python -m copytrade_pm.pm_combo2_cli \
  --input examples/combo2_paper_fixture.json \
  --paper-root /tmp/combo2-paper-fixture
~~~

The example contains only synthetic wallet-identity hashes and hypothetical market observations. Repeating the exact input is idempotent and returns the same hash-chained paper state. Output is explicitly marked \`paper_only: true\`, \`scientifically_qualified: false\` and \`live_trading_authorized: false\`.

Do not copy a fixture's fabricated first-known timestamps into genuine prospective research. A real source run must timestamp receipts on arrival and persist raw immutable evidence separately.

## Input provenance gate

\`pm_combo2_source.standard_mode_book\` can normalize an official all-DEX account observation **only for authenticated/cross-checked Standard separate-DEX balance mode**, with a verified DEX and subaccount census and separately confirmed absence of other spot collateral. It intentionally refuses unified and portfolio-margin modes: official Hyperliquid [account abstraction documentation](https://hyperliquid.gitbook.io/hyperliquid-docs/trading/account-abstraction-modes) explains that individual DEX user states are not meaningful for those modes. A guess about total wallet NAV would directly corrupt the follower position-sizing denominator.

An official [Hyperliquid info state](https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api/info-endpoint/perpetuals) is **read-only** even though it is requested through \`POST /info\`. It is not a broker order. An authenticated Propr display-universe list does not by itself authorize an instrument. Unsupported mappings and missing marks require explicit partial-book attribution and/or a blocked opening.

## Prospective source receipt import (continuation under Issue #22)

The read-only `pm_combo2_capture` bridge consumes official Hyperliquid frames **already captured by the local E4 producer**, with their immutable raw SHA and first-local receipt metadata. It does not open a WebSocket or query/modify an exchange. The downstream Combo2 paper engine records a **second, later consumer first-known time** (the local ingestion clock). A producer frame older than 90 seconds at ingestion is rejected instead of becoming a backdated signal. Reprocessing an already journaled capture is idempotent and cannot move its action clock.

`SOURCE_BOOK` events persist complete normalized leader positions and equity inside the existing owner-private hash-chained PM-03 event ledger. The first book of each source is **baseline only**. Later signed quantity changes schedule T+300s; additional snapshots refresh the live equity denominator without extending the deadline. WebSocket resubscription or generation rotation is an explicit rebaseline, not an invented catch-up fill. `SOURCE_GAP` clears stale pending operations. Prospective rebalances use **only books restored from this ledger**, require all three recently seen, nongapped books, and reject arbitrary leader payload overrides.

This first bridge deliberately accepts only explicit, verified **single-account / no-subaccount** scopes in `STANDARD_SEPARATE_DEX_BALANCES` mode, with official complete all-DEX state and an independent spot-collateral-absent attestation. Parent accounts with children, unified/portfolio-margin accounts, uncertain source equity and incomplete markets remain blocked; it is **not** a whole-manager solution for a leader with subaccounts. Scope evidence hashes and any market contract SHA are frozen into the run manifest. Market quotes require the frozen attestation SHA, a verified native market ID flag and the same freshness/stress checks; SHA fields record private evidence references and are not cryptographic proof that external claims are true.

Owner-private config (file mode 0600, outside Git) has schema `combo2_prospective_source_config_v1` with keys `run_id`, `started_at`, optional `market_contract_sha` (null while unknown), and exactly three `scopes` entries W028/CA-008/W015. Each scope requires `address`, `expected_dexs`, `account_mode`, `subaccount_scope_complete`, `verified_no_subaccounts`, `spot_collateral_verified_absent`, `evidence_sha256`. **Do not set these gates true without independently retained evidence.** Starting a new paper run does not make a previous E4 generation first-known for that run.

Read-only local example (will fail closed until the real private source proofs exist):

~~~bash
uv run --group dev python -m copytrade_pm.pm_combo2_capture_cli \\
  --private-manifest /private/copytrade/combo2-source-config.json \\
  --generation /private/copytrade/e4/gE420261102T000000000000Z-00000000 \\
  --paper-root /private/copytrade/combo2-paper
~~~

The importer requires a finished, private, error-free E4 session with one complete account window, original raw frame SHA parity, no unobserved subjects, and capture timestamps no more than 90 seconds older than ingestion. This input can establish a **captured source event**, not simulated paper execution by itself. A prospective `PAPER_REBALANCE` must be separately called with genuinely attested instrument metadata, valid current quotes and stress evidence; the current CLI **does not automatically trigger a due batch or submit any remote request**.

**Current external blockers:** the running `copytrade-source-abc.service` rotates A/B/C and does not provide continuous complete Combo2 (W028, CA-008, W015) capture. Existing W028 observations report additional subaccounts, so the single-account proof cannot safely be asserted; CA-008 is not an A/B/C member. Starting another reader concurrently can violate the shared Hyperliquid per-IP account limit. A bounded shared-source producer, aggregate source-NAV/subaccount proof, real Propr market-ID/lot/session attestations, and separate connector-owned SQLite projection/independent transport spy remain required. Do not deploy a Combo2 service from this ingestion-only module.

## Current limits and release gates

- **IMPLEMENTED IN THIS BRANCH:** the existing offline synthetic engine plus the new hash-checked, single-account prospective E4 source-book ingest, frozen scope/market proof manifests, independent consumer first-known clock, reconnect baselines and safe source-gap state. Offline receipt-to-paper fixture tests do not establish a continuously running follower.
- **NOT YET VERIFIED AS PROSPECTIVE:** complete continuous real source acquisition for W028/CA-008/W015 across their subaccounts/account modes; official aggregate live source equity; market-ID/lot/cost/calendar support on #JhW9; connector SQLite intent projection; read-only end-to-end paper fills, calibration and no-mutation transport spy.
- **NO DEPLOYMENT AUTHORIZATION:** the original \`trading-connector/connectors/propr/examples/paper_track_combo2.py\` is a separately owned untracked file in a dirty checkout. This work must not overwrite it or install a real order gateway. The current command has no network or order transport.
- **ENGINEERING VERIFIED** requires the exact run's CI/lint, frozen fixture-based P&L reconciliation, duplicate/reconnect/crash fault matrix, an independently reviewed no-mutation boundary and evidence SHA. **PAPER OBSERVED** requires actual first-known source receipts plus separately tagged model fills and bounded observation. **SCIENTIFICALLY QUALIFIED** and **LIVE AUTHORIZED** remain **NO**.

The end-to-end engineering task remains tracked under **one issue**, with the acceptance gates kept as internal checkpoints in \`plan.md\`. Do not create one issue per component.
