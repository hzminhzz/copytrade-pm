"""Retained planner and Combo2 boundaries; legacy archive remains exact."""

from decimal import Decimal
import json
from pathlib import Path

import pytest

from copytrade_pm.pm03_account import digest
from copytrade_pm.pm_forward_admission import Admission
from copytrade_pm.pm_forward_batch import ForwardBatch
from test_pm_forward_batch import admission, BTC as NATIVE, T
from test_pm_combo2_paper import tracker, receipt, rebalance, source, quote, BTC


def gap():
    return Admission(False, ("OFFICIAL_SOURCE_GAP",), None, None, {}, {})


def test_due_is_revoked_by_gap_even_with_a_numeric_follower_mark():
    batch = ForwardBatch(Decimal("1000"))
    batch.ingest(admission(), first_known_at=T)
    batch.ingest(gap(), first_known_at="2026-11-04T04:03:00+00:00")
    report = batch.preview_due(
        decision_at="2026-11-04T04:05:10+00:00", follower_marks={NATIVE: Decimal("100")}
    )
    assert report["status"] == "BLOCKED"
    assert "OFFICIAL_SOURCE_GAP" in report["reasons"]


def test_recovery_baseline_cannot_revive_old_due_or_invent_new_t0():
    batch = ForwardBatch(Decimal("1000"))
    batch.ingest(admission(), first_known_at=T)
    batch.ingest(gap(), first_known_at="2026-11-04T04:03:00+00:00")
    restored = batch.ingest(admission(), first_known_at="2026-11-04T04:05:10+00:00")
    assert restored["status"] == "BASELINE"
    assert batch.due_at is None
    assert batch.blocked_reasons == ()
    again = batch.ingest(admission(), first_known_at="2026-11-04T04:05:20+00:00")
    assert again["status"] == "UNCHANGED" and batch.due_at is None
    transition = batch.ingest(admission(qty="3"), first_known_at="2026-11-04T04:06:00+00:00")
    assert transition["due_at"] == "2026-11-04T04:11:00+00:00"


def test_stress_frozen_display_blocks_new_risk_after_restart(tmp_path):
    engine = tracker(tmp_path)
    receipt(engine)
    first = rebalance(engine, shocks=[{BTC: "-0.5"}])
    assert first["meta"]["status"] == "FROZEN"
    assert not first["account"]["quantities"]
    restored = tracker(tmp_path)
    receipt(restored, eid="after-freeze", sec=310)
    state = rebalance(restored, eid="later", seconds=610)
    assert state["meta"]["status"] == "FROZEN"
    assert not state["account"]["quantities"]
    assert tracker(tmp_path).state() == state


def test_cf11_frozen_flat_target_gap_due_and_expired_quote_cannot_open(tmp_path):
    engine = tracker(tmp_path)
    receipt(engine)
    rebalance(engine, shocks=[{BTC: "-0.5"}])
    receipt(engine, eid="closed-target", sec=310)
    before = engine.state()
    with pytest.raises(ValueError):
        rebalance(
            engine,
            eid="expired",
            seconds=610,
            sources={"W028": source(seconds=610, quantity="0")},
            markets={BTC: quote(300)},
        )
    assert engine.state() == before
    flat = rebalance(
        engine,
        eid="flat",
        seconds=610,
        sources={"W028": source(seconds=610, quantity="0")},
        markets={},
    )
    assert not flat["account"]["quantities"]
    assert flat["meta"]["desired"]["W028"] == {}
    batch = ForwardBatch(Decimal("1000"))
    batch.ingest(admission(), first_known_at=T)
    batch.ingest(gap(), first_known_at="2026-11-04T04:03:00+00:00")
    assert (
        batch.preview_due(
            decision_at="2026-11-04T04:05:00+00:00", follower_marks={NATIVE: Decimal("100")}
        )["status"]
        == "BLOCKED"
    )


def test_prechange_combo2_archive_replays_without_rewriting(tmp_path):
    import shutil

    home = Path(__file__).resolve().parents[1] / ".workspace/pydantic-0911"
    original = home / "legacy-combo2-v1"
    expected = home / "legacy-combo2-v1-expected.json"
    if not original.exists() or not expected.exists():
        pytest.skip("Required VPS acceptance gate: private prechange Combo2 archive")
    proof = json.loads(expected.read_text())
    before = {p: p.read_bytes() for p in original.rglob("*") if p.is_file()}
    legacy = tracker(original)
    assert digest(legacy.state()) == proof["state_sha"]
    assert legacy.head == proof["head"] and len(legacy.ledger.read()) == proof["records"]
    assert all(p.read_bytes() == raw for p, raw in before.items())
    # New appends use current semantics even when historical v1 admitted a trade.
    clone = tmp_path / "replay"
    shutil.copytree(original, clone)
    upgraded = tracker(clone)
    receipt(upgraded, eid="new-version", sec=620)
    previous = upgraded.state()["account"]["quantities"]
    current = rebalance(upgraded, eid="new-version-decision", seconds=920)
    assert current["account"]["quantities"] == previous
