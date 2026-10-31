# E1/E2/E3 research status

Status: INCOMPLETE. This document records verified preliminary work, not a research comparison or a trading recommendation.

The study is a historical-oracle replay of a post-hoc, incomplete-book episode subset. Historical HyperX event timestamps are not locally observed follower receipts. No live orders or account authorization are provided.

## Inputs inspected

- Source cohort: 36 wallets; selected aliases W028, W042 and W030.
- Study window: 2026-07-01 inclusive to 2026-10-01 exclusive, UTC.
- Existing PM-36 output SHA-256: `9806e1064dfb66690886955ef9b1788225ef7d46874f0ce56ad80ce01d477718`.
- Fresh execution of the source cohort loader, overlay verification and PM-36 eligibility filter found 101, 50 and 53 eligible episodes respectively; 2,761 source events and 410 SHA-verified native Hyperliquid market days. The eligibility filter uses future episode completion and coverage and is not prospective.
- Source episode exclusions: 53 outside the post-period display match and six with incomplete native market coverage. Carry-in, carry-out and missing hedge positions are not flat and are not modeled by this subset.
- A preliminary hourly warmup check for the 35 days before 2026-07-01 found 840 of 840 BTC hourly opens and 838 of 840 ETH hourly opens. A complete 840-return calculation additionally needs its preceding price; other instruments and timestamps have not been audited.
- `e123-input.json` SHA-256: `3a3ec464c487e6fb4f9ef64a09ac7d26c0b8c6d8b96bab87f46ba37449fd6e3b`. This is a preliminary configuration referencing the old output, not a complete sealed source input manifest.

## Unfinished integration

E1, E2 and E3 pure sizing functions and isolated tests exist, but no common historical driver connects them to PM-03/PM-04. PM-36's existing replay uses a separate virtual account with an equity-based daily-reset proxy, while PM-03 resets its daily loss floor from realized balance. PM-36's replay also lacks PM-04 pod-level PnL attribution. Therefore its existing outputs cannot be substituted for the requested paired comparison.

No twelve-run outputs, equity curves, funding and execution reconciliation, deterministic historical replay, or requested stress scenarios have been produced. The historical data's existence is not evidence that these experiments ran. No sizing method, position-size distribution, target progress, or pass probability is established.

## Verification

- `uv run --frozen --group dev python -m pytest -q tests`: 342 passed.
- `uv run --frozen --extra market --group dev python -m pytest -q tests`: 342 passed.
- `uv run --frozen --group dev ruff check src tests`: passed.
- `copytrade-pm-shadow --input examples/pm03_synthetic.json` executed the existing synthetic account example; output SHA-256 `a051987810fbbf3bb6eb0522d9058f341dd0a1d4633577e8b6715ecb82cc6eb0`. This is not an E1/E2/E3 historical run.
- A synthetic sizing smoke exercised all three pure sizing functions, including an insufficient-volatility-history case. It was not an account-level research run.
- A deterministic synthetic sample of 10,000 three-leg E2 books confirmed that decimal rounding did not push the calculated stress charge above $60. This is not a historical simulation.
- Three existing PM-04 synthetic tests covering partial fills and attribution, account-floor overrides, and unfilled hedge exits passed. They are not the requested three-method stress comparison.

Engineering verification applies only to the isolated functions and existing synthetic example. Scientific qualification and live authorization remain absent. The most important prerequisite for credible forward shadow trading is independently observed first-known signals with reconciled source books and independently verified follower outcomes.
