# CWSA Chapter 2 — six-portfolio paper runtime and release contract

**Status:** The implementation on `fix/cwsa-chapter2-verified-paper-20261112` is **engineering code under review**, not evidence of a new verified running release, scientifically qualified P&L, or trading authorization. Inspect the actual running service PID and pinned release rather than this document's date.

## Current research identities and existing service

The SQLite sealed registry, not this page, owns the selected membership and versions. Requested research portfolios: `A`, `B`, `C`, `Combo2`, `regime.macro/TriadA`, and `regime.macro/TriadChop`, together using 14 unique source wallet IDs.

- Source: `copytrade-cwsa-5m-source-chapter2.service` — independently owned, official native REST CWSA source authority.
- Paper supervisor: `copytrade-cwsa-5m-paper-chapter2.service` — independent virtual-paper journal owner, **no broker transport**.
- Existing unqualified paper root: `/home/quant/.local/share/copytrade/prospective/cwsa-5m-paper-chapter2-20261112`.
- Canonical source journal: `/home/quant/.local/share/copytrade/prospective/cwsa-5m-source-chapter2-20261112/paper-events.sqlite3`.
- Old V4 paper archive remains immutable and independently replayable. Never clear it to reset Chapter 2.

A six-portfolio SQLite seal is **not** a signed CWSA copy mandate. Source checkpoint collection can operate safely with `BLOCKED_EVIDENCE` financial admission. No modeled fills are claimed merely because journal objects and service processes exist.

## Durable source-wave projection

The paper supervisor reads the canonical source database read-only. Each portfolio stores its own `chapter2_wave_receipts` chain, including original outcome IDs, source clocks, wave membership, evidence hashes and missing-wallet disposition.

- A complete portfolio wave may close independently of unrelated portfolios.
- An incomplete wave waits until the source's **original pinned publication grace**; then it closes with a missing-source record, never a fabricated flat position.
- Same-checkpoint late results cannot retroactively replace a closed wave.
- A crash after a durable receipt but before a JSON status publication is recovered from the ledger; status files are replaceable projections.
- The source journal is never imported as an alternative state authority. The signed finance adapter verifies/mirrors the original source chain and original native evidence into the existing PM03 `PaperJournal` before consuming it.

`cwsa_chapter2_status.json` and each `<portfolio>/status.json` are read-only operator projections, not financial stores.

## Optional signed **paper-only** finance release

This is **not enabled** merely because the six registry seals exist. The current historical registry contracts identify research or virtual-paper selection, including non-executable Triad seals. They do not supply approved fixed-k values for CWSA.

A qualified paper release requires all of the following, separately provided and verified before activation:

1. One **new empty paper epoch root** and unique `--run-label`, with its own six independent PM03 journals. Never upgrade the provisional unsigned paper root in place.
2. Externally authorized Ed25519-signed Copy Mandates for every selected member of each admitted portfolio, with immutable generation, native market scope, frozen decimal k, policy epoch, source account and scope generation, and future activation window.
3. A SHA-256-pinned `cwsa_chapter2_paper_release_v1` bundle containing the exact six-portfolio seal hashes, independently defined risk policy and market catalog, and the signed mandate envelopes. Approval is **per portfolio**: partial portfolio membership is never admitted.
4. A separately provisioned trusted release **public** key (never infer trust from a signature's self-supplied key), and an independently verified, existing read-only L2 quote journal. Vike bars and midpoints cannot be presented as executable follower L2.
5. Risk limits, costs, source proofs, first non-actionable baseline, clocks and all PM03 one-shot protection verified. This adapter cannot sign mandates, discover trading keys, submit orders, or authorize a broker.

CLI:

```bash
python -m copytrade_pm.pm_cwsa_six_paper \
  --state-root /private/new-epoch-root \
  --source-db /private/canonical-source/paper-events.sqlite3 \
  --registry-db /private/registry/wallet_registry.sqlite \
  --run-label cwsa_chapter2_paper_epoch2 \
  --approved-paper-bundle /private/approved-paper-release.json \
  --approved-paper-sha256 '<independently-verified-sha256>' \
  --trusted-paper-authority-public '<independently-trusted-public-key-hex>' \
  --quote-db /private/verified-l2/paper-events.sqlite3 \
  --poll-seconds 5
```

No default signer, default k, synthetic receipt or automatic research-to-production promotion exists. Starting a new epoch does not make the economic qualification calendar retroactive. An approved paper consumer records immutable modeled P&L and costs; it does not create a protected execution permit.

## Verification and rollback

For targeted tests from the exact source checkout:

```bash
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -B -m pytest -p no:cacheprovider -q tests/test_cwsa_chapter2_ingestion.py tests/test_cwsa_chapter2_release.py tests/test_cwsa_chapter2_mirror.py tests/test_cwsa_six_paper.py tests/test_checkpoint_source.py tests/test_checkpoint_journal.py tests/test_checkpoint_paper.py tests/test_checkpoint_campaign.py tests/test_copy_mandates.py
.venv/bin/ruff check src/copytrade_pm/pm_cwsa_*.py tests/test_cwsa_*.py
.venv/bin/ruff format --check src/copytrade_pm/pm_cwsa_*.py tests/test_cwsa_*.py
```

Before any deployment: record service PIDs/sha, journal heads, source cadence, WAL/disk budget, all old service consumers, provider limits, and a pinned rollback release. Test isolated `--once`, restart, same-checkpoint late arrival and original source replay; verify service after restart. Do not change protected Guardian/connector/broker services or the old immutable V4 archive.

The current operator frontend source is `/home/quant/dev/copytrade-pm/dashboard/`; new Chapter 2 evidence should be projected through its existing privacy-safe read-only data flow. **Do not confuse a local JSON status file or a running legacy Grafana process with verified dashboard deployment.**

**Qualification:** A functioning source collector, clean paper journal and passing synthetic tests are engineering evidence. Count prospective economic holdout only after legitimate signed paper admissions, complete source coverage, real independent quotes, paper-financial receipts and risk/cost observations. Tickets #319/#320/#326/#327 retain their original required evidence and acceptance criteria.
