"""PM03 original-finance, SHADOW attempt and open valuation tests."""

from datetime import UTC, datetime
from decimal import Decimal as D

import pytest

from copytrade_pm.strategy_finance import inspect_pm03_original, summarize_pm03_economics
from copytrade_pm.strategy_matched_pm04 import compare_candidate
from test_strategy_matched_pm04 import _input

AS_OF = datetime(2026, 11, 10, 8, tzinfo=UTC)


def test_original_finance_read_only_verified_pm03_reducer(tmp_path):
    spec = _input()
    comparison = compare_candidate(spec, tmp_path)
    root = tmp_path / "runs" / "tbv2-matched-with"
    original = (root / "events.jsonl").read_bytes()
    manifest = (root / "manifest.json").read_bytes()
    details = inspect_pm03_original(
        root,
        as_of=AS_OF,
        expected_head=comparison["comparison"]["with"]["ledger_head"],
    )
    assert details["ledger_head_sha256"] == comparison["comparison"]["with"]["ledger_head"]
    assert details["account"]["equity"] == comparison["comparison"]["with"]["equity"]
    assert details["account"]["risk"] == comparison["comparison"]["with"]["risk"]
    assert details["broker_outcomes_verified"] is False
    economics = summarize_pm03_economics(details, as_of=AS_OF)
    assert economics.evidence_class == "RESEARCH_SYNTHETIC"
    assert economics.marked_equity_usd is not None
    assert economics.costs_usd is not None
    assert economics.net_comparable is False
    assert (root / "events.jsonl").read_bytes() == original
    assert (root / "manifest.json").read_bytes() == manifest


def test_original_rejects_corrupted_chain_wrong_head_or_after_asof(tmp_path):
    spec = _input()
    compare_candidate(spec, tmp_path)
    root = tmp_path / "runs" / "tbv2-matched-with"
    with pytest.raises(ValueError, match="HEAD_CHANGED"):
        inspect_pm03_original(root, as_of=AS_OF, expected_head="a" * 64)
    with pytest.raises(ValueError, match="POST_ASOF"):
        inspect_pm03_original(root, as_of=datetime(2020, 1, 1, 0, tzinfo=UTC))
    ledger = root / "events.jsonl"
    lines = ledger.read_text().splitlines()
    lines[1] = lines[1].replace('"PM04_SIGNAL"', '"TAMPERED_EVENT"')
    ledger.write_text("\n".join(lines) + "\n")
    with pytest.raises(ValueError, match="LEDGER_CHAIN_CORRUPT"):
        inspect_pm03_original(root, as_of=AS_OF)


def test_open_losing_position_marked_without_fabricated_close(tmp_path):
    from test_pm04_compare import _external_event
    from test_pm04_shadow import engine

    spec = _input()
    # Original batched entry at T+300 (~110), then a sharp adverse mark,
    # intentionally no close or fresh signal from the unchanged leader.
    spec["events"][-1] = _external_event(
        "adverse-open-mark", "PM04_TICK", engine(420, mark="80"), 420
    )
    compare_candidate(spec, tmp_path)
    root = tmp_path / "runs" / "tbv2-matched-with"
    original = inspect_pm03_original(root, as_of=AS_OF)
    econ = summarize_pm03_economics(original, as_of=AS_OF, pod_alias="W028")
    assert econ.pod_marked_net_usd is not None
    assert econ.pod_open_gross_usd is not None
    assert econ.pod_open_gross_usd > 0
    assert econ.pod_marked_net_usd < 0
    assert econ.pod_marked_net_r < 0
    assert abs(econ.pod_marked_net_r * econ.pod_budget_usd - econ.pod_marked_net_usd) < D(
        "0.00000000001"
    )
    assert econ.unrealized_pnl_usd < 0
    assert econ.net_comparable is False
    assert "INDEPENDENT_MARKET_AND_COST_COMPLETENESS_UNKNOWN" in econ.reasons
    assert "LAST_MARK_STALE_AT_ASOF" in econ.reasons
    assert econ.original_halt_reason == original["account"]["halt_reason"]
    assert original["broker_outcomes_verified"] is False


def test_original_paper_t300_pending_and_expiry_not_fabricated(tmp_path):
    from copytrade_pm.pm_forward_journal import PaperJournal
    from copytrade_pm.strategy_finance import reconcile_source_attempts
    from copytrade_pm.strategy_health import Opportunity, StrategyAssessment, ZERO_SHA, seal
    from test_pm_forward_single_shot import new_paper
    from test_pm_forward_observed_paper import BTC, add_quote, add_source, at
    from test_strategy_health_v2 import assessment

    tape = PaperJournal(tmp_path / "source")
    add_quote(tape, 10)
    paper = new_paper(tmp_path, tape)
    add_source(tape, 1, 12, {BTC.key: "20"})
    pending = paper.step(at(14))
    assert pending["execution_intents"]["S035"]["status"] == "PENDING_5M"
    add_source(tape, 2, 199, {BTC.key: "10"})
    updated = paper.step(at(201))
    assert (
        updated["execution_intents"]["S035"]["due_at"]
        == pending["execution_intents"]["S035"]["due_at"]
    )
    original = inspect_pm03_original(
        paper.run.ledger.path,
        as_of=AS_OF,
    )
    original_sources = [x for x in original["events"] if x["kind"] == "PM04_PAPER_SOURCE"]
    assert len(original_sources) == 2
    source = original_sources[0]
    known = datetime.fromisoformat(source["first_known_at"])
    due = known + __import__("datetime").timedelta(seconds=300)
    base = assessment()
    opportunity = Opportunity(
        opportunity_id="9" * 64,
        source_event_sha256="8" * 64,
        source_receipt_sha256=source["input"]["source_sha"],
        source_event_at=datetime.fromisoformat(source["source_event_at"]),
        first_known_at=known,
        due_at=due,
        stream_cursor=source["input"]["source_seq"],
        source_epoch="official",
        frozen_k_version="k1",
        frozen_k=D("0.125"),
    )
    report = seal(
        StrategyAssessment.model_validate(
            {
                **base.model_dump(),
                "report_sha256": ZERO_SHA,
                "opportunities": (opportunity,),
            }
        )
    )
    joined = reconcile_source_attempts(report, original)
    assert joined.opportunities[0].state == "PENDING"
    assert joined.opportunities[0].attempt_id is not None
    assert joined.opportunities[0].due_at == due
    assert joined.trading_authorized is False
    no_market = paper.step(at(344))
    assert no_market["execution_intents"]["S035"]["status"] == "EXPIRED_NO_TRADE"
    original_after = inspect_pm03_original(paper.run.ledger.path, as_of=AS_OF)
    expired = reconcile_source_attempts(report, original_after)
    assert expired.opportunities[0].state == "EXPIRED"
    assert expired.opportunities[0].attempt_id == joined.opportunities[0].attempt_id
    assert expired.opportunities[0].due_at == joined.opportunities[0].due_at
