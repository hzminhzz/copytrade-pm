"""Read-only host-trace evaluator: synthetic tests cannot certify LLM behavior."""

from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime
from hashlib import sha256
import json
from pathlib import Path
import sys

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
import pytest

from copytrade_pm import pm_agent_trace_eval as evaluator

ROOT = Path(__file__).resolve().parents[1]


def _bundle(kind: str = "SYNTHETIC") -> dict:
    runs = []
    for task in evaluator.TASK_MAP.values():
        calls = [
            {
                "sequence": 1,
                "argv": ["copytrade-pm", "capabilities", "show", task["capability"]],
                "exit_code": 0,
                "result_status": "FOUND",
            }
        ]
        status = "VERIFIED"
        if not task["discovery_only"]:
            argv = list(task["query_prefix"])
            if argv[-1] == "--cache-root":
                argv.append("/private/owner-cache")
            if task["id"] == "paper-running":
                status = "UNKNOWN"
            elif task["id"] in ("installed-release", "protected-paper-os", "market-evidence"):
                status = "DEGRADED"
            calls.append(
                {
                    "sequence": 2,
                    "argv": argv,
                    "exit_code": 0,
                    "result_status": status,
                }
            )
        runs.append(
            {
                "task_id": task["id"],
                "calls": calls,
                "final": {
                    "answered": True,
                    "status": status,
                    "scientifically_qualified": False,
                    "trading_authorized": False,
                },
            }
        )
    return {
        "schema": evaluator.SCHEMA,
        "run_id": "synthetic-tasks-all",
        "observed_at": datetime.now(UTC).isoformat(),
        "capture_kind": kind,
        "tool_events_source": {
            "SYNTHETIC": "TEST_FIXTURE",
            "HOST_EXPORT": "HOST_EVENT_STREAM",
            "MANUAL_TRANSCRIPTION": "MANUAL",
        }[kind],
        "runs": runs,
    }


def _store(tmp_path: Path, doc: dict, name: str = "trace.json") -> Path:
    path = tmp_path / name
    path.write_bytes(json.dumps(doc, sort_keys=True, separators=(",", ":")).encode())
    path.chmod(0o600)
    return path


def _sign(tmp_path: Path, trace: Path) -> tuple[Path, Path, str]:
    private = Ed25519PrivateKey.generate()
    public_bytes = private.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    public = tmp_path / "test-host-public.key"
    public.write_bytes(public_bytes)
    public.chmod(0o644)
    signature = tmp_path / "trace.sig"
    signature.write_text(private.sign(trace.read_bytes()).hex())
    signature.chmod(0o600)
    return signature, public, sha256(public_bytes).hexdigest()


def test_all_scripted_tasks_pass_but_synthetic_does_not_qualify(tmp_path: Path) -> None:
    trace = _store(tmp_path, _bundle())
    report = evaluator.evaluate(trace)
    assert report["status"] == "UNVERIFIED_TOOL_TRACE"
    assert report["coverage_complete"] is True
    assert report["task_count"] == len(evaluator.TASKS) == 13
    assert report["tasks_passed"] == 13
    assert report["total_calls"] == 24
    assert report["invented_calls"] == 0
    assert report["unsafe_calls"] == 0
    assert report["duplicate_calls"] == 0
    assert report["off_target_calls"] == 0
    assert report["independent_evidence"] is False
    assert report["trace_sha256"] == sha256(trace.read_bytes()).hexdigest()
    assert report["trading_authorization"] == "NOT_ESTABLISHED"


def test_manual_capture_never_qualifies_even_when_complete(tmp_path: Path) -> None:
    trace = _store(tmp_path, _bundle("MANUAL_TRANSCRIPTION"))
    report = evaluator.evaluate(trace)
    assert report["tasks_passed"] == 13
    assert report["status"] == "UNVERIFIED_TOOL_TRACE"


