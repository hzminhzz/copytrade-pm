"""Behavioral gates for an offline experiment, never an LLM-performance claim."""

from datetime import timedelta
from decimal import localcontext
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from cases import build_cases, corpus_sha, evidence
from contracts import Diagnosis, Evidence, ReceiptData, ToolUse, canonical
from evaluate import assess, equity_activity, latency_ms, load_capture, transaction_attribution

ROOT = Path(__file__).resolve().parents[1]


def bundle(kind="SYNTHETIC"):
    cases = build_cases()
    return {
        "schema": "wallet_diagnostic_capture_v1",
        "corpus_sha": corpus_sha(cases),
        "capture_kind": kind,
        "model_id": "test-fixture-not-an-agent",
        "answers": [
            {
                "case_id": c.inputs.case_id,
                "input_sha": c.inputs.pit_view().input_sha,
                "diagnosis": c.expected.model_dump(mode="json"),
            }
            for c in cases
        ],
    }


def trace(tmp_path, body):
    target = tmp_path / "capture.json"
    target.write_bytes(canonical(body))
    target.chmod(0o600)
    return target


def test_wallet_date_holdout_raw_integrity_and_no_label_in_task_inputs():
    cases = build_cases()
    development = [c for c in cases if c.split == "development"]
    holdout = [c for c in cases if c.split == "holdout"]
    assert len(development) == len(holdout) == 16
    assert not {c.inputs.wallet_alias for c in development} & {
        c.inputs.wallet_alias for c in holdout
    }
    assert max(c.inputs.as_of for c in development) < min(c.inputs.as_of for c in holdout)
    before = corpus_sha(cases)
    for c in cases:
        view = c.inputs.pit_view()
        assert all(r.data.known_at <= view.as_of for r in view.receipts)
        assert "expected" not in view.model_dump()
        assert transaction_attribution(view).label == c.expected.label
        assert all(sha256(r.raw.encode()).hexdigest() == r.raw_sha for r in c.inputs.receipts)
    assert corpus_sha(cases) == before


def test_future_attribution_and_later_mark_correction_do_not_change_pit_truth():
    delayed = next(c for c in build_cases() if c.scenario == "withdrawal_known_only_later")
    assert "e03" not in {r.receipt_id for r in delayed.inputs.pit_view().receipts}
    assert transaction_attribution(delayed.inputs.pit_view()).label == "INSUFFICIENT_EVIDENCE"
    with pytest.raises(ValueError, match="NON_PIT_TASK_INPUT"):
        transaction_attribution(delayed.inputs)
    corrected = next(c for c in build_cases() if c.scenario == "later_mark_correction")
    assert transaction_attribution(corrected.inputs.pit_view()).label == "REALIZED_LOSS"


def test_wrong_aggregation_window_cannot_support_attribution():
    c = build_cases()[0]
    receipts = list(c.inputs.receipts)
    original = receipts[2].data
    receipts[2] = evidence(
        "e02",
        "DEPOSIT",
        original.observed_at,
        original.known_at,
        value=original.value,
        window_start=original.window_start - timedelta(days=1),
    )
    altered = c.inputs.model_copy(update={"receipts": tuple(receipts)})
    assert transaction_attribution(altered).label == "INSUFFICIENT_EVIDENCE"


def test_old_liquidation_cannot_describe_current_window():
    c = build_cases()[1]
    old = c.inputs.receipts[0].data.observed_at - timedelta(days=1)
    receipts = (*c.inputs.receipts, evidence("e10", "LIQUIDATION", old, old, complete=True))
    assert (
        transaction_attribution(c.inputs.model_copy(update={"receipts": receipts})).label
        == "REALIZED_LOSS"
    )


def test_correct_label_without_support_or_with_edge_claim_is_false_confident():
    c = build_cases()[0]
    for altered in (
        c.expected.model_copy(update={"evidence_ids": ("e00", "e01")}),
        c.expected.model_copy(update={"edge_decay": "CLAIMED"}),
    ):
        result = assess(c.inputs.pit_view(), altered, c.expected, [])
        assert result["diagnosis_accuracy"] == 1
        assert result["claim_supported"] is False
        assert result["false_confident_claim"] == 1


