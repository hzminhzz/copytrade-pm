# Vike ↔ Hyperliquid source-data recovery — 2026-11-06

**Scope:** research-only, no execution authorization. Actual bounded Vike MCP, authoritative SQLite read-only identity, frozen HyperX raw-page cache, and independent native Hyperliquid `/info` confirmation. This document reports observed evidence, not a full-registry vendor qualification or a verified production WebSocket.

## Sources, ownership and safety

- SQLite wallet registry: `/home/quant/.local/share/copytrade/registry/wallet_registry.sqlite`. SQLite **metadata** remains authoritative; all Vike/HyperX/official native fills are external evidence, **not** cohort/portfolio authority.
- Original HyperX cache: `/home/quant/.local/share/copytrade/reports/five-pod-20261029-research/slow_pod_data_v1/hyperx_fills_cache_v1`. Original compressed pages and SHA sidecars were verified, never overwritten.
- Vike: MCP `hl_wallet_activity(view=fills)`, `stream_check_filter`, `stream_events`, `hl_archive`. Official API: https://vike.io/data/api.
- Independent native confirmation: public Hyperliquid `POST https://api.hyperliquid.xyz/info`, `userFillsByTime` for bounded UTC days. No broker secrets or order mutations.
- Code belongs to `copytrade-pm` research layer; `trading-connector` owns broker-specific connectivity, and `prop-production` owns execution/risk/reconciliation.
- Git branch `feat/vike-data-contract-20261106` isolates changes from the heavily dirty main checkout. **No live service was replaced.**

## Vike small-fill default — verified REST, unverified WebSocket

`hl.fills` has a **$1,000** default minimum notional. Vike's live filter validation:
- With explicit `min_usd: 0`, reports `valid: true`, but normalized `filter` omits the zero.
- With `min_usd` omitted, normalized `filter` explicitly includes `min_usd: 1000`.
- Bounded REST catch-up sample with explicit zero: 180/200 records under $1,000 (smallest ~$7.82).
- Separate REST sample with default: 0/200 under $1,000 (smallest ~$1,000.21).

These filtered REST pages **do not constitute a same-window completeness census** or proof that a persistent WebSocket delivers every small fill. `pm_vike_contract.verify_fill_subscription` binds the actual outbound request to the server validation; it accepts normalized zero-elision as **PREFLIGHT_ONLY** and refuses production admission. WS delivery, cursor/reconnect catch-up, local first-known receipt and event-to-receipt p50/p95/p99 have not been measured.

## W028: actual SHA-verified reconciliation

The authoritative SQLite alias `frozen_pm01/W028` was resolved as a read-only identity (no address is logged). Vike returned **2,732** fills across 40 instruments, requested window `2026-08-19T00:00:00Z` to `2026-11-04T00:00:00Z`, with no remaining pagination cursor. Original Vike MCP records were preserved in 14 private JSON chunks.

The independent frozen HyperX cache covers a broader calendar span (2025-12-30 to 2026-10-30 09:47:12.876 UTC) with **2,939** raw W028 fills across 37 SHA-verified pages.

| Classification | Number |
| --- | ---: |
| Shared native trade IDs, exact event timestamp/side/price/size | 2,516 |
| Conflicting matched trade records | 0 |
| HyperX fills inside Vike requested window absent from Vike | 0 |
| Vike-only records | 216 |
| Vike-only after the older HyperX global cutoff | 187 |
| Vike-only on uncached symbols inside the older period | 27 |
| Vike-only within the observed time range of a cached symbol | 2 |

**Independent native check:** Every one of the 216 Vike-only native trade IDs was confirmed via public Hyperliquid, with exact timestamp, instrument, side, price and quantity, across seven UTC-day queries. **216/216 confirmed, zero economic-field discrepancies.** This is a bounded one-wallet result, not proof that the provider can recover every gap in the whole wallet registry.

The two notable interior omissions were `HYPE` trade `702446943691396` at `2026-10-15T16:05:20.596Z` and `xyz:MU` trade `195369526954987` at `2026-10-15T16:05:47.103Z`. They were directly confirmed in a separate two-minute native request as well.

**Prior 84-record discrepancy:** An earlier benchmark compared *2,603 consolidated local* records versus *2,687 Vike* records in a different window. The present audit compares a different, explicitly SHA-verified **2,939-fill frozen HyperX cache** versus Vike's **2,732** records. Therefore it does **not** prove that the original 84 records were individually classified. Reproducing that particular consolidated-source window still needs its pinned original input and query boundaries.

### Immutable private artifacts

All paths are on the VPS, under `/home/quant/.local/share/copytrade/reports/vike-research-recovery-20261106/`. Raw data is excluded from Git.

