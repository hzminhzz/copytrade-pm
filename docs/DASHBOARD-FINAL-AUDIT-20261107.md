# Dashboard final independent audit — 2026-11-07

## Verdict and scope

**BLOCKED_SAFE_STATE_PRESERVED.** The source audit and corrective work are complete. Private deployment cannot pass its mandatory permission and operational-isolation preflight. This is an observability client; it adds no financial or trading authority.

The mission explicitly authorized an independent dashboard and additive read-only producer after their gates pass. The blocker is demonstrated access enforcement, not an assumption that deployment was never authorized. The execution identity cannot read protected Guardian journal/heartbeat evidence, and noninteractive sudo requires authentication. Automatic approval review rejected obtaining the stored sudo credential for the bounded read-only probe. No rejected privileged command executed, and that access path was stopped.

A dedicated dashboard/producer identity, protected read permissions, live private ingress, real Guardian cadence/journal continuity and actual dashboard-only rollback remain **NOT_VERIFIED**. Unchanged process IDs establish only process continuity. Missing pod budgets, broker-executed follower PnL and an external notification recipient are optional limitations; they are not the reason for this verdict.

## Source and runtime identity

| Boundary | Observed revision |
| --- | --- |
| Dashboard baseline / merged PR #171 | `28bda4f23175a8d2b5f644ee157e8dc732dae7f3` |
| Functional corrections | `65924fcd24e7bc74039ec0f96c442510633e96b2` |
| Actual viewport correction | `1837cf3902a26df3df48aa2daa610649c215fb92` |
| Format-only checkpoint | `12deb5bd25962f1940f76a81eddffe5f0599b733` |
| Final tested source / built-wheel checkpoint | `13f594dfd2d3a0b4582514f86810e482e0894539` |
| Owner source | `00073496e0a3e4dc59b8d1cac4d3533c37c275ce` |
| Current connector source | `5f7664b51988e9f48b3ff3a07876a136c2d97de8` |
| Observed installed protected release | `07551a9978ee9ff3c7412dd1eadd5413e17b8421` |
| Owner compatibility manifest: research | `b1dc9fd9493b28d56385400708e7547f74b173fe` |
| Owner compatibility manifest: connector | `2db29b50af301741821781dedf64e4d8194fc125` |

The owner manifest pins were preserved. Its full compatibility gate passed at those exact older research/connector revisions. That result does not certify a new dashboard installation or the inaccessible installed journal. Current-source component tests and a direct owner-producer/consumer fixture round trip are separate evidence.

## Confirmed failures and corrections

| Reproduced failure | Corrected behavior |
| --- | --- |
| Account B's clear snapshot resolved account A's active incident | Resolution requires the same account-bound incident key |
| Retention reused recurrence IDs after repeated incidents | Persistent monotonic incident sequence survives retention/restart |
| A stopped notifier retained apparently current VERIFIED source status | Missing, future or older-than-120-second state is STALE |
| Stale Guardian/Broker cards displayed unqualified state labels | Evidence is explicit; stale state is last observed; blocked/unavailable state is UNKNOWN |
| A slow cache fill blocked unrelated cached reads | Per-key fill serialization; short metadata-map lock; bounded admission |
| Option-like wallet/report filters reached native argument parsing | Invalid scalar filters fail closed before parser dispatch |
| Actual POST bytes could exceed a claimed short Content-Length | Actual bytes, declared length and total body deadline are enforced |
| Non-ASCII invalid login raised a server error | UTF-8 byte comparison rejects invalid credentials with HTTP 401 |
| Gap/reset retention evicted bucket-local chart extrema | Every bucket min/max remains critical; impossible budgets fail closed |
| Minimal core install failed dashboard test collection/execution | Optional UI/chart tests explicitly require their extra; core adapter coverage remains active |
| Firefox phone tests measured outer windows and silently used 500-pixel viewports | BiDi sets the CSS viewport; dimensions and all eight views are asserted |
| Narrow research forms clipped query-button text despite no page overflow | Query buttons have a dedicated row; all three buttons are checked for content overflow at each viewport |
| An active process alone was labeled financially DEGRADED | OS activity is displayed separately; process liveness leaves financial evidence UNKNOWN |

The 30-file formatting commit was checked for identical Python ASTs against its parent. It changes formatting only. No risk policy, sizing, broker transport, production journal writer or registry mutation implementation changed.

