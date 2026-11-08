# Grafana integrated acceptance — independent bounded audit (2026-11-08)

## Scope and release identity

- Parent #180; acceptance #190; Phase 2 candidate PR #195, source `f9c9bb01b2b26ea6e9c62716cdd16beff63a41d5` (still draft at inspection).
- Isolated worktree/branch: `audit/grafana-phase3-0811`; initial HEAD equal to the candidate. This audit adds a release-pin regression and fail-closed verification function. The final audit commit is recorded by GitHub, not assumed to have been installed.
- Phase 1 reference merged revision `f3343cdde77e793fed373d0b2d80d70ea867f24c`.
- No production Grafana, Marimo, protected financial or broker component was changed. No cutover #191 or retirement #192.

## Engineering and staging evidence

| Gate | Observation | Disposition |
| --- | --- | --- |
| Focused source suite | 49 tests pass at original candidate; 50 after new release-pin regression | PASS (engineering) |
| Full frozen suite | `uv run --frozen --all-extras --group dev pytest -q`: 1560 passed, 3 skipped | PASS (engineering) |
| Lint/format | Ruff check full tree; format of touched files; `git diff --check` | PASS |
| Release pin negative | A structurally valid changed dashboard passes shape checks and creates a new self-hash but is rejected by `verify_approved` against independently supplied expected SHA-256 | PASS (source regression) |
| Isolated deployment | `bash ops/grafana-phase1/stage.sh start`; pinned Grafana/Infinity image build; publisher, projection, Grafana, ingress healthy; tailnet HTTPS 8444 | PASS (staging startup) |
| Real owner ingress/Viewer | `security_acceptance.py`: owner reaches Viewer; no native Admin; admin and file routes, arbitrary Infinity URL/query/method denied | PASS (owner test) |
| Egress and ingress separation | Two Docker networks internal-only; Grafana no default route; gateway native reader absent; direct Unix-socket ingress denied to nonprivileged test | PASS (staging structural check) |
| Browser routes/responsiveness | `browser_phase2.py`: 5 dashboards x 3 CSS viewports = 15 PASS with source rows and no document horizontal overflow | PASS (automated layout only) |
| Complete image review | Screenshots at `/tmp/copytrade-grafana-phase2-qa/` on VPS were not independently viewed or graded | BLOCKED (manual/visual) |
| Genuine non-owner Tailscale peer | No independently authenticated non-owner peer used | BLOCKED_EXTERNAL_IDENTITY_EVIDENCE (#184) |
| Genuine finance & paper execution | Staging intentionally has no canonical private SQLite or protected owner-capture financial source; numerical claims remain unavailable | BLOCKED (source authority) |
| Grafana backend alert transitions | Rule definitions and earlier staging checks exist; this audit did not exercise complete Normal/Pending/Alerting/NoData/Error/recovery transitions | NOT VERIFIED |
| Pinned installed release / rollback | Bundle expectation check is source-only. Neither installed image-to-reviewed-commit proof nor bad-release restore measured here | NOT VERIFIED (#189) |
| Performance p50/p95 | Not measured in this audit; previously reported cold p95 4.48s over six samples is a dated reference, not a current pass | NOT VERIFIED (#190) |
| Protected Guardian journal/cadence | Protected journal sequence and reconciliation cadence were not authenticated or inspected in this audit | BLOCKED (noninterference proof) |
| Teardown | `bash ops/grafana-phase1/stage.sh stop` removed only the 8444 Serve route and isolated Grafana containers/networks; 8443 Serve remained mapped to `127.0.0.1:18777` | PASS (staging cleanup) |

## What the source patch actually changes

`release_verify.py` retains the existing informational SHA-256 inventory in `verify`. A new `verify_approved(root, expected_bundle_sha256=...)` refuses malformed pins and any mismatch (`UNAPPROVED_RELEASE_BUNDLE`). The CLI accepts `--expected-bundle-sha256` and reports `release_admitted=false` when no independent expected hash is provided. Neither code path represents a signed financial authority, actual installed artifact attestation, or verified rollback.

## Decision

**NO_GO for controlled production cutover (#191).** Engineering source tests and isolated staging checks pass, but independently authenticated non-owner peer denial, financial-source provenance, alert failure/recovery, visual inspection, robust performance measurement, installed-release rollback and protected journal/cadence remain incomplete. Do not mark #184–#190 complete. PR #195 must remain draft unless separately audited against its own source requirements. This is not evidence that trading is ready.
