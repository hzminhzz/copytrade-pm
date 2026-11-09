"""Acquisition pairs must be complete and belong to one immutable capture."""

import asyncio
from hashlib import sha256
import gzip
import json
from types import SimpleNamespace

import pytest

from copytrade_pm import pm_e4_backfill as e4
from copytrade_pm.pm_hyperx_gap_recovery import _generation_pages
from copytrade_pm.pm_hyperx_overlay_audit import _read_pages


def page(folder, number=1, *, more=False, tids=(1,), metadata=None):
    folder.mkdir(parents=True, exist_ok=True)
    raw = json.dumps(
        {
            "page": number,
            "page_size": 2000,
            "has_more": more,
            "fills": [{"tid": tid} for tid in tids],
        }
    ).encode()
    (folder / f"page-{number:05d}.json.gz").write_bytes(gzip.compress(raw, mtime=0))
    meta = {
        "alias": "W001",
        "coin": "BTC",
        "page": number,
        "sha256": sha256(raw).hexdigest(),
        "schema": "pm01_hyperx_gap_generation_page_v1",
    }
    meta.update(metadata or {})
    (folder / f"page-{number:05d}.meta.json").write_text(json.dumps(meta))


@pytest.mark.parametrize("reader", [_generation_pages, _read_pages])
@pytest.mark.parametrize("fault", ["hole", "duplicate", "unknown_schema", "bool_page"])
def test_bad_acquisition_pair_never_becomes_a_complete_generation(tmp_path, reader, fault):
    folder = tmp_path / "generation" / "W001" / "BTC"
    if fault == "hole":
        page(folder, more=True)
        page(folder, 3, tids=(3,))
    elif fault == "duplicate":
        page(folder, more=True)
        page(folder, 2)
    elif fault == "unknown_schema":
        page(folder, metadata={"schema": "pm01_hyperx_gap_generation_page_v999"})
    else:
        page(folder, metadata={"page": True})
    before = {p: p.read_bytes() for p in folder.iterdir()}
    with pytest.raises(ValueError):
        reader(folder, "W001", "BTC")
    assert all(p.read_bytes() == raw for p, raw in before.items())


def roster(monkeypatch):
    monkeypatch.setattr(
        e4,
        "load_cohort",
        lambda root: (
            [
                SimpleNamespace(alias=p, address="0x" + "1" * 40, address_sha256="a" * 64)
                for p in e4.PODS
            ],
            {"synthetic": "b" * 64},
        ),
    )


def collect(tmp_path):
    return asyncio.run(
        e4.collect_historical(
            tmp_path, tmp_path / "gsynthetic12345", pages_per_series=1, interval_seconds=3
        )
    )


def test_backfill_rejects_provider_digest_conflict_before_admission(tmp_path, monkeypatch):
    roster(monkeypatch)
    monkeypatch.setattr(e4, "_guarded_info", lambda request: ([], b"[]", "0" * 64))
    report = collect(tmp_path)
    assert all(
        not row[tag]["source_interval_complete"]
        for row in report["wallets"]
        for tag in ("funding", "collateral")
    )
    assert not list((tmp_path / "gsynthetic12345" / "raw").rglob("*.json"))


def test_backfill_reuse_blocks_before_fetch_and_preserves_original_clocks(tmp_path, monkeypatch):
    roster(monkeypatch)
    calls = []

    def provider(request):
        calls.append(request)
        return [], b"[]", sha256(b"[]").hexdigest()

    monkeypatch.setattr(e4, "_guarded_info", provider)
    collect(tmp_path)
    original = {p: p.read_bytes() for p in (tmp_path / "gsynthetic12345").rglob("*") if p.is_file()}
    assert len(calls) == 6
    with pytest.raises(ValueError, match="GENERATION"):
        collect(tmp_path)
    assert len(calls) == 6
    assert all(p.read_bytes() == raw for p, raw in original.items())


