"""E4 continuous forward receiver changes, heartbeats and identity."""

from datetime import UTC, datetime, timedelta

from copytrade_pm.pm_e4_stream import capture_book_change


def test_first_seen_is_snapshot_not_a_trade():
    t = datetime(2026, 10, 31, tzinfo=UTC)
    state = {}
    changed, checkpoint = capture_book_change(
        subject="CO-001",
        positions={"btc": "1"},
        observed_at=t,
        last=state,
        sample_seconds=300,
    )
    assert (changed, checkpoint) == (False, True)


def test_same_positions_are_sampled_not_written_every_block():
    t = datetime(2026, 10, 31, tzinfo=UTC)
    state = {}
    capture_book_change(
        subject="CO-001",
        positions={"btc": "1"},
        observed_at=t,
        last=state,
        sample_seconds=300,
    )
    assert capture_book_change(
        subject="CO-001",
        positions={"btc": "1"},
        observed_at=t + timedelta(seconds=30),
        last=state,
        sample_seconds=300,
    ) == (False, False)
    assert capture_book_change(
        subject="CO-001",
        positions={"btc": "1"},
        observed_at=t + timedelta(seconds=300),
        last=state,
        sample_seconds=300,
    ) == (False, True)


def test_signed_change_is_not_delayed_by_checkpoint_clock():
    t = datetime(2026, 10, 31, tzinfo=UTC)
    state = {}
    capture_book_change(
        subject="CO-001",
        positions={"btc": "1"},
        observed_at=t,
        last=state,
        sample_seconds=300,
    )
    assert capture_book_change(
        subject="CO-001",
        positions={"btc": "-1"},
        observed_at=t + timedelta(seconds=1),
        last=state,
        sample_seconds=300,
    ) == (True, False)
    assert capture_book_change(
        subject="W015",
        positions={"btc": "1"},
        observed_at=t + timedelta(seconds=2),
        last=state,
        sample_seconds=300,
    ) == (False, True)
