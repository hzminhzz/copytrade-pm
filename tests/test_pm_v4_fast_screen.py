"""Black-box v2 fast screen; v1 remains covered in test_pm_offline_job."""

from datetime import UTC, datetime
from hashlib import sha256
import json

import pytest

from copytrade_pm.pm_offline_job import run_offline_job
from copytrade_pm.pm_offline_oracle import _source_digest
from copytrade_pm.pm_offline_manifest import ManifestBlocked
from test_pm_offline_oracle_market import _native_fixture

pytest.importorskip("polars")
START = datetime(2026, 10, 20, tzinfo=UTC)
BTC = "hyperliquid:mainnet:perp:default:BTC"


def prepare(tmp_path, *, missing_k=False, no_exit=False, change_last=False):
    source, market, folder = _native_fixture(tmp_path)
    path = source / "wallet_fills_90d" / "one.json"
    doc = json.loads(path.read_text())
    account = sha256(doc["address"].lower().encode()).hexdigest()
    base = int(START.timestamp() * 1000)
    doc["fills"] = [
        {
            "time": base + 9 * 60000 + 36032,
            "coin": "BTC",
            "tid": 90001,
            "side": "B",
            "px": "109.5",
            "sz": "0.5",
            "startPosition": "0",
        },
        {
            "time": base + 25 * 60000 + 22000,
            "coin": "BTC",
            "tid": 90002,
            "side": "A",
            "px": "125",
            "sz": "0.5",
            "startPosition": "0.5",
        },
    ][: 1 if no_exit else 2]
    path.write_text(json.dumps(doc))
    policy = {
        "schema": "v4_screen_frozen_k_policy_v1",
        "asof": "2026-10-19T00:00:00+00:00",
        "wallets": {}
        if missing_k
        else {
            account: {
                "k": "0.1",
                "known_at": "2026-10-19T00:00:00+00:00",
                "provenance_sha256": "a" * 64,
            }
        },
        "markets": {BTC: {"step": "0.00001", "minimum_notional": "1", "max_notional": "10000"}},
    }
    p = tmp_path / "k.json"
    p.write_text(json.dumps(policy))
    job = {
        "schema": "pm_v4_wallet_screen_job_v2",
        "study_id": "v4-screen-fixture",
        "kind": "V4_HISTORICAL_WALLET_SCREEN",
        "clock_basis": "HISTORICAL_ORACLE",
        "start": "2026-10-20T00:00:00+00:00",
        "end": "2026-10-21T00:00:00+00:00",
        "source_collection_sha256": _source_digest(source),
        "k_policy_path": "k.json",
        "k_policy_sha256": sha256(p.read_bytes()).hexdigest(),
    }
    j = tmp_path / "job.json"
    j.write_text(json.dumps(job))
    return j, source, market


def run(f, source, market, cache):
    return run_offline_job(
        f, input_root=f.parent, source_root=source, market_root=market, cache_root=cache
    )


def test_v2_complete_episode_three_scenarios_and_cache(tmp_path):
    job, source, market = prepare(tmp_path)
    a = run(job, source, market, tmp_path / "cache")
    b = run(job, source, market, tmp_path / "cache")
    assert a["report_sha256"] == b["report_sha256"]
    assert b["report_cache_status"] == "CACHE_HIT"
    assert a["supported_episodes"] == 1
    assert a["estimated_episode_results"] == 3
    wallet = a["wallet_ranking"][0]
    base = wallet["scenarios"]["BASE"]["estimated_net_pnl"]
    delay = wallet["scenarios"]["DELAYED"]["estimated_net_pnl"]
    adverse = wallet["scenarios"]["ADVERSE"]["estimated_net_pnl"]
    assert base is not None and delay is not None and adverse is not None
    assert adverse < base
    assert delay != base
    assert not a["scientifically_qualified"] and a["order_route"] == "NONE"


def test_missing_frozen_k_blocks_economics(tmp_path):
    job, source, market = prepare(tmp_path, missing_k=True)
    a = run(job, source, market, tmp_path / "cache")
    assert a["estimated_episode_results"] == 0
    assert a["wallet_ranking"][0]["scenarios"]["BASE"]["estimated_net_pnl"] is None


