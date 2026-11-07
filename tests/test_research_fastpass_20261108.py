"""Regression tests for local-only Vike fast-pass evidence, using disposable fixtures."""

from __future__ import annotations

from importlib import import_module
import json
from pathlib import Path
import stat
import sys

import pytest


@pytest.fixture
def research_modules():
    scripts = Path(__file__).resolve().parent.parent / "scripts"
    sys.path.insert(0, str(scripts))
    return (
        import_module("research_vike_recovery_audit_20261108"),
        import_module("research_publish_vike_fastpass_20261108"),
    )


def _fill(*, trade_id: int = 101, price: float = 100.0) -> dict:
    return {
        "ts": "2026-11-03T12:30:00+00:00",
        "symbol": "BTC",
        "side": "buy",
        "trade_id": trade_id,
        "size_token": 0.1,
        "price": price,
        "fee_token": "USDC",
        "fee": 0.02,
        "closed_pnl": 0.0,
        "is_maker": False,
    }


def _write_chunk(root: Path, page: int, chunk: int, fills: list, next_cursor=None) -> Path:
    dest = root / f"vike-recovery-20261108-F1-p{page}-c{chunk}.json"
    doc = {
        "schema": "vike_hl_wallet_fills_mcp_chunk_v1",
        "wallet_alias": "F1",
        "requested_start": "2026-11-01T00:00:00Z",
        "requested_end": "2026-11-08T00:00:00Z",
        "page": page,
        "chunk": chunk,
        "items": fills,
        "nextCursor": next_cursor,
    }
    dest.write_text(json.dumps(doc))
    dest.chmod(0o600)
    return dest


def test_vike_page_chunks_deduplicate_and_prove_final_cursor(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, research_modules
) -> None:
    audit, _publisher = research_modules
    _write_chunk(tmp_path, 1, 1, [_fill()], next_cursor=None)
    _write_chunk(tmp_path, 1, 2, [_fill(), _fill(trade_id=102)], next_cursor=None)
    monkeypatch.setattr(audit, "ROOT", tmp_path)
    fills, trades, state = audit.read()
    assert len(fills["F1"]) == 2
    assert len(trades["F1"]) == 0
    assert state["F1"]["fill_parts"][1] == {1, 2}
    assert state["F1"]["fill_cursor"][1] is None
    assert state["F1"]["conflicts"] == 0


def test_vike_incomplete_cursor_never_becomes_complete(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, research_modules
) -> None:
    audit, _publisher = research_modules
    _write_chunk(tmp_path, 1, 1, [_fill()], next_cursor="HAS_MORE")
    monkeypatch.setattr(audit, "ROOT", tmp_path)
    _fills, _trades, state = audit.read()
    assert state["F1"]["fill_cursor"][1] == "HAS_MORE"
    assert state["F1"]["fill_cursor"][max(state["F1"]["fill_parts"])] is not None


def test_vike_conflicting_trade_id_is_explicit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, research_modules
) -> None:
    audit, _publisher = research_modules
    _write_chunk(tmp_path, 1, 1, [_fill()], next_cursor=None)
    _write_chunk(tmp_path, 1, 2, [_fill(price=200.0)], next_cursor=None)
    monkeypatch.setattr(audit, "ROOT", tmp_path)
    _fills, _trades, state = audit.read()
    assert state["F1"]["conflicts"] == 1


def test_private_generation_idempotently_validates_exact_bytes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    research_modules,
) -> None:
    _audit, publisher = research_modules
    stage = tmp_path / "staged"
    stage.mkdir()
    _write_chunk(stage, 1, 1, [_fill()])
    archive = tmp_path / "archive"
    monkeypatch.setattr(publisher, "STAGED", stage)
    monkeypatch.setattr(publisher, "ROOT", archive)
    monkeypatch.setattr(sys, "argv", ["research_publish", "--publish"])
    publisher.main()
    assert "PUBLISHED_VERIFIED_PRIVATE_GENERATION" in capsys.readouterr().out
    roots = list(archive.glob("g-*"))
    assert len(roots) == 1
    assert stat.S_IMODE(archive.stat().st_mode) == 0o700
    assert stat.S_IMODE(roots[0].stat().st_mode) == 0o700
    receipt = roots[0] / "raw" / "vike-recovery-20261108-F1-p1-c1.json"
    assert receipt.is_file()
    assert stat.S_IMODE(receipt.stat().st_mode) == 0o600
    first = receipt.read_bytes()
    publisher.main()
    assert "VERIFIED_EXISTING_GENERATION" in capsys.readouterr().out
    assert receipt.read_bytes() == first
