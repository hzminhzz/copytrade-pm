"""FP-05 non-executing five-minute target planner fixture tests."""

from decimal import Decimal

import pytest

from copytrade_pm.pm_forward_admission import admit_source_book
from copytrade_pm.pm_forward_batch import ForwardBatch
from test_pm_forward_admission import _alter
from test_pm_forward_fill import BTC, _source_book
from test_pm_forward_journal import T


def admission(*, equity="20000", qty="2", source_mark="100"):
    source = _alter(
        _source_book(),
        source_equity=equity,
        positions={BTC.key: qty},
        source_marks={BTC.key: source_mark},
    )
    return admit_source_book(source, decision_at=T, fill_at=T, allow_synthetic_fixture=True)


def test_nonresetting_t300_and_whole_book_equity_scaling() -> None:
    batch = ForwardBatch(Decimal("1000"))
    first = batch.ingest(admission(), first_known_at=T)
    assert first["status"] == "QUEUED"
    assert batch.preview_due(decision_at="2026-11-04T04:04:59+00:00")["status"] == "WAIT"
    later = batch.ingest(
        admission(equity="40000", qty="8"), first_known_at="2026-11-04T04:04:00+00:00"
    )
    assert later["due_at"] == first["due_at"]
    missing_quote = batch.preview_due(decision_at="2026-11-04T04:05:00+00:00")
    assert missing_quote["status"] == "BLOCKED"
    assert missing_quote["reasons"] == ["FOLLOWER_MARKS_REQUIRED_FOR_NOTIONAL_SIZING"]
    due = batch.preview_due(
        decision_at="2026-11-04T04:05:00+00:00", follower_marks={BTC: Decimal("100")}
    )
    assert due["status"] == "DUE"
    assert Decimal(due["target_quantities"][BTC.key]) == Decimal("0.2")
    assert due["source_equity"] == "40000"
    assert due["unexecuted_notional"] == "UNKNOWN_UNTIL_EXECUTION"


def test_source_notional_over_different_follower_mark() -> None:
    batch = ForwardBatch(Decimal("3000"))
    batch.ingest(admission(qty="2", source_mark="110"), first_known_at=T)
    due = batch.preview_due(
        decision_at="2026-11-04T04:05:00+00:00",
        follower_marks={BTC: Decimal("100")},
    )
    assert due["status"] == "DUE"
    assert Decimal(due["source_signed_weights"][BTC.key]) == Decimal("0.011")
    assert Decimal(due["follower_target_notionals"][BTC.key]) == Decimal("33")
    assert Decimal(due["target_quantities"][BTC.key]) == Decimal("0.33")


def test_incomplete_book_does_not_queue_and_backdate_refused() -> None:
    batch = ForwardBatch(Decimal("1000"))
    bad = admit_source_book(
        _alter(_source_book(), source_equity=None),
        decision_at=T,
        fill_at=T,
        allow_synthetic_fixture=True,
    )
    assert batch.ingest(bad, first_known_at=T)["status"] == "BLOCKED"
    assert batch.due_at is None
    batch.ingest(admission(), first_known_at="2026-11-04T04:01:00+00:00")
    with pytest.raises(ValueError, match="BACKDATED_SOURCE_RECEIPT"):
        batch.ingest(admission(), first_known_at=T)
    assert (
        batch.preview_due(
            decision_at="2026-11-04T04:06:00+00:00",
            follower_marks={BTC: Decimal("100")},
        )["status"]
        == "DUE"
    )
