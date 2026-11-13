# P2 agent tool-choice benchmark — capture, evaluation, and evidence boundaries

**Status (2026-11-05):** The trace evaluator is implemented and its
synthetic/negative tests run locally. **Independent live LLM tool-choice
qualification is NOT established.** No independent host-exported signed MCP
tool-event trace was available in the current ChatGPT/DevSpace session.
Neither an assistant-written transcript, the test suite nor shell smoke calls
are substitutes for host capture.

## Purpose and scope

This is a strict **read-only analysis** of an agent's actual selection of
native `copytrade-pm` capabilities. It does not open external coding agents,
place orders, start a worker, replay historical data or create a new registry.
The benchmark does not measure alpha, account economics, broker state, or
scientific qualification.

The native command is:

```bash
copytrade-pm-agent-eval --list-tasks
copytrade-pm-agent-eval --trace /private/trace.json
copytrade-pm-agent-eval --trace /private/host-trace.json \
  --signature /private/host-trace.sig \
  --trusted-public-key /private/host-pubkey.bin \
  --trusted-key-sha256 <externally-reviewed-key-sha256>
```

The first command prints **13 fixed tasks**: current research selection,
W083, research-108, exclusions, E6, q3/B, paper-running, canonical research
cache, installed release, protected paper OS units, market evidence, protected
source collector ownership and PM-03 accounting ownership.

It returns a JSON-only report with `copytrade_agent_trace_evaluation_v1`,
task coverage, correct route count, duplicate calls, off-target lookups,
invented operations, unsafe operations and total calls. No raw wallet
addresses, tool output or secret arguments appear in the report.

For ANOS-02 reproducible pre-change inputs, fixed 13-task and eight-scenario
workloads, resource metrics and preregistered comparison gates, see
[the pinned agent evaluation baseline](ANOS-02-AGENT-EVAL-BASELINE-20261113.md).
Engineering fixture scores are never independent agent observations.

## Trusted evidence collection — what is required

The *independent ChatGPT/MCP host collector* must be the source of truth.
Do not let the model author, omit or edit its own call events.

1. Before running an agent task, an independent operator provisions an
   Ed25519 capture signer **outside the agent runtime** and stores its public
   key SHA-256 in a separate reviewed operator policy. Do not generate a
   signing key inside the agent or commit private keys.
2. Run each of the 13 prompts as a genuine model-led task using the real
   installed read-only CLI. Make all tools and responses observable to the
   collector. Record **every attempted and executed tool operation** in
   sequence, including failures and unknown commands. The collector must
   include retries, repeated lookups and unsafe attempted mutations rather
   than silently filtering them out. Never execute protected operations just
   to benchmark them.
3. The host exporter, not the model, translates each actual tool-call
   argument to a canonical argv vector, after unwrapping `uv run` wrappers
   where necessary. Any compound shell string that cannot be normalized
   unambiguously is an invented/unsafe operation, not a read-only command.
4. The host exporter records exit code and coarse result status from the
   actual tool response. For a successful capability lookup this is
   `FOUND`; for a native query it is the native evidence envelope status
   (`VERIFIED`, `DEGRADED`, `UNKNOWN`, etc.). The final answer's structured
   evidence status and no-trading/no-science claims must be checked against
   the **actual** model final answer, not invented by the exporter.
5. The host exports one complete JSON bundle with
   `capture_kind="HOST_EXPORT"` and
   `tool_events_source="HOST_EVENT_STREAM"`. The trusted exporter signs
   the unmodified UTF-8 file bytes with the separately controlled capture
   private key, writing a 128-character lowercase hex detached signature.
6. Copy the bundle, signature, and public key to owner-private scratch files,
   then run the evaluator with the independently pinned key fingerprint.
   Never commit raw traces containing addresses, credentials, messages,
   account identifiers or subscriber records.

Example *shape* (not a captured run; intentionally incomplete and
unqualified):

```json
{
  "schema": "copytrade_agent_trace_bundle_v1",
  "run_id": "example-not-real",
  "observed_at": "2026-11-05T00:00:00+00:00",
  "capture_kind": "SYNTHETIC",
  "tool_events_source": "TEST_FIXTURE",
  "runs": [
    {
      "task_id": "wallet-w083",
      "calls": [
        {"sequence": 1, "argv": ["copytrade-pm", "capabilities", "show", "wallet.lookup"], "exit_code": 0, "result_status": "FOUND"},
        {"sequence": 2, "argv": ["copytrade-pm", "wallets", "show", "W083"], "exit_code": 0, "result_status": "VERIFIED"}
      ],
      "final": {"answered": true, "status": "VERIFIED", "scientifically_qualified": false, "trading_authorized": false}
    }
  ]
}
```

The file must be 0600, regular, not a symlink, <=512 KiB. Host public key
must be a 32-byte raw Ed25519 key and the pinned fingerprint must match.
The detached signature is not optional for genuine host-evidence acceptance.

## Acceptance gates

A true `INDEPENDENT_TRACE_PASS` requires **all**: 13 distinct scenarios;
a valid, externally pinned signature on the host event export; current known
capability IDs; correct native owner discovery *before* the corresponding
query; no invented commands, no off-target queries, no redundant exact calls,
no unsafe attempted operations and no more than six calls per task;
matching structured final evidence status;
no false scientific or trading claims. Pure discovery-only prompts may
inspect `source.collection` and `account.pm03`, but never invoke their
mutating paths.

Unsigned, manually transcribed and synthetic traces always return
`UNVERIFIED_TOOL_TRACE` and exit 2, even when every scripted case passes.
Malformed payloads, untrusted keys or signatures are
`BLOCKED_INVALID_EVIDENCE` and exit 2. Host-signed but incomplete/failed
runs yield `INDEPENDENT_TRACE_FAILED` and exit 2. Only a full trusted run
passes with exit 0.

**Trust boundary:** Cryptographic verification attests possession of the
supplied capture key; the evaluator cannot itself establish that the key was
actually held by an independent ChatGPT/MCP host. That operational fact must
be reviewed externally. Unit tests can simulate signed exports but are not
real LLM performance evidence. A valid tool trace measures structured
routing/evidence status; human evaluation of prose correctness and domain
facts is separate.

## Existing evidence and status

- The previous 12 scripted discovery cases were deterministic routing tests,
  **not** model-selected tool use.
- P0 release `8bdaf1e` and P1 release `00a6b1e` were independently
  verified installed read-only releases. Their successful operational smoke
  calls show that the tools function; they do not prove an LLM will choose
  the right tools without prompts.
- Forward-Paper execution and scientific qualification remain outside this
  program. A `PAPER_RUNNING` or trading authorization result may not be
  inferred from discovery, Git, an active tracker or a model trace score.
- If an independent host event export cannot be obtained, leave the empirical
  gate **`BLOCKED_NO_INDEPENDENT_HOST_TRACE`**. Do not manufacture evidence
  by running scripted bash commands and labeling them real agent choices.

## Recovery

Keep the benchmark tool read-only and fixture-based. If host export is
unavailable, deliver the evaluated, tested CLI and documentation without
making a positive agent-effectiveness claim. The next accepted evidence must
come from the independent platform capture mechanism; do not add a
competing private collector service or traffic interceptor on the production
VPS to bypass that trust boundary.
