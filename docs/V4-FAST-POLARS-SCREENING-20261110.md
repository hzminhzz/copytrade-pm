# V4-aligned historical fast Polars wallet screening (issue #255)

## Scope and scientific label

This is an **opt-in retrospective historical-oracle proxy**. Historical
Hyperliquid fill times are not authentic first-known source observations.
A reconstructed flat-to-flat market position is not an authenticated complete
selected-account position book. Estimates are neither prospective SHADOW
evidence nor risk-adjusted portfolio PnL, PM03 contractual verdicts, trading
qualification or order authorization.

The original v1 job schema, report hashes, frozen PM01 studies and source files
remain unchanged. The new version is
`pm_v4_wallet_screen_job_v2`/`pm_v4_wallet_screen_report_v2`.

The first stage uses one Polars source episode plan and SHA-verified Hyperliquid
1m market-day panel; it does not execute the PM03 financial account for every
wallet. Historical per-market changes must begin flat, remain continuous, and
close flat. Unknown opening state, duplicates, missing `startPosition`,
source-chain conflicts, unmodeled late rebalances, exit right-censoring, absent
market marks and uncertain capacity are counted as blocked, not converted into
profits. This screening conservatively excludes many complex but potentially
valuable managers. An aggregate of per-market completed episodes is **not**
the equity curve or executable economics of a whole-wallet portfolio.

Entry pricing uses the exact first minute **strictly after** T0 + 300 seconds.
DELAYED adds one minute to entry only. ADVERSE adds 10 bps to the adverse side
of *both* modeled entry and exit, in addition to the V4 estimated minute policy
(5 bps taker fee each side, 4 bps half spread, 8 bps baseline slippage,
10 bps impact at 10% previous completed-minute participation). The source
fill price at the beginning of a continuous episode is an explicitly
**retrospective source-mark proxy**, not an authenticated due-time official
source mark. The follower uses exact matching native 1m open. Exits use the
first eligible minute open strictly after the observed source close, with
**no second 300-second exit delay**. The modeled exit closes the same rounded
follower quantity as entry, and charges fees once per side. Missing previous
completed-minute volume and excessive participation reject the modeled leg.

Each original native DEX/market identity is preserved and matched by full
Hyperliquid instrument scope; there is no fallback to default-market identity
or future/current-minute volume. The source SHA, policy SHA, market day
fingerprints, scenario selection and dependent software files are bound into
the versioned immutable-cache identity. Only report data (not timing or cache
hit status) enters the canonical report hash.

## Frozen k policy

A predeclared independent `k` policy is required for any dollar-denominated
estimated PnL. Do **not** use current equity, lookahead calibration, a fit on
the evaluation window or a default k. The exact policy JSON is SHA-pinned and
must be present inside `--input-root`:

```json
{
  "schema": "v4_screen_frozen_k_policy_v1",
  "asof": "2026-08-04T00:00:00+00:00",
  "wallets": {
    "<64-char SHA256(lowercase source address)>": {
      "k": "0.1",
      "known_at": "2026-08-04T00:00:00+00:00",
      "provenance_sha256": "<SHA256 of independently recorded pre-window decision>"
    }
  },
  "markets": {
    "hyperliquid:mainnet:perp:default:BTC": {
      "step": "0.00001",
      "minimum_notional": "1",
      "max_notional": "10000"
    }
  }
}
```

These are **schema examples**, not actual calibrated `k` values, a signed
release or guaranteed current exchange instrument limits. The caller must
pin genuine pre-window inputs. The report marks `MISSING_FROZEN_K` when
there is no valid supplied wallet policy and `MISSING_MARKET_RULE` when
an instrument has no pinned sizing rule. A policy SHA is data integrity,
not proof that a past decision truly existed; the operator must audit the
referenced provenance independently.

## Reproducing the genuine HL94 smoke

The committed example deliberately has **no frozen k and no market rules**,
so any computed dollar follower PnL must remain null. It tests real source
and native candle processing without fabricating historical policy evidence.

```bash
uv run --frozen --extra market --group dev python -m copytrade_pm.pm_offline_job \
  docs/V4-FAST-SCREEN-HL94-ORACLE-20261110.json \
  --input-root docs \
  --source-root /home/quant/dev/copytrade-pm/data \
  --market-root /home/quant/dev/quant/ml4t-data/.data/store \
  --cache-root /home/quant/.cache/copytrade-v4screen-255

uv run --frozen --extra market --group dev python scripts/benchmark_v4_screen_255.py
```

The result contains separate BASE / DELAYED / ADVERSE rows per anonymized
source-account SHA, observation days, complete episode counts, status
breakdowns, net PnL and recent 7-day values only where fully estimable,
source and market coverage, and scenario sensitivity. No blocked wallet is
silently upgraded to an economically ranked candidate.