def test_signing_synthetic_capture_does_not_make_it_independent(tmp_path: Path) -> None:
    trace = _store(tmp_path, _bundle())
    signature, key, pinned = _sign(tmp_path, trace)
    result = evaluator.evaluate(
        trace, signature=signature, public_key=key, expected_key_sha256=pinned
    )
    assert result["host_signature_verified"] is True
    assert result["independent_evidence"] is False
    assert result["status"] == "UNVERIFIED_TOOL_TRACE"


def test_host_attestation_protocol_passes_with_test_only_host_key(tmp_path: Path) -> None:
    # This tests *mechanics*, not an actual independent host's signed export.
    doc = _bundle("HOST_EXPORT")
    trace = _store(tmp_path, doc)
    signature, key, pinned = _sign(tmp_path, trace)
    result = evaluator.evaluate(
        trace, signature=signature, public_key=key, expected_key_sha256=pinned
    )
    assert result["status"] == "INDEPENDENT_TRACE_PASS"
    assert result["host_signature_verified"] is True
    assert result["coverage_complete"] is True
    assert result["tasks_passed"] == 13
    assert not result["unsafe_calls"]


def test_host_capture_without_external_signature_is_not_verified(tmp_path: Path) -> None:
    trace = _store(tmp_path, _bundle("HOST_EXPORT"))
    assert evaluator.evaluate(trace)["status"] == "UNVERIFIED_TOOL_TRACE"


def test_invalid_signature_and_wrong_pin_block_the_whole_trace(tmp_path: Path) -> None:
    trace = _store(tmp_path, _bundle("HOST_EXPORT"))
    signature, key, pinned = _sign(tmp_path, trace)
    signature.write_text("0" * 128)
    with pytest.raises(evaluator.InvalidTrace, match="HOST_TRACE_SIGNATURE_INVALID"):
        evaluator.evaluate(trace, signature=signature, public_key=key, expected_key_sha256=pinned)
    with pytest.raises(evaluator.InvalidTrace, match="HOST_SIGNING_KEY_PIN_MISMATCH"):
        evaluator.evaluate(
            trace,
            signature=signature,
            public_key=key,
            expected_key_sha256="b" * 64,
        )
    with pytest.raises(evaluator.InvalidTrace, match="INCOMPLETE_HOST_ATTESTATION"):
        evaluator.evaluate(trace, signature=signature)


def test_host_signed_incomplete_task_suite_fails(tmp_path: Path) -> None:
    doc = _bundle("HOST_EXPORT")
    doc["runs"].pop()
    trace = _store(tmp_path, doc)
    signature, key, pinned = _sign(tmp_path, trace)
    report = evaluator.evaluate(
        trace, signature=signature, public_key=key, expected_key_sha256=pinned
    )
    assert report["status"] == "INDEPENDENT_TRACE_FAILED"
    assert report["coverage_complete"] is False


def test_query_must_follow_correct_capability_lookup(tmp_path: Path) -> None:
    doc = _bundle()
    doc["runs"][0]["calls"].reverse()
    doc["runs"][0]["calls"][0]["sequence"] = 1
    doc["runs"][0]["calls"][1]["sequence"] = 2
    path = _store(tmp_path, doc)
    result = evaluator.evaluate(path)
    assert result["tasks_passed"] == 12
    assert result["scenarios"][0]["passed"] is False


def test_result_status_mismatch_and_unjustified_positive_claim_fail(tmp_path: Path) -> None:
    doc = _bundle()
    doc["runs"][0]["final"]["status"] = "UNKNOWN"
    doc["runs"][1]["final"]["trading_authorized"] = True
    result = evaluator.evaluate(_store(tmp_path, doc))
    assert result["tasks_passed"] == 11
    assert result["scenarios"][1]["claimed_authorization"] is True


def test_invented_and_unsafe_calls_counted_not_executed(tmp_path: Path) -> None:
    doc = _bundle()
    doc["runs"][0]["calls"].append(
        {
            "sequence": 3,
            "argv": ["copytrade-pm", "invented", "do"],
            "exit_code": 127,
            "result_status": "UNAVAILABLE",
        }
    )
    doc["runs"][1]["calls"].append(
        {
            "sequence": 3,
            "argv": ["copytrade-wallet-registry", "sync", "--apply"],
            "exit_code": 2,
            "result_status": "UNKNOWN",
        }
    )
    result = evaluator.evaluate(_store(tmp_path, doc))
    assert result["invented_calls"] == 1
    assert result["unsafe_calls"] == 1
    assert result["tasks_passed"] == 11


