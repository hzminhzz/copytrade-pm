"""Secondary CM-002 CSV is a lower-trust read-only source, never native TIDs."""

from __future__ import annotations

import csv
import gzip
from pathlib import Path

import pytest

pytest.importorskip("polars")

from scripts.phase7_native_open_screen import compile_coin_candidates
from scripts.phase7_secondary_cm002_screen import secondary_rows
from scripts.phase7_native_exposure import START_MS


def _source(tmp_path: Path, rows: list[dict]) -> Path:
    path = tmp_path / "source.csv.gz"
    with gzip.open(path, "wt", newline="") as stream:
        writer = csv.DictWriter(
            stream,
            fieldnames=[
                "alias",
                "address",
                "coin",
                "side",
                "price",
                "size",
                "datetime_utc",
            ],
        )
        writer.writeheader()
        writer.writerows(rows)
    return path


def test_csv_second_precision_duplicate_rows_are_preserved_as_uncertain(tmp_path) -> None:
    address = "0x" + "a" * 40
    row = {
        "alias": "CM-002",
        "address": address,
        "coin": "BTC",
        "side": "B",
        "price": "100",
        "size": "3",
        "datetime_utc": "2026-08-05 00:02:34",
    }
    oil = {**row, "coin": "xyz:PLTR"}
    path = _source(tmp_path, [row, row, oil])
    by_coin, quality = secondary_rows(path, expected_address=address)
    assert len(by_coin["BTC"]) == 2  # no exchange TID: cannot dedupe safely
    assert quality["event_identity_unique"] is False
    assert quality["counts"]["unsupported_dex"] == 1
    assert quality["counts"]["main_perp_second_precision_rows"] == 2
    events = compile_coin_candidates("CM-002", "BTC", by_coin["BTC"])
    fives = [x for x in events if x["delay_minutes"] == 5]
    assert len(fives) == 1
    assert fives[0]["source_fill_count"] == 2
    assert fives[0]["last_event_ms"] == START_MS + 154_000


def test_csv_exact_identity_collision_blocks(tmp_path) -> None:
    row = {
        "alias": "CM-002",
        "address": "0x" + "1" * 40,
        "coin": "BTC",
        "side": "A",
        "price": "100",
        "size": "3",
        "datetime_utc": "2026-08-05 00:01:01",
    }
    path = _source(tmp_path, [row])
    with pytest.raises(ValueError, match="IDENTITY_COLLISION"):
        secondary_rows(path, expected_address="0x" + "2" * 40)


def test_csv_out_of_window_never_becomes_position_evidence(tmp_path) -> None:
    address = "0x" + "a" * 40
    row = {
        "alias": "CM-002",
        "address": address,
        "coin": "BTC",
        "side": "B",
        "price": "100",
        "size": "1",
        "datetime_utc": "2026-07-01 00:00:00",
    }
    path = _source(tmp_path, [row])
    with pytest.raises(ValueError, match="NO_SUPPORTED_EVENTS"):
        secondary_rows(path, expected_address=address)