def test_source_right_censor_is_not_a_profit(tmp_path):
    job, source, market = prepare(tmp_path, no_exit=True)
    a = run(job, source, market, tmp_path / "cache")
    assert a["estimated_episode_results"] == 0
    assert a["supported_episodes"] == 0
    assert "RIGHT_CENSORED_OR_MULTIPLE_FLATS" in a["source_blockers"]


def test_policy_sha_tamper_fails(tmp_path):
    job, source, market = prepare(tmp_path)
    (tmp_path / "k.json").write_text("{}")
    with pytest.raises(ManifestBlocked, match="V4_FROZEN_K_POLICY_SHA_MISMATCH"):
        run(job, source, market, tmp_path / "cache")


def test_strict_fractional_minute_due_and_exit_observation(tmp_path):
    from copytrade_pm.pm_v4_fast_screen import _source, _episodes
    from copytrade_pm.pm_offline_repository import _clock

    job, source, market = prepare(tmp_path)
    begin = int(_clock("2026-10-20T00:00:00+00:00").timestamp() * 1000)
    frame, errors, total, untrusted = _source(source, begin, begin + 86400000)
    episodes, reasons = _episodes(frame, end_ms=begin + 86400000, untrusted=untrusted)
    account = sha256(
        json.loads((source / "wallet_fills_90d" / "one.json").read_text())["address"].encode()
    ).hexdigest()
    row = episodes.filter(episodes["account"] == account).row(0, named=True)
    assert row["t0"] == begin + 9 * 60000 + 36032
    assert row["base_ms"] == begin + 15 * 60000
    assert row["delayed_ms"] == begin + 16 * 60000
    assert row["exit_ms"] == begin + 26 * 60000


def test_exact_minute_due_still_advances_one_bar(tmp_path):
    from copytrade_pm.pm_v4_fast_screen import _source, _episodes

    job, source, market = prepare(tmp_path)
    p = source / "wallet_fills_90d" / "one.json"
    data = json.loads(p.read_text())
    data["fills"][0]["time"] = int(START.timestamp() * 1000) + 9 * 60000
    p.write_text(json.dumps(data))
    begin = int(START.timestamp() * 1000)
    frame, _, _, untrusted = _source(source, begin, begin + 86400000)
    ep, _ = _episodes(frame, end_ms=begin + 86400000, untrusted=untrusted)
    account = sha256(data["address"].encode()).hexdigest()
    assert ep.filter(ep["account"] == account)["base_ms"][0] == begin + 15 * 60000


def test_known_but_duplicate_source_tid_blocks_all_episodes(tmp_path):
    job, source, market = prepare(tmp_path)
    p = source / "wallet_fills_90d" / "one.json"
    data = json.loads(p.read_text())
    duplicate = dict(data["fills"][0])
    data["fills"].append(duplicate)
    p.write_text(json.dumps(data))
    j = json.loads(job.read_text())
    j["source_collection_sha256"] = _source_digest(source)
    job.write_text(json.dumps(j))
    result = run(job, source, market, tmp_path / "cache")
    assert result["estimated_episode_results"] == 0
    assert result["source_blockers"]["SOURCE_CHAIN_UNTRUSTED"] == 1
    assert result["source_blockers"]["UNTRUSTED_SOURCE_CHAIN"] == 1


def test_capacity_veto_does_not_create_fill(tmp_path):
    import polars as pl

    job, source, market = prepare(tmp_path)
    original = next(market.rglob("data.parquet"))
    panel = pl.read_parquet(original).with_columns(
        pl.when(pl.col("timestamp") == START + pl.duration(minutes=14))
        .then(0)
        .otherwise(pl.col("volume"))
        .alias("volume")
    )
    panel.write_parquet(original)
    sidecar = original.parent / "source.json"
    metadata = json.loads(sidecar.read_text())
    metadata["sha256"] = sha256(original.read_bytes()).hexdigest()
    sidecar.write_text(json.dumps(metadata))
    result = run(job, source, market, tmp_path / "cache")
    assert result["economic_outcomes"]["ZERO_PRIOR_VOLUME"] >= 1
    assert result["estimated_episode_results"] < 3


