"""Integrated PM-04 policy comparison: identical synthetic events; no broker connection."""

import json
from pathlib import Path
from decimal import Decimal as D

from copytrade_pm.pm03_account import digest
from copytrade_pm.pm03_cli import execute
from copytrade_pm.pm04_compare import compare_pm04_policies
from test_pm04_shadow import SHA, T, engine, event, policy, target
from test_pm03_extended import book


def _external_event(i, kind, input_row, seconds):
    e = event(i, kind, input_row, seconds).to_dict()
    result = {k: v for k, v in e.items() if k != "payload"}
    result["input"] = input_row
    return result


def _spec():
    return {
        "schema": "pm04_compare_input_v1",
        "action": "compare_pm04",
        "mode": "RESEARCH_SYNTHETIC",
        "rulebook": book().to_dict(),
        "policy": policy(max_gross_notional="3000"),
        "started_at": T,
        "pm01_sha": SHA,
        "pm02_sha": SHA,
        "market_manifest_sha": SHA,
        "events": [
            _external_event(
                "rise",
                "PM04_SIGNAL",
                {
                    **engine(60),
                    "targets": [target("W028", 2)],
                },
                60,
            ),
            _external_event("middle", "PM04_TICK", engine(180, mark="110"), 180),
            _external_event("batch", "PM04_TICK", engine(360, mark="110"), 360),
            _external_event(
                "exit",
                "PM04_SIGNAL",
                {
                    **engine(420, mark="115"),
                    "targets": [target("W028", 0, 2, first_known_seconds=420)],
                },
                420,
            ),
        ],
    }


def test_three_pod_policy_comparison_same_inputs_and_sha(tmp_path):
    spec = _spec()
    report = compare_pm04_policies(spec, tmp_path)
    assert report["report_sha"] == digest({k: v for k, v in report.items() if k != "report_sha"})
    assert set(report["comparison"]) == {"immediate", "batched", "asymmetric"}
    immediate = report["comparison"]["immediate"]
    netted = report["comparison"]["batched"]
    assert immediate["account_pnl"] != netted["account_pnl"]
    assert D(immediate["reconciliation_residual"]) == 0
    assert D(netted["reconciliation_residual"]) == 0
    assert all(len(v["equity_curve"]) == 4 for v in report["comparison"].values())
    assert all(v["shadow_only"] for v in report["comparison"].values())
    for scenario in report["comparison"].values():
        assert D(scenario["worst_daily_floor_headroom"]) > 0
        assert D(scenario["worst_contractual_floor_headroom"]) > 0
        assert D(scenario["marked_gross_peak"]) <= D(scenario["gross_limit"])
        assert all("daily_floor_headroom" in row for row in scenario["equity_curve"])
        assert all("conservative_reserved_gross" in row for row in scenario["equity_curve"])
    assert report == compare_pm04_policies(spec, tmp_path)


def test_pm03_cli_accepts_versioned_pm04_compare_without_orders(tmp_path):
    spec = _spec()
    first = execute(spec, tmp_path)
    second = execute(spec, tmp_path)
    assert first == second
    payload = json.loads(Path(first["path"]).read_text(encoding="utf-8"))
    assert payload["no_live_order_path"]
    assert payload["schema"] == "pm04_three_policy_comparison_v1"
    assert payload["comparison"]["asymmetric"]["pending_reductions"] == {}
