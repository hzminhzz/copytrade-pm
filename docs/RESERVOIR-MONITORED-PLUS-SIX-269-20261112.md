# Reservoir 269-wallet acquisition — monitored roster plus six paper portfolios

**As-of:** 2026-11-12 16:30 UTC. **State:** COHORT FROZEN + SOURCE METADATA 32/40 BATCHES VERIFIED. **269-WALLET FILL DOWNLOAD BLOCKED BY EXPIRED AWS LOGIN.** Not paper admission, scientific qualification, canonical ingest, or trading authorization.

## 1. Why 269 rather than 200 or 264?

The current *dated* private SQLite monitoring snapshot (`/home/quant/.local/share/copytrade/registry/wallet_registry.sqlite`) records **264 configured-and-subscribed wallets** at `2026-11-04T09:36:57.574969Z`. The six latest sealed source portfolios contain **14 wallets**; only **9/14** are members of that monitoring snapshot. The correctly deduplicated full research scope is **264 + 5 = 269 unique wallets**. All identity selection is performed privately, with stable scope hashes; no address list appears in Git or command output.

Do **not** use the broader 502-wallet identity registry or 284-wallet research roster as the monitoring cohort. No monitoring state is changed. The November monitored roster applied to July history is a **retrospective fixed cohort**, not a July point-in-time subscription or selection claim.

## 2. Exact approved source scope

- Historical window: **2026-07-01 through 2026-11-11** inclusive (134 completed UTC days).
- DEXes: **`hyperliquid` and `xyz` ONLY**. Every other HIP-3 DEX is prohibited in this acquisition.
- Grain: one bounded DuckDB SELECT per DEX/day with **all 269 addresses in one prepared IN predicate**; 10 core fill columns (`address, timestamp, coin, dex, side, size, start_position, trade_id, direction, is_liquidation`), native decimal/uint64 types.
- Daily per-DEX position anchors, actual ABCI `block_timestamp`, no fabricated 5-minute snapshots, no source-wide fill glob.
- Retention: address-filtered immutable private zstd Parquet and source-provenance sidecars, not exchange-wide files or a mutable SQLite ingestion shortcut.

This is network-efficient at Parquet column-chunk granularity: the source objects must be read regardless of whether the wallet filter has 14 or 269 addresses, because the sampled source lacks wallet-address row-group statistics. Output volume, CPU and validation scale with actual matched rows. This does **not** mean 269-wallet extraction is zero additional S3 traffic for dates already queried for 14 wallets; rereading those source object column chunks is necessary to acquire the additional wallets, but the new broader scope avoids a third separate S3 scan.

## 3. Completed offline preparation and actual blocker

- Frozen 269-wallet set validated by SQLite read-only integrity; 264 subscribed/monitored + 14 sealed, 9 overlap, 5 preserved outsiders.
- The shared collector and per-day preflight enforce the roster generation, explicit AWS billing profile, hard 2-DEX allowlist, per-batch 2,000 MB projected source-column cap, and **50,000 MB whole-history projected cap**.
- **32/40** DEX-week manifests recreated **without any new S3 footer retrieval**, reusing exact source metadata from earlier 14-wallet immutable preflights. Their combined projected compressed-column footprint is **23,501.6 MB**. The other 8 DEX-week manifests require fresh metadata from S3; total final budget is UNKNOWN until they are checked.
- **0/536** expected per-day dataset artifacts for the new 269-wallet cohort have been fetched. Prior 14-wallet evidence is in separate paths and remains immutable.
- Both `default` and `mgmt` AWS sessions expired at approximately 2026-11-12 16:27 UTC; read-only AWS STS and signed S3 calls failed, even with the saved credential configuration. **Do not try anonymous, untrusted, alternative-account or unapproved credential workarounds.**
- AWS profile `mgmt` is a distinct account from `default`; it had previously worked and was recorded as the requester-pays billing identity for the new 269-wallet preflights. An authenticated `mgmt` login must be explicitly restored before any further S3 request.

## 4. Reauthenticate and resume safely

The AWS account owner must run this in the VPS terminal or authorized DevSpace session (requires interactive browser approval):

~~~bash
aws login --profile mgmt --remote --region ap-northeast-1
aws sts get-caller-identity --profile mgmt --region ap-northeast-1
~~~

Then resume the pinned research-only task from the **isolated checkout containing this implementation**:

~~~bash
cd /home/quant/.devspace/worktrees/copytrade-pm-6e037206
export RESERVOIR_AWS_PROFILE=mgmt
/home/quant/dev/quant-lab/.venv/bin/python \
  scripts/backfill_reservoir_six_from_july.py resume \
  --cohort monitored_plus_six \
  --max-batch-mb 2000 --max-total-mb 50000 \
  --max-fetch-batches 4
~~~

Repeat `resume` for subsequent bounded foreground batches; it reuses already verified private Parquet and source manifests, never deletes or overwrites them. For a single long foreground run, `--max-fetch-batches 0` can process all remaining batches after preflight. It must **finish source preflight and check the whole-history projected budget before any S3 fill acquisition**. Recompute S3 ETag/size before reading, fail closed on revision, and retain exact error evidence. No background service is installed.

**After full completion only:**

~~~bash
/home/quant/dev/quant-lab/.venv/bin/python \
  scripts/catalog_reservoir_six_portfolios.py build \
  --cohort monitored_plus_six
/home/quant/dev/quant-lab/.venv/bin/python \
  scripts/catalog_reservoir_six_portfolios.py verify \
  --cohort monitored_plus_six
~~~

Private 269-wallet evidence roots: `/home/quant/.local/share/copytrade/research/reservoir-monitored-plus-six-{dex}-{date-window}/`. Final catalog target: `/home/quant/.local/share/copytrade/research/reservoir-monitored-plus-six-20260701-20261111/catalog.json`. Old 14-wallet catalog and source files are independent and remain untouched.

## 5. Acceptance and non-qualification

**Engineering DONE only when:** 40/40 frozen preflights, 536/536 SHA-verified source fill/snapshot Parquet artifacts, full 134/134 main and xyz days, exact 269-wallet frozen scope, final aggregate row counts by DEX, and independently matching source-state timestamps. All source-only/local-only trade-ID discrepancies, zero-row days and position gaps must be labeled explicitly.

**Research validity:** A November-fixed wallet universe projected backward is a retrospective cohort; not survivorship-bias-free discovery. Native simultaneous fills can lack causal intra-millisecond order; daily delta agreement proves endpoints only, not continuous position books. Historical vendor execution time is not actual local first-known source-observation time. Net follower economics, spread, slippage, funding and frozen-k admission require independent qualification.

**Operations:** No source-registry mutation, no canonical wallet-store ingestion, no CWSA/paper worker restart, no Guardian or broker change, and absolutely no trading authorization. Existing six paper portfolios remain separate from this wider research data acquisition.

See [Reservoir DuckDB plan](RESERVOIR-WALLET-DUCKDB-PLAN-20261112.md) and [verified 14-wallet 31-day research](RESERVOIR-SIX-PORTFOLIO-BACKFILL-20261112.md). Attribution: Hydromancer Reservoir, CC BY 4.0; transformations filter selected addresses and preserve state time.
