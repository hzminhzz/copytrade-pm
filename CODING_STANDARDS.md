# Coding Standards (`copytrade-pm`)

Judgment standards for engineering changes and code review. Mechanical formatting and automated lint rules live in [pyproject.toml](pyproject.toml) and `scripts/ci.sh` rather than here; see [docs/INDEX.md](docs/INDEX.md) for domain authority boundaries.

## Module Structure and Cohesion

- **Separate static catalogs from inspectors and validators:** Keep reviewed metadata tables declarative, and split AST inspectors or parity validators out into a focused sibling module once a mixed file grows past roughly 500–800 lines or forces callers to load thousands of catalog lines to modify inspection logic.
- **Share validators across command families:** Reuse parameterized contract and access validators across families (`NATIVE`, `OPERATIONS_SUBCOMMANDS`, `GROUP_OPERATIONS`) instead of duplicating slightly different validation loops per family.
- **Separate parser vs runtime argument contracts:** Keep unconditional argparse requirements (`required_arguments`) distinct from conditional mode-specific requirements (`runtime_required_arguments`) so dry-run metadata checks track actual CLI parser behavior without runtime guesswork.

## Fail-Closed Inspection and Isolation

- **Keep discovery modules import-isolated:** Capability discovery and metadata inspection paths (`pm_capabilities.py`, `capabilities list`/`show`/`validate`) use stdlib-only imports and static inspection; never import optional network providers, credential loaders, broker clients, or state-mutating writers into discovery modules.
- **Bounded AST inspectors fail closed:** Inspect only explicitly supported syntax constructs and reviewed owner contracts. Emit explicit `UNSUPPORTED_*`, `UNREVIEWED_*`, or `UNKNOWN` diagnostics on dynamic dispatch (`exec`, computed action routing, factory helpers) instead of silently certifying completeness.
- **Isolate git subprocess environments in hooks and tests:** Clear repository-local `GIT_*` overrides (`pm_runtime_readonly.clean_git_env` / `git rev-parse --local-env-vars`) before invoking isolated temporary-repo git fixtures or inspecting release directories so caller hook environments never mutate the parent worktree index.
- **Anchor relative test timestamps to a single fixture clock:** Do not compare module-import `NOW_MS` constants against per-test `datetime.now(UTC)` calls; long full-suite CI runs (`>180s`) turn clock drift into spurious failures.

## Static Typing Hygiene

- **Model distinct record schemas with distinct `TypedDict`s:** Split subclasses from a shared base (such as `_OperationsSubcommandSpec` and `_GroupOperationSpec` inheriting `_BaseCommandSpec`) rather than marking required family keys `NotRequired` or suppressing mismatches with `# type: ignore` casts.
- **Verify touched Python modules with `pyright` and `mypy`:** Keep edited modules error-free under strict checking before committing, and do not add type-checking or lint packages to `uv.lock` without explicit approval.

## CLI Contracts and Verification

- **Reject deprecated aliases fail-closed:** When replacing or tightening an input flag or field contract (for example `--input` vs `--request`), reject legacy aliases explicitly rather than silently accepting both.
- **Keep catalog, parser, and ops docs in three-way parity:** Update [pm_capabilities.py](src/copytrade_pm/pm_capabilities.py), [pm_operations.py](src/copytrade_pm/pm_operations.py), and [docs/AGENT-NATIVE-OPERATIONS.md](docs/AGENT-NATIVE-OPERATIONS.md) together whenever subcommands, flags, or modes change, verified with `copytrade-pm capabilities validate`.
- **Test CLI wiring end-to-end with positive and falsifier cases:** Exercise added flags and error codes directly through `copytrade_pm.pm_operations.main` alongside targeted falsifier assertions rather than testing helpers in isolation.