The final regression file includes 20 tests, including the actual owner producer -> six captures -> dashboard consumer fixture path. That fixture preserves journal bytes, source sequence, exact zero, account redaction and PAPER_SHADOW classification. It does not attest production OS ACLs.

## Source verification

The final clean source gate passed at `13f594dfd2d3a0b4582514f86810e482e0894539`, with an unchanged, clean worktree before/after. The subsequent receipt update changes documentation only.

```bash
uv sync --frozen --all-extras --group dev
uv build
PYTHONPATH=/home/quant/dev/prop-production/src uv run --no-sync pytest -q --tb=short
uv run --no-sync ruff check src tests scripts
uv run --no-sync ruff format --check src tests scripts/dashboard_runtime_probe.py
uv run --no-sync marimo check src/copytrade_pm/dashboard/pages/*.py
uv run --no-sync copytrade-pm capabilities validate
UV_PROJECT_ENVIRONMENT=.workspace/dashboard-final-0711/core-venv uv run --frozen --group dev pytest -q --tb=short
git diff --check
```

| Gate | Final observed result |
| --- | --- |
| All extras, including direct owner fixture | **1,496 passed, 1 skipped**, 30.46 s; the optional Selenium browser module is exercised separately below |
| Separate minimal core environment | **1,347 passed, 32 skipped**, 22.31 s; optional dashboard/chart/owner dependencies are explicitly skipped |
| Ruff / formatting | PASS / **359 files** already formatted |
| Marimo notebooks | **9 valid** |
| Native capability catalog | **110 capabilities, 0 errors** |
| Wheel and sdist | Built successfully |
| Clean source gate resource observation | **53.876 CPU s**, **57.760 wall s**, **401.8 MiB** peak; test-unit measurements, not dashboard production resource acceptance |

CPython was **3.14.6**. The unchanged `uv.lock` SHA-256 is `bf7f8494358f11953fc71d5aece84c61354970a9e7560316a41c957f765520cd`. Dashboard dependencies include Marimo **0.24.0**, Altair **6.3.0**, Polars **2.1.0**, Starlette **1.10.0**, Uvicorn **0.52.4**, httpx **0.28.1** and httpx2 **2.16.0**. Owner typing checks are recorded below; no new typing gate was invented for the dashboard repository.

### Built-wheel and disposable-stage receipt

A separate Python 3.14 environment installed **44** dashboard dependencies from a frozen, hash-checked export (`uv pip sync --offline --require-hashes`), then the built wheel with `--offline --no-deps`. An isolated `python -I` smoke check imported from the wheel environment, verified all **169 packaged Python files** against the source bytes, and passed HTTP authentication/cookie/startup checks. This was not an editable-checkout test.

- Wheel: `copytrade_pm-0.1.0-py3-none-any.whl`.
- Wheel SHA-256: `e718faa6bf139dd2421ac847e3d20111ea7d6ad2338a93166833758c9e089d27`.
- Sdist SHA-256: `c16a59142a0a48ab9f1da78b024b007863d2c3093d69675227aafc8502fdbdf2`.
- Final artifact manifest inspection: **173 wheel entries**, **480 sdist entries**; no `.env`, private workspace, database, Parquet or credential-key payload paths.
- Disposable candidate: `13f594dfd2d3-e718faa6bf13`, with the exact owner/current-connector pins in the identity table.
- Prepare, verify and selection passed. Rejected candidate selection preserved the existing staged pointer. There was no earlier dashboard staging target in this disposable root.
- Scope: **BUILT_WHEEL_AND_DISPOSABLE_STAGING_ONLY**; `production_installed=false`; `trading_authorized=false`.

This receipt does not establish least-privilege installation, an operational service or actual service rollback.

Already observed companion evidence:

- `bash scripts/verify-local.sh all` on owner source `0007349`, with the manifest-pinned research and connector worktrees: **PASS**.
- Owner Python 3.13 and 3.14: **148 passed, 1 skipped** on each; Ruff and mypy (31 files) passed; wheel/sdist built.
- Pinned connector: **303 passed, 1 skipped**; Ruff/build passed. Native owner gateway: **2 passed**. Bybit adapter/observer fixtures: **15 passed**.
- Pinned research: **1,378 passed**; Ruff, formatting, build and 110-capability validation passed.
- Current connector `5f7664` against current research source: **303 passed, 1 skipped**; Ruff and wheel/sdist builds passed. The skip is the absent legacy `pm_combo2_rest_capture` module; existing dependency deprecation warnings remain.
- Current owner gateway/observer/capture tests against connector `5f7664`: **23 passed**.

