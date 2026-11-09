"""Original financial restrictions survive later diagnostics and UTC reset."""

from datetime import UTC, datetime, timedelta

import pytest

from copytrade_pm.pm_forward_journal import PaperJournal
from copytrade_pm.pm_forward_protected_ops import watchdog_cycle, worker_cycle
from test_pm_forward_funding import _filled
from test_pm_forward_observed_paper import BTC
from test_pm_forward_protected_ops import REV, standby_two


@pytest.mark.parametrize(
    "diagnostic",
    [
        {"kind": "MARK", "state_known": False},
        {"kind": "HALT", "reason": "LATER_OPERATIONAL_FAILURE"},
    ],
)
def test_original_halt_reason_survives_diagnostic_midnight_and_restart(tmp_path, diagnostic):
    _, journal = _filled(tmp_path)
    halted = journal.append(
        "run_1",
        "financial-halt",
        {
            "kind": "HALT",
            "reason": "ORIGINAL_LOSS_RESTRICTION",
            "event_at": "2026-11-04T23:59:00+00:00",
        },
    )
    after = journal.append(
        "run_1",
        "diagnostic",
        {
            **diagnostic,
            "event_at": "2026-11-04T23:59:30+00:00",
        },
    )
    assert after["account"]["halt_reason"] == "ORIGINAL_LOSS_RESTRICTION"
    marked = journal.append(
        "run_1",
        "midnight",
        {
            "kind": "MARK",
            "state_known": True,
            "prices": {BTC.key: "100"},
            "event_at": "2026-11-05T00:00:01+00:00",
        },
    )
    assert marked["account"]["daily_key"] != halted["account"]["daily_key"]
    assert marked["account"]["risk"] == "HALT"
    assert marked["account"]["halt_reason"] == "ORIGINAL_LOSS_RESTRICTION"
    assert marked["account"]["quantities"] == halted["account"]["quantities"]
    assert PaperJournal(journal.root).restore("run_1") == marked


def test_standby_recovery_across_utc_midnight_keeps_existing_halt_and_no_finance(tmp_path):
    guard, roots, now = standby_two(tmp_path)
    first = datetime.fromisoformat(now)
    stale = (first + timedelta(seconds=91)).isoformat()
    args = dict(
        watchdog_root=guard, worker_roots=roots, revision=REV, release=tmp_path, strict=False
    )
    assert watchdog_cycle(**args, as_of=stale)["status"] == "HALT_LATCHED"
    original = (guard / "halt-latch.json").read_bytes()
    tomorrow = (
        (first + timedelta(days=2))
        .astimezone(UTC)
        .replace(
            hour=0,
            minute=0,
            second=1,
            microsecond=0,
        )
        .isoformat()
    )
    for portfolio, root in roots.items():
        worker_cycle(
            portfolio=portfolio,
            root=root,
            revision=REV,
            release=tmp_path,
            strict=False,
            as_of=tomorrow,
        )
    restored = watchdog_cycle(**args, as_of=tomorrow)
    assert restored["status"] == "HALT_LATCHED"
    assert restored["manual_reset_required"] is True
    assert restored["paper_running"] is False
    assert all(w["status"] == "ALIVE_STANDBY_ONLY" for w in restored["workers"].values())
    assert (guard / "halt-latch.json").read_bytes() == original
    assert not list(tmp_path.rglob("*.sqlite*"))
