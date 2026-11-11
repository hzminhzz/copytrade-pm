from copytrade_pm.pm_checkpoint_capacity import summarize
from copytrade_pm.pm_forward_journal import PaperJournal
from test_checkpoint_journal import sample
from test_checkpoint_source import BOUNDARY


def test_measurement_separates_observed_completeness_from_policy_qualification(tmp_path):
    journal = PaperJournal(tmp_path / "capture")
    complete = sample(journal, BOUNDARY)
    failed = sample(journal, BOUNDARY + 300_000, fail=True)
    result = summarize(
        [complete, failed],
        expected_accounts=2,
        revision="a" * 40,
        requests=[
            {"weight": 2, "requested_ms": BOUNDARY, "received_ms": BOUNDARY + 90, "error": None}
        ],
        roster_sha="b" * 64,
        rate_weight_per_second=8,
        mode="fixture",
    )
    assert result["complete_scope_count"] == 1
    assert result["expected_accounts"] == 2
    assert result["observed"]["request_latency_ms"]["max"] == 90
    assert result["observed"]["acquisition_ms"]["max"] == 0
    assert result["disposition"] == "UNKNOWN"
    assert result["trading_authorized"] is False
    assert result["shared_ip_headroom"] == "UNKNOWN"
    assert all(value["qualified"] is False for value in result["dimensions"].values())


def test_zero_capture_is_not_capacity_success():
    result = summarize(
        [],
        expected_accounts=14,
        revision="a" * 40,
        requests=[],
        roster_sha="b" * 64,
        rate_weight_per_second=8,
        mode="fixture",
    )
    assert result["complete_scope_count"] == 0
    assert result["observed"]["request_latency_ms"] is None
    assert result["disposition"] == "NO_GO"
