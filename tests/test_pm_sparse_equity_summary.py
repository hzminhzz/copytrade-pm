"""No fabricated ranks, missing cohorts or mutable lineage in Q3 summary."""

from hashlib import sha256
import json

import pytest

from copytrade_pm.pm_sparse_equity_portfolio import SCHEMA
from copytrade_pm.pm_sparse_equity_summary import aggregate


def write_report(root, doc):
    content = json.dumps(doc, sort_keys=True).encode()
    digest = sha256(content).hexdigest()
    path = root / f"pm01-36-wallets-{digest[:20]}.json"
    path.write_bytes(content)
    return path


def row(name, scenario):
    return {
        "name": name,
        "wallets": ["W028", "W030", "W042"],
        "scenario": scenario,
        "status": "PARTIAL_CONDITIONAL_REPLAY",
        "stop_reason": "SIMULATED_STAGE_TARGET_REACHED",
        "pnl_usd": "1000",
        "max_observed_drawdown_usd": "100",
        "counters": {"hypothetical_net_orders": 3},
        "action_weighted_exposure_tracking": {
            "W028": {"action_weighted_tracking_error_fraction": "0"}
        },
        "equity_sizing": {
            "W028": {"counters": {"skipped_sizing_decisions_SOURCE_EQUITY_TOO_OLD": 2}}
        },
    }


def document(rows):
    return {
        "schema": SCHEMA,
        "results": rows,
        "source_fill_manifests": {"f": "a" * 64},
        "source_account_raw_sha256": {"W028": "b" * 64},
        "propr_browser_scope_sha256": "c" * 64,
        "risk_caps_usd": {"pod_gross": "6000"},
        "execution": {"max_stale_mark_minutes": 180},
        "portfolio_membership": {"A": ["W028", "W042", "W030"]},
        "source_window_inclusive_start": "2026-07-01T00:00:00+00:00",
        "source_window_exclusive_end": "2026-10-01T00:00:00+00:00",
        "study_days": 92,
        "account_initial_usd": "10000",
        "pod_capital_usd": "2000",
        "source_account_nav_audit": {
            "W028": {"q3_points": 14, "q3_max_gap_hours_between_samples": 170},
        },
        "source_episode_eligibility": {"W028": {"admitted": 50}},
        "mixed_batch": {"only_mixed": False, "offset": 0},
    }


def evidence(tmp_path):
    labels = (
        "BASE_8D_1X",
        "NAV_16D_1X",
        "COST_8D_2X",
        "CAPACITY_8D_1X",
    )
    base = document([row(port, mode) for port in ("A", "B", "C") for mode in labels])
    basepath = write_report(tmp_path, base)
    mixed = []
    for offset in range(0, 81, 12):
        count = min(12, 81 - offset)
        doc = document([row("MIX_" + str(k), labels[0]) for k in range(offset, offset + count)])
        doc["mixed_batch"] = {
            "only_mixed": True,
            "offset": offset,
            "total_mixed_available": 81,
            "executed_mixed_count": count,
        }
        mixed.append(write_report(tmp_path, doc))
    selected = []
    for i in range(3):
        doc = document([row("CUSTOM_" + str(i), mode) for mode in labels])
        doc["custom_trio"] = [f"W{i}", f"W{i + 1}", f"W{i + 2}"]
        for rec in doc["results"]:
            rec["name"] = "CUSTOM_" + "_".join(doc["custom_trio"])
        selected.append(write_report(tmp_path, doc))
    return basepath, tuple(mixed), tuple(selected)


def test_correctly_complete_84_report_cannot_promote_toy_success(tmp_path):
    base, mixed, custom = evidence(tmp_path)
    summary = aggregate(base, mixed, custom)
    assert summary["total_unique_3wallet_combinations"] == 84
    assert summary["historical_base_outcome_counts"] == {
        "SIMULATED_STAGE_TARGET_REACHED": 84,
    }
    assert len(summary["all_84_baseline_outcomes"]) == 84
    assert len(summary["post_selected_custom_sensitivity"]) == 3
    assert summary["status_assessment"]["valid_best_wallet_combo"] is None
    assert summary["status_assessment"]["qualification"] is False
    assert summary["status_assessment"]["trading_authorized"] is False
    assert summary["all_84_baseline_outcomes"][0]["source_equity_skipped_decisions"]["W028"] == 2


def test_provenance_content_tampering_is_rejected(tmp_path):
    base, mixed, custom = evidence(tmp_path)
    path = mixed[0]
    old = json.loads(path.read_text())
    old["source_account_raw_sha256"]["W028"] = "0" * 64
    path.write_text(json.dumps(old, sort_keys=True))
    with pytest.raises(ValueError, match="REPLAY_REPORT_CONTENT_SHA_INVALID"):
        aggregate(base, mixed, custom)


def test_missing_or_duplicated_mixed_batch_rejected(tmp_path):
    base, mixed, custom = evidence(tmp_path)
    with pytest.raises(ValueError, match="EXPECTED_7_BATCHES"):
        aggregate(base, mixed[:-1], custom)
    with pytest.raises(ValueError, match="INVALID_MIXED_BATCH_INDEX"):
        aggregate(base, (mixed[0],) * 7, custom)


def test_unchanged_sha_but_different_policy_rejected(tmp_path):
    base, mixed, custom = evidence(tmp_path)
    modified = document([row("MIX_0", "BASE_8D_1X")])
    modified["risk_caps_usd"] = {"pod_gross": "1"}
    modified["mixed_batch"] = {
        "only_mixed": True,
        "offset": 0,
        "total_mixed_available": 81,
        "executed_mixed_count": 1,
    }
    changed = write_report(tmp_path, modified)
    with pytest.raises(ValueError, match="MIXED_SOURCE_EVIDENCE_MISMATCH"):
        aggregate(base, (changed,) + mixed[1:], custom)
