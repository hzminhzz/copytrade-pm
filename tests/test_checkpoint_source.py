"""Checkpoint collection at the existing native source seam (spec #313, S1)."""

from datetime import UTC, datetime
from decimal import Decimal
from hashlib import sha256
import json

import pytest

from copytrade_pm.pm_checkpoint_source import CheckpointScope, SamplingLimits, collect_checkpoint
from copytrade_pm.pm_v4_evidence import read_wire

ADDRESS = "0x" + "a" * 40
BOUNDARY = int(datetime(2026, 11, 12, 0, 5, tzinfo=UTC).timestamp()) * 1000


def scope():
    return CheckpointScope(
        source_id="fixture-leader",
        account_sha=sha256(ADDRESS.encode()).hexdigest(),
        generation="a" * 64,
        selection_sha="b" * 64,
        dexes=("default", "xyz"),
    )


def limits():
    # Synthetic fixture limits only; never a measured production policy.
    return SamplingLimits(
        max_state_age_ms=4000,
        max_acquisition_ms=3000,
        max_dex_skew_ms=2000,
        publication_grace_ms=5000,
    )


def native(request):
    if request["type"] == "perpDexs":
        body = [None, {"name": "xyz"}]
    else:
        assert request["user"] == ADDRESS
        body = {
            "time": BOUNDARY - 1000,
            "assetPositions": (
                []
                if request.get("dex") == "xyz"
                else [{"position": {"coin": "BTC", "szi": "2.00000000000000000001"}}]
            ),
        }
    raw = json.dumps(body, indent=2).encode()
    return body, raw, sha256(raw).hexdigest()


def test_checkpoint_retains_native_complete_scope_and_actual_receipt_clocks(tmp_path):
    times = iter(
        [
            BOUNDARY,
            BOUNDARY,
            BOUNDARY + 100,
            BOUNDARY + 100,
            BOUNDARY + 200,
            BOUNDARY + 200,
            BOUNDARY + 300,
            BOUNDARY + 300,
        ]
    )
    sample = collect_checkpoint(
        scope(),
        ADDRESS,
        checkpoint_ms=BOUNDARY,
        limits=limits(),
        evidence_root=tmp_path / "originals",
        info=native,
        now_ms=lambda: next(times),
    )
    assert sample.kind == "COMPLETE"
    assert sample.checkpoint_ms == BOUNDARY
    assert sample.received_ms == BOUNDARY + 300
    assert sample.positions[0].quantity == Decimal("2.00000000000000000001")
    assert sample.positions[0].instrument == "hyperliquid/mainnet:perp:default/BTC"
    assert tuple(r.dex for r in sample.receipts) == ("default", "xyz")
    assert sample.receipts[1].position_count == 0
    assert sample.receipts[0].state_ms == BOUNDARY - 1000
    for receipt in (sample.catalog, *sample.receipts):
        original = read_wire(
            tmp_path / "originals" / "paper-events.sqlite3", receipt.raw_sha
        ).encode()
        assert sha256(original).hexdigest() == receipt.raw_sha
    assert sample.financial_authority == "NONE"


@pytest.mark.parametrize(
    "fault", ["timeout", "missing", "float", "namespace", "duplicate", "identity"]
)
def test_incomplete_native_scope_never_becomes_flat_or_actionable(tmp_path, fault):
    def broken(request):
        if request.get("dex") != "xyz":
            return native(request)
        if fault == "timeout":
            raise TimeoutError("fixture")
        body, _, _ = native(request)
        if fault == "missing":
            del body["assetPositions"]
        elif fault == "float":
            body["assetPositions"] = [{"position": {"coin": "xyz:TSLA", "szi": 0.1}}]
        elif fault == "namespace":
            body["assetPositions"] = [{"position": {"coin": "other:TSLA", "szi": "1"}}]
        elif fault == "duplicate":
            body["assetPositions"] = [{"position": {"coin": "xyz:TSLA", "szi": "1"}}] * 2
        elif fault == "identity":
            body["user"] = "0x" + "b" * 40
        raw = json.dumps(body).encode()
        return body, raw, sha256(raw).hexdigest()

    sample = collect_checkpoint(
        scope(),
        ADDRESS,
        checkpoint_ms=BOUNDARY,
        limits=limits(),
        evidence_root=tmp_path / "originals",
        info=broken,
        now_ms=lambda: BOUNDARY + 1000,
    )
    assert sample.kind == "UNAVAILABLE"
    assert sample.reasons
    assert sample.positions == ()
    assert sample.receipts[0].dex == "default"
    assert sample.financial_authority == "NONE"


