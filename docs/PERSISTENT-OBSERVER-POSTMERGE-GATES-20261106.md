# Observer post-merge live preflight — 2026-11-06

**Scope:** independent read-only diagnostics of the merged persistent-observer
engineering path. This record is not a startup, 72-hour shadow, release cutover,
portfolio re-selection, or trading authorization.

## Reproducible source and observed cut

- Remote `main` at the start of this work: `c4becf5a3093bf4d97acdf1ffc51cbba81b6f0a5` (PR #144 merged).
- Diagnostic executable: `8860db7fd9db2b2d8e9554e16357d04498383771` on isolated branch `fix/observer-preflight-diagnostics-20261106`.
- Actual diagnostic observed at **2026-11-06T15:33:52.175712+00:00**.
- Immutable live SQLite inventory SHA: `b2e5ea14fc3f1b71778bc78f4a568b0e7ee711802e2ab3ebfd72ef282cbdb855`.
- Source/private data, original observer journal, registry rows, and systemd services were **not modified**.
- Exact config was an ignored local diagnostic copy of the previously prepared blocked 157-market configuration, with only its executable revision pinned to `8860db7`; it was never installed or activated.

## Strict-gate results

The native `copytrade-pm-paper-observe` command was called with both
`--preflight-only` and `--diagnose-preflight`. It exited **2**, returned
`status=BLOCKED`, `safe_to_start=false`, `financial_admission=BLOCKED_NO_TRADE`
and `order_route=NONE`. No candidate state directory was created.

| Gate | Result | Independent evidence |
| --- | --- | --- |
| Private state collision/permissions | PASS | New isolated candidate path |
| SQLite integrity/foreign keys | PASS | Native query-only integrity scan |
| Registry generation and stability | PASS | Inventory SHA unchanged across checks |
| Latest research selection provenance | **BLOCKED** | `STREAM_SELECTION_PROOF_MISSING` |
| Frozen P1/P14 portfolio seals | PASS | Both found as-of |
| Exclusion-aware P1/P14 watchlist | **BLOCKED** | `PUBLIC_TRADE_WALLET_PROPFIRM_EXCLUDED` |
| Sealed identity count for planning | ESTIMATE ONLY | Five distinct recorded parents; not an eligible watchlist |
| Configured shared-IP subscription budget | **BLOCKED** | `STREAM_CONNECTION_BUDGET_EXCEEDED` |
| Protected legacy journal reader | PASS | Read-only verified heads |
| Financial admission | BLOCKED | No broker route or financial event |

### Selection provenance

The live registry is structurally intact, but contains **zero** accepted
`research_selection_proofs`. Its latest dated selection SHA
`a899f0f6a4331c246307189f3ab75d87e1a515b84a2e926073ce33ff994ce9eb`
has two research rows (`regime.macro/TriadA`, `regime.macro/TriadChop`)
without the required trusted Ed25519 proof.

Do **not** forge a signer, backdate this selection, rewrite the SHA-sealed history,
or consider ordinary user chat approval a cryptographic signature. An authentic
reviewed future selection and independently verified key fingerprint are required
for the established signed catalog import. The original owner-approved 2026-11-04
V2 research selection remains separate historical evidence.

### Portfolio exclusions

The owner-private prop-firm exclusion table has **75** records at this cut.
In the sealed P1/P14 definitions, **P1 has 0/3 excluded**; **P14 has 1/5
excluded**. For comparison, `gemini.phase4/E6` has **2/5 excluded**. These
are only aggregate counts, not a recommendation or an alternative roster.

An existing exclusion does not disappear because an account is observable or
its source NAV can be ignored for read-only collection. Keep the affected
watchlist blocked until a *separately approved, versioned, cryptographically
attested* prospective selection satisfies the authority and exclusion contracts.
Do not mutate the original frozen P1/P14 definitions to make the preflight pass.

### Shared-IP resource capacity

The prepared configuration requests 157 distinct native markets and five
recorded unique parent accounts (a census **estimate**, not approved watchlist).
Under its existing conservative reservation:

| Resource | Candidate estimate | Existing reservation | Provider maximum | Result |
| --- | ---: | ---: | ---: | --- |
| Physical WebSocket connections | 5 | 8 | 10 | **13 > 10: blocked** |
| User-specific identities | 5 | 10 | 10 | **15 > 10: blocked** |
| Subscriptions | 476 | 350 | 1000 | 826 <= 1000: within configured arithmetic limit |

These are **planner calculations**, not live authenticated measurements.
Ordinary established TCP connections are not automatically counted as WebSocket
sessions. A new allocation requires observed per-service socket/user/subscription
usage, conservative reconnect/dial headroom, and nondisruptive shared-IP
coordination. Do not lower reservation constants merely to pass preflight.
Do not silently reduce the required 157-market denominator or omit held hedges.

## What can proceed

1. Resolve authentic future research-selection provenance through the existing
   read-only preview and externally approved signed importer. Preserve every
   previous source SHA and first-known timestamp.
2. Obtain an explicitly approved non-excluded prospective watchlist. Keep
   P1/P14 historical frozen membership and all owner exclusions unchanged.
3. Independently measure existing Hyperliquid IP usage and reserve enough capacity
   for the candidate; otherwise retain the resource block.
4. Re-run **strict** read-only `--preflight-only` with a current clean pinned
   release, then launch the separate candidate/watchdog only if all gates pass.
5. Accumulate 72 actual elapsed hours and independently audit real coverage under
   issue #141. Issue #142 still requires a **separate** public-observer cutover
   authorization and compatible release/journal rollback pair.

**Actual operational state:** no 72-hour portfolio shadow was started or
completed by this work. The active public observer remained on its older pinned
release during the audit. No demo/real broker operation was invoked. Missing
whole-wallet NAV is not used as an excuse to refuse read-only capture, and
neither code merge nor the diagnostic qualifies financial execution.

## Engineering verification

At `8860db7`, the full frozen all-extras suite passed **1,237 tests**.
Ruff check and format check passed (303 Python files formatted); the native
capability catalog verified 94 entries with zero errors, and offline wheel/sdist
build succeeded. The core suite passed **1,118 with 15 skipped** and the market
suite **1,236 with 1 skipped**. The negative preflight integration invocation
above separately reproduced the real source and resource blockers without any
state-root creation.

The canonical documentation auditor's live-registry invocation is **BLOCKED**
by the same unsigned newest research selection. A separate explicitly
**STATIC_LINKS_ONLY** invocation checked 13 required files and 210 local links,
with zero broken links; its injected absent generation deliberately reported
`dated_status_requires_refresh=true`. It must not be mistaken for a passing
live SQLite source-status audit.
