# Coding Standards (`copytrade-pm`)

Engineering and review rules for the single-owner appliance. Formatting and executable verification live in [pyproject.toml](pyproject.toml) and `scripts/ci.sh`; [docs/INDEX.md](docs/INDEX.md) routes domain authority.

## Ownership and deletion

- Keep financial, source, fact and roster writes with their existing journal owners. Do not introduce a second implementation of a financial transition.
- Prefer deleting an unused mechanism to moving it into another module. Delete its executable entry points, comments and tests together; preserve historical evidence and obligations.
- Portfolios are private configuration and independent data. Software revision, environment and lifecycle are appliance-wide.
- Use native git, uv and systemd operations. Do not add a supervisor, release controller, dashboard or deployment framework.

## Discovery and input contracts

- Keep capability discovery and actual parser construction stdlib-only. Never import providers, credential loaders or state writers just to list commands.
- Keep the declarative capability catalog, actual argparse routes and operations documentation in parity. Unknown and retired routes fail closed.
- Reuse existing authority validators. Required parser arguments and conditional runtime requirements remain explicit; a dry run cannot imply successful execution.
- Validate private paths, pins, clocks and ownership before mutation. Missing or incomplete evidence remains unknown or unavailable.

## Isolation and typing

- Clear repository-local `GIT_*` overrides before inspecting another checkout or running isolated Git fixtures.
- Anchor relative test timestamps to one fixture clock. Do not combine import-time clocks with later wall-clock expectations.
- Model distinct structured records with distinct types. Use explicit JSON/provider boundary types where inputs remain heterogeneous; do not suppress mismatches with blanket ignores.
- Verify touched Python modules with pyright and strict mypy before committing. Do not add lint or type-checking packages to `uv.lock` without explicit approval.

## Acceptance

- Verify meaningful public behavior and falsifiers: point-in-time cutoffs, fixed-k, source gaps, duplicate replay, financial identity, rollback and protected authority.
- Exercise CLI wiring alongside owner-level contracts. Verify real journal copies before a runtime cutover.
- Run full local CI at the clean committed candidate and retain its exact-revision receipt. Report implementation, verification, activation and scientific qualification separately.
