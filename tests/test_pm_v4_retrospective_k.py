"""Vike retrospective k is explicitly derived now from prewindow-only inputs.

These tests are *not* claims of historical release authority or prospective
follower profitability.
"""

from __future__ import annotations

from decimal import Decimal
from hashlib import sha256
import json

import pytest

from copytrade_pm.pm_offline_job import run_offline_job
from copytrade_pm.pm_offline_manifest import ManifestBlocked
from copytrade_pm.pm_v4_fast_screen import (
    RETRO_MODEL,
    RETRO_REPORT,
    RETRO_SCHEMA,
    _retro_policy,
)
from scripts.research_vike_prewindow_k import build
from test_pm_v4_fast_screen import BTC, prepare


def fixture_retro(tmp_path):
    jobfile, source, market = prepare(tmp_path)
    job = json.loads(jobfile.read_bytes())
    record = json.loads((tmp_path / "k.json").read_bytes())
    account = next(iter(record["wallets"]))
    maximum = Decimal("5000")
    ratio = Decimal("200") / (Decimal("0.2") * maximum)
    retro = {
        "schema": "v4_screen_retrospective_k_policy_v1",
        "training_start": "2026-07-01T00:00:00+00:00",
        "training_end": "2026-10-20T00:00:00+00:00",
        "generated_at": "2026-11-10T02:00:00+00:00",
        "model": RETRO_MODEL,
        "vike_training_aggregates_sha256": "b" * 64,
        "wallets": {
            account: {
                "k": str(ratio),
                "max_observed_gross_usd": str(maximum),
                "observation_days": 35,
                "snapshots": 500,
                "first_observed_at": "2026-07-01T00:00:00+00:00",
                "last_observed_at": "2026-10-19T23:00:00+00:00",
                "evidence_sha256": "c" * 64,
            }
        },
        "markets": {BTC: {"step": "0.00001", "minimum_notional": "1", "max_notional": "10000"}},
    }
    policyfile = tmp_path / "retro_policy.json"
    policyfile.write_text(json.dumps(retro))
    job.update(
        schema=RETRO_SCHEMA,
        kind="V4_RETROSPECTIVE_TRAINED_K_SCREEN",
        k_policy_path=policyfile.name,
        k_policy_sha256=sha256(policyfile.read_bytes()).hexdigest(),
    )
    jobfile.write_text(json.dumps(job))
    return jobfile, source, market, retro


def test_retro_screen_runs_three_scenarios_without_historical_release_claim(tmp_path):
    job, source, market, policy = fixture_retro(tmp_path)
    kw = dict(
        input_root=tmp_path, source_root=source, market_root=market, cache_root=tmp_path / "cache"
    )
    first = run_offline_job(job, **kw)
    again = run_offline_job(job, **kw)
    assert first["schema"] == RETRO_REPORT
    assert first["estimated_episode_results"] == 3
    assert first["k_provenance_class"] == "COMPUTED_AFTER_OOS_FROM_PREWINDOW_VIKE_DATA"
    assert first["historical_signed_k_release_claimed"] is False
    assert first["market_rules"] == "RESEARCH_PROXY_NOT_ASOF_EXCHANGE_PRECISION"
    assert first["order_route"] == "NONE"
    assert first["scientifically_qualified"] is False
    assert first["report_sha256"] == again["report_sha256"]
    assert again["report_cache_status"] == "CACHE_HIT"


@pytest.mark.parametrize(
    ("field", "value", "expected"),
    [
        ("training_end", "2026-10-21T00:00:00+00:00", "RETRO_TRAINING_OVERLAPS_EVALUATION"),
        ("generated_at", "2026-10-19T00:00:00+00:00", "RETRO_CALIBRATION_CREATION_MISLABELED"),
    ],
)
def test_retro_refuses_leakage_or_forged_early_release(tmp_path, field, value, expected):
    job, source, market, policy = fixture_retro(tmp_path)
    policy[field] = value
    with pytest.raises(ManifestBlocked, match=expected):
        _retro_policy(policy, json.loads(job.read_text()))


