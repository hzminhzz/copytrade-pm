# copytrade-pm repository rules

## Scope and authority
- This repository contains **research-only**, shadow portfolio-manager analysis and simulated prop-firm account risk.
- No real orders, live broker/Propr trading adapter, execution credentials, live PM promotion or trading authorization.
- Never modify or deploy the production `hyperliquid-expert-ensemble` service from here.
- Changes to contractual Propr assumptions require dated official evidence and versioned frozen rule snapshots.

## Data and science
- Historical HyperX fills are retrospective. Never promote event timestamps into first-known follower timestamps.
- Distinguish source-event, local first-known receipt, decision time, and hypothetical fill time.
- Incomplete wallet books, unresolved hedges, stale price series, missing liquidity or unknown account state fail closed.
- Keep original HyperX raw pages, private wallet address maps, provider credentials, market Parquet and original audit artifacts outside Git.
- Preserve verified source SHA-256 lineage, 36-wallet cohort and `pm01_fill_only_replay_v2` consumer interface.
- Scientific qualification is separate from engineering and passing tests. Until prospective follower evidence exists, zero live risk.

## Decisions and recommendations
- Before recommending any non-trivial decision to the user, MUST consult the judge model (`judge` / `judge_batch` from `eval`; see `xd://eval/judge`) with the evidence, not just an opinion.
- Non-trivial means: cohort or tier changes, wallet removal or inclusion, scope or data cuts, architecture or interface changes, policy or threshold changes, anything irreversible, and any claim of qualification or suitability.
- Trivial and exempt: mechanical edits, factual lookups, test runs, lint fixes, and restating already-agreed decisions.
- Report the judge's verdict and its confidence alongside the recommendation. If confidence is low, revalidate with data before acting — never present a low-confidence judge answer as settled.
- The judge informs the decision; it does not override repository evidence, fail-closed rules or the user's call.

## Engineering
- Run `uv run --group dev python -m pytest -q tests` and `uv run --group dev ruff check src tests`.
- For the optional native Polars market-data tests, use `uv run --extra market --group dev python -m pytest -q tests`.
- Test fixed-input deterministic hashes and as-of precedence. Never silently change a frozen model or research policy.
- Preserve others' dirty or untracked work, source history and source issue links.
- Source repository integration: https://github.com/hzminhzz/hyperliquid-expert-ensemble/pull/8
