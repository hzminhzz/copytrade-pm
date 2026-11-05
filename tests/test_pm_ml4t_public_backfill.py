"""Bounded public read-only fill recovery tests: no real network."""

from __future__ import annotations

from hashlib import sha256
import json

import pytest

from copytrade_pm import pm_ml4t_public_backfill as recovery


ADDR = "0x" + "a" * 40
START = 1786060800000
END = 1793836800000


def _event(tid: int, time: int) -> dict:
    return {
        "user": ADDR,
        "coin": "HYPE",
        "time": time,
        "tid": tid,
        "side": "B",
        "sz": "2",
        "px": "12",
        "startPosition": "0",
    }


def _patch_missing(monkeypatch):
    monkeypatch.setattr(
        recovery,
        "roster",
        lambda _db: ({ADDR: {"alias": "M01", "wallet_id": 1}}, "f" * 64),
    )
    monkeypatch.setattr(
        recovery,
        "local_sources",
        lambda _root, _identities: ({ADDR: {"events": {}}}, {}),
    )


def test_two_page_overlap_saved_sha_and_no_future_fill(monkeypatch, tmp_path):
    _patch_missing(monkeypatch)
    calls = []

    def provider(query):
        calls.append(query)
        rows = (
            [_event(1, START + 1000), _event(2, START + 2000)]
            if len(calls) == 1
            else [_event(2, START + 2000), _event(3, START + 3000)]
        )
        if len(calls) == 3:
            rows = [_event(3, START + 3000)]
        raw = json.dumps(rows).encode()
        return rows, raw, sha256(raw).hexdigest()

    out = tmp_path / "generation"
    report = recovery.acquire(
        db=tmp_path,
        source_root=tmp_path,
        out=out,
        start_ms=START,
        end_ms=END,
        transport=provider,
        max_calls=4,
        pages_per_wallet=4,
        min_interval=3.0,
        page_size=2,
        sleep=lambda _: None,
    )
    assert report["requests"] == 3
    assert report["wallets"][0]["rows"] == 3
    assert report["wallets"][0]["status"] == "RETROSPECTIVE_SOURCE_ONLY"
    assert calls[0]["type"] == "userFillsByTime"
    assert calls[1]["startTime"] == START + 2000
    assert (out / "report.json").exists()
    normalized = list((out / "normalized").glob("*.json"))
    assert len(normalized) == 1
    assert len(json.loads(normalized[0].read_text())["fills"]) == 3
    assert normalized[0].stat().st_mode & 0o777 == 0o600
    assert out.stat().st_mode & 0o777 == 0o700
    assert json.loads(normalized[0].read_text())["historical_first_known_proven"] is False


def test_wrong_account_quarantined_without_normalized_promotion(monkeypatch, tmp_path):
    _patch_missing(monkeypatch)

    def provider(_query):
        rows = [dict(_event(1, START + 1000), user="0x" + "b" * 40)]
        raw = json.dumps(rows).encode()
        return rows, raw, sha256(raw).hexdigest()

    out = tmp_path / "failed"
    report = recovery.acquire(
        db=tmp_path,
        source_root=tmp_path,
        out=out,
        start_ms=START,
        end_ms=END,
        transport=provider,
        min_interval=3.0,
        sleep=lambda _: None,
    )
    assert report["requests"] == 1
    assert report["wallets"][0]["status"] == "PROVIDER_OR_SCHEMA_ValueError"
    assert not (out / "normalized").exists()
    assert (out / "report.json").exists()


def test_api_budget_and_immutable_generation(monkeypatch, tmp_path):
    _patch_missing(monkeypatch)
    with pytest.raises(ValueError, match="UNSAFE_API_CALL_BUDGET"):
        recovery.acquire(
            db=tmp_path,
            source_root=tmp_path,
            out=tmp_path / "no",
            start_ms=START,
            end_ms=END,
            max_calls=13,
        )
    out = tmp_path / "existing"
    out.mkdir()
    with pytest.raises(ValueError, match="IMMUTABLE_API_GENERATION_ALREADY_EXISTS"):
        recovery.acquire(db=tmp_path, source_root=tmp_path, out=out, start_ms=START, end_ms=END)
