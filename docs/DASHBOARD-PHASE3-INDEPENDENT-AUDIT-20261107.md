# Independent Phase 3 audit — 2026-11-07

Scope: copytrade-pm PR #171, submitted source `c39b9975c900c36750294851656692af1821ee3e`, against `main` at `458dfc9787bf99a252f11626372ec8d3779b6732`. This is source/security verification, not dashboard deployment or trading authorization. No protected services, broker orders, Guardian HALT, financial journals, or release pointers were changed.

## Disposition: REQUEST_FIXES — DO NOT MERGE

**HIGH — inter-session browser route integrity is not verified.** Real Firefox tests for 390x844, 430x932, and 1280x800 on the same disposable run-only Marimo ASGI process reproduced a cross-session failure. After a previous session opens `/health`, a subsequent fresh Selenium session loading `/` can render the `Operations · System health` notebook while the browser URL is still `/`. Initial viewport test runs produced 3/3 `ACCESS_DENIED` on login; changing the login page's `Referrer-Policy` from `no-referrer` to `same-origin` allows same-origin form authentication while preserving the configured Host/Origin protections. Subsequent runs produced a reproducible view mismatch (in one full attempt 1 pass/2 fail; another attempt 2 pass/1 fail). A distinct ASGI builder per notebook was tested and did **not** solve the last-session issue; that unproven change was reverted. The existing Firefox test deliberately remains strict. Do not treat isolated single-viewport passes or HTTP 200 as route acceptance. Diagnose Marimo session routing and rerun repeated independent browser sessions on a shared disposable server. Also verify all eight routes, mobile/keyboard navigation, reconnect, stale source handling and concurrent sessions before source merge.

**MEDIUM — staging pin mismatch (FIXED in follow-up source).** The submitted `dashboard.release.prepare` reused a candidate with the same copytrade-pm/wheel hashes even if the Guardian or connector SHA changed. `verify` accepted a syntactically valid but internally inconsistent manifest source SHA/candidate ID. Added failing-first regression tests for both and corrected the checks. The fix enforces all companion pins and consistent candidate identity; no protected installation is performed.

**LOW — browser login compatibility (FIXED in follow-up source).** The GET `/login` response used `Referrer-Policy: no-referrer` while POST login requires an allowed Origin. Actual Firefox form submission failed before the policy change; the strict same-origin policy permits ordinary browser login without disclosing the login URL to other origins. Other-origin POST is still denied. A security regression checks the response header.

## Independent verification before remediation

- `uv run --frozen --extra dashboard --group dev pytest -q`: **1,431 passed, 7 skipped** at the submitted source.
- `uv run --frozen --extra dashboard --group dev ruff check .`: PASS.
- `uv run --frozen --extra dashboard --group dev marimo check src/copytrade_pm/dashboard/pages/*.py`: PASS.
- `uv run --frozen --extra dashboard --group dev copytrade-pm capabilities validate`: 110 valid, 0 errors.
- `uv build`: wheel and source distribution built.
- `prop-production` owner tests `uv run --frozen --group dev pytest -q tests/test_dashboard_capture.py tests/test_operator.py tests/test_guardian.py`: **14 passed** against its checkout `00073496e0a3e4dc59b8d1cac4d3533c37c275ce`.
- Relevant trading-connector checkout: `5f7664b51988e9f48b3ff3a07876a136c2d97de8`. Guardian's compatibility manifest still pins older source/connector revisions (`b1dc9fd...` and `2db29b...`); exact full pinned three-repository verification with the PR revision has **not** passed. Do not claim compatible installed deployment from these targeted tests.
- The notification/backend performance suite is synthetic only, not proof of independent Guardian cadence or external message delivery.

## Operational observations (read-only)

`prop-production-guardian.service`, `prop-production-watchdog.service`, `prop-production-broker.service`, `prop-production-planner.service`, `prop-production-observer.service` and `prop-production-bybit-observer.service` were observed **active/running**. Guardian and broker service identities: `prop-runtime`; watchdog: `prop-watchdog`. The operating installation uses `/opt/prop-production/current` per `ExecStart`. Exact installed release commit, full process binary provenance, private ACL, real authenticated ingress, journal integrity under dashboard load and live owner capture cadence were not independently established. Dashboard is **NOT DEPLOYED**. Guardian/broker production was not restarted.

## Remaining mandatory acceptance

Fix the shared-server cross-session routing defect with a behavioral regression. Re-run the real Firefox suite across repeated browser sessions and all eight routes, then rerun full core, security, failure-injection/notification, Marimo, lint, built-artifact staging/rollback, owner compatibility and clean pinned cross-repository gates. Publish exact final SHAs and independent evidence before reconsidering the conditional squash merge. External notifications are NOT_CONFIGURED; protected capture installation and operational isolation acceptance remain separate future authorization.

Ticket status: #164–#167 **source work present**, engineering acceptance **NOT VERIFIED**, PR source **NOT MERGED**, operational deployment **NOT DEPLOYED**. Parent #153 remains open. No scientific or live trading authorization follows from this work.