def test_shortlist_only_completed_base_passes_stage_two(tmp_path):
    from copytrade_pm.pm_v4_fast_screen import shortlist_for_pm03

    job, source, market = prepare(tmp_path)
    result = run(job, source, market, tmp_path / "cache")
    wallet = result["wallet_ranking"][0]["account_sha256"]
    handoff = shortlist_for_pm03(result, [wallet])
    assert handoff["wallet_sha256s"] == [wallet]
    assert handoff["research_only"] and handoff["no_order_route"]
    assert handoff["screen_report_sha256"] == result["report_sha256"]
    (tmp_path / "blocked").mkdir()
    job2, source2, market2 = prepare(tmp_path / "blocked", missing_k=True)
    blocked = run(job2, source2, market2, tmp_path / "blocked_cache")
    with pytest.raises(ManifestBlocked, match="V4_SHORTLIST_MISSING_COMPLETED_BASE_ECONOMICS"):
        shortlist_for_pm03(blocked, [blocked["wallet_ranking"][0]["account_sha256"]])


def test_multiple_entry_changes_coalesce_without_clock_reset(tmp_path):
    from copytrade_pm.pm_v4_fast_screen import _source, _episodes

    job, source, market = prepare(tmp_path)
    p = source / "wallet_fills_90d" / "one.json"
    doc = json.loads(p.read_text())
    start = doc["fills"][0]
    extra = dict(start, tid=90003, time=start["time"] + 30000, startPosition="0.5", sz="0.25")
    doc["fills"][1]["startPosition"] = "0.75"
    doc["fills"][1]["sz"] = "0.75"
    doc["fills"].insert(1, extra)
    p.write_text(json.dumps(doc))
    begin = int(START.timestamp() * 1000)
    frame, _, _, untrusted = _source(source, begin, begin + 86400000)
    ep, _ = _episodes(frame, end_ms=begin + 86400000, untrusted=untrusted)
    account = sha256(doc["address"].encode()).hexdigest()
    row = ep.filter(ep["account"] == account).row(0, named=True)
    assert row["source_status"] == "SUPPORTED_EPISODE"
    assert row["target_base"] == 0.75
    assert row["t0"] == start["time"]


def test_new_job_does_not_change_v1_job_hash(tmp_path):
    from test_pm_offline_job import _oracle_job

    old, source, market = _oracle_job(tmp_path)
    original = run(old, source, market, tmp_path / "old_cache")
    assert original["schema"] == "pm_offline_research_job_report_v1"
    assert original["policy"] == "PER_FILL_ELIGIBILITY"
    assert original["delays_minutes"] == [0, 1, 2, 5, 10]


@pytest.mark.parametrize("short", [False, True])
def test_adverse_worsens_long_and_short_after_both_side_costs(tmp_path, short):
    job, source, market = prepare(tmp_path)
    if short:
        file = source / "wallet_fills_90d" / "one.json"
        doc = json.loads(file.read_text())
        doc["fills"][0]["side"] = "A"
        doc["fills"][1]["side"] = "B"
        doc["fills"][1]["startPosition"] = "-0.5"
        file.write_text(json.dumps(doc))
        manifest = json.loads(job.read_text())
        manifest["source_collection_sha256"] = _source_digest(source)
        job.write_text(json.dumps(manifest))
    report = run(job, source, market, tmp_path / "cache")
    account = sha256(
        json.loads((source / "wallet_fills_90d" / "one.json").read_text())["address"].encode()
    ).hexdigest()
    wallet = next(row for row in report["wallet_ranking"] if row["account_sha256"] == account)
    assert (
        wallet["scenarios"]["ADVERSE"]["estimated_net_pnl"]
        < wallet["scenarios"]["BASE"]["estimated_net_pnl"]
    )


def test_source_opening_not_flat_blocks_without_inventing_position(tmp_path):
    job, source, market = prepare(tmp_path)
    path = source / "wallet_fills_90d" / "one.json"
    doc = json.loads(path.read_text())
    doc["fills"][0]["startPosition"] = "1.0"
    path.write_text(json.dumps(doc))
    manifest = json.loads(job.read_text())
    manifest["source_collection_sha256"] = _source_digest(source)
    job.write_text(json.dumps(manifest))
    report = run(job, source, market, tmp_path / "cache")
    assert report["source_blockers"]["UNKNOWN_OPENING_POSITION"] >= 1


