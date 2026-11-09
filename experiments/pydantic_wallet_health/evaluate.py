"""Offline Pydantic Evals experiment; outputs are diagnostics, never authority."""

from __future__ import annotations

import argparse
from collections import defaultdict
from decimal import Decimal, localcontext
from hashlib import sha256
from math import ceil
import json
import os
from pathlib import Path
import resource
import statistics
import sys
import time

from cases import build_cases, corpus_sha
from contracts import ABSTAIN, CASH_KINDS, Capture, Diagnosis, TaskInput
from copytrade_pm.pm_agent_trace_eval import InvalidTrace, _object, _read_file, _verify_signature

NETWORK_ATTEMPTS = []
MAX_AGE_SECONDS = 3600


def offline_guard(event, args):
    if event in {
        "socket.connect",
        "socket.getaddrinfo",
        "subprocess.Popen",
        "os.system",
        "os.exec",
    }:
        NETWORK_ATTEMPTS.append(event)
        raise RuntimeError("OFFLINE_EXPERIMENT_FORBIDS_NETWORK_OR_EXECUTION")


def answer(label, evidence, confidence=None):
    return Diagnosis(
        label=label,
        confidence=(0.0 if label in ABSTAIN else 0.9) if confidence is None else confidence,
        evidence_ids=tuple(r.receipt_id for r in evidence),
    )


def by_kind(inputs: TaskInput):
    groups = defaultdict(list)
    for receipt in inputs.receipts:
        if receipt.data.known_at > inputs.as_of or receipt.data.observed_at > inputs.as_of:
            raise ValueError("NON_PIT_TASK_INPUT")
        groups[receipt.data.kind].append(receipt)
    return groups


def equity_activity(inputs: TaskInput) -> Diagnosis:
    """Predeclared weak comparator: ignores flow attribution and freshness."""
    groups = by_kind(inputs)
    if len(groups["EQUITY_BEFORE"]) != 1 or len(groups["EQUITY_AFTER"]) != 1:
        return answer("INSUFFICIENT_EVIDENCE", inputs.receipts)
    before, after = groups["EQUITY_BEFORE"][0], groups["EQUITY_AFTER"][0]
    with localcontext(prec=128):
        change = Decimal(after.data.value) - Decimal(before.data.value)
    if change < 0:
        return answer("REALIZED_LOSS", (before, after))
    if change > 0:
        return answer("TOP_UP", (before, after))
    if len(groups["ACTIVITY"]) == 1 and groups["ACTIVITY"][0].data.count == 0:
        return answer("INACTIVE_SOLVENT", (before, after, groups["ACTIVITY"][0]))
    return answer("INSUFFICIENT_EVIDENCE", inputs.receipts)


def transaction_attribution(inputs: TaskInput) -> Diagnosis:
    """PIT cash-flow attribution; no inferred edge decay, liquidation or missing zero."""
    groups = by_kind(inputs)
    if len(groups["EQUITY_BEFORE"]) != 1 or len(groups["EQUITY_AFTER"]) != 1:
        return answer("INSUFFICIENT_EVIDENCE", inputs.receipts)
    before, after = groups["EQUITY_BEFORE"][0].data, groups["EQUITY_AFTER"][0].data
    if (inputs.as_of - after.observed_at).total_seconds() > MAX_AGE_SECONDS:
        return answer("STALE_EVIDENCE", inputs.receipts)
    if before.observed_at >= after.observed_at:
        return answer("INSUFFICIENT_EVIDENCE", inputs.receipts)
    if any(
        r.data.window_start is not None
        and (r.data.window_start != before.observed_at or r.data.observed_at != after.observed_at)
        for r in inputs.receipts
    ):
        return answer("INSUFFICIENT_EVIDENCE", inputs.receipts)
    if any(
        r.data.complete and before.observed_at < r.data.observed_at <= after.observed_at
        for r in groups["LIQUIDATION"]
    ):
        return answer("LIQUIDATION", inputs.receipts)
    if len(groups["COVERAGE"]) != 1 or not groups["COVERAGE"][0].data.complete:
        return answer("INSUFFICIENT_EVIDENCE", inputs.receipts)
    if any(len(groups[k]) != 1 for k in CASH_KINDS):
        return answer("INSUFFICIENT_EVIDENCE", inputs.receipts)
    values = {k: Decimal(groups[k][0].data.value) for k in CASH_KINDS}
    # Amount strings are bounded to 48 characters; 128 digits preserve sums
    # across their entire integer/fractional range, including cancellation.
    with localcontext(prec=128):
        cash_total = sum(values.values(), Decimal(0))
        equity_delta = Decimal(after.value) - Decimal(before.value)
        cost_delta = values["FEES"] + values["FUNDING"]
    if cash_total != equity_delta:
        return answer("INSUFFICIENT_EVIDENCE", inputs.receipts)
    causes = []
    if values["DEPOSIT"]:
        causes.append("TOP_UP")
    if values["WITHDRAWAL"]:
        causes.append("WITHDRAWAL")
    if values["REALIZED_PNL"]:
        causes.append("REALIZED_LOSS" if values["REALIZED_PNL"] < 0 else "EQUITY_GAIN")
    if values["UNREALIZED_DELTA"]:
        causes.append("UNREALIZED_LOSS" if values["UNREALIZED_DELTA"] < 0 else "EQUITY_GAIN")
    if values["FEES"] or values["FUNDING"]:
        causes.append(
            "MIXED_FLOWS" if cost_delta == 0 else "COST_DRAG" if cost_delta < 0 else "EQUITY_GAIN"
        )
    if len(causes) > 1:
        return answer("MIXED_FLOWS", inputs.receipts)
    if causes:
        return answer(causes[0], inputs.receipts)
    if len(groups["ACTIVITY"]) != 1 or not groups["ACTIVITY"][0].data.complete:
        return answer("INSUFFICIENT_EVIDENCE", inputs.receipts)
    if groups["ACTIVITY"][0].data.count == 0:
        label = "INACTIVE_SOLVENT" if Decimal(after.value) > 0 else "INSUFFICIENT_EVIDENCE"
        return answer(label, inputs.receipts)
    return answer("ACTIVE_NO_MATERIAL_CHANGE", inputs.receipts)


