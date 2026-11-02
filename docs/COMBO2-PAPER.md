# Combo 2 — prospective Propr paper tracking (engineering preview)

**Scope:** local hypothetical shadow ledger only. **Not a live connector, not a working unattended monitor, not scientifically qualified.** Source of truth: [spec](specs/combo2-propr-paper-tracking/spec.md) and [single-issue plan](specs/combo2-propr-paper-tracking/plan.md). This document describes only what the current repository implementation establishes; external source/event services and the existing untracked Propr launcher are separate components.

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

## Current limits and release gates

- **IMPLEMENTED IN THIS BRANCH:** synthetic event receipts, five-minute deadline, whole-position equity scaling, pre-net instrument gross clamping, nominal portfolio gross restriction, PM-03 reused cash/P&L/position accounting, local append-only event hashes, modeled fee/spread/slippage/capacity, fixture CLI, and unit tests.
- **NOT YET VERIFIED AS PROSPECTIVE:** continuous first-local-receipt source acquisition for the three exact wallet/subaccount scopes, complete live equity across account abstraction modes, complete market-ID/lot/cost/calendar support on account #JhW9, local SQLite intent projection by the existing connector launcher, true paper fill calibration, and end-to-end read-only connector smoke.
- **NO DEPLOYMENT AUTHORIZATION:** the original \`trading-connector/connectors/propr/examples/paper_track_combo2.py\` is a separately owned untracked file in a dirty checkout. This work must not overwrite it or install a real order gateway. The current command has no network or order transport.
- **ENGINEERING VERIFIED** requires the exact run's CI/lint, frozen fixture-based P&L reconciliation, duplicate/reconnect/crash fault matrix, an independently reviewed no-mutation boundary and evidence SHA. **PAPER OBSERVED** requires actual first-known source receipts plus separately tagged model fills and bounded observation. **SCIENTIFICALLY QUALIFIED** and **LIVE AUTHORIZED** remain **NO**.

The end-to-end engineering task remains tracked under **one issue**, with the acceptance gates kept as internal checkpoints in \`plan.md\`. Do not create one issue per component.
