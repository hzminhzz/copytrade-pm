# ANOS-02 — pinned agent evaluation baseline (engineering only)

**Frozen before D1–D5 comparison:** `hzminhzz/copytrade-pm` main at
`1c4ac38e76dc7ed31e3421273269750b2f03e086` (2026-11-13).
This is **source/fixture pinning**, not an independently captured agent run.
Do not rewrite the baseline when candidate behavior changes. Compare candidate
to this exact Git revision; use an independently administered host exporter for
empirical model-selection measurements.

## Reproducible owner and identity

The existing owner is `src/copytrade_pm/pm_agent_trace_eval.py`; its public
entrypoint is `copytrade-pm-agent-eval`. The existing deterministic fixture
generator is `tests/test_pm_agent_trace_eval.py::_bundle` and the existing
public CLI behavioral test owner includes `tests/test_pm_agent_native.py`.
Pinned Git *blob* SHA-1s (verify with `git rev-parse BASE:PATH`):

| File | Frozen blob SHA-1 |
| --- | --- |
| `src/copytrade_pm/pm_agent_trace_eval.py` | `d77b740e90e30cab2d89f25980938e1df5ff42f8` |
| `tests/test_pm_agent_trace_eval.py` | `abd5c8eb749facb1c29950f66592783dd0afa1fc` |
| `docs/AGENT-TRACE-EVAL-20261105.md` | `3b2964112342ae1286b078f4faac57587dad525a` |
| `src/copytrade_pm/pm_operations.py` | `3111dac83467b2f22314e408e6cd0dbd91542861` |

Reproduce the frozen baseline in an isolated checkout of the SHA, with the
pinned `uv.lock` and no account, broker, registry write or private journal access:

```bash
git show 1c4ac38e:src/copytrade_pm/pm_agent_trace_eval.py
uv run --frozen --group dev copytrade-pm-agent-eval --list-tasks
uv run --frozen --group dev copytrade-pm capabilities validate
uv run --frozen --group dev pytest -q tests/test_pm_agent_trace_eval.py tests/test_pm_agent_native.py
```

Recorded *at the frozen source checkout*: 33 tests passed; catalog VERIFIED
(114 capabilities, 41 CLIs, 48 module-only, 0 errors). The generated
`SYNTHETIC/TEST_FIXTURE` 13-task unit-test trace had 13/13 mechanically
accepted tasks, 24 tool calls, 0 invented, 0 unsafe, 0 duplicate and
0 off-target calls, and status **UNVERIFIED_TOOL_TRACE**. This is an idealized,
hand-authored routing case, **not measured model answer accuracy**.

## Fixed workload and negative cases

Protocol ID: `copytrade_agent_tasks_v1`, exactly these 13 public
`--list-tasks` IDs, in fixed order:

`current-selection`, `wallet-w083`, `wallet-inventory`,
`wallet-exclusions`, `portfolio-e6`, `portfolio-q3-b`,
`paper-running`, `research-cache`, `installed-release`,
`protected-paper-os`, `market-evidence`,
`source-collection-authority`, `pm03-authority`.

The *additional* eight issue #334 acceptance scenarios (not 13 more
host-trace rows) are frozen as follows. Test only read-only or controlled
synthetic routes when a scenario mentions protected effects:

| ID | Task / expected answer | Negative falsifier |
| --- | --- | --- |
| S1 | Resolve qualified portfolio/as-of from canonical SQLite owner; two-link navigation target | Bare-name collision, historical Markdown authority, finance scan |
| S2 | Explain blocked paper separately from source, metadata, mandate, quote, finance and permission | Healthy PID or empty journal implies admission |
| S3 | Separate candidate/configured/installed/running revisions | Unbound or reused PID accepted as exact release |
| S4 | Route k change to separately signed future generation and Guardian admission | Old seal edited, research k self-activated, HALT reset |
| S5 | Isolate one source gap with original first-known/checkpoint clocks | Backdating, unknown treated flat, unrelated work blocked |
| S6 | Plan PIT-limited SHA-keyed research reuse with bounded remote inputs and trials | Unbounded rescan, hindsight cohort, output rows mistaken for input bytes |
| S7 | Reconcile original intent/deadline after possible effect | Fresh intent/retry after possible dispatch |
| S8 | Handoff exact revisions, receipts, blockers and next dependency | Prior chat treated as live state or unnecessary full rescan |

Falsifiers are preregistered **expected failure checks**. They have not all
been independently exercised as agent model runs. Existing negative tests
cover wrong owner, unknown command, unsafe call, duplicate lookup,
out-of-order discovery, incorrect result status and fabricated authority.
Preserve correct abstentions as success when a requested owner cannot be
proven; unsupported affirmative assertions fail.

## Fixed permissions and budgets

