"""Summary consolidation must reject corrupted, duplicate, or mismatched research inputs."""
from decimal import Decimal as D
from pathlib import Path

import pytest

from copytrade_pm.pm_hl94_research import REPLAY_SCHEMA, SCHEMA, write_evidence
from copytrade_pm.pm_hl94_summary import consolidate, SUMMARY_SCHEMA


def _fixture(tmp_path: Path):
    screen = {
        "schema": SCHEMA, "source_file_sha256": {"f.json": "abc"},
        "raw_wallet_count": 3, "shortlist": ["A", "B", "C"],
        "all_discovery_triples_screened": 1,
        "top_10_candidate_triples": [{"wallets": ["A", "B", "C"]}],
        "frozen_validation_triples": [{"wallets": ["A", "B", "C"]}],
    }
    screen_path, sha = write_evidence(tmp_path, screen)
    first = {"phase": "DISCOVERY", "wallets": ["A", "B", "C"],
             "pnl_usd": "5", "observed_through": "2026-09-30T00:00:00+00:00"}
    second = {"phase": "VALIDATION", "wallets": ["A", "B", "C"],
              "pnl_usd": "-2", "max_observed_drawdown_usd": "3",
              "stop_reason": "UNCLOSED_FOLLOWER_BOOK_AT_Q3_END",
              "observed_through": "2026-10-30T00:00:00+00:00"}
    replay = {
        "schema": REPLAY_SCHEMA,
        "screening_source_sha256": sha,
        "risk_scale": "0.5", "delay_minutes": 5,
        "cost_multiplier": "1", "capacity_enforced": False,
        "pod_hard_stop_usd": "200", "results": [first, second],
    }
    replay_path, _ = write_evidence(tmp_path, replay)
    return screen_path, replay_path


def test_summary_descriptive_not_qualified(tmp_path):
    screen, replay = _fixture(tmp_path)
    result = consolidate(screen, (replay,))
    assert result["schema"] == SUMMARY_SCHEMA
    assert result["replayed_portfolios"] == 1
    assert result["ranking"][0]["validation_pnl_usd_at_stop_or_end"] == "-2"
    assert result["ranking"][0]["not_comparable_to_full_period_pnl"] is True
    assert result["scientifically_qualified"] is False
    assert result["live_trading_authorized"] is False
    assert D(result["ranking"][0]["max_observed_drawdown_usd"]) == 3


def test_summary_rejects_duplicate_comparison(tmp_path):
    screen, replay = _fixture(tmp_path)
    with pytest.raises(ValueError, match="DUPLICATED"):
        consolidate(screen, (replay, replay))


def test_summary_refuses_source_hash_fraud(tmp_path):
    screen, replay = _fixture(tmp_path)
    replay.write_text(replay.read_text() + " ")
    with pytest.raises(ValueError, match="FILENAME_SHA_MISMATCH"):
        consolidate(screen, (replay,))


def test_summary_refuses_mismatched_screen_hash(tmp_path):
    screen, replay = _fixture(tmp_path)
    import json
    contents = json.loads(replay.read_text())
    contents["screening_source_sha256"] = "1"*64
    altered, _ = write_evidence(tmp_path, contents)
    with pytest.raises(ValueError, match="SCREENING_HASH_DRIFT"):
        consolidate(screen, (altered,))
