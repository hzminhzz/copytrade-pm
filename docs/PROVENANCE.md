# PM extraction provenance

## Scope
Source: `hzminhzz/hyperliquid-expert-ensemble`; isolated integration branch `feat/copytrade-pm-extraction`, commit `00382c6e5846b7df540f679b970a09e507750521`.

Target: private `hzminhzz/copytrade-pm`, new source package `src/copytrade_pm/`.

The source Git history was filtered in a *separate disposable local clone* with an index filter admitting exactly:

- `src/ensemble/pm*.py` (22 modules)
- `tests/test_pm*.py` (19 test files)
- `docs/PM*` (historical PM documentation and staging checkpoint)

The 12 relevant filtered commits were merged with the destination's original README initialization commit, retaining the **branch and merge ancestry** of PM-01 and PM-02. Git commit IDs necessarily changed because unrelated runtime trees and predecessors were deleted. Source commit objects, private original data and source deployments were not modified.

## Original → filtered Git commit identities

| Original abbreviated SHA | Filtered abbreviated SHA | Work |
|---|---|---|
| `9070b91` | `8b08421` | Original PM-01 shadow portfolio |
| `4cdddb0` | `4df4f61` | Historical fill replay |
| `ed007e4` | `5db4e0a` | Position chain ordering and native audit |
| `ff8b053` | `94b509d` | HyperX overlays and 1m data |
| `715a1d3` | `8e81313` | HIP-3 markets |
| `3befca9` | `b4983d7` | PM-01 tape and PM-03 contract |
| `7785e02` | `076b38b` | Account-state evidence triage |
| `9100f99` | `6a267e8` | Bounded REST receipt |
| `3654dba` | `e077fcb` | Propr market-scope research |
| `7728e75` | `af8c62d` | PM-02 early evidence facade |
| `0f0fdc9` | `6460ec0` | PM-02 marginal risk and immutable audit |
| `00382c6` | `1d2a337` | PM-01/02 integration checkpoint |

Source PRs: [PM-01 #6](https://github.com/hzminhzz/hyperliquid-expert-ensemble/pull/6), [PM-02 #7](https://github.com/hzminhzz/hyperliquid-expert-ensemble/pull/7), [integration #8](https://github.com/hzminhzz/hyperliquid-expert-ensemble/pull/8).

Successor issues: [PM-01/PM-02 extraction #1](https://github.com/hzminhzz/copytrade-pm/issues/1); [PM-03 #2](https://github.com/hzminhzz/copytrade-pm/issues/2).

## Data boundary
The original private HyperX source pages, wallet address maps, sidecars, native Parquet market data, sealed report JSON, source event journal and any provider/broker credentials remain **outside the repository**. Their original recorded SHA-256 digests are not reinterpreted or overwritten. Evidence is attached by sealed source digest rather than copied.

## Verified extraction checks (2026-10-31)

- Source combined PM-01/02 staging: 231 tests passed, 2 skipped. Original non-PM ensemble regression suite: **79 passed**.
- Independent extracted package with optional native market-data dependencies: **162 passed, 0 skipped**, Ruff lint and formatting passed.
- **PM-01 byte-level parity:** identical verified private source inputs and native market store; source and extracted 1%-gross 36-wallet replay yielded the same immutable report hash `c89a8eaa5974043ce24ab2f76549a10177fee9b5e98be37a260bc735bfa9ef6b`, with **3 historical-only and 105 blocked** scenarios. File contents were compared with `cmp` and `sha256sum`.
- **PM-02 byte-level parity:** both applications consumed the same sealed PM-01 v2 artifact `33f95784345e79ca5b1fd9e870d0882ea0e4c37e634ff316da49ab76a961e1c5` at `2026-10-31T00:00:00+00:00`, producing identical manager-report digest `7bf28ee5ad53cdac9212bb0222ae1b3e0ef020eee5faae9972c53028e4b60f4f` and identical raw bytes. Both recommend **36 historical-only cards, 0 qualified, five EMPTY seats, 0 R**.
- The original active `copytrade-ensemble.service` was checked on its independent pinned `ens-e5af40be870d_trk-8646ea573f68` release; this extraction does not restart or deploy it.
- All report data remains owner-private on the VPS; only digests and classifications are documented.

## Remaining scientific gates
Propr market-day coverage is a limited acquisition gate, not economic qualification. A real follower still needs first-known observations, complete source books/accounting, executable market depth/costs and written compliance approval. This repository is **not live trading authorized**.