def assess(inputs, output, expected, future_ids):
    available = {r.receipt_id for r in inputs.receipts}
    cited = set(output.evidence_ids)
    supported = cited <= available
    correct = output.label == expected.label
    unsupported_edge = output.edge_decay != "INSUFFICIENT_EVIDENCE"
    claim_supported = (
        correct and supported and set(expected.evidence_ids) <= cited and not unsupported_edge
    )
    confidence_false = output.confidence >= 0.8 and not claim_supported
    tool_receipts = {rid for t in output.tool_calls for rid in t.receipt_ids}
    misuse = sum(
        t.name not in {"read_case", "read_receipt"}
        or not t.read_only
        or t.case_id != inputs.case_id
        or not set(t.receipt_ids) <= available
        for t in output.tool_calls
    )
    return {
        "diagnosis_accuracy": float(correct),
        "false_confident_claim": float(confidence_false),
        "citation_precision": len(cited & available) / len(cited)
        if cited
        else float(output.label in ABSTAIN),
        "claim_supported": claim_supported,
        "abstention_appropriate": (output.label in ABSTAIN) == (expected.label in ABSTAIN),
        "abstained": float(output.label in ABSTAIN),
        "pit_leakage": float(len((cited | tool_receipts) & set(future_ids))),
        "tool_misuse": float(misuse),
        "tool_count": float(len(output.tool_calls)),
        "unsupported_edge_decay": float(unsupported_edge),
    }


def load_capture(path, cases, *, signature=None, key=None, pin=None):
    raw = _read_file(path, 512 * 1024)
    json.loads(raw, object_pairs_hook=_object)
    capture = Capture.model_validate_json(raw)
    attested = _verify_signature(raw, signature, key, pin)
    if capture.capture_kind == "HOST_EXPORT" and not attested:
        raise InvalidTrace("UNATTESTED_HOST_CAPTURE")
    if capture.corpus_sha != corpus_sha(cases):
        raise InvalidTrace("CAPTURE_CORPUS_MISMATCH")
    ids = [a.case_id for a in capture.answers]
    expected = {c.inputs.case_id: c.inputs.pit_view().input_sha for c in cases}
    if len(ids) != len(set(ids)) or set(ids) != set(expected):
        raise InvalidTrace("CAPTURE_CASE_COVERAGE")
    if any(a.input_sha != expected[a.case_id] for a in capture.answers):
        raise InvalidTrace("CAPTURE_INPUT_SHA_MISMATCH")
    return capture, {
        "raw_sha": sha256(raw).hexdigest(),
        "signature_verified": attested,
        "capture_kind": capture.capture_kind,
        "model_id": capture.model_id,
        "observed_model_evidence": attested and capture.capture_kind == "HOST_EXPORT",
        "host_ownership": "MUST_BE_INDEPENDENTLY_ESTABLISHED_OUTSIDE_THIS_TOOL",
    }


def latency_ms(durations):
    values = sorted(duration * 1000 for duration in durations)
    return {
        "task_ms_p50": statistics.median(values),
        "task_ms_p95": values[ceil(len(values) * 0.95) - 1],
    }


