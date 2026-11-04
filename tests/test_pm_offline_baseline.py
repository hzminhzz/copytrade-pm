"""Regression checks for the frozen PM-01 baseline instrumentation."""

from copytrade_pm.pm_offline_baseline import SCHEMA, benchmark, _payload


def test_reference_fixture_is_repeatable_and_read_only():
    assert _payload(120) == _payload(120)
    report = benchmark(count=120, iterations=2)
    assert report["schema"] == SCHEMA
    assert report["source_fill_count"] == 120
    assert report["clock_basis"] == "HISTORICAL_ORACLE"
    assert report["synthetic_market"] is True
    assert len({row["result_sha256"] for row in report["samples"]}) == 1
    assert all(row["status"] == "HISTORICAL_HINDSIGHT_SIMULATION_ONLY" for row in report["samples"])


def test_reference_rejects_unbounded_workload():
    import pytest

    with pytest.raises(ValueError, match="FIXTURE_COUNT_OUT_OF_BOUNDS"):
        benchmark(count=1001)
    with pytest.raises(ValueError, match="ITERATIONS_OUT_OF_BOUNDS"):
        benchmark(iterations=11)