def test_wrong_market_identity_never_maps_to_default_dex(tmp_path):
    job, source, market = prepare(tmp_path)
    path = source / "wallet_fills_90d" / "one.json"
    doc = json.loads(path.read_text())
    for fill in doc["fills"]:
        fill["coin"] = "xyz:BTC"
    path.write_text(json.dumps(doc))
    manifest = json.loads(job.read_text())
    manifest["source_collection_sha256"] = _source_digest(source)
    job.write_text(json.dumps(manifest))
    result = run(job, source, market, tmp_path / "cache")
    assert result["estimated_episode_results"] == 0
    assert result["market_action_coverage"] is not None


def test_realistic_fee_stack_once_per_side_and_exact_1m_open(tmp_path):
    from copytrade_pm.pm_v4_fast_screen import (
        _source,
        _episodes,
        _actions,
        _join_actions,
        _economics,
        _policy,
    )

    job, source, market = prepare(tmp_path)
    manifest = json.loads(job.read_text())
    policy, _ = _policy(tmp_path, manifest)
    begin = int(START.timestamp() * 1000)
    frame, _, _, untrusted = _source(source, begin, begin + 86400000)
    episodes, _ = _episodes(frame, end_ms=begin + 86400000, untrusted=untrusted)
    account = sha256(
        json.loads((source / "wallet_fills_90d" / "one.json").read_text())["address"].encode()
    ).hexdigest()
    episodes = episodes.filter(episodes["account"] == account)
    matched, _, _ = _join_actions(_actions(episodes), market)
    economics = _economics(matched, policy, scenarios=("BASE", "ADVERSE"))
    base = economics.filter(economics["scenario"] == "BASE").row(0, named=True)
    adverse = economics.filter(economics["scenario"] == "ADVERSE").row(0, named=True)
    assert base["legs"] == 2
    assert base["both_filled"] is True
    assert base["fees"] > 0
    assert adverse["fees"] > 0
    assert adverse["estimated_net_pnl"] < base["estimated_net_pnl"]
    # A 10bps adverse execution on entry+exit cannot improve follower PnL.
    assert base["estimated_net_pnl"] - adverse["estimated_net_pnl"] > 0.01


def test_source_sha_tamper_fails_closed(tmp_path):
    job, source, market = prepare(tmp_path)
    p = source / "wallet_fills_90d" / "one.json"
    p.write_text(p.read_text() + " ")
    with pytest.raises(ManifestBlocked, match="V4_SOURCE_COLLECTION_SHA_MISMATCH"):
        run(job, source, market, tmp_path / "cache")


def test_streaming_and_memory_economics_are_deterministic(tmp_path):
    from copytrade_pm.pm_v4_fast_screen import (
        _source,
        _episodes,
        _actions,
        _join_actions,
        _economics,
        _policy,
    )
    from copytrade_pm.pm_offline_oracle import _json_bytes

    job, source, market = prepare(tmp_path)
    policy, _ = _policy(tmp_path, json.loads(job.read_text()))
    begin = int(START.timestamp() * 1000)
    events, _, _, bad = _source(source, begin, begin + 86400000)
    episodes, _ = _episodes(events, end_ms=begin + 86400000, untrusted=bad)
    matched, _, _ = _join_actions(
        _actions(episodes.filter(episodes["source_status"] == "SUPPORTED_EPISODE")), market
    )
    a = _economics(matched, policy, scenarios=("BASE", "DELAYED", "ADVERSE"), engine="streaming")
    b = _economics(matched, policy, scenarios=("BASE", "DELAYED", "ADVERSE"), engine="in-memory")
    assert a.to_dicts() == b.to_dicts()
    assert (
        sha256(_json_bytes({"rows": a.to_dicts()})).hexdigest()
        == sha256(_json_bytes({"rows": b.to_dicts()})).hexdigest()
    )