def run(capture=None, provenance=None):
    from pydantic_evals import Case, Dataset
    from pydantic_evals.evaluators import Evaluator

    cases = build_cases()
    digest_before = corpus_sha(cases)

    class DiagnosticMetrics(Evaluator):
        def evaluate(self, ctx):
            return assess(ctx.inputs, ctx.output, ctx.expected_output, ctx.metadata["future_ids"])

    dataset = Dataset(
        name="wallet-health-synthetic-pit-v1",
        cases=[
            Case(
                name=c.inputs.case_id,
                inputs=c.inputs.pit_view(),
                expected_output=c.expected,
                metadata={
                    "split": c.split,
                    "scenario": c.scenario,
                    "future_ids": [
                        r.receipt_id
                        for r in c.inputs.receipts
                        if r.receipt_id not in {v.receipt_id for v in c.inputs.pit_view().receipts}
                    ],
                },
            )
            for c in cases
        ],
        evaluators=[DiagnosticMetrics()],
    )
    tasks = {"equity_activity": equity_activity, "transaction_attribution": transaction_attribution}
    if capture is not None:
        captured = {a.case_id: a.diagnosis for a in capture.answers}
        tasks["captured_candidate"] = lambda inputs: captured[inputs.case_id]
    start, cpu = time.perf_counter(), time.process_time()
    runs = {}
    for name, task in tasks.items():
        report = dataset.evaluate_sync(
            task, name=name, max_concurrency=1, progress=False, task_timeout=2
        )
        if (
            report.failures
            or report.report_evaluator_failures
            or any(c.evaluator_failures for c in report.cases)
        ):
            raise RuntimeError("EVALUATION_EXECUTION_FAILED")
        groups = {}
        for split in ("development", "holdout"):
            rows = [c for c in report.cases if c.metadata["split"] == split]
            groups[split] = {
                "case_count": len(rows),
                "scores": {
                    k: sum(r.scores[k].value for r in rows) / len(rows) for k in rows[0].scores
                },
                "assertion_pass_rates": {
                    k: sum(r.assertions[k].value for r in rows) / len(rows)
                    for k in rows[0].assertions
                },
                **latency_ms(r.task_duration for r in rows),
            }
        runs[name] = groups
    assert corpus_sha(cases) == digest_before
    return {
        "schema": "wallet_diagnostic_experiment_v1",
        "disposition": "EXPERIMENT"
        if provenance and provenance["observed_model_evidence"]
        else "DEFER_MODEL_COMPARISON",
        "framework_disposition": "EXPERIMENT",
        "evidence_class": "SYNTHETIC_ENGINEERING",
        "corpus_sha": digest_before,
        "case_count": len(cases),
        "wallet_time_holdout": True,
        "case_labels": "PREDECLARED_ACCOUNTING_ORACLES_NOT_LLM_LABELS",
        "independent_real_wallet_labels": False,
        "template_overlap_between_splits": True,
        "candidate": provenance or {"status": "NOT_OBSERVED", "accuracy": None, "cost_usd": None},
        "runs": runs,
        "resources": {
            "wall_seconds": time.perf_counter() - start,
            "cpu_seconds": time.process_time() - cpu,
            "process_peak_rss_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
            "network_attempts": len(NETWORK_ATTEMPTS),
            "provider_calls": 0,
            "baseline_model_tokens": 0,
            "baseline_api_cost_usd": "0",
            "candidate_usage": None
            if capture is None
            else [
                {
                    "case_id": a.case_id,
                    "input_tokens": a.input_tokens,
                    "output_tokens": a.output_tokens,
                    "api_cost_usd": a.api_cost_usd,
                    "provenance": "CAPTURE_REPORTED_NOT_INFERRED",
                }
                for a in capture.answers
            ],
        },
        "raw_receipts_unchanged": True,
        "trading_authorized": False,
        "scientifically_qualified": False,
        "limitations": [
            "No real wallet/provider labels; shared templates limit holdout generalization",
            "No LLM improvement claim without an independently trusted captured model run",
            "All edge-decay labels require abstention; sensitivity to real edge decay is unmeasured",
            "Observed equity changes alone cannot identify losses, liquidation or edge decay",
            "A signature proves bytes and key binding; host ownership remains an external trust requirement",
            "Recorded model cost/tokens remain unknown if absent; no estimated price is substituted",
            "Leakage checks cover supplied inputs, citations and captured tool scope, not hidden model internals",
        ],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--capture", type=Path)
    parser.add_argument("--signature", type=Path)
    parser.add_argument("--trusted-public-key", type=Path)
    parser.add_argument("--trusted-key-sha256")
    parser.add_argument("--export-inputs", action="store_true")
    args = parser.parse_args()
    os.environ["OTEL_SDK_DISABLED"] = "true"
    sys.addaudithook(offline_guard)
    if args.export_inputs:
        print(
            json.dumps(
                {
                    "schema": "wallet_diagnostic_inputs_v1",
                    "corpus_sha": corpus_sha(build_cases()),
                    "cases": [
                        {
                            "inputs": c.inputs.pit_view().model_dump(mode="json"),
                            "input_sha": c.inputs.pit_view().input_sha,
                        }
                        for c in build_cases()
                    ],
                },
                sort_keys=True,
            )
        )
        return
    capture, provenance = None, None
    if args.capture:
        capture, provenance = load_capture(
            args.capture,
            build_cases(),
            signature=args.signature,
            key=args.trusted_public_key,
            pin=args.trusted_key_sha256,
        )
    elif any((args.signature, args.trusted_public_key, args.trusted_key_sha256)):
        parser.error("attestation options require --capture")
    print(json.dumps(run(capture, provenance), indent=2, sort_keys=True, allow_nan=False))


if __name__ == "__main__":
    main()