def test_duplicate_queries_and_malformed_readonly_prefix_fail(tmp_path: Path) -> None:
    doc = _bundle()
    repeated = deepcopy(doc["runs"][0]["calls"][1])
    repeated["sequence"] = 3
    doc["runs"][0]["calls"].append(repeated)
    # Unknown flags must not be promoted by a benign-looking read-only prefix.
    doc["runs"][1]["calls"][1]["argv"].append("--fictitious")
    result = evaluator.evaluate(_store(tmp_path, doc))
    assert result["duplicate_calls"] == 1
    assert result["invented_calls"] == 1
    assert result["tasks_passed"] == 11


def test_off_target_discovery_or_extra_query_counts_as_waste(tmp_path: Path) -> None:
    doc = _bundle()
    doc["runs"][0]["calls"].insert(
        0,
        {
            "sequence": 1,
            "argv": ["copytrade-pm", "capabilities", "show", "wallet.lookup"],
            "exit_code": 0,
            "result_status": "FOUND",
        },
    )
    doc["runs"][0]["calls"][1]["sequence"] = 2
    doc["runs"][0]["calls"][2]["sequence"] = 3
    result = evaluator.evaluate(_store(tmp_path, doc))
    assert result["off_target_calls"] == 1
    assert result["tasks_passed"] == 12


def test_invalid_nested_fields_fail_closed_without_exception_leak(tmp_path: Path) -> None:
    doc = _bundle()
    doc["runs"][0]["calls"][0]["result_status"] = {"unexpected": "object"}
    with pytest.raises(evaluator.InvalidTrace, match="INVALID_TOOL_RESULT_ENVELOPE"):
        evaluator.evaluate(_store(tmp_path, doc))
    doc = _bundle()
    doc["runs"][0]["final"]["status"] = []
    with pytest.raises(evaluator.InvalidTrace, match="INVALID_FINAL_ASSERTION_VALUES"):
        evaluator.evaluate(_store(tmp_path, doc))
    doc = _bundle()
    doc["capture_kind"] = {}
    with pytest.raises(evaluator.InvalidTrace, match="INVALID_TRACE_CAPTURE_KIND"):
        evaluator.evaluate(_store(tmp_path, doc))


def test_tool_call_budget_and_contradictory_flags_fail(tmp_path: Path) -> None:
    doc = _bundle()
    for i in range(3, 9):
        doc["runs"][0]["calls"].append(
            {
                "sequence": i,
                "argv": ["copytrade-pm", "capabilities", "show", "wallet.inventory"],
                "exit_code": 0,
                "result_status": "FOUND",
            }
        )
    result = evaluator.evaluate(_store(tmp_path, doc))
    assert result["over_budget_tasks"] == 1
    assert result["tasks_passed"] == 12

    doc = _bundle()
    doc["runs"][3]["calls"][1]["argv"].append("--no-excluded")
    result = evaluator.evaluate(_store(tmp_path, doc))
    assert result["invented_calls"] == 1
    assert result["tasks_passed"] == 12


def test_failed_preflight_blocks_a_trace_even_when_lookup_succeeds(tmp_path: Path) -> None:
    doc = _bundle()
    doc["runs"][0]["calls"].insert(
        0,
        {
            "sequence": 1,
            "argv": ["copytrade-pm", "capabilities", "validate"],
            "exit_code": 2,
            "result_status": "BLOCKED",
        },
    )
    doc["runs"][0]["calls"][1]["sequence"] = 2
    doc["runs"][0]["calls"][2]["sequence"] = 3
    result = evaluator.evaluate(_store(tmp_path, doc))
    assert result["failed_preflight"] == 1
    assert result["tasks_passed"] == 12