@pytest.mark.parametrize(
    "offset,state_offset,policy,expected",
    [
        (-1000, -2000, limits(), "UNAVAILABLE"),
        (1000, -1000, limits(), "COMPLETE"),
        (5000, 4000, limits(), "UNAVAILABLE"),
        (301000, 300000, limits(), "UNAVAILABLE"),
        (1000, -6000, limits(), "UNAVAILABLE"),
        (1000, 1001, limits(), "UNAVAILABLE"),
        (1000, -1000, None, "UNAVAILABLE"),
    ],
)
def test_sampling_window_never_backdates_or_invents_freshness(
    tmp_path, offset, state_offset, policy, expected
):
    def timed(request):
        body, _, _ = native(request)
        if request["type"] == "clearinghouseState":
            body["time"] = BOUNDARY + state_offset
        raw = json.dumps(body).encode()
        return body, raw, sha256(raw).hexdigest()

    sample = collect_checkpoint(
        scope(),
        ADDRESS,
        checkpoint_ms=BOUNDARY,
        limits=policy,
        evidence_root=tmp_path / "originals",
        info=timed,
        now_ms=lambda: BOUNDARY + offset,
    )
    assert sample.kind == expected
    assert sample.started_ms == sample.received_ms == BOUNDARY + offset
    assert sample.checkpoint_ms == BOUNDARY
    assert (not sample.reasons) == (expected == "COMPLETE")


@pytest.mark.parametrize("fault", ["429", "raw", "skew", "acquisition", "catalog"])
def test_collection_faults_and_all_dex_timing_are_nonactionable(tmp_path, fault):
    from urllib.error import HTTPError

    def response(request):
        if fault == "429" and request.get("dex") == "xyz":
            raise HTTPError("fixture", 429, "limited", {}, None)
        body, raw, provided = native(request)
        if fault == "raw" and request.get("dex") == "xyz":
            return body, raw, "0" * 64
        if fault == "catalog" and request["type"] == "perpDexs":
            body.append({"name": "newdex"})
        if fault == "skew" and request.get("dex") == "xyz":
            body["time"] = BOUNDARY + 1500
        raw = json.dumps(body).encode()
        return body, raw, sha256(raw).hexdigest()

    ticks = iter([BOUNDARY] + [BOUNDARY + 2000] * 6 + [BOUNDARY + 4000])
    sample = collect_checkpoint(
        scope(),
        ADDRESS,
        checkpoint_ms=BOUNDARY,
        limits=limits(),
        evidence_root=tmp_path / "originals",
        info=response,
        now_ms=(lambda: next(ticks)) if fault == "acquisition" else lambda: BOUNDARY + 2000,
    )
    assert sample.kind == "UNAVAILABLE"
    assert sample.positions == ()
    if fault == "raw":
        assert len(sample.receipts) == 2
        assert read_wire(
            tmp_path / "originals" / "paper-events.sqlite3", sample.receipts[-1].raw_sha
        )
    if fault == "429":
        assert any("429" in reason for reason in sample.reasons)


def test_selected_checkpoint_roster_reuses_verified_sqlite_selection(tmp_path, monkeypatch):
    from contextlib import closing
    import sqlite3
    from test_pm_forward_multi_portfolio import full_registry, pin_reviewed_registry
    from test_pm_forward_observed_paper import at
    from copytrade_pm.pm_checkpoint_source import selected_checkpoint_sources

    pin_reviewed_registry(monkeypatch)
    registry = full_registry(tmp_path)
    with closing(sqlite3.connect(registry)) as db:
        db.execute("CREATE TABLE portfolio_seals (id INTEGER PRIMARY KEY)")
        db.commit()
    selected = selected_checkpoint_sources(
        registry,
        portfolios=("P1", "P14", "P16"),
        as_of=at(0),
        dexes=("default", "xyz"),
    )
    assert set(selected) == {"S035", "S051", "S053", "S064", "Whale_0x5f94"}
    assert len({s.account_sha for s, address in selected.values()}) == 5
    for source, address in selected.values():
        assert source.account_sha == sha256(address.encode()).hexdigest()
        assert source.dexes == ("default", "xyz")
    with pytest.raises(ValueError, match="PORTFOLIO_UNAPPROVED"):
        selected_checkpoint_sources(
            registry,
            portfolios=("unknown",),
            as_of=at(0),
            dexes=("default",),
        )
