# Registry review hardening — 2026-11-04

**Scope:** engineering corrections to reviewed commit `5d7b4d7` / PR #79, after the already merged frozen-membership PIT fix `e5d9933` / PR #91. The registry remains owner-private **research metadata**, not a broker, paper worker, trading permission, or scientific qualification system.

## Invariants and fixes

1. **Sealed definitions are independently checked on every read.** `wallet_registry_portfolios.select_asof` checks the exact approved alias set, sizing/status, source SHA, source commit and expected canonical definition digest, rather than trusting a `portfolio_seals` row by itself. SQLite triggers block INSERT/UPDATE/DELETE of membership rows once a version has been sealed. These triggers are an integrity guard, not a complete defense against a malicious SQLite administrator who can drop triggers. Read verification still detects alias substitution after simulated trigger removal. The previous v7 retrofilled historical `wallet_id` values are not rewritten; query-time as-of alias resolution follows PR #91.
2. **Version-pinned selection queries.** `portfolio --current` verifies the **exact** `research_selections.portfolio_version`, not whichever portfolio version is newest today. A later signed E6 v2 does not change the original V2 historical query for E6 v1.
3. **Exact whale identity.** The specific `Whale_0x5f94` requires the SHA-256 of the **entire 42-character** owner-private Ethereum address, not `startswith("0x5f94")`. The original Phase 4 identity CSV itself is SHA-pinned. The generic display label `HL Perps Whale` is never a standalone canonical alias. A different source or identity requires a distinct reviewed generation; account/subaccount scope remains a separate paper-admission prerequisite.
4. **Preflight before pointer rollback.** `registry_release.py rollback` now runs the target pinned release's own read-only doctor against the **current** SQLite and current source SHA generation before changing the pointer. If the old release cannot read the current database, rollback aborts with the active pointer intact. Pointer rollback does **not** revert the database. An offline restore requires an independently reviewed verified backup plus explicit source-generation reconciliation; do not restore older database bytes while the tracker/evidence source has advanced.
5. **Data-driven future research selections.** A future report does not require edits to the old V2 priority constants. `wallet_registry_signed_catalog` accepts a bounded, owner-private, Ed25519-signed `copytrade_signed_research_selection_v1` manifest with namespace-qualified portfolio IDs, canonical member aliases, research role and rank. An independently supplied trusted public key fingerprint must match. Imports are **manual, opt-in, and append-only**. The manifest's source SHA, signature, key fingerprint, original first-local import time and exact versions are persisted; every read re-verifies the signature and membership. Selections are labeled `SIGNATURE_CHECKED_RESEARCH_ONLY`, **not** owner-approved production, trading-authorized, scientifically qualified or paper-running. A signature proves only signer-key possession; operator review of signer identity is external and mandatory. No signing keys, live wallet addresses or source fills are stored in Git.

## Future report schema (example only)

```json
{
  "schema": "copytrade_signed_research_selection_v1",
  "scope": "NEW_FORWARD_PAPER_RESEARCH",
  "trading_authorized": false,
  "definitions": {
    "gemini.phase7/E12": {"members": ["ACT04", "S053-HYPE"]}
  },
  "selections": [
    {
      "portfolio_id": "gemini.phase7/E12",
      "role": "PRIMARY_FORWARD_PAPER_RESEARCH",
      "priority": 1
    }
  ]
}
```

The example is illustrative, **not a selected portfolio**. An externally trusted operator must create and sign the manifest; ChatGPT must not generate a substitute owner key or sign Gemini analysis on the operator's behalf. Canonical identities still require owner-private evidence. Duplicate aliases representing the same wallet are rejected. No source `k` multiplier is automatically imported into follower sizing.

### Preview (read-only)

```bash
uv run --frozen --group dev copytrade-wallet-registry signed-selection \
  --manifest /owner-private/research/new-selection.json \
  --signature /owner-private/research/new-selection.sig \
  --trusted-public-key /owner-private/research/reviewer.pub \
  --trusted-key-sha256 '<externally-verified-64hex-public-key-SHA256>'
```

Each file must be owner-private mode `0600` under a `0700` directory. The review public-key fingerprint must originate independently from the signed manifest. A matching signature alone does not prove owner approval.

### Explicit metadata import (only after real operator review)

Repeat the same command with `--apply`. This creates a fresh, integrity-checked SQLite backup under the private registry backup directory before a single-writer transaction. It does not mutate any existing historical sealed portfolio, Telegram subscriber list, PM financial journal, broker or service. It never registers a paper run. The first-known time is the actual local import time; it is not the time in a vendor fill or Gemini report.

Query with `portfolio --current` and `portfolio <namespace>/<id> --asof <UTC>`. The original Git-pinned Gemini V2 stays immutable and remains queryable at its original known-at timestamp.

## Controlled release and rollback

1. From a clean reviewed Git commit, run the core/market tests, Ruff, format, documentation-link audit and build. Test source/SHA, PIT, collision, backup and tamper regressions. Do not use a future synthetic known-at as real follower evidence.
2. Back up the actual owner-private SQLite with the registry `backup --to` command; verify `PRAGMA integrity_check` and `PRAGMA foreign_key_check`, and independently preserve the source evidence manifest SHA.
3. On a **disposable copy** of that backup, execute `sync --apply`, `doctor`, `portfolio --current`, `portfolio E6`, `wallet --alias W083`, and historical P1/E6 as-of reads. Existing sealed version/hash counts must not be changed unexpectedly.
4. Only then update the owner-private registry metadata in a controlled transaction and activate the new read-only on-demand release via `registry_release.py activate`. Verify pinned release and pre/post service PID parity. Do not touch broker, paper worker, tracker, ensemble or Telegram.
5. `registry_release.py rollback` is **blocked** if the previous pinned code fails current registry/source doctor. Restoring an old database is a **separate operator-approved offline restore**, not an automatic fallback. Preserve the new and old backups, logs and exact Git SHA before any recovery action.

**Release vs qualification:** Even a verified active registry release establishes only metadata correctness. Runtime admission, independently verified paper worker heartbeats, whole-source equity and scientific matched follower PnL remain separate UNKNOWN/NOT_ESTABLISHED gates.
