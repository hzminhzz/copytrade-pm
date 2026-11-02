"""Health is descriptive and must never authorize paper or broker orders."""

from datetime import UTC, datetime, timedelta

import pytest

from copytrade_pm.pm_combo2_health import status

T = datetime(2026, 11, 2, 12, tzinfo=UTC)


def report():
    return {
        "schema": "combo2_rest_account_capture_v1",
        "finished_at": T.isoformat(),
        "account_count": 10,
        "dex_count": 11,
        "all_subjects_captured": True,
        "network_order_mutations": 0,
        "errors": [],
        "subjects": {str(i): {"account_mode": "unifiedAccount"} for i in range(10)},
    }


def test_healthy_source_does_not_authorize_paper_or_live_orders():
    result = status(report(), observed_at=(T + timedelta(seconds=2)).isoformat())
    assert result["source_acquisition_health"] == "HEALTHY"
    assert result["paper_opening_status"] == "BLOCKED_SOURCE_EQUITY_AND_MARKET_ATTESTATION"
    assert result["unattended_paper_service_deployed"] is False
    assert result["live_trading_authorized"] is False
    assert result["account_modes"] == ["unifiedAccount"]


def test_stale_or_incomplete_data_is_never_marked_healthy():
    stale = status(report(), observed_at=(T + timedelta(seconds=902)).isoformat())
    assert stale["source_acquisition_health"] == "STALE"
    incomplete = report()
    incomplete["errors"] = ["PARTIAL_DEX"]
    result = status(incomplete, observed_at=T.isoformat())
    assert result["source_acquisition_health"] == "DEGRADED"


def test_any_reported_order_mutation_fails_health_closed():
    unsafe = report()
    unsafe["network_order_mutations"] = 1
    with pytest.raises(ValueError, match="UNEXPECTED_REMOTE_ORDER_MUTATION"):
        status(unsafe, observed_at=T.isoformat())
