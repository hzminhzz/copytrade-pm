# PM-03 shadow account — initial engineering slice

Status: PARTIAL. Does **not** satisfy all Issue #2 acceptance criteria.

## Modules
- `pm03_account.py`: Decimal-only synthetic account, venue/market/symbol instrument identity, PM target netting, virtual allocation, basic fill book, fixed/daily/trailing equity floor, conservative target gate, HALT/manual reset.
- `pm03_memory.py`: append-only JSONL SHA chain with event identity, causal clocks, schema/hash checked checkpoint. Local files only. No LLM, broker or order API.
- `tests/test_pm03_account.py`: focused regression tests.

## Limitations and contract unknowns

The rulebook can represent a synthetic Classic/Turbo/2-Step stage, but **no official Propr challenge rules have been frozen or independently verified**. Confirmed rules must include dated official URLs, reset timezone, precise daily-floor calculation, HWM trailing caps/locks, funding, stage transitions, restrictions and special execution conditions. The synthetic tests set `confirmed=True` **only as fixture consent**, not contractual authority.

Current ledger does not yet include fill-event replay/recovery into the account object, PM virtual economic reconciliation across central internal crosses, hedge funding, spread/slippage/impact/participation, partial execution, stage transitions, durable HALT hydration, or three-policy identical-path stress evaluation. `simulate_fill` operates on **hypothetical** synthetic fills and is not an exchange fill engine.

## Risk and authority

PM-02 outputs are proposals, not executed instructions. Unverified input, unconfirmed rules, unknown price or account state, and non-positive stress headroom block targets. Rulebook fixture confirmation is not equivalent to live rule confirmation. Historical HyperX timestamps are not follower first-known clocks; PM-01/02 real cohort still has zero qualified wallets and five empty seats.

Open compliance questions requiring written Propr confirmation: external wallet signal aggregation, permissible market/DEX IDs, algorithmic/API trading, source copying vs independently sized risk allocation, daily drawdown reset and breach semantics, funded-stage restrictions, platform/broker order behavior.

Do not use this slice to place orders, purchase challenges, claim pass probabilities, or promote live allocation.

## Reproduction

```sh
uv run --group dev python -m pytest -q tests
uv run --group dev ruff check src tests
uv run --group dev ruff format --check src tests
uv build
```

## Architecture decisions

Decimal accounting and instrument triple identity prevent float drift and HIP-3 alias collisions. Deny-on-unknown rather than impute flat portfolios. The file-backed ledger is a record of evidence; checkpoints may only reference its current SHA head. Historical evidence and modeled follower equity are not interchangeable. Future slices must add restart-safe account state reconstruction before accepting a persistent HALT claim.
