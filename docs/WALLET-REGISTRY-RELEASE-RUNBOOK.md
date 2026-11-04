# Registry-only read-only release and rollback — 2026-11-04

**Scope:** controlled, owner-approved activation of the standalone SQLite **metadata** registry. No timer, no new daemon, no broker/order route, and no restart or mutation of the production tracker, ensemble, source-ABC or forward-paper workers. The registry database already exists independently at `/home/quant/.local/share/copytrade/registry/wallet_registry.sqlite`; this release mechanism pins and activates a *read-only on-demand consumer*, not a financial or source-observation authority.

## Preconditions

1. Use the **clean reviewed Git feature branch** in a DevSpace worktree, not a dirty `main` checkout. Inspect GitHub CI and release commit. Stop on unexpected non-Git source drift.
2. Run the full core and optional native-market test suites, Ruff, formatting, `uv build`, the original PM-02 36-wallet frozen parity regression, source/ledger doctor and local [docs reference audit](WALLET-REGISTRY-ACCEPTANCE-20261104.md).
3. Capture service names, active state and MainPID for `copytrade-tracker.service`, `copytrade-ensemble.service`, `copytrade-source-abc.service`. Their source/financial DBs are explicitly out of scope.
4. The `doctor` must show live source SHA match and CURRENT; frozen research must remain 158, exclusion 22 at this source cut, desired 215, subscribed 150, seven sealed research definitions. These dated counts are **not permanent thresholds**; unexplained source changes require a separately reviewed generation.
5. Actual admitted/receipt-health count remains UNKNOWN, paper global RUNNING UNKNOWN, scientific qualification NOT ESTABLISHED and trading authorization false. Do not release code that upgrades these states from config, tests or vendor history.

## Commands

From the clean registry feature worktree:

```bash
uv run --group dev python scripts/audit_wallet_registry_docs.py
uv run --group dev python scripts/registry_release.py preview
uv run --group dev python scripts/registry_release.py activate
uv run --group dev python scripts/registry_release.py verify
uv run --group dev copytrade-wallet-registry doctor
uv run --group dev copytrade-wallet-registry paper
```

`activate` creates an owner-private Git-archived release under:

```text
/home/quant/.local/share/copytrade/registry/release-control/
  releases/<Git-SHA>/         # staged tracked source and pinned dependency lock
  current                    # atomic symlink to reviewed Git SHA
  release-state.json         # 0600 manifest of tracked source SHA values
  preactivation-*.sqlite     # 0600 ONLINE backup of registry inventory only
```

Every root directory is `0700`, the inventory and backup are `0600`. Activation, verification, rollback and repair use a shared owner-private `operator.lock` with nonblocking filesystem locks; a concurrent operator must retry rather than race the pointer. File and directory metadata changes are fsynced. Activation and rollback restore **both** the original pointer and committed state on ordinary post-switch exceptions. The controller verifies the tracked source fingerprints and the **installed pinned release** with `uv run --offline --frozen --no-dev`. It checks restored backup SQLite integrity and foreign keys before changing the `current` pointer. No network install is authorized; unavailable offline dependencies fail the release. No existing service unit, timer, release, source or broker database is replaced.

To reverse **only the pointer**:

```bash
uv run --group dev python scripts/registry_release.py rollback
uv run --group dev python scripts/registry_release.py verify

# Crash recovery ONLY if verify reports a pointer/state mismatch.
# This returns to the last committed state, never guessing an uncommitted SHA.
uv run --group dev python scripts/registry_release.py repair
uv run --group dev python scripts/registry_release.py verify
```

`repair` is deliberately narrower than `rollback`: if a process was killed between the two atomic pointer/state renames, the normal `verify` fails closed. With an intact committed state and matching prior source hashes, repair restores only the pointer recorded in that last committed state. Missing metadata or a tampered pinned release stops repair for manual inspection; it never chooses a new release from an uncommitted symlink. Crash recovery and same-process error recovery are independently fault-tested.

Rollback never modifies the inventory database or other service. With no previously active release, `verify` returns `NO_RELEASE_POINTER`. Source generation and registry backups are preserved for independent recovery; a previous release remains under `releases/<sha>`. To restore an actual damaged registry SQLite database requires a **separate reviewed offline recovery**, not the pointer rollback. Do not overwrite a healthy current inventory with an older backup simply to satisfy an acceptance checkbox.

## Acceptance and monitoring

- Verify all three pre/post service PIDs and states unchanged. A PID change during release fails closed and requires investigation; no automatic service restart.
- Verify the pinned release uses `mode=ro` / SQLite `query_only` for source tracker/FP ledgers and does not write to them. Registry metadata status can be queried independently of the FP worker.
- `copytrade-wallet-registry doctor` and `paper` run from the pinned release, not just the developer worktree. Missing/stale sources abort activation; the prior pointer remains untouched.
- Confirm `current` resolves to the expected Git SHA and all tracked file hashes match the manifest.
- Verify backup integrity with `PRAGMA integrity_check` and `PRAGMA foreign_key_check`; the prior private DB remains usable.
- An on-demand CLI is sufficient for WR-11. **Do not add a registry refresh timer automatically.** Timer evaluation is a separate optional operational change requiring proof of source freshness cadence and failure alerts.
- Public-facing summaries carry date/cutoff and UNKNOWN as appropriate. Never expose source addresses, chat IDs, private account labels or credentials in CI/PR comments.

**Executed operator checkpoint (2026-11-04):** the first pinned on-demand release at `7a282846a33422a2ae82e38353ad224ec18800fc` returned `READ_ONLY_RELEASE_ACTIVE`. `verify` returned `ACTIVE_READ_ONLY_VERIFIED`; the rollback test returned `POINTER_ROLLED_BACK` and `NO_RELEASE_POINTER`, followed by successful reactivation and verification. Pre/post tracker, ensemble, and source-ABC PIDs stayed unchanged, all preactivation SQLite backup integrity checks passed, and no timer was installed. The source manifest remained `562750974cc7f3746483c9bbaab38c1294c87f970acea2584f6c59ca88684202`. **This is a dated result, not a guarantee that later source files or services remain unchanged.**

The registry release only proves infrastructure safety and source indexing. It **does not** create a paper campaign, verify follower economics, authorize execution or close FP-10/#67. WR-07 still needs a genuine independently operating publisher with durable worker/feed/market heartbeats. WR-08 cannot import positive scientific outcomes without independent attested follower/control evidence.
