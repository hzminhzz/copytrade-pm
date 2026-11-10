# Track C: separate October evaluation after late wallet calibration (2026-11-10)

**Scope:** Secondary retrospective, read-only 16-portfolio calibration/episode-price
screen using existing V4 Polars and Track C abstention. This does **not**
replace the July/August baseline, the running paper `PM04_CONFIG`, or
historical portfolio-selection proof. The 16 Gemini rosters were selected later.

## Causal cutoffs, frozen inputs and independent evidence

- Existing 52-original-wallet plus 4 supplemental prewindow k rates are derived
  from exposures known in **2026-07-01 to 2026-08-05 exclusive** only. No later
  winner-based recalibration of those rates is allowed.
- Three missing July-wallet aliases (W028, VS005, ACT08) have a second,
  nonoverlapping **2026-08-05 to 2026-10-05 exclusive** training window.
  Vike position pagination was exhausted before study creation. Distinct
  observation days: W028 47, VS005 24, ACT08 13. All exceed the declared
  seven-day and 24-snapshot minimum. Empty July history remains recorded.
- **Evaluation is 2026-10-05 to 2026-11-03 exclusive**, on the same native
  source-fill collection and 1m market context. No test-window data is
  permitted to choose k or group membership. The "OOS" label applies only
  to the **parameter-training cutoff**, not to the retrospectively selected
  portfolio membership or first-known T0.
- Risk method: `k=min(1, pod_budget_usd/(0.20*pre-window peak gross))`,
  separately for $200, $150 or $120 pod budgets and rounded down to 12
  decimal places. This is not an observed worst-case loss bound.
- The original 94-source-wallet SHA, market fingerprint, October job SHA,
  private Vike July/late aggregate receipt hashes, SQLite portfolio seals
  and selection review flags are retained in an immutable private report.
  Raw vendor response signatures and historical tick-executable depth are
  **not** independently verified.
- Uses the existing BASE (T+300 strictly next 1m open), DELAYED (+1m) and
  ADVERSE (+10bps per side) Polars episode-price engine and native
  capacity/step blockers. It does not invent prices for incomplete episodes.
- Track C `evaluate_k` receives honest missing PM03 finance frames and
  abstains rather than granting an increase or rewriting an existing risk
  release. Market depth, funding, account MTM, genuine first-known, original
  OOS selection, joint trailing/daily stops and real broker fills remain
  **UNKNOWN/BLOCKED**.

## Actual retrospective findings

- **16/16 portfolios have pre-evaluation k inputs**, up from 2/16 original
  July calibration and 11/16 after supplemental July pagination.
- Source window has 274,676 source fill rows, 1,737 candidate episodes,
  **295 supported episodes**. Failed/unknown/rebalanced episodes are
  not included as zero.
- W028 in E11 has 37 priced BASE episode outcomes under this proxy;
  ACT08's E5/E9/E10/E11 panels have **0** completed estimable episode
  outcomes; VS005 is absent from the 94-wallet historical fills collection.
  Therefore all-pod k coverage is **not** whole-portfolio economic coverage.
- No correct account-level $10k equity path, max trailing drawdown,
  contractual PASS rate or scientific qualification was established.
  Declared 8% trailing / 5% daily limits therefore cannot be tested
  definitively with this limited screening tape.

## Reproduce isolated one-shot

Install private inputs (all readable only by quant) under
`/home/quant/.local/share/copytrade/research/track-c-pit-1011/`.
`trackc-oct-screen-job.json` is a separate, SHA-addressed job, using
the same original frozen SHA-verified July policy and source collection.
Store the original seven July receipts under `supplemental/`, and the
three new fully paged Aug–Oct receipts under `supplemental-late/`.
Do not place any source addresses, private outputs or vendor pages in Git.

The additive unit
`ops/track-c-pit/copytrade-track-c-pit-oct-1011.service`
executes a resource-bounded, nonrecurring research job from pinned
`track-c-pit-1011-r3`. The original r1/r2 units, evidence receipts and
running 16 paper workers are preserved. Rollback removes only this
additional unit and retains its immutable report.

The first independent dry run at the frozen as-of
`2026-11-10T12:57:54+00:00` produced study SHA
`4e87a54789913ca92c93b6252d86ec51dabe7eca56a8d4257a14843411d56279`.
The installed unit must independently reproduce that exact SHA before
claiming deployment verification.

**Classification:** PARAMETER-CUTOFF RETROSPECTIVE RESEARCH ONLY.
Scientific qualification: false. Active k changed: false. Order route: NONE.
Trading authorized: false.
