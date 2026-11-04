"""Read-only paper status prevents false worker health."""

from copytrade_pm.pm_forward_journal import PaperJournal
from copytrade_pm.pm_forward_status import paper_operator_status
from test_pm_forward_journal import manifest


def test_missing_worker_does_not_claim_running(tmp_path):
    j = PaperJournal(tmp_path / "paper")
    j.register(manifest("run_1", "acct_1"))
    state = paper_operator_status(j.path, run_id="run_1", as_of="2026-11-04T04:05:00+00:00")
    assert state["health"] == "NOT_RUNNING"
    assert state["order_route"] == "NONE"
    assert state["cursor"] == 0
    assert state["real_worker_evidence"] is False


def test_fresh_transport_and_quiet_wallet_not_disconnect(tmp_path):
    j = PaperJournal(tmp_path / "paper")
    j.register(manifest("run_1", "acct_1"))
    state = paper_operator_status(
        j.path,
        run_id="run_1",
        as_of="2026-11-04T04:05:00+00:00",
        worker_pid=123,
        worker_heartbeat_at="2026-11-04T04:04:55+00:00",
        transport_heartbeat_at="2026-11-04T04:04:55+00:00",
        source_snapshot_at="2026-11-04T04:04:00+00:00",
        market_quote_at="2026-11-04T04:04:55+00:00",
        last_wallet_trade_at="2026-11-02T04:04:55+00:00",
    )
    assert state["health"] == "DEGRADED"
    assert "WORKER_IDENTITY_UNATTESTED" in state["reasons"]
    assert state["real_worker_evidence"] is False
    assert state["quiet_wallet_not_automatic_disconnect"]
    degraded = paper_operator_status(
        j.path,
        run_id="run_1",
        as_of="2026-11-04T04:05:00+00:00",
        worker_pid=123,
        worker_heartbeat_at="2026-11-04T04:04:55+00:00",
        transport_heartbeat_at="2026-11-04T04:00:00+00:00",
    )
    assert degraded["health"] == "DEGRADED"
    assert "TRANSPORT_NOT_HEALTHY" in degraded["reasons"]
