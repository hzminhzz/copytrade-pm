# Appliance operational hardening (AH-01–04)

Baseline: `003dee6a8cf0e11ad389d758cafdec9fd9bd254a`. Implements the owner's four-ticket hardening request; does not change source policy, financial authority or appliance topology.

- AH-01: preflight prepares both frozen environments offline, verifies candidate-native configuration and rendered unit semantics/native parsing, confirms the active rollback checkout and installed units, and rejects invalid candidates before shutdown.
- AH-02: compare actual worker identity, configuration, READY receipts, source/quote advancement and durable paper cursors; check prior journal prefix hashes. Scope existing coverage/review blockers separately; require advancement for unaffected owners. Verify software rollback and distinguish failed recovery. Never roll back financial journals.
- AH-03: the observed replay hotspot was repeated JSON outcome-ID table scans. Add a non-unique SQLite expression index in the existing checkpoint schema, preserving the duplicate detection and full source-chain/finance verification. No replay cache across invocations.
- AH-04: one concise update/recovery result with a private evidence receipt; canonical [operations](../AGENT-NATIVE-OPERATIONS.md) explains preflight, recovery, safe retirement, dirty-tree preservation and reproducible measurement.

## Authentic benchmark

Frozen input: retirement/20261128/parity-2; SQLite copies made in temporary directories. V4Pod3 source: 9,963 transitions. Liquid12 LPOD_15 finance: 754 committed events (snapshot, not the live 755+ cursor).

| Restore | Baseline seconds (2 samples) | Indexed seconds (2 samples) |
| --- | --- | --- |
| Source | 5.700, 6.277 | 5.567, 5.996 |
| Paper | 18.013, 17.447 | 2.818, 3.394 |

Paper profile: 19.297 s before, 3.528 s after; repeated SQLite fetchall accounted for 12.899 s before indexing. Full replay result digest unchanged: `cfe501d6810e38b3e3d9b6f2b438b50fb60358afc5639db167122a34bf979dbd`. Source proof digest unchanged: `857e677e9517a45af5e3dc357ea55e4f06d16a3571463c22efbeafb442827ed0`.

Inputs SHA-256: source `ade7adef85e1bb3f84437d239655759a648deae9305cb98df768ef7c6d2a0663`; paper `2eb621b00f2c5d6b3895750fa3b264c73aa677e70bb211f49b36590de026b868`. The timings are local warm runs, not a service startup SLA. Reproduce with the benchmark script. Preserve source Pydantic/hash verification, which dominates remaining source time.

## Boundary

Liquid12 signed scope conflict, pending finance reviews, external retirement and the frozen December 2 assessment are unchanged. No live order route, financial qualification or trading authority. Native fault tests use isolated journal copies and transient systemd units, not production fault injection.
