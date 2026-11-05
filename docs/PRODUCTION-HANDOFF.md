# Production research handoff

This repository remains research only. It has no broker credential or order route.

## Metadata and immutable releases

`copytrade-pm-production-export --db PRIVATE_DB --portfolio A --asof UTC_TIME`
reads schema-v8 SQLite through one query-only transaction. Its inventory digest
hashes logical authoritative rows, never a live SQLite/WAL file. It keeps missing
point-in-time identity, complete source scope and NAV as explicit blockers. An
optional private export file must be new and inside a directory with mode 0700.

A legacy sizing-contract label is not a sealed per-pod allocation. The explicit
`production_manifest.store_policy` API accepts a separately signed
`research-release-policy` and stores it in the same metadata-authority database.
The namespaced `production_portfolio_policies` extension is created only by that
explicit operation. It does not rewrite existing schema-v8 authority rows.
Versions are immutable, protected against update/delete by SQL triggers and against
equivocation by signature/digest checks. Live databases are never migrated by reads.

`copytrade-pm-production-manifest` reads the metadata and policy in one consistent
snapshot. It requires external reviewer and source-observer public keys, signed
complete source scope/NAV attestations, point-in-time identities, exact allocations,
native-market scope, account binding, risk/rulebook digests, expiry and generation.
It signs the canonical `portfolio_release_v1` wire contract using a separately
delivered release key. No broker key is accepted. All signing keys and exports
remain outside Git in protected private directories.

The consumer separately pins its release authority and rollback floor. A manifest
does not grant broker mutation authority. Fresh complete source books and NAV must
still be admitted on every runtime proposal. Public fixtures use invented identities
and an explicit SYNTHETIC mode only.

The producer's inventory commitment combines the native logical registry digest
with the approved policy digest, including signed scope evidence. Changing either
invalidates the original approval. Policy approval does not repair an unknown
historical identity.

## Twenty-day economics

`copytrade-pm-production-economics` reuses `load_tape`,
`JointBlockBootstrap` and the native `contract_actuary.simulate`. It adds no
execution simulator. Supply three independently generated, cost-complete net-MTM
tapes for FIXED, VOLATILITY_THROTTLED and BARRIER_AWARE policies. The tapes must
match portfolio, membership, window and observation grid. Each tape must already
encode the actual causal policy decisions and execution costs; scaling a hindsight
leader-PnL series is not an admissible replacement.

The native actuator now exposes mutually exclusive evaluation pass, breach-before-
pass and timeout probabilities, conditional pass time and maximum daily adverse
excursion. The dossier reports conditional Monte Carlo intervals, contract EV
under an explicit assumed fee, a zero-cost no-buy alternative, and extra-cost
sensitivities using identical joint bootstrap blocks. It does not pick a winner
from the holdout. Predeclared policy code, disjoint training/OOS clocks, independent
follower attestation, account terms and payout rules remain external evidence gates.

Two-minute versus five-minute batching and margin/liquidity/gap variants require
matched executable tapes. Missing variants are UNKNOWN, not fabricated scalar
adjustments. Current real evidence is BLOCKED_ECONOMICS. Synthetic model success,
four weeks of elapsed time and a positive modeled EV never authorize trading.

## Verification

```bash
uv run --frozen --extra actuary --group dev pytest -q tests/test_production_export.py tests/test_production_manifest.py tests/test_production_economics.py tests/test_contract_actuary.py tests/test_pm_contract_selector.py
uv run --frozen --group dev copytrade-pm capabilities validate
```

No live registry migration, source identity edit, signing approval or broker
mutation was performed when implementing these interfaces.
