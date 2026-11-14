# Reservoir 269-wallet acquisition — monitored roster plus six paper portfolios

**Verified completion:** 2026-11-13 07:15:38 UTC. **State: HISTORICAL SOURCE COMPLETE (134/134 dates, 536/536 immutable artifacts, two DEXes, 269 wallets).** Final catalog SHA-256: `11a706c7849fa8118d33d926d41dd2572b1a9fc74e9f47fb0c92b586a7b91ee7`. Independent offline verification passed. This is **not** point-in-time selection, canonical ingestion, financial paper admission, scientific qualification, or trading authorization.

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

## 3. Verified completion and authentication incidents

- Frozen 269-wallet scope: 264 subscribed/monitored plus 14 sealed, 9 overlap and 5 preserved outsiders. November's roster projected back to July is retrospective, not a historical subscription series.
- **40/40** source preflights completed; projected compressed source-column scan: **29,709.796 MB**, below the approved 50,000 MB guard. This is not actual network traffic or AWS invoice.
- **536/536** source artifacts verified (268 fills and 268 daily per-DEX position snapshots). Dates: **2026-07-01 through 2026-11-11**, 134/134 on each of `hyperliquid` and `xyz`.
- `hyperliquid`: **1,970,537 fills**, **140,912 position rows**. `xyz`: **586,311 fills**, **51,288 position rows**. Total **2,556,848 fills**, **192,200 position rows**.
- Final private catalog: `/home/quant/.local/share/copytrade/research/reservoir-monitored-plus-six-20260701-20261111/catalog.json`, SHA-256 `11a706c7849fa8118d33d926d41dd2572b1a9fc74e9f47fb0c92b586a7b91ee7`.
- AWS `mgmt` login expired during earlier attempts; after interactive reauthentication the bounded resumable systemd job finished successfully at **2026-11-13 07:15:38 UTC**. Its transient `systemd-run --collect` unit then disappeared **by design**. Missing process/unit after this receipt is **COMPLETED**, not disconnected.
- `mgmt` is the requester-pays billing identity; no permanent programmatic credentials were provisioned. Existing narrower 14-wallet source files were not changed.

## 4. Durable status, verification, and future credentials

**To check whether the historical backfill finished, use the catalog, not `systemctl is-active`.** The exact command below verifies the archived cohort, 268 date/DEX entries, 536 immutable Parquet hashes, frozen source ETags/state IDs, daily cross-DEX source state alignment and aggregate row totals. It works **without valid AWS credentials and without consulting the current mutable monitored registry**:

~~~bash
cd /home/quant/.devspace/worktrees/copytrade-pm-6e037206
/home/quant/dev/quant-lab/.venv/bin/python \
  scripts/catalog_reservoir_six_portfolios.py offline-status \
  --cohort monitored_plus_six
~~~

**Expected:** `status=HISTORICAL_SOURCE_COMPLETE_VERIFIED_OFFLINE`, `artifacts_verified=536`, `dates=134`, `wallets=269`, and the pinned catalog SHA above. Exit 2 means evidence validation failed; do not interpret a missing catalog or changed checksum as completion. The existing `verify` command also checks content against the *current* live roster, which may legitimately change after November 2026; use `offline-status` for the **frozen historical cohort**.

The earlier AWS login issue is a **future unattended-acquisition concern**, not a remaining blocker for this finished dataset. AWS's interactive `aws login` refreshes short-lived credentials only within the finite console session (up to 12 hours). On the Contabo VPS, genuinely unattended repeated S3 acquisitions require a separate narrowly scoped workload identity, preferably **IAM Roles Anywhere** with a CA trust anchor, certificate rotation and an IAM role allowing only the needed S3 requester-pays reads. Read [AWS Roles Anywhere documentation](https://docs.aws.amazon.com/rolesanywhere/latest/userguide/credential-helper.html) before establishing that identity. On 2026-11-13, the `mgmt` account had **zero** Roles Anywhere trust anchors/profiles; none were silently created. Do not automate interactive `aws login`, embed permanent broad `AccountFullAccessRole` credentials, or install a permanent data-writing service just to monitor a completed historical backfill.

The former one-shot job was `copytrade-reservoir-269-resume2-20261113.service` and exited successfully; `systemd-run --collect` discards the transient unit after exit. Private 269-wallet evidence remains under `/home/quant/.local/share/copytrade/research/reservoir-monitored-plus-six-{dex}-{date-window}/`; the older 14-wallet catalog and all canonical wallet-store/Guardian/paper state remain independent.

## 5. Acceptance and non-qualification

**Historical acquisition COMPLETE / VERIFIED:** 40/40 frozen preflights, 536/536 SHA-verified source fill/snapshot Parquet artifacts, 134/134 dates on both DEXes, frozen 269-wallet scope, exact counts by DEX, and matching cross-DEX source block/time identities. **Separate, not completed by acquisition:** full historical wallet-to-local trade-ID discrepancy audit, intraday position-path reconstruction, zero-fill-day interpretation, per-wallet contiguous episode validity, source-to-follower economic replay, and PIT/scientific admission. Do not promote acquisition checks to those gates.

**Research validity:** A November-fixed wallet universe projected backward is a retrospective cohort, not survivorship-bias-free discovery. Native simultaneous fills can lack causal intra-millisecond order. Cross-DEX source-state alignment is verified; **269-wallet consecutive-day fill-delta parity has not been independently reported**, and daily snapshots alone do not prove continuous position books. Historical vendor execution time is not actual locally first-known source-observation time. Net follower economics, spread, slippage, funding and frozen-k admission require independent qualification.

**Operations:** No source-registry mutation, no canonical wallet-store ingestion, no CWSA/paper worker restart, no Guardian or broker change, and absolutely no trading authorization. Existing six paper portfolios remain separate from this wider research data acquisition.

See [Reservoir DuckDB plan](RESERVOIR-WALLET-DUCKDB-PLAN-20261112.md) and [verified 14-wallet 31-day research](RESERVOIR-SIX-PORTFOLIO-BACKFILL-20261112.md). Attribution: Hydromancer Reservoir, CC BY 4.0; transformations filter selected addresses and preserve state time.