No connected broker orders or Demo orders were exercised.

## Browser evidence

The final Firefox suite passed **15 tests in 138.39 s** at source `13f594dfd2d3a0b4582514f86810e482e0894539`:

```bash
UV_PROJECT_ENVIRONMENT=.workspace/dashboard-final-0711/browser-venv \
DASHBOARD_BROWSER_ARTIFACT_DIR=.workspace/dashboard-final-0711/browser-final2 \
uv run --frozen --with selenium --extra dashboard --group dev pytest -q --tb=short \
  -W ignore::ResourceWarning -W ignore::pytest.PytestUnraisableExceptionWarning \
  tests/test_dashboard_browser.py
```

The browser process asserted actual CSS viewports **390 x 844**, **430 x 932** and **1280 x 800**, all eight views at each size, no page overflow, and no clipped query-button content. The suite also covered 20 fresh document sessions, two concurrent independent clients, keyboard/hash navigation, reload, safe URL scope, registry reactivity and the explicit OS-state column. **27 genuine PNG screenshots** were produced. Final 390-pixel Wallets/Research Lab screenshots were visually checked after the button correction. The transient test unit consumed **30.251 CPU s** and **213.9 MiB** peak; these are local test observations.

The first 15-test Firefox pass was insufficient evidence for phone dimensions: its PNGs were 500x758 and 500x846 despite requested 390x844 and 430x932 outer windows. An explicit inner-viewport assertion reproduced the failure. The corrected BiDi tests passed all three actual viewport sizes before the final full run. Historical outer-window results are not used as proof of phone layout. Later screenshot review also reproduced a 23-pixel-high wallet button containing 37 pixels of text; the final browser assertions check button content bounds in Wallets, Portfolios and Research Lab.

Screenshots and XML receipts are retained privately with the local test evidence. The browser points at a disposable loopback server with unavailable protected captures. It is not an operational private-deployment test.

## Permitted live-registry measurements

These are real SQLite reads as the existing unprivileged operator, with 50 observations per row. They measure the adapter, not browser rendering, HTTPS ingress or production financial capture.

| Workload | p50 ms | p95 ms | p99 ms |
| --- | ---: | ---: | ---: |
| Wallet search, fresh reader/cache | 34.896 | 52.219 | 55.649 |
| Wallet search, reused reader/cache | 21.287 | 38.984 | 41.980 |
| Overview, fresh reader/cache | 21.203 | 62.830 | 109.117 |
| Overview, reused reader/cache | 0.012 | 0.047 | 17.147 |

Registry bytes were unchanged. Wallet results were STALE because registry parity/provenance was not promoted; Overview financial fields were UNAVAILABLE because there was no admitted capture. A 32-call/eight-thread burst completed in 1,735.904 ms with 7 STALE and 25 UNKNOWN results. This documents load shedding, not successful high-concurrency acceptance. The process used 4.013 CPU seconds and a peak RSS of 58,144 KiB.

The two-read semaphore is **per Python reader process**, not a service-wide limit across Marimo kernels. Production aggregate concurrency and cgroup limits still require measurement. Producer full-chain duration/I/O, financial capture freshness, real private-page latency and Guardian noninterference remain NOT_VERIFIED.

## Protected-runtime comparison

At **2026-11-07 11:13:19.887 UTC**, the committed read-only probe ran as UID 1001 and observed the same installed release and protected process identities/restart counts as the initial baseline:

| Protected service | Baseline PID -> final PID | Baseline -> final restart count | Final OS state |
| --- | --- | --- | --- |
| Guardian | 2518410 -> 2518410 | 0 -> 0 | active/running |
| Broker | 2518409 -> 2518409 | 1 -> 1 | active/running |
| Planner | 2518411 -> 2518411 | 0 -> 0 | active/running |
| Observer | 1924914 -> 1924914 | 0 -> 0 | active/running |
| Bybit observer | 1924915 -> 1924915 | 0 -> 0 | active/running |
| Watchdog | 1924920 -> 1924920 | 0 -> 0 | active/running |

