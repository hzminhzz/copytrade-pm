# Seven-day fast-pass wallet screen — 2026-11-07

**SUPERSEDED:** This was an initial one-week, alias-constrained screen. The full July 1–November 7 closed-trade and Vike recovery results in [the November 8 research audit](2026-11-08-fastpass-july-nov-vike.md) replace its candidate conclusions. Preserve the former screen only as a reproducible dated methodology checkpoint; do not use its one-wallet result to veto the three verified newer history candidates.

**Evidence status:** Exploratory source-wallet screening only; no complete first-known follower replay, prop-challenge result, or permission to deploy.

**Workspace:** `/home/quant/dev/copytrade-0711` on `research/0711` at `613dbd975188e820ff8762e3d6ca87fd9bad09b4`. Production left untouched.

## Inputs

- SQLite registry: `/home/quant/.local/share/copytrade/registry/wallet_registry.sqlite` (URI read-only).
- Inventory SHA: `6553b8b7a725474b73a3924fcce63c198e42656d8064c82144816240ca0a762d`.
- Vike `7d` wallet summaries: `/tmp/vike7d_432.json`, SHA-256 `d3158770a376d9d4cb0e448edc84a6001f0909d907a066aeb7b989f72e6ed75c`, registry observed at 2026-11-07T01:09:35Z.
- The Vike source's last metrics updates are heterogeneous; the file is NOT complete immutable first-known fill-level evidence. Open-PnL and vendor-provided drawdown cannot substitute follower MTM.
- Native HL 1m lake has dates through **November 6** for inspected BTC/ETH/HYPE/SOL/ZEC/NEAR/ENA; not a full November 7 session at observation time.

## Results

| Filter or authority | Count |
|---|---:|
| Raw Vike wallet keys | 432 |
| Non-null Vike wallet summaries | 423 |
| Vike summaries with 7d metrics | 359 |
| Vike summaries matching SQLite registry | 423 |
| Non-excluded registered wallets with known aliases | 107 |
| Above $1,000, 7d source win, >=5 closed trades, average hold <=24h (all registered and non-excluded) | 23 |
| Same screen with vendor historical/current drawdown <=25%/20% | 10 |
| Same screen with canonical as-of alias mapping, 72h metric/fill freshness, max gross 8x | **1 (M22)** |
| Existing named latest portfolio definitions | **13** |
| New distinct portfolio membership sets meeting strict filter | **0** |

The single strict named candidate `M22` is not fast-pass-qualified: 16 seven-day closed trades; $436.33 realized source PnL; 23.72h mean hold; 24.1% vendor maximum drawdown and 7.4% current drawdown; 37.5% vendor win rate. This is descriptive vendor evidence, **not net follower profitability**.

## High-priority unaliased registry wallets — screen-only

These have authentic current SQLite wallet IDs **within the pinned registry generation**, but no indexed canonical as-of alias. IDs are local only and MUST NOT be treated as durable identifiers. The private wallet address mapping remains in SQLite.

| Generation-local wallet ID | 7d trades | 7d realized source PnL | Average hold | Vendor max DD | Current DD | Snapshot open unrealized | Preliminary action |
|---|---:|---:|---:|---:|---:|---:|---|
| 179 | 32 | +$7,008.53 | 16.87h | 6.3% | 0.0% | +$324.32 | Prioritize identity/census and real follower replay |
| 267 | 57 | +$1,206.03 | 9.73h | 9.2% | 0.0% | -$94.86 | Prioritize identity/census and real follower replay |
| 238 | 150 | +$5,274.88 | 15.87h | 8.7% | 6.8% | -$15,515.57 | Audit simultaneous open exposure and unrealized PnL before considering |
| 132 (M22) | 16 | +$436.33 | 23.72h | 24.1% | 7.4% | +$2,371.40 | Marginal drawdown, lower priority |

Vendor DD is source-only and may omit unfavorable open-position path or use a distinct denominator. Trading frequency and short average hold are NOT proof that profits came from the volatile Nov 1–7 shock rather than earlier positions closed this week. A 5-minute delayed follower may earn substantially less or lose money.

**Risk observation:** An additional high-realized-PnL candidate (338 trades, +$56,831 source PnL) has 49.1% vendor DD; excluded from robust fast-pass screen. Do not optimize merely for realized PnL.

## Decision

**DO NOT fabricate 17 new fast-pass portfolios.** All 13 saved latest definitions are real registry metadata, whereas adding 17 overlapping unverified triples from one or two vetted managers would be a misleading numerical achievement. The original user's 16-portfolio count may refer to definitions outside this specific registry; independent accounting is needed.

Next meaningful workflow: resolve/approve new as-of aliases for 179, 267 and 238 in a versioned intake; reconcile 7d source episodes + first-known clocks with independent 1m quotes, enforce same-event entry/exit T+5 minutes, single-shot market model, per-pod $200 stop, fixed-k native quantity, $10k account, fees/funding/spread/slippage, and simulate the same historical event times across multiple wallets. Use PM-03/04 native account/risk and the native contract-EV tool only when fully matched net follower tapes exist. Qualify a *portfolio* by joint drawdown/throughput and challenge pass time, not sums of vendor PnL.

### Reproduction

```bash
cd /home/quant/dev/copytrade-0711
uv run --frozen --group dev --extra market python scripts/research_fastpass_0711.py
```

**Status:** SELECTION_SCREEN_ONLY; no manifests added to protected registry, no existing portfolios altered, no running services restarted, no trades placed, no verified prop-fast-pass expectancy.