def test_attribution_does_not_round_large_offsetting_cash_flows():
    c = build_cases()[0]
    replacements = {
        "e01": "999.99",
        "e02": "123456789012345678901234567890.01",
        "e03": "-123456789012345678901234567890",
        "e04": "-0.02",
    }
    receipts = tuple(
        evidence(
            r.receipt_id,
            r.data.kind,
            r.data.observed_at,
            r.data.known_at,
            value=replacements[r.receipt_id],
            window_start=r.data.window_start,
        )
        if r.receipt_id in replacements
        else r
        for r in c.inputs.receipts
    )
    with localcontext(prec=4):
        result = transaction_attribution(c.inputs.model_copy(update={"receipts": receipts}))
    assert result.label == "MIXED_FLOWS"


@pytest.mark.parametrize(
    "replacements,expected",
    [
        ({"e06": "-5", "e07": "5"}, "MIXED_FLOWS"),
        ({"e00": "0", "e01": "0"}, "INSUFFICIENT_EVIDENCE"),
    ],
)
def test_zero_equity_change_does_not_invent_profit_or_activity(replacements, expected):
    c = next(c for c in build_cases() if c.scenario == "inactive_solvent")
    receipts = tuple(
        evidence(
            r.receipt_id,
            r.data.kind,
            r.data.observed_at,
            r.data.known_at,
            value=replacements[r.receipt_id],
            window_start=r.data.window_start,
        )
        if r.receipt_id in replacements
        else r
        for r in c.inputs.receipts
    )
    result = transaction_attribution(c.inputs.model_copy(update={"receipts": receipts}))
    assert result.label == expected


def test_scorer_detects_false_confidence_future_citation_tool_scope_and_edge_claim():
    c = next(c for c in build_cases() if c.scenario == "withdrawal_known_only_later")
    malicious = Diagnosis(
        label="WITHDRAWAL",
        confidence=0.99,
        evidence_ids=("e03",),
        edge_decay="CLAIMED",
        tool_calls=(
            ToolUse(name="place_order", case_id="c999", receipt_ids=("e03",), read_only=False),
        ),
    )
    result = assess(c.inputs.pit_view(), malicious, c.expected, ["e03"])
    assert result["diagnosis_accuracy"] == 0
    assert result["false_confident_claim"] == 1
    assert result["citation_precision"] == 0
    assert result["pit_leakage"] == 1
    assert result["tool_misuse"] == 1
    assert result["unsupported_edge_decay"] == 1
    assert result["abstention_appropriate"] is False


@pytest.mark.parametrize(
    "field,value",
    [
        ("trading_authorized", True),
        ("trading_authorized", 0),
        ("scientifically_qualified", True),
        ("confidence", float("nan")),
    ],
)
def test_diagnostic_cannot_claim_financial_or_scientific_authority(field, value):
    raw = build_cases()[0].expected.model_dump()
    raw[field] = value
    with pytest.raises(ValueError):
        Diagnosis.model_validate(raw)


@pytest.mark.parametrize("value", [True, 100.0, "NaN", "Infinity"])
def test_cash_values_never_coerce_unknown_or_nonfinite(value):
    raw = build_cases()[0].inputs.receipts[0].data.model_dump()
    raw["value"] = value
    with pytest.raises(ValueError):
        ReceiptData.model_validate(raw)


def test_raw_sha_and_duplicate_json_critical_fields_reject():
    r = build_cases()[0].inputs.receipts[0]
    with pytest.raises(ValueError, match="RAW_SHA_MISMATCH"):
        Evidence(receipt_id=r.receipt_id, raw=r.raw + " ", raw_sha=r.raw_sha)
    damaged = r.raw[:-1] + ',"value":"9999"}'
    with pytest.raises(ValueError, match="DUPLICATE_JSON_KEY"):
        Evidence(receipt_id=r.receipt_id, raw=damaged, raw_sha=sha256(damaged.encode()).hexdigest())


