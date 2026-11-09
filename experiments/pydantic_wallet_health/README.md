# Offline wallet diagnostic evaluation — #230

## Decision and scope

**EXPERIMENT** with the isolated Pydantic Evals harness. **DEFER** the research-agent comparison. No model-provider endpoint or independently trusted wallet-diagnostic capture was available in this DevSpace session. No independently labeled real-wallet corpus was supplied.

The engineering harness and deterministic comparison run are implemented. **Issue #230 remains open** because the observed agent comparison and independently sourced wallet labels are incomplete. The experiment does not block completed core tickets #214–#228 or authorize #229.

This directory has its own environment and lockfile. It imports the existing read-only capture verification utilities from `copytrade_pm.pm_agent_trace_eval`; it introduces no source owner, paper/financial journal, portfolio state, selection authority, service configuration or Guardian policy. The core `pyproject.toml` and `uv.lock` are unchanged.

## Reproduce

Run from the repository root with Python 3.14:

```bash
uv sync --frozen --project experiments/pydantic_wallet_health --group dev
uv run --frozen --project experiments/pydantic_wallet_health --group dev pytest -q -c experiments/pydantic_wallet_health/pyproject.toml experiments/pydantic_wallet_health/tests
uv run --frozen --project experiments/pydantic_wallet_health --group dev ruff check experiments/pydantic_wallet_health
uv run --frozen --project experiments/pydantic_wallet_health --group dev ruff format --check experiments/pydantic_wallet_health
uv run --frozen --project experiments/pydantic_wallet_health --group dev python experiments/pydantic_wallet_health/evaluate.py
```

The CLI writes JSON to stdout. It has no provider client or executable tool dispatcher. Before importing Pydantic Evals, it disables OpenTelemetry and installs a Python audit guard rejecting socket connections, name resolution and child-process execution. This guard is a defense for the fixed offline runner, not a sandbox for arbitrary Python code. The test suite deliberately probes the guard in a child process and confirms rejection before connection.

Pinned direct dependencies: Pydantic Evals **2.66.0**, Pydantic **2.14.3**, cryptography **50.0.2**, pytest **9.2.0**, Ruff **0.17.3**. The installed Pydantic Evals distribution requires **pydantic-ai-slim 2.66.0** transitively; the lockfile includes it. No provider SDK extra or Logfire exporter is configured. The recorded environment is Python **3.14.6**, uv **0.12.15**; other interpreters are not qualified by these results.

