# Direct architecture and code review — 2026-11-28

Baseline: `a2cf400c3aeb7a9d47be87b6e1576bde3bda2669`.
Scope: the single-owner appliance request and the complete diff from that baseline.
Reviewer: the direct executor; no delegated or independent-review claim.

## Standards review

- Deleted obsolete executable owners, release paths, dashboard/Site code, Prefect, old capability routes and their tests. An import-closure pass found the remaining frozen E0 portfolio wrapper had no production caller; its hardcoded portfolio mechanism and tests were also removed.
- Preserved FactStore/RosterStore ownership, canonical source state transitions, PM03 financial transitions and shared kernel semantics. Retained historical replay functions still needed by existing signed journals.
- Made source and paper ownership explicit in private configuration. Reject path overlap, symlinks, pin drift, unknown schema and incompatible legacy source unit files before mutation.
- Capability listing remains stdlib-only and matches the actual CLI parser. Runtime status distinguishes process identity, source coverage, quote freshness and financial admission.
- New and previously adapted source modules pass strict mypy (20 modules). The two legacy replay modules have 120 pre-existing strict-mypy diagnostics; normalized diagnostics are identical before and after the replay optimization. Their broader typing debt is not represented as a clean strict-type gate. Pyright also reports nine existing diagnostics in those two legacy modules.
- The source-chain replay change is bounded to one locked replay invocation. All source chains are fully verified before their proofs are reused, every event binding is checked, and no cache survives restore. A regression test first failed on three repeated chain reads, then passed with one read and rejection of subsequent tampering.

## Specification review

- One canonical checkout, frozen environment, target, three continuous roles and one health timer replace independent releases and portfolio-specific workers.
- The source unit retains a compatibility alias required by independent Prop-Production. Its source database path remains stable; protected accounts are not part of the lifecycle.
- Observation adoption retains original seals/clocks and a separate adoption clock. An incomplete historical selection is quarantined as a whole; no addresses, research cards, leases or coefficients are invented.
- V4Pod3 remains source-only because no approved paper epoch was found.
- Liquid12's signed source-policy/census conflict remains fail-closed. Resolving it requires an explicit future source/mandate transition.
- Native systemd readiness follows durable owner verification. Paper groups poll independently, and cancellation drains admitted writes before owner leases release.
- Update uses the installed interpreter for reconciliation and preserves journals during software rollback.
- A verified retirement archive preserves historical installations, unmerged/dirty work and Git objects before deletion. The December 2 frozen assessment remains an explicit unfinished obligation.

- Authentic restore matched historical finance, but the Liquid12 journal has pending source reviews. An initial all-input poll correctly processed pending work in the diagnostic copy, so it cannot be labeled duplicate replay. Acceptance separately checks the acknowledged prefix, an actual committed terminal financial outcome, restart equality and the size of the pending backlog. Diagnostic copies never modify active journals.

## Activation gate

Targeted appliance/adoption tests and financial/source replay falsifiers passed during review. Full CI and authentic-journal parity must bind to the clean committed candidate before activation. The runtime receipt must then show the same revision, checkout and environment for every retained PID, source and quote progress, and preserved independent account processes. These engineering checks confer no scientific qualification or trading authorization.
