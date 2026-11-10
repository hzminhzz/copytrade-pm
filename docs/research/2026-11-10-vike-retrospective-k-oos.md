# Vike pre-window k calibration and V4 Polars OOS wallet screen

**Research receipt date:** 2026-11-10 UTC. **Authority:** RETROSPECTIVE_OOS_RESEARCH_ONLY.
**NOT** an authentic pre-August signed k release, forward SHADOW qualification, broker
execution, verified 20% maximum source loss, Guardian approval or deployment.

## Objective and evidence

At owner direction, run the opt-in #255 V4 1m BASE / DELAYED / ADVERSE screen
against genuine stored Hyperliquid fills and SHA-checked native minute data, using
wallet-specific risk fractions derived *only from observed July 1–August 4
historical Vike positions*. The code uses the same V4 estimated-minute
cost/participation policy; it does not use future PnL to select k.

The original 94-wallet local source collection remains unchanged. Vike MCP
`hl_market(view=positions, wallet=..., start=2026-07-01T00:00:00Z,
end=2026-08-05T00:00:00Z, resolution=1h, limit=5000)`
was queried for each wallet. Private, ignored batches of **derived summary
statistics**, one per wallet, were stored in 16 files
`<isolated-worktree>/.workspace/transitions/vike-prewindow-1011-batch00.json`
through `batch15.json`; original full Vike responses were **not** retained
(the connector rejected large writes). Each summary reports timestamps,
distinct observed days, hourly peak notional, number of rows, pagination
status and market list. Original historic source/market snapshots are not
authentic first-local-known observations. This is a reproducible calculation
from retained aggregates, **not** a raw-vendor-bytes-level re-verification.
Only the connected Vike historical API was queried; no daily bulk archive
files were downloaded. API access does not imply commercial archive reuse
rights or automatic source-license clearance.

### Training cohort

| Category | Wallets |
| --- | ---: |
| Original locally sourced | 94 |
| Complete bounded Vike first-page responses | 65 |
| Blocked: additional Vike pagination required | 29 |
| Blocked: insufficient prewindow observed history | 13 |
| Derived valid retrospective k | **52** |

**Risk rule (declared, not optimized against holdout)**

```text
training: [2026-07-01, 2026-08-05) UTC
follower budget: $200 per wallet
stress shock: 20% simultaneous loss on observed source gross notional
gross source notional: sum absolute size_usd across reported hourly positions
k = floor_to_12dp(min(1.0, 200 / (0.20 * max_prewindow_hourly_gross_usd)))
minimum training history: 7 distinct days and 24 hourly snapshots
incomplete Vike pagination or invalid records: BLOCKED / k absent
```

This is **not a worst-case bound**: gaps between hourly positions, unobserved
DEX exposure, hypothetical correlated shocks, liquidation and follower
risk-stop/portfolio losses can exceed the nominal $200. `k` is a *risk
scenario*. The Vike rows used only `snapshot_ts` and `size_usd`; the
provider's current and potentially lookahead `pnl_cohort` labels and
post-window performance were never used for calibration.

The actual policy creation time is **2026-11-10T03:34:42.064213Z**,
well after the full evaluation period. No code or document asserts it existed
before August 5. The new `pm_v4_retrospective_k_job_v3` contract strictly
separates it from v2's genuine pre-window-frozen `k` policy and labels the
report `COMPUTED_AFTER_OOS_FROM_PREWINDOW_VIKE_DATA`.
The research lot rules are unverified approximations
(`step=0.00001`, `minimum_notional=$10`, `max_notional=$10,000` per
native market, **217** original market identities, including builder DEX).
They are not historical exchange precision/orderability evidence.

## Actual OOS evaluation

The predeclared evaluation window is **2026-08-05 00:00 UTC to
2026-11-03 00:00 UTC, exclusive**, original 94-wallet fill source and
local SHA-verified Hyperliquid 1m OHLCV. Source and prices are retrospective
oracle evidence; the first eligible 1m *open strictly after* T0+300 is not
actual V4 intraminute price. DELAYED adds one entry minute; ADVERSE adds
10 bps on **both executed sides**, on top of V4 fees/spread/slippage/impact.
Exits do **not** wait five minutes.

| Metric | Actual |
| --- | ---: |
| Historical source wallets | 94 |
| Source episode candidate groups | 4,787 |
| Episodes passing conservative source checks | 1,377 |
| Matched 1m market actions | 3,994 / 4,131 = 96.68% |
| Completed scenario episode estimates | 2,553 |
| Scenario outcomes blocked for absent k | 1,191 |
| Scenario outcomes blocked by capacity | 179 |
| Wallets with at least one completed BASE estimate | 27 |
| BASE-positive wallets | 17 |
| Positive wallets vetoed by current SQLite exclusions | 5 |
| Research shortlist (positive, >=10 BASE episodes, >=30 obs days, no current exclusion) | **8** |

Other typed blocked scenarios include missing native market day (66),
rejected minimum notional (74), unknown prior-minute volume (24),
partial native day (12), invalid metadata (6), and native data SHA mismatch
(9). Scenario outcome counts are not distinct wallets or trade entries.
Unresolved episodes are *not* marked zero-PnL or filled.

### Ranked research shortlist, current SQLite exclusion veto applied

All dollar figures are the estimated **sum of completed follower-leg
episodic PnL only**, not whole-account NAV, portfolio equity, executable
margin/accounting, funding carry, or a prop challenge verdict. Multiple
concurrent copied exposures are not netted or subject to global Guardian.
The shortlist is **diagnostic only, not automatic promotion**.