def test_retro_refuses_future_vike_position_snapshots(tmp_path):
    job, _, _, policy = fixture_retro(tmp_path)
    wallet = next(iter(policy["wallets"].values()))
    wallet["last_observed_at"] = "2026-10-20T00:00:00+00:00"
    with pytest.raises(ManifestBlocked, match="RETRO_TRAINING_TIMESTAMP_LEAKAGE"):
        _retro_policy(policy, json.loads(job.read_text()))


def test_retro_refuses_k_tuned_after_training(tmp_path):
    job, _, _, policy = fixture_retro(tmp_path)
    wallet = next(iter(policy["wallets"].values()))
    wallet["k"] = "0.4"
    with pytest.raises(ManifestBlocked, match="RETRO_K_NOT_PRESPECIFIED_RISK_FUNCTION"):
        _retro_policy(policy, json.loads(job.read_text()))


def test_retro_refuses_invalid_evidence_or_model(tmp_path):
    job, _, _, policy = fixture_retro(tmp_path)
    wallet = next(iter(policy["wallets"].values()))
    wallet["observation_days"] = 0
    with pytest.raises(ManifestBlocked, match="RETRO_TRAINING_EVIDENCE_INSUFFICIENT"):
        _retro_policy(policy, json.loads(job.read_text()))
    wallet["observation_days"] = 35
    policy["model"] = {**RETRO_MODEL, "risk_budget_usd": "500"}
    with pytest.raises(ValueError, match="INVALID_V4_RETROSPECTIVE_RISK_MODEL"):
        _retro_policy(policy, json.loads(job.read_text()))


def test_builder_partial_and_missing_vike_are_not_dollar_pnl(tmp_path):
    job, source, market = prepare(tmp_path)
    records = []
    for folder in (
        "wallet_fills_90d",
        "broader_active_inventory_fills_90d",
        "nansen_smart_money_fills_90d",
    ):
        for path in (source / folder).glob("*.json"):
            address = json.loads(path.read_text())["address"].lower()
            records.append(
                {
                    "sha": sha256(address.encode()).hexdigest(),
                    "max_usd": 5000,
                    "rows": 24,
                    "snapshots": 24,
                    "days": 7,
                    "invalid": 0,
                    "first_ts": "2026-07-01T00:00:00+00:00",
                    "last_ts": "2026-07-07T23:00:00+00:00",
                    "more": False,
                }
            )
    evidence = tmp_path / "evidence"
    evidence.mkdir()
    records[1]["more"] = True
    records[1]["cursor"] = "partial"
    records[2]["max_usd"] = 0
    records[2]["days"] = 0
    for i in range(16):
        payload = {
            "schema": "vike_prewindow_exposure_aggregate_v1",
            "results": [records[i]] if i < 3 else [],
        }
        (evidence / f"vike-prewindow-1011-batch{i:02d}.json").write_text(json.dumps(payload))
    destination = tmp_path / "private"
    result = build(
        evidence_dir=evidence,
        source_root=source,
        output_root=destination,
        generated_at="2026-11-10T02:00:00+00:00",
    )
    assert result["source_wallets"] == 3
    assert result["with_k"] == 1
    assert result["blocked"]["INCOMPLETE_VIKE_PAGINATION"] == 1
    assert result["blocked"]["INSUFFICIENT_PREWINDOW_OBSERVATION"] == 1
    policy = json.loads(next(destination.glob("retro-vike-k-policy-*.json")).read_text())
    assert len(policy["wallets"]) == 1
    k = Decimal(next(iter(policy["wallets"].values()))["k"])
    assert k == Decimal("0.2")
    assert policy["generated_at"].startswith("2026-11")
    assert policy["schema"] == "v4_screen_retrospective_k_policy_v1"
    assert len(policy["markets"]) == 1
    again = build(
        evidence_dir=evidence,
        source_root=source,
        output_root=destination,
        generated_at="2026-11-10T02:00:00+00:00",
    )
    assert result["receipt_sha256"] == again["receipt_sha256"]