Official references: [Pydantic Evals documentation](https://pydantic.dev/docs/ai/evals/evals/) and [2.66.0 distribution](https://pypi.org/project/pydantic-evals/2.66.0/). Installed metadata and the frozen lockfile determine the actual dependencies.

## Corpus and point-in-time protocol

`cases.py` declares 16 accounting scenarios, repeated over two disjoint wallet/date partitions:

| Partition | Wallet aliases | As-of date | Amount scale | Cases |
|---|---|---|---:|---:|
| Development | FAKE001–FAKE016 | 2026-10-01 | 1 | 16 |
| Holdout | FAKE101–FAKE116 | 2026-11-01 | 7 | 16 |

The cases cover withdrawal versus realized loss, top-up versus profit, explicit liquidation, unexplained zero equity, inactive but solvent, stale equity, ambiguous decline, deposit plus loss, later-known withdrawal, later mark correction, fees/funding, unrealized loss, offsetting transfers, missing activity coverage and realized gain.

Labels are **predeclared synthetic accounting oracles**, authored from the scenario facts before candidate responses. They are not model judgments, independent human annotations or independently observed provider truth. Both partitions share scenario templates. Perfect holdout performance therefore does not establish generalization, field accuracy or scientific qualification.

Each receipt retains its original synthetic JSON bytes, SHA-256, observed clock and known clock. The task receives only receipts whose observed and known clocks are at or before its as-of time. Late withdrawal evidence and later corrections are excluded. Aggregate cash/activity/coverage receipts must span the exact before/after interval. A late receipt never becomes a historical zero.

Expected labels, scenario names, split metadata and future receipts are not passed in the task input. The corpus hash binds the original corpus, expected answers and partitions; each task input has a separate hash over its PIT projection. The latter does not replace the raw receipt hash.

Amounts are exact decimal strings. Booleans, floats, nonfinite values, duplicate JSON keys, malformed chronology and conflicting receipt IDs are rejected. Attribution sums use a bounded 128-digit local decimal context, including cancellation of large offsetting amounts. No mutable process-wide precision is assumed.

All cases require `edge_decay=INSUFFICIENT_EVIDENCE`. This tests resistance to unsupported edge claims; sensitivity to genuine edge decay is **UNKNOWN**.

## Comparators and scoring

**Equity/activity** is an intentionally simple, predeclared comparator: equity declines are labeled realized losses, increases top-ups, and zero-change/zero-activity intervals inactive. It ignores attribution and freshness. Concrete answers receive confidence 0.9 by protocol; this is not calibrated model confidence.

**Transaction attribution** requires fresh equity, complete coverage, exactly one explicit value for every cash-flow category, matching windows, and exact reconciliation. Missing decomposition yields `INSUFFICIENT_EVIDENCE`. Liquidation requires an explicit, complete receipt inside the evaluation interval. An old liquidation or zero equity alone is insufficient. Complete zero activity with positive equity can support inactive-but-solvent status. Multiple cash causes are reported as mixed flows.

Both comparators run through the real `pydantic_evals.Dataset.evaluate_sync` API with one concurrent task and a two-second task timeout. Failures in tasks or evaluators fail the run.

| Metric | Definition and limitation |
|---|---|
| Diagnosis accuracy | Exact match with the predeclared diagnosis label. |
| Supported claim | Correct label, every cited ID available at the as-of time, every oracle-required receipt cited, and no unsupported edge-decay claim. |
| False confident claim | Confidence at least 0.8 while the supported-claim condition fails. A correct label with insufficient evidence still fails. |
| Citation precision | Fraction of cited IDs present in the PIT input. This measures availability, not semantic entailment. Empty citations score one only for abstention labels. |
| Appropriate abstention | Whether predicted and expected labels both belong, or both do not belong, to the stale/insufficient-evidence abstention set. Exact abstention type is assessed separately by accuracy. |
| PIT leakage | Number of distinct future receipt IDs cited or referenced in recorded tool calls. Input filtering is also checked independently. Hidden model reasoning cannot be audited here. |
| Tool misuse | Recorded calls outside read_case/read_receipt, non-read-only calls, wrong-case calls or unavailable receipt IDs. Calls are scored as data and never executed. |
| Resource cost | Actual evaluation wall/CPU time, process peak RSS, per-task median and nearest-rank p95, guard attempts and provider-call count. Captured tokens/API cost remain unknown when absent. |

The 16-sample nearest-rank p95 is the maximum sample. Task timings include evaluation framework scheduling overhead and are not production latency measurements. Wall/CPU fields cover dataset evaluation after setup; peak RSS covers the whole CLI process.

## Observed synthetic findings

Both partitions have the same categorical results:

| Metric, per 16-case split | Equity/activity | Transaction attribution |
|---|---:|---:|
| Correct diagnoses | 5/16 (31.25%) | 16/16 (100%) |
| Supported claims | 1/16 (6.25%) | 16/16 (100%) |
| False confident claims | 15/16 (93.75%) | 0/16 |
| Appropriate abstention | 12/16 (75%) | 16/16 (100%) |
| Abstained | 1/16 | 5/16 |
| Citation availability precision | 100% | 100% |
| Future receipt leakage | 0 | 0 |
| Tool misuse / unsupported edge claims | 0 / 0 | 0 / 0 |

The baseline discrepancy follows directly from the controlled cases: the sign of equity change does not identify transfers, trading losses, liquidation or causal edge decay. Citation availability alone also fails to prove a diagnosis. The stronger baseline uses the necessary accounting evidence. This is an engineering sanity check, not evidence that these percentages hold for real wallets.

The default run records **zero provider calls, zero model tokens and zero API cost for the baselines**, with actual network attempts zero. Candidate diagnosis accuracy, candidate tokens and candidate cost remain **UNKNOWN**. No synthetic candidate responses are substituted for a real agent run.

The committed result receipt records the exact executable revision, command output and machine-readable run. It also records the initial review failures: unsupported confident answers were undercounted and decimal cancellation depended on ambient precision. Both were reproduced by failing behavioral tests before repair. Two further review regressions prevent fully offsetting fees/funding from becoming profit and prevent an empty inactive wallet from being called active. The final experiment has **26 passing tests**.

## Supplying genuine captured model evidence later

Export only PIT inputs:

```bash
uv run --frozen --project experiments/pydantic_wallet_health --group dev python experiments/pydantic_wallet_health/evaluate.py --export-inputs
```

A capture must conform to `Capture` in `contracts.py`: schema `wallet_diagnostic_capture_v1`, exact corpus hash, explicit `SYNTHETIC` or `HOST_EXPORT` kind, privacy-safe model ID, and one answer for every case. Each answer binds the case ID, PIT input hash and strict diagnosis; token counts and exact-string API cost are optional reported fields.

Use existing private-file and Ed25519 verification with an independently pinned public key:

```bash
uv run --frozen --project experiments/pydantic_wallet_health --group dev python experiments/pydantic_wallet_health/evaluate.py --capture /private/capture.json --signature /private/capture.sig --trusted-public-key /private/host.pub --trusted-key-sha256 EXPECTED_PUBLIC_KEY_SHA256
```

Unsigned host exports, mismatched input/corpus hashes, missing or duplicate cases and tampered signatures are rejected. A signed synthetic fixture remains synthetic. A signature proves bytes and key binding; **organizational control of the host key and the authenticity of a model run must be established independently outside this CLI**. Locally generated test keys do not establish that trust. Recorded model tokens/cost are capture-reported, not independently metered by the evaluator.

The remaining executable frontier is to obtain a privacy-safe independently labeled wallet corpus and a genuine model run bound to its PIT inputs, using authorized model access and independently trusted capture provenance. Then run the same metrics against both baselines and evaluate uncertainty, failure modes and measured resource cost. A useful agent must demonstrate evidence beyond these shared synthetic templates.

No result can enable trading, source selection, financial-policy changes, Guardian access or agent-generated scientific qualification. Strict response fields require both `trading_authorized=false` and `scientifically_qualified=false`.

## Related evidence

- [#230 contract](https://github.com/hzminhzz/copytrade-pm/issues/230)
- [Core #228 acceptance receipt](../../docs/PYDANTIC-NATIVE-ACCEPTANCE-RESULTS-20261109.md)
- [Existing trace evaluation and attestation owner](../../src/copytrade_pm/pm_agent_trace_eval.py)