| Alias / wallet SHA prefix | Retro k | Train days | BASE episodes | BASE USD | DELAYED USD | ADVERSE USD |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| S051-BTC | 0.008839923570 | 28 | 77 | +263.09 | +248.69 | +219.89 |
| S056-HYPE | 0.014543328575 | 35 | 36 | +144.04 | +144.41 | +100.90 |
| Unlabeled (5af0525565f8) | 0.009296397506 | 35 | 27 | +126.21 | +115.99 | +91.17 |
| S060-HYPE | 0.007871659208 | 16 | 54 | +113.62 | +113.44 | +81.02 |
| S064-xyz:BRENTOIL | 0.011813830569 | 22 | 26 | +101.16 | +113.68 | +87.49 |
| N051-HYPE | 0.082653030018 | 35 | 65 | +67.15 | +66.52 | +59.89 |
| C021-NEAR | 0.128592885212 | 29 | 69 | +54.54 | +55.35 | +44.84 |
| S053-HYPE | 0.026047710549 | 35 | 32 | +49.24 | +58.55 | +20.19 |

S051 has 77 priced BASE episodes out of 86 conservatively supported source
episodes. Other wallets also have excluded/unpriceable trades, so these
aggregate dollar estimates are conditional on successfully priceable legs,
**not complete paths**. Recent 7-day BASE economics were observed for only
a subset (e.g. S051 +$7.77, N051 +$6.58, C021 +$5.47); missing 7-day
results are **null, not zero**. A current identity without a canonical alias
(e.g. `5af0525565f8`) must be reviewed before any downstream membership.
S064 is a builder-DEX contract, requiring separately verified orderability.

### Current registry exclusion review, not retrospective PIT selection

The current indexed SQLite `exclusions` and `propfirm_exclusions` were
queried read-only with an integrity check, matching exact lowercase-address
SHA-256. They remain an *as-of-now recommendation veto*, **not** a historical
as-of-August selection feature. Do not rewrite any frozen wallet membership.

| Positive wallet | Existing exclusion reason |
| --- | --- |
| S058-PUMP | Underwater bagholder |
| S048-BTC | Underwater bagholder; inactive 30d |
| C026-XMR | Passive maker scalper |
| CA-003 (Atlas) | Recorded catastrophic DD 30.1% |
| S059-HYPE | Recorded catastrophic DD 42.6% |

Raw scores and reasons remain in the immutable full ranking receipt; no
potentially favorable result was erased to manufacture a cleaner backtest.

## Immutable private artifacts (VPS)

All below were created in ignored `.workspace/transitions` within the
**isolated worktree** `/home/quant/.devspace/worktrees/copytrade-pm-7fabfa5a`,
not committed and not deployed:

| Type | Filename / SHA-256 |
| --- | --- |
| Training aggregate source binding | `29faf130a016a635ed414a47312f23e7ee211c447bc189b8d8cd6245df4636ec` |
| Post-window k policy | `retro-vike-k-policy-413adf51121eff0a.json` |
| Calibrated job | `retro-vike-screen-job-a06fe947219c0cea.json` |
| Calibration receipt | `retro-vike-calibration-receipt-5943187adfd51a43.json` (SHA `5943187adfd51a43f43769269946c54b4349df97264e22f72f365c51cfc76ca5`) |
| Screen canonical report SHA | `d1ab40e3b09c613c25ea1f34f75b0118edc38de2b1429aa8203c2f2ce135cdd0` |
| Registry-excluded ranking | `retro-vike-oos-ranking-5afac938cbf16e60.json` (SHA `5afac938cbf16e60ac40f720d968d4ee28603951757e84966cb9ac4bc84f1a68`) |
| Original source collection | `1deefe08279936770e896f0521664cf0ee1976bc0eecec78d5c615cb8799117d` |
| SHA-checked native market days | `ce0cbdb9a7815065b2319a3246e61fe68850c7f5752422cc1928e13671207312` |
| Current SQLite exclusion fingerprint | `0688cd506c303e427b95f6528a8ff5838a588351cb3f8b7ffbeef6c3e581ca28` |

Final k policy and ranking have file permissions `0600`. Earlier
development diagnostics remain preserved with their original hashes.

## Reproduction

From the isolated repo worktree with existing private original data present:

```bash
uv run --frozen --extra market --group dev python -m scripts.research_vike_prewindow_k \
  --evidence-dir .workspace/transitions \
  --source-root /home/quant/dev/copytrade-pm/data \
  --output-root .workspace/transitions

uv run --frozen --extra market --group dev python -m scripts.run_vike_retrospective_screen \
  --jobfile .workspace/transitions/retro-vike-screen-job-a06fe947219c0cea.json \
  --input-root .workspace/transitions \
  --source-root /home/quant/dev/copytrade-pm/data \
  --market-root /home/quant/dev/quant/ml4t-data/.data/store \
  --cache-root /home/quant/.cache/copytrade-vike-retro-1011-final \
  --output-root .workspace/transitions \
  --registry-db /home/quant/.local/share/copytrade/registry/wallet_registry.sqlite
```

The first command creates a **new** generated-at receipt at the actual current
time, not a byte-identical historical release. For strict comparison,
**reuse the already sealed private job and policy**; the second command then
reproduces the same report SHA and current-registry-ranked receipt only while
the SQLite exclusion fingerprint remains unchanged.

**Recommendation:** EXPERIMENT with the eight in further research,
prioritizing S051-BTC, S056-HYPE, and S060-HYPE for data/price coverage
validation. Require authentic historic market rules if seeking defensible
notional economics, and stage-2 PM03/PM04 portfolio risk, funding and overlapping
pod accounting before any portfolio or SHADOW admission. No alpha, broker
orderability or drawdown guarantee is established by this run.