| Artifact directory | Result | Manifest SHA-256 |
| --- | --- | --- |
| `W028-raw-1725effe42185069b435` | 14 original MCP chunks, 2,732 fills | `0bb71d237beb11cab59b07962e7ef79bda57fc401f34b43aea43932c1a487acf` |
| `W028-60257fa9852c898e16a8` | Initial 29 older-cache gaps | `3f8f616142e0b7c6ae50bfd259c854a21d6fcfa728ef91fabeefb1fd31a3cb5b` |
| `W028-840ef85e2a383570a843` | v1 complete set of 216 Vike-only, native-confirmed fills | `8189ef805581eef27e189005a8ffe11700560d44c6c65dfeff81a41f9c1f27c3` |
| `W028-906a295a777a9a0740e9` | **Current v2** complete 216-fill set retaining each matching raw native Hyperliquid record alongside raw Vike record | `c8c39a591e95219f39184e017de8cc60c1e649b01cce5e5e98ddd36f0de74d35` |

The current v2 overlay's derived JSONL SHA-256 is `45271d1345996a6481ccc84a44981ea4a3f19b1e8c02c10a9228a3a25d1c58e7` (prior v1 derived SHA `db35d005c43fb2c885f7ce03cd999eb9534f3dfa21155919798c2c0d7af1a379`). The v2 overlay preserves each **matching native source record**, not only its comparison verdict; complete native day-query response bytes were not separately archived. The source Vike SHA chain is `1725effe42185069b4359d7dde9af4b3cb2efd299e2497178e0eed2c3ae14e3d`; frozen HyperX pages SHA chain is `22ac164bc4b92b80aea482872a931d29475d612b6099b805ff751ab1a6682abb`. All artifacts are private directories and files (0700 / 0600). Records carry `local_first_known_at = null`, `is_retrospective = true`, `follower_eligible = false`. No source journal, SQLite roster, frozen research cohort or execution engine was mutated.

### Reproducible, read-only commands

From the branch that implements the commands (and with the pinned private raw archive available as `--vike-dir`):

```bash
uv run --frozen --group dev python -m copytrade_pm.pm_vike_reconcile \
  --vike-dir /home/quant/.local/share/copytrade/reports/vike-research-recovery-20261106/W028-raw-1725effe42185069b435 \
  --hyperx-cache /home/quant/.local/share/copytrade/reports/five-pod-20261029-research/slow_pod_data_v1/hyperx_fills_cache_v1 \
  --alias W028 \
  --registry-db /home/quant/.local/share/copytrade/registry/wallet_registry.sqlite
```

For native verification use `python -m copytrade_pm.pm_vike_native_verify` with the same four arguments plus `--include-after-cutoff`. This uses bounded official public API calls and may encounter external rate limits; no `--output-root` is needed to re-verify existing immutable overlays. Do not rerun immutable publish with the same fingerprint; exclusive creation deliberately rejects overwrites.

**Known limitation:** The archive reader expects `vike_w028_part_NNN.json` chunks under `--vike-dir`, and this v1 implementation is deliberately bounded to W028; it is not a multi-wallet ingestion worker.

## Continuation: 2026-11-06 registry provenance, NAV and Vike canary

### Registry truth: physical bytes vs research authority

The current SQLite and six relevant historical backup files all contain **zero** `research_selection_proofs` rows. None can restore an independently reviewed signature by rolling back. `copytrade-wallet-registry doctor` now includes `selection_diagnostics` on failure, without changing its fail-closed exit code 2 or metadata authority. Actual read-only output identifies:

- Reviewed pinned V2 source `21f4e940...`: six selections, `PINNED_V2_LEGACY`; it is not required to have an Ed25519 signature.
- `a899f0f6a4331c246307189f3ab75d87e1a515b84a2e926073ce33ff994ce9eb`: `regime.macro/TriadA` and `regime.macro/TriadChop`, `MISSING_SIGNED_PROOF`.
- `sqlite_physical_integrity=VERIFIED`, `selection_provenance=BLOCKED`, `doctor_ready=false`. No keys were generated; no registry or sealed portfolio rows changed.

The only acceptable repair is an independently trusted, externally reviewed signer manifest and public key fingerprint through the existing `signed-selection` backed-up import mechanism. The live missing row cannot be recreated from a Vike feed, old V2 decision or an invented signing key.

### Actual NAV audit: W028 and P1/P14

Official Hyperliquid public `userAbstraction` reported W028 in **`unifiedAccount`** mode. `subAccounts` returned **seven linked subaccounts**. Its parent `spotClearinghouseState` reported a USDC total of **39,162.65464661** and USDC on hold of **39,160.623702** at observation time (2026-11-06); these are quote collateral quantities, not source equity. No atomic whole-account family snapshot was obtained. Do not sum Vike main accountValue and HIP-3/DEX values or treat the spot quote as capital.

