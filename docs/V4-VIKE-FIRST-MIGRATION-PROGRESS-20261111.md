# Vike-first migration: nonactivating engineering and live evidence (2026-11-11)

**Status:** transport observation and independent REST census implemented/tested; **no reconciled complete-position source, no 14/14 continuous coverage, no V4 source cutover**. Authoritative design: [Vike-first ADR](decisions/2026-11-11-vike-first-wallet-source.md). Finance and timing contract: [position-first ADR](decisions/2026-11-08-position-first-t300.md).

## What exists

- `pm_vike_selected_fills.selected_campaign_wallets`: resolve the complete frozen 16-portfolio cohort to exactly **14 unique selected parent accounts**, checked against the canonical SQLite registry and private SHA-pinned campaign. A historical campaign alone is not a signed trading selection.
- `pm_vike_selected_fills.run_selected(... include_positions=True)`: opt-in single Vike WebSocket for `hl.fills` and `hl.positions`, both with `min_usd:0`. Independent cursors, strict event IDs, actual receive clocks, retrospective recovery tagging, atomic raw observation/checkpoint, deduplication, explicit gap tracking. Existing 0811 fill-only service is unchanged unless separately released.
- `pm_vike_position_observations`: new tables in the existing selected-fills observation SQLite, original wire SHA and canonical event SHA, position notification parsing, per-channel ACK and latching GAP. Every position observation is **NOT_COMPLETE_BOOK** and **NOT_PAPER_ELIGIBLE**. A duplicate original event with a different transport cursor must not mutate financial state.
- `pm_vike_official_parity`: bounded official HTTP `perpDexs` + per-DEX `clearinghouseState` complete selected-parent REST census, strict scope and native Decimal parsing from existing E4, provider-time skew ceiling, original raw response SHA validation. Private `0700` archive stores each original response and SHA-sealed `0600` manifest. The aggregate cohort report is independent audit evidence, not a continuous native stream or paper signal.

## Observed external evidence (read-only, redacted)

- On 2026-11-11, **14/14** selected parent accounts returned a complete **11-DEX** official REST census (max per-account provider stamp skew **4,311 ms**). It was a bounded sampled census, **not** 14 simultaneously continuous subscriptions and not a valid baseline-to-transition source proof.
- The live 14-parent, two-channel Vike WebSocket canary ran for approximately 70 seconds, with one live connection and a dedicated private source key. `hl.fills` acknowledged once; `hl.positions` emitted one GAP at cursor `1794392781332-0000`; no selected fill/position events arrived in this window. The selected position GAP is durable in its private journal. **Continuous 14/14 is 0 verified, paper new-risk eligibility 0.**
- The canary temporarily stopped only the separate `copytrade-vike-selected-0811` *research fill* collector to avoid Vike's same-key `4410` replacement; it was restarted after the canary. `copytrade-v4-sixteen-source-0911` and `copytrade-v4-canonical-sixteen-1111` remained running during the canary. Subsequently, at 11:29:55 CET, the official 0911 service independently exited cleanly with `STOPPED_NATIVE_SUBSCRIPTION_BLOCKED` due to its shared-IP user-subscription limit; an explicitly bounded one-time restart at 11:42:11 CET restored its process to active (PID 2237785 at the immediate check). This does not establish durable native 7/14 continuity; never retry in a storm or infer recovery of missed first-known signals.
- Private original official REST evidence root: `~/.local/share/copytrade/prospective/vike-first-rest-census-1111/`; campaign manifest `campaign-20261111T102300734906Z.json`, SHA-256 `e0d8846407954603829e8ad8cf569ea95192a21a05acb4b3743976c27afd29a4`. Vike canary journal: `~/.local/share/copytrade/prospective/vike-fourteen-canary-1111/selected-fills.sqlite3`. Both are observations, not paper source authority; never point `--source-db` at either.

## Reproducible read-only commands

From the pinned checkout with `uv sync --frozen --group dev --extra source`:

```sh
uv run --frozen --group dev pytest -q tests/test_pm_vike_selected_fills.py tests/test_pm_vike_position_observations.py tests/test_pm_vike_official_parity.py
uv run --frozen --group dev python -m copytrade_pm.pm_vike_official_parity \
  --registry-db "$REGISTRY_DB" --campaign-manifest "$PRIVATE_CAMPAIGN" \
  --campaign-sha256 "$CAMPAIGN_SHA256" --archive-root "$NEW_PRIVATE_ARCHIVE"
```

The second command performs fresh bounded *read-only* official network requests and archives private original evidence. It must not be used as a source of actionable positions, from a cron job without explicit budget, or to silently clear source gaps. `--positions` on `pm_vike_selected_fills` is a live collector option that must use a dedicated key and a separately scoped private state root; avoid running two clients using the same Vike API key on `/stream/hl`.

## Independently replayed original-source proof and pure candidate reducer (follow-up)

An additive nonactivating engineering increment adds `pm_vike_official_parity.verify_archived_official_census`: the consumer must know the expected wallet and SHA of the archived manifest, re-hash **every original official response**, reconstruct the complete per-DEX state from the original bytes through the existing parser and compare all market quantities, times and DEX hashes with the recorded report. A re-derived report alone is not acceptable proof. On the original private 2026-11-11 campaign archive, all **14/14** parents independently verified, with **127** nonzero native position rows across their complete selected-parent DEX scopes (sum of positions across parents, not necessarily unique instruments).

`pm_vike_reconciled_positions` is a strict, pure Pydantic **candidate** position-state reducer: verified initial REST census is always non-actionable; monotonic Vike event cursor and source time, explicit native quantities, position prestate and action, selected account/DEX and locally known event clocks are checked. Provider GAP, retrospective event, mismatch or epoch change fail closed. An independently verified later census can mark a matching candidate `RECONCILED_CANDIDATE_NOT_PAPER_PROOF`, **not** produce a V4 `OBSERVED_STATE_CHANGE`. This is testable deterministic logic, not a durable account-source event journal or a replacement for the existing official stream proof. The existing Pydantic/PM03/04 contracts and paper service remain unchanged.

## Remaining release-critical work

1. Create a versioned official-baseline-plus-Vike observation reconciler with independent complete-book parity, parent/child/DEX identity, bounded source lag, event ordering, durable GAP epochs and provider cursor recovery. Original vendor frames and REST bytes must be individually verifiable. Initial/rejoin baseline is never an entry. No silent flat or exit on gap.
2. Integrate a **separately verified Vike source proof** with V4's `verify_official_position_transition`/consumer seam; do not manufacture an `OFFICIAL_WS` payload from non-atomic REST frames. Preserve T+300 first-local-known, non-resetting coalescing, immediate verified reductions, signed k, PM03/04 and finance journals.
3. Run an authenticated simultaneous 14/14 observation window with live Vike position events, at least one independent per-parent complete-book reconciliation, documented freshness thresholds, and adverse restart/reorder/drop/cursor expiry tests. Quiet accounts require independent reconciliation. The short canary above is **negative/insufficient** evidence.
4. Qualify exact-source reader parity, fail-closed replay and rollback and an isolated 16-portfolio paper-source canary before source-authority cutover. The old official source and old paper ledgers remain unchanged.

**Safety:** This engineering evidence never establishes follower alpha, scientific qualification, broker permission or trading authorization. All 14 selected accounts remain `NO_TRADE` for *new risk from this Vike candidate* until independent source proof. Existing paper-ledger inventories must not be reset or inferred flat.