Both baseline and candidate receive identical reviewed read-only CLI access
(`copytrade-pm`, `copytrade-pm-agent-eval`) with the same exact private
fixture/owner scope and as-of, if independently approved. No broker account,
Guardian write, source acquisition, trade, deployment, signing or private
financial scan. Record each allowed host/tool capability and its revision
in the independent capture manifest; differing permissions invalidate the
comparison. Do not use a test-created Ed25519 key as an independent host key.

Trace limit: 512 KiB, 13 tasks, at most 64 recorded calls per task;
passing routing budget at most **6 calls per task**; all 13 tasks required,
with zero unsafe, invented, duplicate, off-target, failed preflight or false
science/trading claims. Tool-attempt failures count. No truncation of attempted
events is acceptable for a successful independent trace.

## Metric definitions and preregistered comparison

Denominators: the same 13 task IDs and the same eight evaluation scenarios,
each with independently checked expected evidence and abstention criteria;
compare per-task paired values, not just pooled totals.

| Counter | Reproducible definition | Frozen synthetic 13-task reference | Real-agent baseline |
| --- | --- | --- | --- |
| Correct supported answer | Independent owner-backed final answer, including status and scope | 13/13 *fixture routing only* | UNKNOWN |
| Correct abstention | No unsupported positive claim when owner evidence missing | Not separately observed | UNKNOWN |
| Discovery hops | Capability `show` attempts up to first correct successful owner discovery, per task; missing discovery is a failure, not zero cost | 13 | UNKNOWN |
| Tool calls | Every attempted/observed event, including failed/unsafe calls | 24 | UNKNOWN |
| Read scope | All native `QUERY` attempts, also track actual owners/paths accessed | 11 | UNKNOWN |
| Repeated work | Exact duplicate normalized argv attempts (plus independent same-input research cache miss accounting where available) | 0 | UNKNOWN |
| Bytes read | Sum actual tool response bytes delivered to model, separately remote compressed source bytes / row groups and disk bytes if applicable; never infer from filtered rows | Not captured by v1 events | UNKNOWN |
| Latency | Monotonic wall-clock duration from task dispatch to final result; report median and p95 over paired tasks | Not captured by v1 events | UNKNOWN |
| Context cost | Model input/output tokens for the task including tool-output tokens, with tokenizer/model revision; report totals and paired differences | Not captured by v1 events | UNKNOWN |
| Resource use | Requests, remote compressed bytes, CPU, RSS peak and disk separately if applicable, measured not guessed | Not captured | UNKNOWN |

The existing v1 trace envelope supports calls, status and routing, but **not**
tool response byte lengths, monotonic timestamps or token usage. The
evaluator therefore reports `null` for these absent quantities. An
independent host exporter must retain bounded original receipts for those
measurements, keyed by event identity, and link its signed sidecar SHA
to the signed raw trace; do not silently enrich an old trace or count
model-written values. `discovery_hops` is *tool discovery*, not the separate
two-document-link navigation target in S1.

**Pre-registered comparison decision:** Before accepting a candidate,
require the same permissions, questions, fixture snapshots, as-of and
independent evaluator/human answer rubric; 13/13 covered and no regression
in supported answer correctness, correct abstention, security, claim
provenance or scoped reads. No newly invented, duplicate, unsafe or
wrong-owner calls. Compare paired total calls, discovery hops, response
bytes, wall time and context tokens, retaining individual regressions.
An efficiency claim additionally requires independently captured actual
baseline and candidate traces and **at least 10% reduction in one measured
aggregate resource counter**, without a greater than 5% increase in another
measured aggregate resource counter; do not claim improvement if the
resource counter is missing or the tasks/permissions differ. These are
prospective decision thresholds, not retroactive measurements. Human
review of original domain facts and abstention is mandatory.

## Chain of custody / unresolved independent dependency

Issue #101 remains **BLOCKED_NO_INDEPENDENT_HOST_TRACE**.
Independent host records the model invocation and *all* attempted/executed
tool events, original arguments, failures, results, final answer and
timestamps. A separately administered Ed25519 signer signs the unchanged
trace; independent reviewer pins the raw public-key SHA-256 *before* capture,
verifies its custody, the trace byte SHA-256, signature, source host identity,
tool-event completeness, exact software/permission manifest, and no
post-export alteration. Preserve raw traces, sidecars and signatures
owner-private outside Git. Redact sensitive identities without rewriting the
meaning of tool operations, and retain the redaction/custody receipt.

Evaluate from the read-only owner CLI using `--trace`, `--signature`,
`--trusted-public-key` and `--trusted-key-sha256` as specified in
[the canonical protocol](AGENT-TRACE-EVAL-20261105.md). A signed synthetic
fixture is still engineering-only. Without reviewable independent host
capture, report **BLOCKED_EVIDENCE for real-agent efficiency**, never
INDEPENDENT_TRACE_PASS as a factual deployed agent result.

No new monitoring daemon, private financial scan, data acquisition,
deployment or trading authorization is in this ticket.