def hyperx_provider(tmp_path, monkeypatch):
    from copytrade_pm import pm_hyperx_gap_recovery as gap
    from test_pm_hyperx_gap_recovery import _case

    root = tmp_path / "original"
    entry, old, new = _case(root)
    body = {"page": 1, "page_size": 2000, "has_more": False, "fills": [*old, new]}
    raw = json.dumps(body, sort_keys=True).encode()
    provider = SimpleNamespace(
        key_from_existing_tracker_env=lambda: "synthetic",
        safe_coin=lambda coin: coin,
        validate=lambda *args: {"synthetic": True},
        provider_request=lambda *args: (body, raw, {"x-ratelimit-remaining": "30"}),
    )
    monkeypatch.setattr(gap, "load_cohort", lambda _: ([entry], {}))
    monkeypatch.setattr(gap, "_adapter", lambda _: provider)
    return gap, root, raw


def test_new_hyperx_generation_binds_raw_pair_and_rejects_foreign_complete_pair(
    tmp_path, monkeypatch
):
    gap, root, raw = hyperx_provider(tmp_path, monkeypatch)
    first, second = tmp_path / "generation_first", tmp_path / "generation_second"
    a = gap.recover(root, first, aliases=("W001",))
    b = gap.recover(root, second, aliases=("W001",))
    assert a["generation_id"] != b["generation_id"]
    folder = first / "W001" / "BTC"
    assert gzip.decompress((folder / "page-00001.json.gz").read_bytes()) == raw
    assert _read_pages(folder, "W001", "BTC")[0]["fills"]
    for file in folder.iterdir():
        (second / "W001" / "BTC" / file.name).write_bytes(file.read_bytes())
    with pytest.raises(ValueError, match="GENERATION_IDENTITY"):
        _read_pages(second / "W001" / "BTC", "W001", "BTC")
    assert a["historical_first_known"] is False


@pytest.mark.parametrize("after_sidecar", [False, True])
def test_hyperx_crash_pair_recovery_preserves_raw_and_original_clock(
    tmp_path, monkeypatch, after_sidecar
):
    import multiprocessing
    import os

    gap, root, raw = hyperx_provider(tmp_path, monkeypatch)
    output = tmp_path / "generation_crash"
    original = gap._atomic

    def child():
        def cut(path, data):
            if path.name == "page-00001.meta.json":
                if after_sidecar:
                    original(path, data)
                os._exit(73)
            return original(path, data)

        gap._atomic = cut
        gap.recover(root, output, aliases=("W001",))

    worker = multiprocessing.get_context("fork").Process(target=child)
    worker.start()
    worker.join(10)
    assert worker.exitcode == 73
    files = {p: p.read_bytes() for p in output.rglob("*") if p.is_file()}
    folder = output / "W001" / "BTC"
    assert gzip.decompress((folder / "page-00001.json.gz").read_bytes()) == raw
    if after_sidecar:
        result = gap.recover(root, output, aliases=("W001",))
        assert result["api_requests"] == 0
        assert result["rows"][0]["overlay_eligible"]
    else:
        with pytest.raises(ValueError, match="PARTIAL_IMMUTABLE"):
            gap.recover(root, output, aliases=("W001",))
    assert all(p.read_bytes() == content for p, content in files.items())


def test_ledger_consumer_rejects_complete_foreign_generation_pair(tmp_path, monkeypatch):
    from copytrade_pm.pm_acquisition_contracts import read_ledger_page

    roster(monkeypatch)
    monkeypatch.setattr(e4, "_guarded_info", lambda request: ([], b"[]", sha256(b"[]").hexdigest()))
    roots = [tmp_path / "gsyntheticfirst01", tmp_path / "gsyntheticsecond1"]
    for root in roots:
        asyncio.run(e4.collect_historical(tmp_path, root, pages_per_series=1))
    alias = e4.PODS[0]
    assert read_ledger_page(roots[0], alias, "funding", 0) == []
    relative = f"metadata/{alias}/funding/page-000.json"
    (roots[1] / relative).write_bytes((roots[0] / relative).read_bytes())
    with pytest.raises(ValueError, match="GENERATION_IDENTITY"):
        read_ledger_page(roots[1], alias, "funding", 0)
