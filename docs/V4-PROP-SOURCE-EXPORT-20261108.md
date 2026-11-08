# V4 official-source export to protected SHADOW (2026-11-08)

## Authority and scope

The installed V4 `pm_v4_selected_positions` observer is the only owner of
complete selected-account Hyperliquid perp position observations. This
change **does not** alter its existing user service, paper journals, source
census, or PM-03/PM-04 modeled fills. Its public Vike minute data remains
an *estimate*, not an executable follower quote.

`copytrade_pm.v4_source_export` verifies the original `PaperJournal`
chain, stream checkpoints, SHA-linked source receipts, first-local-known
clocks, native DEX coverage, account identity and original raw frame. It
exports a versioned `v4_signed_source_export_v1` packet, with an independently
key-pinned `source-observer-v4` proof and (only when complete valid marks
exist) a separately signed `source_book_v1`.

The source mark is derived only from official native `positionValue / abs(szi)`
in that observed frame. No marks are fabricated from Vike minute OHLC or
synthetic spreads. Missing native positionValue results in a signed source
event **without a book**. An initial or reconnect BASELINE is never an
eligible transition. GAP/SCOPE/STOP invalidate pending new risk; they do
not prove a close. The original event clock is retained.

## External trust and private transfer

The production signer is an **externally provisioned** Ed25519 source-observer
key, *not* a key generated or approved by this module. A separate externally
pinned source public key must match the private key exactly. Source signing
is **not an exchange signature**: it authenticates the verifier's chain
assessment and observed account scope. A separate reviewed, signed
`portfolio_release_v1` and root trust floor must still authorize the exact
selected accounts and k. A private source JSON map must be checked against
the sealed SQLite selection, not inferred from aliases alone.

The exporter takes a read-only source journal, private (0600) selected-account
JSON, source key and pinned public key, a private cursor-state path and a new
private output path:

```bash
python -m copytrade_pm.v4_source_export \
  --journal-db /absolute/private/v4-selected-positions/paper-events.sqlite3 \
  --selected-json /absolute/private/selected-accounts.json \
  --source-signing-key /absolute/private/source-observer.key \
  --source-public-key /absolute/private/source-observer.pub \
  --cursor-state /absolute/private/v4-source-export-cursors.json \
  --private-output /absolute/private/v4-export-unique.json
```

Run under the `quant` owner with a pinned Copytrade release and an
owner-private output directory. The initial invocation anchors at the
existing verified head and exports **no historical transitions**.
Subsequent invocations advance the cursor only after an immutable signed
packet is durable; a crash can repeat a packet, and the receiving projection
must deduplicate by signed cursor. When more than 256 events accumulate per
account, invoke again with a distinct output name to drain the backlog.

For a protected handoff, establish a narrowly scoped, read-only source-export
directory or independent root-mediated transfer and verify permissions,
consumer identities, installed hashes and public key pin. Do **not** chmod
the source journal or signing key for `prop-planner`, install a signing key
into Guardian, or let Planner modify the original `PaperJournal`.

## What this does not prove

A signed export is not a signed production portfolio, follower equity,
coherent Propr order history, independent executable quote, broker permit,
funded trading authorization or proof of matched PnL. An unobserved real
transition remains UNOBSERVED despite fixture tests.

Missing external signer, recipient trust pin, signed portfolio manifest,
protected transfer or accurate native-to-broker market identity mapping must
be reported as blocking actual Guardian admission. Existing V4/V3/CCXT user
services and all protected services are unchanged by this producer.
