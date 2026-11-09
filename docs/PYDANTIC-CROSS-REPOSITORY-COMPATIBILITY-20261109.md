# Pydantic-native producer compatibility — #227

Status: ENGINEERING VERIFIED, not deployed or repinned. The only companion pin
authority remains each reviewed prop-production compatibility.json. No shared
model package, new broker route, Guardian policy change or protected write was made.

## Revisions and boundaries

| Reviewed consumer/source | Revision | Result |
| --- | --- | --- |
| Existing Guardian compatibility baseline | prop-production b60aef9302340d0a8d2c66439a03a8ee7162ef7a | Existing worktree; source/tests/scripts/dependency files verified equal to the preserved preflight runtime source baseline. Complete pinned all-repository gate passed. |
| Default-branch Guardian application | prop-production 00073496e0a3e4dc59b8d1cac4d3533c37c275ce | Complete existing pinned all-repository gate passed independently. |
| Additive V4 SHADOW consumer | prop-production 36918fdcf1b3df27312dadd27c7e077f00fd54a0 | Existing worktree, same source/tests/scripts/dependencies as inspected V4 branch tip. Real candidate producer -> signed packet -> consumer T+300 -> Guardian denial passed. This is an offline candidate consumer, not an installed V4 claim. |
| Existing manifest's research pin | copytrade-pm b1dc9fd9493b28d56385400708e7547f74b173fe | 1378 tests, Ruff, format, build and capabilities passed. |
| Existing manifest's connector pin | trading-connector 2db29b50af301741821781dedf64e4d8194fc125 | 303 tests passed, one unsupported historical optional canary skipped; Ruff/build passed. |
| Candidate Pydantic source | copytrade-pm 9aa94d23a3f1a3e65d524bbb078d061d2043c010 plus this test/document commit | Existing signed wire contracts accepted. Runtime research bridge explicitly rejects this unpinned checkout. No compatibility manifest changed. |

Runtime-specific inventories and protected baseline identifiers remain in the
private preflight evidence. A successful test is not an active release or pin.

The V4 producer keeps v4_signed_source_export_v1, v4_official_event_proof_v1 and
source_book_v1. Internal native source/paper semantics are separately versioned.
The exporter signs derived evidence without replacing original native raw hashes,
observer chain/receipt hashes or first-known clocks. Existing portfolio_release_v1
exports are accepted for both explicitly selected legacy NAV sizing and fixed-k.
Old journal readers retain their documented semantic version dispatch.

## Candidate acceptance and adversarial evidence

tests/test_pydantic_crossrepo_contracts.py runs the actual exporter and current
SQLite release producer against the separately supplied consumer source, using
temporary synthetic identities and keys. Fifteen cases passed:

- Original signed source-book hash and first-known clock survive; source journal
  bytes do not change during consumer verification.
- Missing or positive diagnostic NAV leaves fixed-k requested notionals identical.
  It does not establish source performance, cash, equity or order authority.
- Unknown source/release schema versions, unknown financial fields, changed
  identity/account scope/DEX, boolean/future/backdated clocks, nonnumeric quantity,
  invented order identity and signature tampering reject consumer admission.
- Both existing release policies verify and retain trading_authorized=false.
- Existing research_bridge.verify_checkout rejects the unpinned candidate.

The existing V4 consumer suite executed against the actual candidate producer:
47 passed. This includes real producer subprocesses, exact signed-byte handoff,
private packet scanning, durable consumer restart/duplicate handling, scoped
markets, original T+300, independent follower quote signer, source gaps and
Guardian SHADOW denial. No broker intents, reservations or FakeBroker dispatches
are produced by those denial paths. Real broker credentials are absent.

Known optional diagnostics remain outside the financial command schema or in
already defined inert fields. A diagnostic label cannot add a protected command
field; the signed source-book/leg/target schema rejects unknown financial content.
The producer does not claim its Pydantic model is Guardian's authority.

## Commands and results

All companion worktrees were reused and left source-clean. No checkout, branch,
service or protected financial state was modified.

- In each reviewed Guardian baseline, with PROP_RESEARCH_ROOT and
  PROP_CONNECTOR_ROOT set to the existing exact manifest-pinned checkouts:
  bash scripts/verify-local.sh all.
- b60aef9 gate: Python 3.13 and 3.14 each 142 passed / 1 skipped; Ruff and mypy
  (30 source files), synthetic status/smoke and build passed.
- 0007349 gate: Python 3.13 and 3.14 each 148 passed / 1 skipped; Ruff and mypy
  (31 source files), synthetic status/smoke and build passed.
- Both gates: pinned connector 303 passed / 1 skipped; native Propr gateway
  2 passed; Bybit read-only adapters 15 passed; pinned research 1378 passed,
  329 files formatted; capabilities 110 with errors=[].
- Connector skip: the pinned research revision lacks the historical optional
  pm_combo2_rest_capture module. A websockets.legacy deprecation warning is
  retained; neither is silently counted as executed coverage.
- Candidate contract: PYTHONPATH=<reviewed Guardian src>
  uv run --frozen --group dev pytest -q tests/test_pydantic_crossrepo_contracts.py
  -> 15 passed.
- V4 consumer with PROP_RESEARCH_ROOT=<candidate checkout>, pinned connector on
  PYTHONPATH, uv run --frozen --extra connector --group dev pytest -q on its
  V4 producer/spool/timing/Guardian/receiver/handoff/shared-source/market suites
  and native/Bybit adapter suites -> 47 passed.

The candidate production regression immediately before this test-only change was
1746 passed / 1 skipped (#226). Final program-wide coverage is recorded under #228.

## Rollback and authorization

Keep the existing manifest pins and original journal bytes. New source/paper and
Combo2 events require readers that understand their explicit semantic version.
Reject unknown versions; do not rewrite signatures, truncate history or backdate
receipts to run an older reader. No protected trust floor or release was activated.
A future SHADOW installation and any Guardian repin need the separate #229
authorization and their own concrete offline release checks. Scientific
qualification and trading authorization remain false/unestablished.
