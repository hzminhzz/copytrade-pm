"""FP-05 non-executing five-minute target planner fixture tests."""

from decimal import Decimal

import pytest

from copytrade_pm.pm_forward_admission import admit_source_book
from copytrade_pm.pm_forward_batch import ForwardBatch
from test_pm_forward_admission import _alter
from test_pm_forward_fill import BTC, _source_book
from test_pm_forward_journal import T


def admission(*, equity="20000", qty="2"):
    source = _alter(_source_book(), source_equity=equity, positions={BTC.key: qty})
    return admit_source_book(source, decision_at=T, fill_at=T)


def test_nonresetting_t300_and_whole_book_equity_scaling() -> None:
    batch = ForwardBatch(Decimal("1000"))
    first = batch.ingest(admission(), first_known_at=T)
    assert first["status"] == "QUEUED"
    assert batch.preview_due(decision_at="2026-11-04T04:04:59+00:00")["status"] == "WAIT"
    later = batch.ingest(
        admission(equity="40000", qty="8"), first_known_at="2026-11-04T04:04:00+00:00"
    )
    assert later["due_at"] == first["due_at"]
    due = batch.preview_due(decision_at="2026-11-04T04:05:00+00:00")
    assert due["status"] == "DUE"
    assert due["target_quantities"] == {BTC.key: "0.200"}
    assert due["source_equity"] == "40000"
    assert due["unexecuted_notional"] == "UNKNOWN_UNTIL_PRICED"


def test_incomplete_book_does_not_queue_and_backdate_refused() -> None:
    batch = ForwardBatch(Decimal("1000"))
    bad = admit_source_book(_alter(_source_book(), source_equity=None), decision_at=T, fill_at=T)
    assert batch.ingest(bad, first_known_at=T)["status"] == "BLOCKED"
    assert batch.due_at is None
    batch.ingest(admission(), first_known_at="2026-11-04T04:01:00+00:00")
    with pytest.raises(ValueError, match="BACKDATED_SOURCE_RECEIPT"):
        batch.ingest(admission(), first_known_at=T)
    assert batch.preview_due(decision_at="2026-11-04T04:06:00+00:00")["status"] == "DUE"