All six retain their original unit identities, group `prop`, 512 MiB memory limit and TasksMax 64. Final available host memory was **15,192,800 kB**. Protected heartbeat reads returned **PermissionError**, and journal opening returned **OperationalError**. Therefore real reconciliation cadence, financial journal continuity/integrity and financial health remain **NOT_VERIFIED**. The installed release remains `07551a9978ee9ff3c7412dd1eadd5413e17b8421`; owner source `0007349` was not installed.

The observed baseline had all six protected units active/running, no dashboard dependency, and installed release `07551a9`. Guardian, broker and planner had the same start epoch. Broker's restart count of 1 was pre-existing; the other five restart counts were 0.

The read-only probe in `scripts/dashboard_runtime_probe.py` reads fixed systemd properties, fixed release metadata, bounded heartbeat fields and at most 64 journal event identities/timestamps when permitted. It uses a read-only SQLite URI, query-only mode, a one-second busy timeout and 384 MiB address-space limit. It never obtains credentials or changes services. Journal metadata is explicitly not full hash-chain validation.

No dashboard/capture/notifier production service, OS account, protected ACL, release symlink, private ingress route or trust-floor change was made. Disposable test processes are separate from the six financial services. Root permission, journal integrity/continuity and reconciliation cadence cannot be inferred from their process IDs.

## Financial evidence classification

| Evidence class | Verified boundary and remaining limitation |
| --- | --- |
| Historical research | Native report/portfolio readers, immutable hashes and evidence labels are tested. Dashboard correctness does not requalify a study or establish out-of-sample profitability. |
| SHADOW accounting | The installed compatibility manifest remains SHADOW/NO_TRADE. The actual owner-producer fixture round trip retains PAPER_SHADOW classification. Live protected account captures were inaccessible. |
| Demo observations | Connector and owner adapter fixtures passed. No Demo order or live Demo performance acceptance was performed. |
| Broker-executed follower economics | UNAVAILABLE without an admitted independently authoritative tape; no executable follower PnL or alpha claim is made. |
| Missing/unsupported history | Unverified pod budgets, pod equity and follower history remain explicitly unavailable. No synthetic accounting or interpolated financial proof was added. |

Engineering correctness, scientific qualification and trading authorization remain separate. External notification delivery is **NOT_CONFIGURED**; the verified contract is durable dry-run behavior.

## Deployment receipt

**NOT_DEPLOYED.** No new dashboard, producer or notifier service was activated. There is no verified private dashboard URL, production service identity, installed dashboard SHA or operational rollback result to report. The candidate/wheel above is disposable staging evidence only. Existing Tailscale/Cloudflare routes and policies were not changed. Authenticated private ingress, effective production OS permissions, source freshness, real UI latency, producer scan cost, dashboard-only fault/recovery and protected Guardian cadence remain gated.

## Issue disposition

Closure follows original criteria and the recorded amendments, after the corrective source merge:

| Issues | Disposition and evidence boundary |
| --- | --- |
| #154–#158 | Source acceptance satisfied: bounded reader, auth/run-only shell, truthful Overview, canonical wallets, independent health |
| #159–#163 | Source acceptance satisfied: risk, execution, portfolio state, evidence-qualified charts and immutable research catalog; absent financial data remains explicit |
| #164 | Dry-run contract satisfied: independent source incidents, deduplication/retries/restarts/ACK, external delivery NOT_CONFIGURED |
| #165 | Source/mobile evidence recorded; keep open because its amendment retains private deployment/operational acceptance |
| #166 | Keep open: real permissions, Guardian cadence/journal continuity, production load and isolation faults not verified |
| #167 | Keep open: dedicated identity/private ingress and actual installed restart/failed-start/rollback not verified |
| #153 | Keep open: mandatory private operational acceptance has not passed |

The release module is disposable staging only. A staged pointer reversal and artifact-hash test is not an installed-service rollback.

## Required external action

An explicitly approved protected-runtime observation path is required to complete the mandatory baseline, followed by least-privilege setup and measured isolated deployment under the existing conditional authorization. The automatic approval rejection must be resolved by the operator; it must not be bypassed through another credential or root-equivalent route. Optional external notifications may remain NOT_CONFIGURED.