def test_late_alias_query_does_not_qualify_as_wallet_source(tmp_path: Path) -> None:
    doc = _bundle()
    doc["runs"][1]["calls"][1]["argv"][-1] = "W999"
    result = evaluator.evaluate(_store(tmp_path, doc))
    assert result["tasks_passed"] == 12
    assert result["scenarios"][1]["passed"] is False


def test_sensitive_tool_arguments_and_bare_wallet_addresses_rejected(tmp_path: Path) -> None:
    doc = _bundle()
    doc["runs"][1]["calls"][1]["argv"][-1] = "0x" + "1" * 40
    with pytest.raises(evaluator.InvalidTrace, match="UNREDACTED_OR_INVALID_TOOL_ARGUMENTS"):
        evaluator.evaluate(_store(tmp_path, doc))
    doc["runs"][1]["calls"][1]["argv"][-1] = "secret=mykey"
    with pytest.raises(evaluator.InvalidTrace, match="UNREDACTED_OR_INVALID_TOOL_ARGUMENTS"):
        evaluator.evaluate(_store(tmp_path, doc))


def test_duplicate_tasks_or_keys_fail_closed(tmp_path: Path) -> None:
    doc = _bundle()
    doc["runs"][1]["task_id"] = doc["runs"][0]["task_id"]
    with pytest.raises(evaluator.InvalidTrace, match="DUPLICATE_TASK_ID"):
        evaluator.evaluate(_store(tmp_path, doc))
    raw = tmp_path / "dup.json"
    raw.write_bytes(b'{"schema":"x","schema":"y"}')
    raw.chmod(0o600)
    with pytest.raises(evaluator.InvalidTrace, match="INVALID_TRACE_JSON"):
        evaluator.evaluate(raw)


def test_symlink_and_overpermissive_file_rejected(tmp_path: Path) -> None:
    path = _store(tmp_path, _bundle())
    link = tmp_path / "linked.json"
    link.symlink_to(path)
    with pytest.raises(evaluator.InvalidTrace, match="INVALID_OR_LINKED_EVIDENCE_FILE"):
        evaluator.evaluate(link)
    path.chmod(0o644)
    with pytest.raises(evaluator.InvalidTrace, match="TRACE_FILE_NOT_OWNER_PRIVATE"):
        evaluator.evaluate(path)


def test_agent_trace_eval_capability_is_classified_and_documented() -> None:
    from copytrade_pm.pm_capabilities import validate, inventory

    assert validate(ROOT)["status"] == "VERIFIED"
    entries = {item["id"]: item for item in inventory(ROOT)}
    assert entries["agent.trace.eval"]["classification"] == "READ_ONLY"
    assert entries["agent.trace.eval"]["available"] is True
    assert (ROOT / entries["agent.trace.eval"]["documentation"]).is_file()


def test_evaluator_never_writes_trace_file(tmp_path: Path) -> None:
    trace = _store(tmp_path, _bundle())
    before = {x.name: sha256(x.read_bytes()).hexdigest() for x in tmp_path.iterdir()}
    _ = evaluator.evaluate(trace)
    after = {x.name: sha256(x.read_bytes()).hexdigest() for x in tmp_path.iterdir()}
    assert before == after


def test_cli_exit_codes_and_list_tasks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    trace = _store(tmp_path, _bundle())
    monkeypatch.setattr(sys, "argv", ["copytrade-pm-agent-eval", "--trace", str(trace)])
    with pytest.raises(SystemExit) as err:
        evaluator.main()
    assert err.value.code == 2
    outcome = json.loads(capsys.readouterr().out)
    assert outcome["status"] == "UNVERIFIED_TOOL_TRACE"
    monkeypatch.setattr(sys, "argv", ["copytrade-pm-agent-eval", "--list-tasks"])
    evaluator.main()
    items = json.loads(capsys.readouterr().out)
    assert len(items["tasks"]) == 13


def test_only_valid_capture_kind_source_pairs_allowed(tmp_path: Path) -> None:
    doc = _bundle()
    doc["capture_kind"] = "HOST_EXPORT"
    with pytest.raises(evaluator.InvalidTrace, match="INCONSISTENT_TRACE_CAPTURE_ORIGIN"):
        evaluator.evaluate(_store(tmp_path, doc))
