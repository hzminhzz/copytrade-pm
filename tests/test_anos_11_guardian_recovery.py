"""ANOS-11 synthetic owner projections; never interpret a status file as an order receipt."""

from __future__ import annotations

import copy
import json
import sys
from types import ModuleType

import pytest

from copytrade_pm import pm_operations
from copytrade_pm.pm_cwsa_chapter2_projection import explain_native_guardian_intent

INTENT = "a" * 64
RELEASE = "b" * 64
ACCOUNT = "c" * 64


def owner_fixture(monkeypatch, *, status="QUEUED", sent=None, bad=False):
    """A controlled stand-in for original Guardian Journal.read + operator.project_state."""
    state = {
        "schema": "guardian_journal_v1",
        "sequence": 17,
        "active_release_sha": RELEASE,
        "account_binding": "synthetic-account",
        "intents": {
            INTENT: {
                "intent_id": INTENT,
                "status": status,
                "reservation_id": "decision-1",
                "release_sha": RELEASE,
                "expires_at_ms": 9999,
                "sent_at_ms": sent,
            }
        },
        "reservations": {
            "decision-1": {"loss": "2", "margin": "5", "cost": "1", "intent_ids": [INTENT]}
        },
        "halts": ["UNKNOWN_OUTCOME"],
        "finance": {"daily_floor": "9500", "trailing_floor": "9000", "risk_floor": "9200"},
        "runtime": {"certainty": "UNKNOWN"},
    }
    package = ModuleType("prop_production")
    package.__path__ = []
    journal_mod = ModuleType("prop_production.journal")
    operator_mod = ModuleType("prop_production.operator")

    class Journal:
        @staticmethod
        def read(path):
            assert str(path) == "/synthetic/journal"
            return copy.deepcopy(state)

    def project_state(snapshot, command, now_ms, intent_id=None):
        assert snapshot == state
        assert now_ms == 5000
        common = {
            "schema": f"operator_{command}_v1",
            "journal_sequence": snapshot["sequence"] + int(bad),
            "release_sha": RELEASE,
            "account_binding_sha": ACCOUNT,
            "halts": snapshot["halts"],
        }
        if command == "intent":
            assert intent_id == INTENT
            return common | {"intents": [snapshot["intents"][INTENT]]}
        if command == "risk":
            return common | {
                "reservations": snapshot["reservations"],
                "finance": snapshot["finance"],
            }
        if command == "broker":
            return common | {"certainty": snapshot["runtime"]["certainty"]}
        raise AssertionError("NO_DISPATCH_OR_MUTATION_ALLOWED")

    journal_mod.Journal = Journal
    operator_mod.project_state = project_state
    monkeypatch.setitem(sys.modules, "prop_production", package)
    monkeypatch.setitem(sys.modules, "prop_production.journal", journal_mod)
    monkeypatch.setitem(sys.modules, "prop_production.operator", operator_mod)
    return state


@pytest.mark.parametrize(
    "status,sent,expected",
    [
        ("QUEUED", None, "NOT_DISPATCHED"),
        ("DISPATCHING", 4000, "POSSIBLY_DISPATCHED"),
        ("UNKNOWN", 4000, "POSSIBLY_DISPATCHED"),
        ("ACKNOWLEDGED", 4000, "POSSIBLY_DISPATCHED"),
        ("CANCEL_PENDING", 4000, "POSSIBLY_DISPATCHED"),
        ("REJECT_PENDING_PROOF", 4000, "POSSIBLY_DISPATCHED"),
        ("FILLED", 4000, "VERIFIED_COMPLETED"),
        ("REJECTED", 4000, "VERIFIED_REJECTED"),
        ("NOT_ACCEPTED", 4000, "VERIFIED_REJECTED"),
        ("REVOKED", None, "VERIFIED_REJECTED"),
    ],
)
def test_original_owner_state_preserves_intent_reservation_halt_and_floors(
    monkeypatch, status, sent, expected
):
    state = owner_fixture(monkeypatch, status=status, sent=sent)
    before = copy.deepcopy(state)
    result = explain_native_guardian_intent(
        journal_path="/synthetic/journal", intent_id=INTENT, observed_at_ms=5000
    )
    assert result["dispatch_state"] == expected
    assert result["intent_id"] == INTENT
    assert result["reservation_active"] is True
    assert result["reservation"] == {"loss": "2", "margin": "5", "cost": "1"}
    assert result["halt_reasons"] == ["UNKNOWN_OUTCOME"]
    assert result["risk_floors"]["daily_floor"] == "9500"
    assert result["original_deadline_ms"] == 9999
    assert result["mandate_generation"] is None
    assert result["broker_certainty"] == "UNKNOWN"
    assert result["order_route"] == "NONE"
    assert result["retry_authorized"] is False
    assert result["trading_authorized"] is False
    assert state == before


