"""Archive compatibility and adversarial owner-based paper contracts."""

from copy import deepcopy
from decimal import Decimal
import json
from pathlib import Path

import pytest

from copytrade_pm.pm03_account import RiskState
from copytrade_pm.pm03_memory import Event
from copytrade_pm.pm04_broker import pending_quantities
from copytrade_pm.pm_forward_journal import PaperJournal
from copytrade_pm.pm_forward_observed_paper import ObservedP1Paper, _event
from copytrade_pm.pm_paper_contracts import PaperOpportunity
from test_pm_forward_observed_paper import BTC, RAW_MARKET, add_quote, add_source, at, registry
from test_pm_forward_single_shot import new_paper


def _archived(tmp_path):
    witness = Path(__file__).parent.parent / ".workspace/pydantic-0911/legacy-opportunity-v1.json"
    if not witness.exists():
        pytest.skip("local-only legacy journal witness; required VPS acceptance gate")
    archive = json.loads(witness.read_text())
    source = PaperJournal(tmp_path / "source")
    root = tmp_path / "private"
    root.mkdir(mode=0o700)
    run_root = root / "single_attempt"
    run_root.mkdir(mode=0o700)
    for filename, content in (
        ("manifest.json", json.dumps(archive["manifest"], sort_keys=True, separators=(",", ":"))),
        ("events.jsonl", archive["ledger_text"]),
    ):
        path = run_root / filename
        path.write_text(content)
        path.chmod(0o600)
    paper = ObservedP1Paper(
        source_db=source.path,
        state_root=root,
        run_id="single_attempt",
        registry_db=registry(tmp_path / "registry.sqlite"),
        catalog={RAW_MARKET["symbol"]: RAW_MARKET},
    )
    return paper, archive


def test_v1_archive_is_exact_then_flat_reconciliation_is_new_durable_event(tmp_path):
    paper, archive = _archived(tmp_path)
    assert paper.run.ledger.events_path.read_text() == archive["ledger_text"]
    assert paper.run.account.pm04_state["routed_targets"]["S035"]
    assert not any(paper.run.account.quantities.values())
    before = paper.run.account.snapshot()
    old_event = json.loads(archive["ledger_text"].splitlines()[-1])["event"]
    paper.run.record(Event(**old_event))
    assert paper.run.account.snapshot() == before
    result = paper.step(at(900))
    assert result["tick"] == "NO_ACTIVE_TARGETS"
    assert paper.run.account.pm04_state["routed_targets"]["S035"] == {}
    assert paper.run.ledger.events_path.read_text().startswith(archive["ledger_text"])
    new = paper.run.ledger.read()[-1]["event"]
    assert new["kind"] == "PM04_PAPER_RECONCILE_FLAT"
    assert new["payload"]["paper_semantics_version"] == 2
    for key in ("cash", "costs", "quantities", "risk", "pm_costs", "pm_cash"):
        assert paper.run.account.snapshot()[key] == before[key]
    assert paper.run.restore()["account"] == paper.run.account.snapshot()
    assert paper.step(at(901))["last_event_id"] == new["event_id"]


def test_cancel_late_fill_stale_snapshot_cannot_clear_target_or_reservation(tmp_path):
    tape = PaperJournal(tmp_path / "source")
    add_quote(tape, 10)
    paper = new_paper(tmp_path, tape)
    add_source(tape, 1, 12, {BTC.key: "20"})
    paper.step(at(14))
    add_quote(tape, 312)
    paper.step(at(313))

    def observe(name, kind, seconds, **extra):
        row = {
            "schema": "pm04_broker_observation_v1",
            "evidence_id": name,
            "kind": kind,
            "event_at": at(seconds),
            "first_known_at": at(seconds),
            **extra,
        }
        return paper.run.record(
            _event(paper.run, "PM04_BROKER", name, at(seconds), at(seconds), {"observation": row})
        )

    observe(
        "intent",
        "ORDER_INTENT",
        330,
        order_id="O1",
        instrument=BTC.key,
        quantity="3",
        provider_sequence=1,
    )
    observe("cancel", "CANCEL", 340, order_id="O1", provider_sequence=2)
    observe(
        "late-fill", "PARTIAL_FILL", 350, order_id="O1", cumulative_filled="1", provider_sequence=3
    )
    observe(
        "old-snapshot",
        "POSITION_SNAPSHOT",
        360,
        event_at=at(335),
        complete=True,
        positions={BTC.key: "0"},
    )
    assert pending_quantities(paper.run.account, at(361))[BTC] == 2
    assert paper.run.account.risk == RiskState.HALT
    before_step = paper.run.account.pm04_state["routed_targets"]["S035"].copy()
    add_source(tape, 2, 361, {})
    add_quote(tape, 362)
    closed = paper.step(at(363))
    assert closed["positions"] == {}
    assert paper.run.account.pm04_state["routed_targets"]["S035"] == before_step
    assert pending_quantities(paper.run.account, at(364))[BTC] == 2
    again = paper.step(at(364))
    assert Decimal(again["cash"]) == Decimal(closed["cash"])
    assert again["costs"] == closed["costs"]
    assert paper.run.account.risk == RiskState.HALT
    assert paper.run.restore()["account"] == paper.run.account.snapshot()
    assert not any(
        r["event"]["kind"] == "PM04_PAPER_RECONCILE_FLAT" for r in paper.run.ledger.read()
    )


@pytest.mark.parametrize(
    "field,value",
    [
        ("source_seq", True),
        ("source_sha", "unknown"),
        ("due_at", at(314)),
        ("deadline_at", at(400)),
        ("first_known_at", "2026-11-07T08:00:13"),
        ("positions", {BTC.key: "NaN"}),
        ("positions", {BTC.key: 20.0}),
        ("unexpected_financial_authority", True),
        ("terminal_at", at(15)),
        ("attempted_at", at(15)),
    ],
)
def test_typed_opportunity_rejects_critical_ambiguity(tmp_path, field, value):
    tape = PaperJournal(tmp_path / "source")
    add_quote(tape, 10)
    paper = new_paper(tmp_path, tape)
    add_source(tape, 1, 12, {BTC.key: "20"})
    intent = deepcopy(paper.step(at(14))["execution_intents"]["S035"])
    intent[field] = value
    with pytest.raises(ValueError):
        PaperOpportunity.model_validate(intent)


def test_terminal_or_regressed_opportunity_cannot_coalesce(tmp_path):
    tape = PaperJournal(tmp_path / "source")
    add_quote(tape, 10)
    paper = new_paper(tmp_path, tape)
    add_source(tape, 1, 12, {BTC.key: "20"})
    intent = PaperOpportunity.model_validate(paper.step(at(14))["execution_intents"]["S035"])
    assert intent.eligibility(at(312)) == "WAIT"
    assert intent.eligibility(at(313)) == "READY"
    assert intent.eligibility(at(343)) == "READY"
    assert intent.eligibility(at(344)) == "EXPIRED"
    with pytest.raises(ValueError, match="NOT_COALESCIBLE"):
        intent.coalesce(
            source_seq=1,
            source_sha=intent.source_sha,
            source_event_at=at(20),
            positions={BTC.key: "10"},
            decision_at=at(21),
        )
    add_quote(tape, 312)
    completed = PaperOpportunity.model_validate(paper.step(at(313))["execution_intents"]["S035"])
    with pytest.raises(ValueError, match="NOT_COALESCIBLE"):
        completed.coalesce(
            source_seq=2,
            source_sha=intent.source_sha,
            source_event_at=at(320),
            positions={BTC.key: "10"},
            decision_at=at(321),
        )