def test_unsigned_host_claim_and_signed_synthetic_cannot_promote_observed_model(tmp_path):
    cases = build_cases()
    with pytest.raises(ValueError, match="UNATTESTED_HOST_CAPTURE"):
        load_capture(trace(tmp_path, bundle("HOST_EXPORT")), cases)
    path = trace(tmp_path, bundle())
    signer = Ed25519PrivateKey.generate()
    public, signature = tmp_path / "public", tmp_path / "signature"
    public.write_bytes(signer.public_key().public_bytes_raw())
    public.chmod(0o644)
    signature.write_text(signer.sign(path.read_bytes()).hex())
    signature.chmod(0o600)
    _, receipt = load_capture(
        path, cases, signature=signature, key=public, pin=sha256(public.read_bytes()).hexdigest()
    )
    assert receipt["signature_verified"] is True
    assert receipt["observed_model_evidence"] is False
    signature.write_text("0" * 128)
    with pytest.raises(ValueError, match="HOST_TRACE_SIGNATURE_INVALID"):
        load_capture(
            path,
            cases,
            signature=signature,
            key=public,
            pin=sha256(public.read_bytes()).hexdigest(),
        )


@pytest.mark.parametrize(
    "damage,reason",
    [
        ("input", "INPUT_SHA"),
        ("corpus", "CORPUS"),
        ("duplicate", "CASE_COVERAGE"),
    ],
)
def test_capture_is_bound_to_exact_corpus_pit_input_and_case_set(tmp_path, damage, reason):
    body = bundle()
    if damage == "input":
        body["answers"][0]["input_sha"] = "0" * 64
    elif damage == "corpus":
        body["corpus_sha"] = "0" * 64
    else:
        body["answers"][1] = body["answers"][0]
    with pytest.raises(ValueError, match=reason):
        load_capture(trace(tmp_path, body), build_cases())


def test_equity_only_baseline_cannot_identify_withdrawal_or_liquidation():
    cases = build_cases()
    assert equity_activity(cases[0].inputs.pit_view()).label != cases[0].expected.label
    assert equity_activity(cases[3].inputs.pit_view()).label != cases[3].expected.label


def test_report_latency_uses_nearest_rank_for_small_samples():
    result = latency_ms(n / 1000 for n in range(16, 0, -1))
    assert result == {"task_ms_p50": 8.5, "task_ms_p95": 16.0}
    assert latency_ms([0.001]) == {"task_ms_p50": 1.0, "task_ms_p95": 1.0}


def test_actual_cli_runs_pydantic_evals_offline_and_keeps_model_unknown():
    completed = subprocess.run(
        [sys.executable, "evaluate.py"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
        timeout=30,
    )
    report = json.loads(completed.stdout)
    assert report["disposition"] == "DEFER_MODEL_COMPARISON"
    assert report["candidate"]["accuracy"] is None
    assert report["candidate"]["cost_usd"] is None
    assert report["raw_receipts_unchanged"] is True
    assert report["resources"]["provider_calls"] == report["resources"]["network_attempts"] == 0
    assert report["resources"]["baseline_api_cost_usd"] == "0"
    assert report["runs"]["transaction_attribution"]["holdout"]["scores"]["diagnosis_accuracy"] == 1
    assert report["trading_authorized"] is report["scientifically_qualified"] is False


def test_cli_audit_guard_blocks_network_before_any_connection():
    code = (
        "import socket,sys,evaluate\n"
        "sys.addaudithook(evaluate.offline_guard)\n"
        'try:\n socket.create_connection(("127.0.0.1",9))\n'
        "except RuntimeError:\n print(len(evaluate.NETWORK_ATTEMPTS))\n"
        'else:\n raise AssertionError("NETWORK_WAS_NOT_BLOCKED")\n'
    )
    completed = subprocess.run(
        [sys.executable, "-c", code],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
        timeout=10,
    )
    assert completed.stdout.strip() == "1"