def test_missing_or_inconsistent_owner_evidence_stays_unknown(monkeypatch):
    owner_fixture(monkeypatch, bad=True)
    result = explain_native_guardian_intent(
        journal_path="/synthetic/journal", intent_id=INTENT, observed_at_ms=5000
    )
    assert result["dispatch_state"] == "EVIDENCE_UNAVAILABLE"
    assert result["reservation_active"] is None
    assert result["halt_reasons"] is None
    assert result["unrelated_read_only_work_allowed"] is True
    assert result["retry_authorized"] is False


def test_missing_optional_protected_owner_never_promotes_authority(monkeypatch):
    owner_fixture(monkeypatch)
    sys.modules.pop("prop_production.journal")
    monkeypatch.setitem(sys.modules, "prop_production.journal", None)
    result = explain_native_guardian_intent(
        journal_path="/synthetic/journal", intent_id=INTENT, observed_at_ms=5000
    )
    assert result["dispatch_state"] == "EVIDENCE_UNAVAILABLE"
    assert result["retry_authorized"] is False


def test_native_original_journal_read_without_broker_transport(tmp_path):
    """Optional companion integration: original hash chain and owner projections."""
    guardian = pytest.importorskip("prop_production.journal")
    path = tmp_path / "guardian-synthetic.sqlite3"
    with guardian.Journal(path, "synthetic-account", initialize=True) as journal:

        def reserve(state):
            state["intents"][INTENT] = {
                "intent_id": INTENT,
                "status": "DISPATCHING",
                "sent_at_ms": 4000,
                "reservation_id": "decision-1",
                "release_sha": RELEASE,
                "expires_at_ms": 9999,
            }
            state["reservations"]["decision-1"] = {
                "loss": "2",
                "margin": "5",
                "cost": "1",
                "intent_ids": [INTENT],
            }
            state["halts"].append("UNKNOWN_OUTCOME")
            state["active_release_sha"] = RELEASE
            state["finance"]["daily_floor"] = "9500"

        journal.update("SYNTHETIC_RESERVE_DISPATCHING", 4000, reserve)
    before = guardian.Journal.read(path)
    first = explain_native_guardian_intent(journal_path=path, intent_id=INTENT, observed_at_ms=5000)
    second = explain_native_guardian_intent(
        journal_path=path, intent_id=INTENT, observed_at_ms=5000
    )
    assert first == second
    assert first["dispatch_state"] == "POSSIBLY_DISPATCHED"
    assert first["reservation_active"] is True
    assert first["halt_reasons"] == ["UNKNOWN_OUTCOME"]
    assert first["risk_floors"]["daily_floor"] == "9500"
    assert first["retry_authorized"] is False
    assert guardian.Journal.read(path) == before
    # The original writer's crash-recovery reducer owns DISPATCHING -> UNKNOWN.
    with guardian.Journal(path, "synthetic-account") as restarted:
        assert restarted.snapshot()["intents"][INTENT]["status"] == "UNKNOWN"
        assert restarted.snapshot()["reservations"]["decision-1"]["intent_ids"] == [INTENT]
        assert "UNKNOWN_OUTCOME" in restarted.snapshot()["halts"]
    recovered = explain_native_guardian_intent(
        journal_path=path, intent_id=INTENT, observed_at_ms=5000
    )
    assert recovered["dispatch_state"] == "POSSIBLY_DISPATCHED"
    assert recovered["retry_authorized"] is False
    assert recovered["reservation_active"] is True


def test_read_only_recover_cli_uses_owner_and_never_dispatches(monkeypatch, capsys):
    owner_fixture(monkeypatch, status="UNKNOWN", sent=4000)
    code = pm_operations.cli(
        [
            "cwsa",
            "chapter2",
            "recover",
            "--guardian-journal",
            "/synthetic/journal",
            "--intent-id",
            INTENT,
            "--observed-at-ms",
            "5000",
        ]
    )
    result = json.loads(capsys.readouterr().out)
    assert code == 0
    assert result["dispatch_state"] == "POSSIBLY_DISPATCHED"
    assert result["next_operation"] == "prop-production broker --journal PATH"
    assert result["retry_authorized"] is False