def test_one_fee_per_executed_side_matches_independent_formula(tmp_path):
    from math import floor
    from copytrade_pm.pm_v4_fast_screen import (
        _source,
        _episodes,
        _actions,
        _join_actions,
        _economics,
        _policy,
    )

    job, source, market = prepare(tmp_path)
    policy, _ = _policy(tmp_path, json.loads(job.read_text()))
    begin = int(START.timestamp() * 1000)
    events, _, _, bad = _source(source, begin, begin + 86400000)
    episodes, _ = _episodes(events, end_ms=begin + 86400000, untrusted=bad)
    account = sha256(
        json.loads((source / "wallet_fills_90d" / "one.json").read_text())["address"].encode()
    ).hexdigest()
    subset = episodes.filter(episodes["account"] == account)
    matched, _, _ = _join_actions(_actions(subset), market)
    result = _economics(matched, policy, scenarios=("BASE",))
    row = result.row(0, named=True)
    q = floor((0.5 * 0.1 * 109.5 / 115) / 0.00001) * 0.00001
    assert q > 0
    entry_vwap = 115 * (1 + (4 + 8 + 10 * (q / 114) / 0.1) / 10000)
    exit_vwap = 126 * (1 - (4 + 8 + 10 * (q / 125) / 0.1) / 10000)
    expected_fees = q * (entry_vwap + exit_vwap) * 0.0005
    expected_pnl = q * (exit_vwap - entry_vwap) - expected_fees
    assert row["fees"] == pytest.approx(expected_fees, abs=1e-8)
    assert row["estimated_net_pnl"] == pytest.approx(expected_pnl, abs=1e-8)


def test_native_fixed_k_quantity_matches_v4_pure_sizing():
    from decimal import Decimal as D
    from copytrade_pm.pm_exposure_sizing import target_from_fixed_k
    from copytrade_pm.pm_v4_fast_screen import v4_instrument_key

    v4_btc = v4_instrument_key(BTC)
    assert v4_btc == "hyperliquid/mainnet:perp:default/BTC"
    result = target_from_fixed_k(
        source_quantities={v4_btc: D("0.5")},
        k=D("0.1"),
        source_marks={v4_btc: D("109.5")},
        follower_marks={v4_btc: D("115")},
        follower_equity_usd=D("10000"),
        max_gross_notional_usd=D("10000"),
        max_market_notional_usd=D("10000"),
        pod_loss_budget_usd=D("200"),
    )
    expected = D("0.5") * D("0.1") * D("109.5") / D("115")
    assert result["sizing_policy"] == "FIXED_K_NATIVE_QUANTITY"
    assert D(result["target_quantities"][v4_btc]) == expected
    assert not result["trading_authorized"]


def test_shortlist_rejects_tampered_report_even_if_base_is_eligible(tmp_path):
    from copytrade_pm.pm_v4_fast_screen import shortlist_for_pm03

    job, source, market = prepare(tmp_path)
    report = run(job, source, market, tmp_path / "cache")
    wallet = report["eligible_shortlist_wallets"][0]
    report["wallet_ranking"][0]["scenarios"]["BASE"]["estimated_net_pnl"] = 1234567
    with pytest.raises(ManifestBlocked, match="V4_SHORTLIST_REPORT_HASH_MISMATCH"):
        shortlist_for_pm03(report, [wallet])


def test_documented_p1_live_due_is_not_forced_to_equal_candle_open():
    from copytrade_pm.pm_v4_fast_screen import MINUTE

    due = datetime(2026, 11, 9, 10, 14, 38, 250828, tzinfo=UTC)
    receipt = due.timestamp() * 1000 - 300000
    assert receipt + 300000 == pytest.approx(due.timestamp() * 1000)
    historical_base = (int(due.timestamp() * 1000) // MINUTE + 1) * MINUTE
    expected = datetime(2026, 11, 9, 10, 15, tzinfo=UTC)
    assert historical_base == int(expected.timestamp() * 1000)
    assert historical_base > int(due.timestamp() * 1000)


def test_v2_scales_past_frozen_v1_source_file_cap_without_loosening_v1(tmp_path):
    from copytrade_pm.pm_v4_fast_screen import _v2_source_digest
    from copytrade_pm.pm_offline_repository import _source_files

    job, source, market = prepare(tmp_path)
    for idx in range(251):
        address = "0x" + f"{idx + 1000:040x}"
        path = source / "wallet_fills_90d" / f"expanded-{idx:04d}.json"
        path.write_text(json.dumps({"address": address, "fills": []}))
    with pytest.raises(ManifestBlocked, match="TOO_MANY_SOURCE_FILES"):
        _source_files(source)
    manifest = json.loads(job.read_text())
    manifest["source_collection_sha256"] = _v2_source_digest(source)
    job.write_text(json.dumps(manifest))
    output = run(job, source, market, tmp_path / "cache")
    assert output["source_accounts"] == 254
    assert output["estimated_episode_results"] == 3
