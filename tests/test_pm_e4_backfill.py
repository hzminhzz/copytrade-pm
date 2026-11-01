"""E4 account source pagination validates bounds and historical causality."""

import pytest

from copytrade_pm.pm_e4_backfill import PAGE_SIZE, _validate_rows


def test_ledger_backfill_page_clock_and_bounds():
    assert _validate_rows([], start=1, end=100) == (None, None)
    assert _validate_rows([{"time": 10}, {"time": 10}, {"time": 15}], start=1, end=100) == (10, 15)


@pytest.mark.parametrize(
    "rows,reason",
    [
        ([{"time": 100}, {"time": 99}], "E4_NONCHRONOLOGICAL_PROVIDER_BACKFILL"),
        ([{"time": 200}], "E4_BACKFILL_OUTSIDE_REQUESTED_RANGE"),
        ([{"time": "10"}], "E4_INVALID_BACKFILL_EVENT_CLOCK"),
        ([{"time": 50}] * (PAGE_SIZE + 1), "E4_UNTRUSTED_BACKFILL_PAGE"),
    ],
)
def test_e4_backfill_fail_closed(rows, reason):
    with pytest.raises(ValueError, match=reason):
        _validate_rows(rows, start=1, end=100)