Read-only `copytrade-pm-paper-readiness` against the current P1/P14 observer journal returned `BLOCKED_NO_TRADE` for **both** portfolios. All five observed accounts had incomplete independent NAV scope; four were in unifiedAccount mode, one was disabled; frozen alias identities remained `UNSEALED_FROZEN_MEMBER_WALLET_IDS`. P1 needed 12 observed native market instruments, P14 needed 26, while venue quote freshness and executable volume were also blocked. No broker or worker mutation was made.

### Read-only Vike stream canary: implemented, live not authenticated

The `pm_vike_stream_canary` research CLI implements:

- A single wallet-scoped `hl.fills` subscription with **explicit `min_usd: 0`**, a dedicated key on the `X-API-KEY` handshake header (never a URL query token), and Vike's required JSON `{"action":"pong"}` response to server ping frames.
- Per-subscription frame cursor persistence, replay deduplication by `event_id`, source timestamp versus **fresh first-local receipt timestamp**, immutable raw event hash and evidence in an isolated `0700` directory / `0600` SQLite journal.
- Atomic event+cursor checkpoints, no cursor rewind on duplicate, fail-closed gap handling, bounded REST cursor catch-up with the same wallet and `min_usd=0` filters. REST/WS parity only reports a *sample* if both sets agree, the stream had no gap, pages are complete and at least one actual sub-$1,000 event was observed.
- Bounded duration, bounded pages, no broker route. Without `VIKE_API_KEY` in the VPS environment or explicit acknowledgment of a **dedicated key**, it refuses to start or create local state. The Vike MCP OAuth session is not exposed to the VPS.

Proposed bounded run **only after provisioning a distinct read-only key in a protected VPS environment**:

```bash
uv run --frozen --extra source --group dev python -m copytrade_pm.pm_vike_stream_canary \
  --registry-db /home/quant/.local/share/copytrade/registry/wallet_registry.sqlite \
  --alias W028 --state-root /home/quant/.local/share/copytrade/reports/vike-stream-canary-20261106 \
  --seconds 60 --live --dedicated-key-only
```

The code is an opt-in research tool, **not** a permanently deployed collector, and has **not** connected to live Vike WS. The VPS variables `VIKE_API_KEY`, `VIKE_TOKEN` and `VIKE_ACCESS_TOKEN` were not configured at inspection. Vike's official [API reference](https://vike.io/data/api) limits one active connection per key/path; new sockets replace old sockets with close 4410. Never share a streaming key with an active production consumer. Official stream reference: [event channels](https://vike.io/docs/data/reference/stream-channels). REST cursor retention is three days; a source idle gap must not be silently interpreted as complete observations.

## Remaining blockers — not production data ready

1. **SQLite signed selection provenance**: the actual private database passed SQLite `PRAGMA integrity_check` but had **0 rows in `research_selection_proofs`** while required signed selection records exist in the application. The registry `doctor` fails. Reimport only authentic owner-signed source evidence through the approved, backed-up registry release process. Vike cannot resolve this provenance defect. Do not fabricate a signature.
2. **Whole-source-account NAV**: Vike's W028 summary includes HL and XYZ positions, but its reported equity is not a synchronized, independently reconciled parent/subaccount/HIP-3/unified-collateral denominator. Missing whole-account NAV means **no follower sizing admission**.
3. **Persistent stream**: No equivalent Vike API credentials or `vike-data` binary were available in the VPS environment inspected. ChatGPT MCP access is not unattended VPS service authentication. WS small-fill delivery, 3-day cursor retention, crash recovery and REST catch-up parity remain unverified; production adapter was **not** activated.
4. **Provider completeness**: Only W028 has this actual native-confirmed recheck. Remaining authoritative wallets require staged quota-aware comparisons, gap classification, ledger/funding and full-DEX/subaccount scope checks.
5. **Licensing**: Vike's [API changelog](https://vike.io/data/changelog) explicitly changed **archive files downloaded from 2026-11-05** to CC BY-NC 4.0, requiring a separate commercial license; earlier downloads stay under their earlier license. The live [API reference](https://vike.io/data/api) confirms this, while the separate [licensing page](https://vike.io/data/licensing/) still describes archive CC BY 4.0 and appears inconsistent. The REST/MCP response attribution guidance is distinct from archive licensing; do not infer archive commercial rights from API access. Do not ingest archive files into commercial production without resolved written permission.
6. **Science and trading**: Retrospective Vike timestamps cannot supply the time our system first observed the signal, or actual follower costs/PnL, Propr instrument orderability or authorization. No historical data repair changes these gates.

**Current disposition: engineering-verified bounded W028 historical recovery, not production-ready ingestion, whole-account NAV, scientifically qualified portfolio, or authorization to trade.**
