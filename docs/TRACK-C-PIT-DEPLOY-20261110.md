# Track C PIT retrospective SHADOW research — 2026-11-10

Scope: **one-shot, read-only research deployment** of the merged Track C proposal
engine, using the original V4 Polars one-minute execution oracle and privately
SHA-pinned Vike July pre-window data. This is **not** activation of a new k,
reconfiguration of the 16 virtual paper accounts, risk-off action, or broker order.

## Exact study and information cutoffs

- Calibration exposure: 2026-07-01 00:00 UTC to 2026-08-05 00:00 UTC exclusive.
- Historical evaluation: 2026-08-05 00:00 UTC to 2026-11-03 00:00 UTC exclusive.
- Actual calibration computation: 2026-11-10 (retrospective). Do **not** backdate
  its sign-off to August. The portfolio roster itself was selected using later
  evidence; **there is no untouched portfolio-selection OOS result**.
- Risk k used in the counterfactual backtest: min(1, pod_loss_budget /
  (0.20 * maximum pre-window hourly source gross notional)), rounded down to
  12 decimal places. The cap uses each running *paper* scenario's $600 total
  nominal budget; 3-pod=$200, 4-pod=$150 and 5-pod=$120. It deliberately does
  **not** use post-cutoff portfolio-k or OOS profit to fit k.
- The original #255 native engine, including B=5-minute strict-next-minute
  execution, delayed entry +1m, 10bps per-side additional adverse cost,
  minute volume capacity, lot proxies and blocked/untrusted fill episodes,
  is reused directly. No duplicate simulator.
- Source raw 94-wallet file SHA, native market SHA, calibration policy SHA and
  campaign SHA are recorded in an immutable private output receipt.
- Optional SHA-recorded Vike hourly-snapshot supplements are **retrospective
  vendor assertions** and cannot rewrite the original policy SHA. All pages must
  finish, all timestamps must precede the training cutoff, and the selected
  wallet identity must match the SQLite-campaign source. Overlapping original
  policy wallet identities, truncated pages, duplicated rows, nonfinite figures
  or timestamp drift fail closed. An hourly union of nonaligned snapshot minutes
  is conservatively summed for stress peak k; missing July rows remain blocked.
  These supplements do **not** independently authenticate source raw pages.
- Historical independent *completed episodic* follower estimates are not full
  PM03/PM04 account time series. PnL of unobserved/blocked episodes is null,
  not zero. Funding, correlated portfolio drawdown, real execution, and
  contract pass rates are always null.
- Each eligible pod is passed through actual Track C `evaluate_k` with
  **no fabricated FinanceWindow or PM03FinanceFrame**. The correct release
  outcome is `INSUFFICIENT_EVIDENCE` (or `HOLD` for exact equal k), never
  a signed/activated k change. Missing pre-window k blocks that pod.
- Current SQLite exclusions are preserved in `review_flags`; later exclusions
  are recommendation vetoes, not retrospectively available training features.

## Reproduction (read-only historical sources)

The 16-portfolio campaign manifest is owner-private and not checked into Git.
The operator must confirm SHA `7c0b2a021a449c06f818cacf2f757a4d40b89e77669316107dc08ca659237e6f`
and SQLite authority before use. Run under the pinned installed release:

```sh
uv run --frozen --extra market --group dev python -m scripts.track_c_pit_replay \
  --manifest /home/quant/dev/copytrade-pm/data/private/gemini_phase3_phase4_eligibility_20261104.json \
  --registry-db /home/quant/.local/share/copytrade/registry/wallet_registry.sqlite \
  --jobfile /home/quant/.local/share/copytrade/research/track-c-pit-1011/retro-vike-screen-job-a06fe947219c0cea.json \
  --input-root /home/quant/.local/share/copytrade/research/track-c-pit-1011 \
  --source-root /home/quant/dev/copytrade-pm/data \
  --market-root /home/quant/dev/quant/ml4t-data/.data/store \
  --supplemental-root /home/quant/.local/share/copytrade/research/track-c-pit-1011/supplemental \
  --output-root /home/quant/.local/share/copytrade/research/track-c-pit-1011/results \
  --as-of 2026-11-10T12:31:32+00:00
```

The separately deployed unit is
`ops/track-c-pit/copytrade-track-c-pit-1011.service`. It is a pinned
**non-recurring one-shot** service to avoid repeatedly scanning a static
July-November dataset on an already loaded VPS. Do not install a daily
timer until an independently approved rolling PIT calibration with new
source snapshots and guarded trial schedules exists.

Deployment order: preserve existing user units; ensure the commit-pinned
release directory is immutable, hash-verify the private input job and policy,
run focused unit and integration checks, execute the one-shot service under
systemd, inspect journal/outputs/source PIDs, and verify no new paper/trader
configuration or broker route. Rollback disables and unlinks **only this
additive unit**, leaving its research receipts and all current workers intact.

## Research limitations and decision authority

- No live/deployed k change. Active 16-paper `PM04_CONFIG` retains old frozen k.
- Track C issue #268 (pending T+300 immutable k identity and version-aware
  cutover) is separate, with no automatic activation.
- First replay: 2/16 portfolios had complete July k coverage. After independently
  requested, fully paged Vike hourly positions for ACT04, W004, Whale_0x5f94,
  CM-002, coverage is 11/16; E5/E9/E10/E11/E12 remain missing ACT08, W028 or
  VS005. These three wallets had zero position observations July 1–August 4;
  no zero-risk k can be imputed. The 94-wallet historical fills cohort also
  omits some supplemental wallets, so k availability is **not** a portfolio PnL
  receipt. The seven private supplements include three zero-evidence receipts,
  whose SHA identities and exclusion statuses must be retained.
- ACT04 observed July peak gross is above $25m and its counterfactual stress k
  is far below E2/E6 active paper k. This does not imply actual broker loss,
  and the source-position aggregation is not intraday portfolio MTM.
- No full account mark-to-market, authenticated period funding, capacity,
  independent controls, or authentic first-known receipt proof. These are
  required for real risk/return and challenge qualification.
- Current $10k challenge has user-supplied 8% trailing and 5% daily floors.
  Since historical joint equity is unavailable, no breach/pass frequency is
  computed from incomplete episodic estimates.
- Source-to-follower calibration is an **exposure shock proxy** and the
  original method's 20% move is not guaranteed maximum downside.
- No risk increases or funding/unrealized-PnL assumptions are authorized.

Artifact status must be separately reported:
IMPLEMENTED, ENGINEERING_VERIFIED, DEPLOYED_READ_ONLY_RESEARCH,
RUNNING_ONESHOT_COMPLETE, SCIENTIFICALLY_QUALIFIED=false,
TRADING_AUTHORIZED=false.
