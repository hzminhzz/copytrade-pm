# PM migration checkpoint — historical source staging, reconciled 2026-10-31

This file originated in the **source** `hyperliquid-expert-ensemble` staging branch. It is retained for provenance; its older test counts and unfinished migration instructions are **not the current state of `copytrade-pm`**.

## Verified current destination state (as of 2026-10-31)

- Destination: `hzminhzz/copytrade-pm`, independent research-only package.
- [Migration PR #3](https://github.com/hzminhzz/copytrade-pm/pull/3) merged PM-01/PM-02 with preserved filtered ancestry at `1c24e4edac94c69f286fb6eef21c723a1f8f705d`. See [PROVENANCE.md](PROVENANCE.md).
- [PM-03 PR #6](https://github.com/hzminhzz/copytrade-pm/pull/6) merged as `50f6fac0f559e940466f2fbf918e815306b9710a`. Shadow-only code and test fixtures, no executable broker adapter.
- On that destination `main`, **198 passed** using `uv run --extra market --group dev python -m pytest -q tests`. This is a dated baseline; consult CI and actual code before claiming a new state.
- [PM-36 PR #7](https://github.com/hzminhzz/copytrade-pm/pull/7) is separate, still draft at this checkpoint, head `78ccaa0`: independent worktree passed **187 tests**, not yet merged into `main`.
- [PM-01 successor Issue #4](https://github.com/hzminhzz/copytrade-pm/issues/4) and [PM-02 successor Issue #5](https://github.com/hzminhzz/copytrade-pm/issues/5) retain **scientific** qualifications. Actual 36-wallet PM-02 output: **zero qualified, five EMPTY seats, zero actionable R**.
- Source ensemble service and its pinned production deployment remain independent and must not be changed by PM research.

## Archived source-repository staging checkpoint (not current)

- Source repo: `hzminhzz/hyperliquid-expert-ensemble`, original PM-01 PR #6, original PM-02 PR #7 (distinct from destination PRs of the same number).
- PM-01 historical base SHA: `3654dba637244ffb645ddb2b21ad7c687306345d`.
- PM-02 historical commit: `0f0fdc9446469d60aa2d9bde9450caf78ad224cf`.
- **231 passed, 2 skipped** applied to that *source staging merge* only, not to the independent destination repository.
- All six then-changed source PM-02 files passed Ruff lint and format.
- Source PM-01 v2 artifact identity `pm01_fill_only_replay_v2` is preserved, and private SHA-addressed artifacts must not be committed.

## Preserved migration/evidence invariants

1. Keep PM-only history and source/evidence SHAs linked, without importing raw vendor pages, Parquet, private address alias maps, deployment config, credentials, or unrelated runtime paths.
2. Keep `pm01_fill_only_replay_v2` accepted by its existing PM-02 consumer. Any additive schema extension requires a consumer-contract test before the change.
3. Source-event, first-known local receipt, decision, outcome-known, and hypothetical fill clocks are distinct. Historical vendor fills are **never** prospective follower observations.
4. Missing complete source books, funding, quote availability or coverage are UNKNOWN, not zero returns or flat hedges.
5. PM-03 is an isolated **shadow account** risk supervisor; its synthetic results cannot be interpreted as actual Propr fills or challenge pass probabilities.
6. Do not route PM-01/02/03 to production Telegram/ensemble, broker APIs, or live trading without separate explicit authorization.
7. Source repository production regressions and release pinning are independently verified before any future integration affecting it.
8. Source-only Propr 90% market-day coverage for four wallets is a data-acquisition gate, not position/account/execution/alpha qualification.

## Next scientific/engineering boundary

Receive genuine first-known wallet observations into a sealed local receipt ledger; independently audit the chain before materializing PM-02 prospective consumer rows. Written Propr clarification and authenticated market identifiers remain separate gating requirements.