The original native OHLCV colon identifier, such as
`hyperliquid:mainnet:perp:default:BTC`, is translated by the validated
`v4_instrument_key` adapter into PM03's
`hyperliquid/mainnet:perp:default/BTC` key. DEX and symbol are preserved
without using a default-DEX fallback. The handoff includes both report
provenance and native V4 instrument identities per shortlisted wallet.

The optional Python handoff
`copytrade_pm.pm_v4_fast_screen.shortlist_for_pm03(report, wallet_shas)`
rejects unsupported or PnL-unestimated BASE candidates and returns only
the immutable source/market/policy/report evidence references required to
prepare a separate **explicit** PM03/PM04 sequential portfolio study. It
never simulates cash, funding, DD, margin or a Guardian permit.

## Recorded real-data and throughput evidence

Historical source SHA:
`1deefe08279936770e896f0521664cf0ee1976bc0eecec78d5c615cb8799117d`.

First 90-day run: 94 source wallets, 86 with in-window supported records,
450,172 parsed native fills, 4,787 reconstructed candidate episode groups,
1,377 passing the conservative source episode filter. No genuine pre-window
frozen k was provided. Consequently **zero completed follower-dollar
estimates and zero economically eligible shortlisted wallets** were reported;
this is a missing-evidence result, not zero realized PnL.

First identical-workload warm research benchmark, four repetitions per policy:
BASE-only median **10.4310 s**; three-scenario median **11.4747 s**,
**+10.01%**. Process peak high-water **819,268 KiB** across both modes.
This was an opportunistic shared-host benchmark with warmed OS page cache
and application cache, not an independent physical cold-cache/p95 SLA;
the 25% median warm-runtime target was met in this sample.

**Final integrated build (shared V4 cost policy and PM03 native identity adapter):**
four same-input warm-cache repetitions per scenario mode measured BASE-only
median **10.8167 s** (10.9361, 10.9228, 10.7107, 9.8153 s),
three-scenario median **11.6558 s** (11.7233, 9.8125, 11.7532, 11.5884 s):
**+7.76%**, below the target of +25%. Results reflect shared-VPS noise,
not a guaranteed latency bound. Separate-process single-run peak RSS:
**724,000 KiB** BASE and **729,840 KiB** three scenarios (**+0.81%**).
The combined eight-run process max RSS was 773,720 KiB.

For the final build, a distinct initially empty application-cache run
completed in **11.2623 s** (CACHE_CREATED), immediately followed by
**11.5817 s** (CACHE_HIT). Both reproduced exactly the same canonical
report SHA. The cache is an immutable artifact cache, not a promise of
skipping source reconstruction; this does not measure OS cold disk.
Final-code three-scenario report SHA:
`b90517f5a95415c3d2c291232531171fd58f691c8901b137d294554bdbfc4c53`.
After isolating the v2 larger-cohort source contract (1,000 bounded source
files and 3 million normalized rows, versus the preserved 250-file v1
contract), an additional four-run-per-mode warm benchmark measured a BASE
median of **10.7215 s** (10.7208, 13.0989, 9.9768, 10.7222 s), and
three-scenario median **13.3863 s** (12.9287, 11.7510, 14.3398, 13.8439 s):
**+24.85%**. It narrowly meets the provisional +25% target, but the spread
across repeated measurements on the shared VPS means this is not a robust
upper bound. The latest combined process peak RSS was 767,232 KiB. Earlier
same-code economics runs observed +7.76% overhead; neither sample is an SLA.

A total of **3,994 / 4,131** requested native market action observations
matched independently SHA-verified complete days and previous completed-minute
volume (**96.68%**). Source episode filter coverage was **1,377 / 4,787**
(**28.77%**); none of the 4,131 scenario observations had genuine frozen k
evidence, so all are labeled `MISSING_FROZEN_K`.

Full repository regression was run on the isolated worktree: **1,726 passed,
12 skipped**. Ruff lint and formatting passed, the package source distribution
and wheel built, and `git diff --check` was clean.

**Pre-existing v1 receipt drift:** the November 4 dated documentation retains
a historical SHA `3141e4ac...`, but **both current-main and this branch**
reproduce SHA `2fc393eef6fc40760bf3e3765ade3c614913d24d05a2725cf1a60726a58b622c`
for the v1 real-oracle job. The v2 dispatch does not explain that drift.
Previously sealed report objects have not been edited or overwritten.

## Execution boundary

The full accounting phase remains owned by PM03/PM04 and requires explicit
shortlisting, configured financial rulebook, causal marks and sequential
follower risk constraints. Neither this path nor a valid report changes
the V4 observer, Pydantic SHADOW consumers, Guardian, live financial
policies, source subscription, services, ports or broker route.
