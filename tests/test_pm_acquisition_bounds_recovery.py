"""ANOS-14 (#348): bounded acquisition cost prediction and verified incremental recovery.

Tests exercise existing owners (`pm_offline_job_catalog`, `pm_offline_cache`,
`pm_acquisition_contracts`, `pm_operations`, `pm_capabilities`) against a
pure-Python fake S3/Parquet provider with zero network I/O, zero AWS credential
discovery, and zero real campaign authorization.
"""

from __future__ import annotations

from datetime import UTC, datetime
from hashlib import sha256
import json
from pathlib import Path
import struct
from typing import Any

import pytest

from copytrade_pm import pm_bounded_acquisition as acq
from copytrade_pm.pm_offline_cache import ImmutableCache
from tests.test_pm_research_preflight import (
    START,
    publish_coverage_receipt,
    request as base_request,
    sha,
)

DAY1 = "2026-10-20"
DAY2 = "2026-10-21"
DAY1_MS = int(datetime(2026, 10, 20, tzinfo=UTC).timestamp() * 1000)
DAY2_MS = int(datetime(2026, 10, 21, tzinfo=UTC).timestamp() * 1000)
TWO_DAY_END = "2026-10-22T00:00:00+00:00"
W1 = "0xaaa"
W2 = "0xbbb"
WALLETS = [W1, W2]
DEXES = ["hyperliquid", "xyz"]
SOURCE_COLS = ["time", "user", "coin", "px", "sz", "side"]
MARKET_COLS = ["ts_ms", "symbol", "open", "close", "volume"]


def fake_parquet_bytes(rows: list[dict], *, corrupt_magic: bool = False) -> bytes:
    """Build deterministic self-delimited Parquet-framed bytes verifiable in pure Python."""
    body = json.dumps(rows, sort_keys=True, separators=(",", ":")).encode()
    footer = struct.pack("<I", len(body)) + (b"BAD1" if corrupt_magic else b"PAR1")
    prefix = b"BAD1" if corrupt_magic else b"PAR1"
    return prefix + body + footer


class FakeS3ParquetProvider:
    """In-memory fake S3/Parquet provider tracking exact requests and remote read bytes."""

    def __init__(self, *, observable_remote_bytes: bool = True) -> None:
        self.objects: dict[tuple[str, str, str], dict] = {}
        self.observable_remote_bytes = observable_remote_bytes
        self.head_calls: list[tuple[str, str, str]] = []
        self.scan_calls: list[dict] = []
        self.total_requests = 0
        self.total_remote_bytes_read = 0

    def put_object(
        self,
        *,
        kind: str,
        dex: str,
        date: str,
        rows: list[dict],
        row_groups: list[dict],
        object_bytes: int | None = None,
        schema_columns: list[str] | None = None,
        etag: str | None = None,
        corrupt_magic: bool = False,
        actual_bytes_per_request: int | None = None,
        range_per_row_group: bool = False,
        estimated_filtered_return_rows: int | None = None,
        estimated_output_bytes: int | None = None,
    ) -> dict:
        payload = fake_parquet_bytes(rows, corrupt_magic=corrupt_magic)
        payload_sha = sha256(payload).hexdigest()
        total_rg_bytes = sum(
            sum(col_meta["compressed_bytes"] for col_meta in rg["columns"].values())
            for rg in row_groups
        )
        obj = {
            "kind": kind,
            "dex": dex,
            "date": date,
            "etag": etag or f'"etag-{kind}-{dex}-{date}-{payload_sha[:8]}"',
            "object_bytes": object_bytes
            if object_bytes is not None
            else max(len(payload), total_rg_bytes),
            "schema_columns": list(
                schema_columns or (SOURCE_COLS if kind == "source" else MARKET_COLS)
            ),
            "row_groups": row_groups,
            "rows": list(rows),
            "payload": payload,
            "payload_sha256": payload_sha,
            "range_per_row_group": range_per_row_group,
            "estimated_filtered_return_rows": estimated_filtered_return_rows,
            "estimated_output_bytes": estimated_output_bytes,
            "actual_bytes_per_request": actual_bytes_per_request,
        }
        self.objects[(kind, dex, date)] = obj
        return obj

    def inspect_unit(self, unit: dict) -> dict:
        key = (unit["kind"], unit["dex"], unit["date"])
        self.total_requests += 1
        self.head_calls.append(key)
        obj = self.objects[key]
        return {
            "kind": obj["kind"],
            "dex": obj["dex"],
            "date": obj["date"],
            "etag": obj["etag"],
            "object_bytes": obj["object_bytes"],
            "schema_columns": obj["schema_columns"],
            "row_groups": obj["row_groups"],
            "metadata_requests": 1,
            "range_per_row_group": obj["range_per_row_group"],
            "estimated_filtered_return_rows": obj["estimated_filtered_return_rows"],
            "estimated_output_bytes": obj["estimated_output_bytes"],
        }

    def scan_unit(self, unit: dict, *, cancel_event=None, budget_guard=None) -> dict:
        key = (unit["kind"], unit["dex"], unit["date"])
        obj = self.objects[key]
        rows = list(obj["rows"])
        target_wallets = set(unit.get("target_wallets") or [])
        projected = set(unit["projected_columns"])

        rgs = obj["row_groups"]
        selected_rgs = []
        for rg in rgs:
            u_col = rg["columns"].get("user", {})
            if unit["kind"] == "source" and u_col.get("has_stats") and target_wallets:
                cmin, cmax = u_col.get("min"), u_col.get("max")
                if (
                    cmin is not None
                    and cmax is not None
                    and all(w < cmin or w > cmax for w in target_wallets)
                ):
                    continue
            selected_rgs.append(rg)

        comp_bytes = sum(
            rg["columns"][c]["compressed_bytes"]
            for rg in selected_rgs
            for c in unit["projected_columns"]
        )
        req_count = len(selected_rgs) if obj.get("range_per_row_group") else 1
        wire_bytes = (
            obj["actual_bytes_per_request"] * max(1, req_count)
            if obj.get("actual_bytes_per_request") is not None
            else comp_bytes
        )
        if not self.observable_remote_bytes:
            wire_bytes_reported = None
        else:
            wire_bytes_reported = wire_bytes

        if budget_guard is not None:
            budget_guard(
                delta_requests=req_count,
                delta_remote_bytes=comp_bytes
                if wire_bytes_reported is None
                else wire_bytes_reported,
            )

        self.total_requests += req_count
        if wire_bytes_reported is not None:
            self.total_remote_bytes_read += wire_bytes_reported
        self.scan_calls.append(
            {
                "key": key,
                "columns": list(unit["projected_columns"]),
                "wallets": sorted(target_wallets),
            }
        )

        if unit["kind"] == "source":
            filtered = [
                {k: v for k, v in r.items() if k in projected or k in {"user", "dex", "time_ms"}}
                for r in rows
                if r.get("user") in target_wallets
            ]
        else:
            filtered = [
                {k: v for k, v in r.items() if k in projected or k in {"dex", "ts_ms"}}
                for r in rows
            ]

        return {
            "unit_id": unit["unit_id"],
            "kind": unit["kind"],
            "dex": unit["dex"],
            "date": unit["date"],
            "etag": obj["etag"],
            "payload_sha256": obj["payload_sha256"],
            "parquet_bytes": obj["payload"],
            "rows": filtered,
            "requests_made": req_count,
            "remote_bytes_read": wire_bytes_reported,
            "compressed_bytes_scanned": comp_bytes,
            "selected_row_groups": [rg["row_group_id"] for rg in selected_rgs],
            "source_verified": True,
            "empty_verified": len(filtered) == 0,
        }


def _unit_request(
    root: Path,
    *,
    receipts: list[str] | None = None,
    partition_root: Path | None = None,
    acquisition: dict | None = None,
    **override,
) -> dict:
    acq = {
        "unit_kinds": ["source"],
        "allowed_dexes": list(DEXES),
        "projected_columns": {"source": list(SOURCE_COLS), "market": list(MARKET_COLS)},
        "budget": {
            "max_requests": 50,
            "max_remote_bytes": 50_000_000,
            "max_disk_bytes": 10_000_000,
            "max_workers": 2,
        },
    }
    if acquisition:
        acq.update(acquisition)
    req = base_request(
        root,
        receipts=receipts if receipts is not None else [],
        dexes=list(DEXES),
        wallets=list(WALLETS),
        utc_start=START,
        utc_end=TWO_DAY_END,
        as_of="2026-10-25T00:00:00+00:00",
        acquisition=acq,
    )
    req.update(override)
    return req


def _write_local_partition(
    partition_root: Path,
    *,
    kind: str = "source",
    dex: str,
    wallet: str,
    date: str,
    rows: list[dict],
    input_name: str = "input-1",
    source_name: str = "source-1",
    market_name: str = "market-1",
    known_at: str = START,
    tamper_data: bool = False,
) -> Path:
    year, month, day = date.split("-")
    if kind == "market":
        folder = partition_root / kind / dex / f"year={year}" / f"month={month}" / f"day={day}"
    else:
        folder = (
            partition_root / kind / dex / wallet / f"year={year}" / f"month={month}" / f"day={day}"
        )
    folder.mkdir(parents=True, exist_ok=True, mode=0o700)
    payload = fake_parquet_bytes(rows)
    data_path = folder / "data.parquet"
    data_path.write_bytes(b"TAMPERED" if tamper_data else payload)
    manifest = {
        "schema": "pm_local_immutable_partition_v1",
        "kind": kind,
        "dex": dex,
        "wallet": wallet,
        "date": date,
        "known_at": known_at,
        "input_sha256": sha(input_name),
        "source_sha256": sha(source_name),
        "market_sha256": sha(market_name),
        "sha256": sha256(payload).hexdigest(),
        "bytes": len(payload),
        "rows": len(rows),
    }
    (folder / "source.json").write_text(json.dumps(manifest, sort_keys=True))
    return data_path


def test_preflight_checks_scope_and_local_partitions_choosing_only_missing_units(
    tmp_path: Path,
) -> None:
    root = tmp_path / "cache"
    ImmutableCache(root, min_free_bytes=0)
    part_root = tmp_path / "partitions"

    # W1 on (hyperliquid, DAY1) has a verified local immutable partition.
    # W2 on (hyperliquid, DAY1) already has a verified T13 coverage receipt.
    # Therefore (source, hyperliquid, DAY1) is COMPLETELY covered and must NOT be scanned.
    _write_local_partition(
        part_root,
        kind="source",
        dex="hyperliquid",
        wallet=W1,
        date=DAY1,
        rows=[{"user": W1, "dex": "hyperliquid", "time_ms": DAY1_MS}],
    )
    cov_w2_hl_day1 = publish_coverage_receipt(
        root,
        wallet=W2,
        dex="hyperliquid",
        utc_start=START,
        utc_end=f"{DAY2}T00:00:00+00:00",
        row_count=3,
    )
    # On (xyz, DAY1), ONLY W1 has a verified local partition; W2 is missing -> unit scans only W2 once.
    _write_local_partition(
        part_root,
        kind="source",
        dex="xyz",
        wallet=W1,
        date=DAY1,
        rows=[],
    )

    provider = FakeS3ParquetProvider()
    rg = [
        {
            "row_group_id": 0,
            "num_rows": 100,
            "columns": {c: {"compressed_bytes": 1000, "has_stats": False} for c in SOURCE_COLS},
        }
    ]
    for dex in DEXES:
        for date in (DAY1, DAY2):
            provider.put_object(kind="source", dex=dex, date=date, rows=[], row_groups=rg)

    req = _unit_request(root, receipts=[cov_w2_hl_day1])
    plan = acq.plan_bounded_acquisition(
        root, req, partition_root=part_root, metadata_provider=provider
    )

    assert plan["status"] == "PLANNED"
    assert plan["acquisition_needed"] is True
    assert plan["request_binding_sha256"]
    assert plan["plan_binding_sha256"]
    assert plan["immutable_inputs"] == {
        "job_sha256": sha("job-1"),
        "input_sha256": sha("input-1"),
        "source_sha256": sha("source-1"),
        "market_sha256": sha("market-1"),
        "software_sha256": sha("software-1"),
    }
    # Complete unit (hyperliquid, DAY1) was reused without remote inspection or rescan!
    assert ("source", "hyperliquid", DAY1) not in provider.head_calls
    assert set(provider.head_calls) == {
        ("source", "xyz", DAY1),
        ("source", "hyperliquid", DAY2),
        ("source", "xyz", DAY2),
    }
    missing = {(u["kind"], u["dex"], u["date"]): u for u in plan["missing_units"]}
    assert set(missing) == {
        ("source", "xyz", DAY1),
        ("source", "hyperliquid", DAY2),
        ("source", "xyz", DAY2),
    }
    assert missing[("source", "xyz", DAY1)]["target_wallets"] == [W2]
    assert missing[("source", "hyperliquid", DAY2)]["target_wallets"] == sorted(WALLETS)
    assert plan["reused_local_partition_count"] == 2
    assert plan["reused_coverage_receipt_count"] == 1
    assert plan["scan_calls_made"] == 0
    assert plan["trading_authorized"] is False
    assert all(v is False for v in plan["authority"].values())
    assert plan["campaign_auto_authorized"] is False


def test_corrupt_or_symlinked_local_partition_fails_closed(tmp_path: Path) -> None:
    root = tmp_path / "cache"
    ImmutableCache(root, min_free_bytes=0)
    part_root = tmp_path / "partitions"
    _write_local_partition(
        part_root,
        kind="source",
        dex="hyperliquid",
        wallet=W1,
        date=DAY1,
        rows=[{"user": W1}],
        tamper_data=True,
    )
    req = _unit_request(root)
    tampered = acq.plan_bounded_acquisition(root, req, partition_root=part_root)
    assert tampered["status"] == "BLOCKED"
    assert tampered["error_code"] == "CORRUPT_LOCAL_PARTITION"

    # Symlink partition directory or file also fails closed.
    part_sym = tmp_path / "sym_partitions"
    part_sym.mkdir()
    outside = tmp_path / "outside.parquet"
    outside.write_bytes(b"PAR1[]\x02\x00\x00\x00PAR1")
    y1, m1, d1 = DAY1.split("-")
    folder = part_sym / "source" / "hyperliquid" / W1 / f"year={y1}" / f"month={m1}" / f"day={d1}"
    folder.mkdir(parents=True)
    (folder / "data.parquet").symlink_to(outside)
    sym_out = acq.plan_bounded_acquisition(root, req, partition_root=part_sym)
    assert sym_out["status"] == "BLOCKED"
    assert sym_out["error_code"] == "CORRUPT_LOCAL_PARTITION"


def test_cost_prediction_separates_compressed_bytes_from_rows_and_reports_forecast_vs_actual(
    tmp_path: Path,
) -> None:
    root = tmp_path / "cache"
    ImmutableCache(root, min_free_bytes=0)

    provider = FakeS3ParquetProvider(observable_remote_bytes=True)
    # Row group 0 lacks user stats (must be scanned: 3_000 bytes for projected SOURCE_COLS).
    # Row group 1 has user stats [0xccc, 0xddd], disjoint from target wallets [0xaaa, 0xbbb] (pruned!).
    # Extra non-projected column 'tx_hash' (50_000 bytes/rg) must NOT enter projected compressed cost.
    rgs_with_pruning = [
        {
            "row_group_id": 0,
            "num_rows": 5000,
            "columns": {
                **{c: {"compressed_bytes": 500, "has_stats": False} for c in SOURCE_COLS},
                "tx_hash": {"compressed_bytes": 50_000, "has_stats": False},
            },
        },
        {
            "row_group_id": 1,
            "num_rows": 5000,
            "columns": {
                **{
                    c: {
                        "compressed_bytes": 1_500,
                        "has_stats": c == "user",
                        **({"min": "0xccc", "max": "0xddd"} if c == "user" else {}),
                    }
                    for c in SOURCE_COLS
                },
                "tx_hash": {"compressed_bytes": 50_000, "has_stats": False},
            },
        },
    ]
    rows = [
        {"time": DAY1_MS, "user": W1, "coin": "BTC", "px": "100", "sz": "1", "side": "B"},
        {
            "time": DAY1_MS + 60_000,
            "user": "0x999",
            "coin": "BTC",
            "px": "101",
            "sz": "2",
            "side": "A",
        },
    ]
    provider.put_object(
        kind="source",
        dex="hyperliquid",
        date=DAY1,
        rows=rows,
        row_groups=rgs_with_pruning,
        object_bytes=120_000,
        schema_columns=[*SOURCE_COLS, "tx_hash"],
        range_per_row_group=True,
        estimated_filtered_return_rows=1,
        estimated_output_bytes=256,
    )

    req = _unit_request(
        root,
        dexes=["hyperliquid"],
        utc_end=f"{DAY2}T00:00:00+00:00",
        acquisition={
            "unit_kinds": ["source"],
            "allowed_dexes": ["hyperliquid"],
            "projected_columns": {"source": list(SOURCE_COLS)},
            "budget": {"max_requests": 10, "max_remote_bytes": 10_000, "max_disk_bytes": 50_000},
        },
    )
    # Wildcard projection is always refused fail-closed.
    bad_wildcard = _unit_request(
        root,
        dexes=["hyperliquid"],
        utc_end=f"{DAY2}T00:00:00+00:00",
        acquisition={
            "unit_kinds": ["source"],
            "allowed_dexes": ["hyperliquid"],
            "projected_columns": {"source": ["*"]},
            "budget": {"max_requests": 10, "max_remote_bytes": 10_000, "max_disk_bytes": 50_000},
        },
    )
    with pytest.raises(ValueError, match="INVALID_OR_WILDCARD_PROJECTION"):
        acq.plan_bounded_acquisition(root, bad_wildcard, metadata_provider=provider)

    plan = acq.plan_bounded_acquisition(root, req, metadata_provider=provider)
    assert plan["status"] == "PLANNED"
    # Forecast: 1 metadata request + 1 unpruned row-group scan = 2 requests.
    # Remote compressed bytes = 6 cols * 500 = 3_000 (NOT 120_000 object_bytes, NOT 1 return row!).
    assert plan["forecast"]["requests"] == 2
    assert plan["forecast"]["metadata_requests"] == 1
    assert plan["forecast"]["scan_requests"] == 1
    assert plan["forecast"]["remote_object_bytes"] == 120_000
    assert plan["forecast"]["remote_compressed_bytes"] == 3_000
    assert plan["forecast"]["estimated_filtered_return_rows"] == 1
    assert plan["forecast"]["selected_row_groups"] == 1
    assert plan["forecast"]["stats_pruned_row_groups"] == 1
    assert plan["forecast"]["disk_bytes"] == 256

    # Execute and inspect forecast-vs-actual measured reporting.
    exec_provider = FakeS3ParquetProvider(observable_remote_bytes=True)
    exec_provider.objects = provider.objects
    result = acq.execute_bounded_acquisition(root, req, provider=exec_provider, run_id="run-slice2")
    assert result["status"] == "COMPLETE"
    assert result["forecast"]["remote_compressed_bytes"] == 3_000
    assert result["forecast"]["estimated_filtered_return_rows"] == 1
    assert result["actual"]["requests"] == 2
    assert result["actual"]["remote_bytes_observable"] is True
    assert result["actual"]["remote_bytes_read"] == 3_000
    assert result["actual"]["remote_compressed_bytes_scanned"] == 3_000
    assert result["actual"]["returned_rows"] == 1
    assert result["actual"]["disk_bytes_written"] > 0
    assert result["actual"]["disk_free_bytes_after"] > 0
    assert result["actual"]["units_completed"] == 1
    assert result["comparison"]["within_budget"] is True
    assert result["comparison"]["remote_bytes_delta"] == 0
    assert result["scientifically_qualified"] is False
    assert result["trading_authorized"] is False


def test_budget_caps_stop_preflight_and_report_unobservable_bytes_honestly(tmp_path: Path) -> None:
    root = tmp_path / "cache"
    ImmutableCache(root, min_free_bytes=0)

    provider = FakeS3ParquetProvider(observable_remote_bytes=False)
    rg = [
        {
            "row_group_id": 0,
            "num_rows": 500,
            "columns": {c: {"compressed_bytes": 2_000, "has_stats": False} for c in SOURCE_COLS},
        }
    ]
    provider.put_object(
        kind="source",
        dex="hyperliquid",
        date=DAY1,
        rows=[{"time": DAY1_MS, "user": W1, "coin": "BTC", "px": "100", "sz": "1", "side": "B"}],
        row_groups=rg,
        object_bytes=50_000,
        estimated_filtered_return_rows=1,
        estimated_output_bytes=200,
    )

    # Tight remote byte cap (10_000 < 12_000 compressed) blocks BEFORE any scan call.
    too_big_req = _unit_request(
        root,
        dexes=["hyperliquid"],
        utc_end=f"{DAY2}T00:00:00+00:00",
        acquisition={
            "unit_kinds": ["source"],
            "allowed_dexes": ["hyperliquid"],
            "projected_columns": {"source": list(SOURCE_COLS)},
            "budget": {"max_requests": 10, "max_remote_bytes": 10_000, "max_disk_bytes": 50_000},
        },
    )
    blocked = acq.execute_bounded_acquisition(
        root, too_big_req, provider=provider, run_id="run-over-bytes"
    )
    assert blocked["status"] == "BLOCKED"
    assert blocked["error_code"] == "BUDGET_EXHAUSTED"
    assert blocked["actual"]["scan_requests"] == 0
    assert len(provider.scan_calls) == 0

    # Tight request cap (1 < 2 predicted metadata+scan) also blocks before scan.
    tight_req_cap = _unit_request(
        root,
        dexes=["hyperliquid"],
        utc_end=f"{DAY2}T00:00:00+00:00",
        acquisition={
            "unit_kinds": ["source"],
            "allowed_dexes": ["hyperliquid"],
            "projected_columns": {"source": list(SOURCE_COLS)},
            "budget": {"max_requests": 1, "max_remote_bytes": 50_000, "max_disk_bytes": 50_000},
        },
    )
    req_blocked = acq.execute_bounded_acquisition(
        root, tight_req_cap, provider=provider, run_id="run-over-reqs"
    )
    assert req_blocked["status"] == "BLOCKED"
    assert req_blocked["error_code"] == "BUDGET_EXHAUSTED"
    assert len(provider.scan_calls) == 0

    # Tight disk cap blocks before scan.
    tight_disk_cap = _unit_request(
        root,
        dexes=["hyperliquid"],
        utc_end=f"{DAY2}T00:00:00+00:00",
        acquisition={
            "unit_kinds": ["source"],
            "allowed_dexes": ["hyperliquid"],
            "projected_columns": {"source": list(SOURCE_COLS)},
            "budget": {"max_requests": 10, "max_remote_bytes": 50_000, "max_disk_bytes": 100},
        },
    )
    disk_blocked = acq.execute_bounded_acquisition(
        root, tight_disk_cap, provider=provider, run_id="run-over-disk"
    )
    assert disk_blocked["status"] == "BLOCKED"
    assert disk_blocked["error_code"] == "BUDGET_EXHAUSTED"
    assert len(provider.scan_calls) == 0

    # Within budget, unobservable wire bytes stay None (not forged as 0 or row count).
    ok_req = _unit_request(
        root,
        dexes=["hyperliquid"],
        utc_end=f"{DAY2}T00:00:00+00:00",
        acquisition={
            "unit_kinds": ["source"],
            "allowed_dexes": ["hyperliquid"],
            "projected_columns": {"source": list(SOURCE_COLS)},
            "budget": {"max_requests": 10, "max_remote_bytes": 20_000, "max_disk_bytes": 50_000},
        },
    )
    unobs_out = acq.execute_bounded_acquisition(
        root, ok_req, provider=provider, run_id="run-unobservable"
    )
    assert unobs_out["status"] == "COMPLETE"
    assert unobs_out["actual"]["remote_bytes_observable"] is False
    assert unobs_out["actual"]["remote_bytes_read"] is None
    assert unobs_out["actual"]["remote_compressed_bytes_scanned"] == 12_000
    assert unobs_out["actual"]["returned_rows"] == 1
    assert unobs_out["comparison"]["remote_bytes_delta"] is None


def test_faults_and_scope_drift_stop_fail_closed_without_inventing_zeros(tmp_path: Path) -> None:
    from copytrade_pm.pm_acquisition_contracts import AcquisitionContractError

    rg = [
        {
            "row_group_id": 0,
            "num_rows": 10,
            "columns": {c: {"compressed_bytes": 100, "has_stats": False} for c in SOURCE_COLS},
        }
    ]
    two_day_req = lambda r: _unit_request(  # noqa: E731
        r,
        dexes=["hyperliquid"],
        wallets=[W1],
        utc_start=START,
        utc_end=TWO_DAY_END,
        acquisition={
            "unit_kinds": ["source"],
            "allowed_dexes": ["hyperliquid"],
            "projected_columns": {"source": list(SOURCE_COLS)},
            "budget": {"max_requests": 20, "max_remote_bytes": 50_000, "max_disk_bytes": 50_000},
        },
    )

    # 1. Credential failure during inspect stops immediately with 0 scan calls.
    cred_root = tmp_path / "cred"
    ImmutableCache(cred_root, min_free_bytes=0)

    class CredFailProvider(FakeS3ParquetProvider):
        def inspect_unit(self, unit):
            self.total_requests += 1
            raise AcquisitionContractError("PROVIDER_CREDENTIAL_FAILURE", "AWS creds expired")

    cred_out = acq.execute_bounded_acquisition(
        cred_root, two_day_req(cred_root), provider=CredFailProvider(), run_id="run-cred"
    )
    assert cred_out["status"] == "BLOCKED"
    assert cred_out["error_code"] == "PROVIDER_CREDENTIAL_FAILURE"
    assert cred_out["coverage_receipt_keys"] == []

    # 2. Mid-run permission expiry after DAY1 leaves DAY1 intact & never invents zero for DAY2.
    exp_root = tmp_path / "exp"
    ImmutableCache(exp_root, min_free_bytes=0)

    class ExpireDay2Provider(FakeS3ParquetProvider):
        def scan_unit(self, unit, **kw):
            if unit["date"] == DAY2:
                self.total_requests += 1
                raise AcquisitionContractError("PERMISSION_EXPIRED", "STS token expired mid-run")
            return super().scan_unit(unit, **kw)

    exp_p = ExpireDay2Provider()
    exp_p.put_object(
        kind="source",
        dex="hyperliquid",
        date=DAY1,
        rows=[
            {
                "time": DAY1_MS,
                "user": W1,
                "dex": "hyperliquid",
                "coin": "BTC",
                "px": "1",
                "sz": "1",
                "side": "B",
            }
        ],
        row_groups=rg,
    )
    exp_p.put_object(kind="source", dex="hyperliquid", date=DAY2, rows=[], row_groups=rg)
    exp_out = acq.execute_bounded_acquisition(
        exp_root, two_day_req(exp_root), provider=exp_p, run_id="run-exp"
    )
    assert exp_out["status"] == "BLOCKED"
    assert exp_out["error_code"] == "PERMISSION_EXPIRED"
    assert exp_out["actual"]["units_completed"] == 1
    assert exp_out["actual"]["units_failed"] == 1
    assert len(exp_out["coverage_receipt_keys"]) == 1  # ONLY DAY1! Never zero receipt for DAY2.
    assert "source:hyperliquid:2026-10-20" in exp_out["acquired_unit_keys"]
    assert "source:hyperliquid:2026-10-21" not in exp_out["acquired_unit_keys"]

    # 3. Corrupt Parquet magic, payload SHA mismatch, and mid-read ETag mutation fail closed.
    for fault_kind in ("corrupt_magic", "sha_mismatch", "etag_mutated"):
        c_root = tmp_path / f"corrupt_{fault_kind}"
        ImmutableCache(c_root, min_free_bytes=0)

        class CorruptProvider(FakeS3ParquetProvider):
            def scan_unit(self, unit, **kw):
                res = super().scan_unit(unit, **kw)
                if fault_kind == "sha_mismatch":
                    res["payload_sha256"] = "0" * 64
                elif fault_kind == "etag_mutated":
                    res["etag"] = '"mutated-etag"'
                return res

        cp = CorruptProvider()
        cp.put_object(
            kind="source",
            dex="hyperliquid",
            date=DAY1,
            rows=[],
            row_groups=rg,
            corrupt_magic=(fault_kind == "corrupt_magic"),
        )
        cp.put_object(kind="source", dex="hyperliquid", date=DAY2, rows=[], row_groups=rg)
        c_out = acq.execute_bounded_acquisition(
            c_root, two_day_req(c_root), provider=cp, run_id=f"run-{fault_kind}"
        )
        expected_code = (
            "REMOTE_OBJECT_MUTATED" if fault_kind == "etag_mutated" else "CORRUPT_REMOTE_PAGE"
        )
        assert c_out["status"] == "BLOCKED"
        assert c_out["error_code"] == expected_code
        assert c_out["coverage_receipt_keys"] == []

    # 4. Scope drift returned by provider (wrong DEX, unrequested wallet, out-of-window time) stops!
    for bad_row in (
        {"time": DAY1_MS, "user": W1, "dex": "other_dex", "coin": "BTC"},
        {"time": DAY1_MS, "user": W2, "dex": "hyperliquid", "coin": "BTC"},
        {"time": DAY2_MS + 10 * 86_400_000, "user": W1, "dex": "hyperliquid", "coin": "BTC"},
    ):
        s_root = tmp_path / f"scope_{len(list(tmp_path.iterdir()))}"
        ImmutableCache(s_root, min_free_bytes=0)

        class DriftedProvider(FakeS3ParquetProvider):
            def scan_unit(self, unit, **kw):
                res = super().scan_unit(unit, **kw)
                res["rows"] = [bad_row]
                return res

        dp = DriftedProvider()
        dp.put_object(kind="source", dex="hyperliquid", date=DAY1, rows=[], row_groups=rg)
        dp.put_object(kind="source", dex="hyperliquid", date=DAY2, rows=[], row_groups=rg)
        s_out = acq.execute_bounded_acquisition(
            s_root, two_day_req(s_root), provider=dp, run_id="run-scope"
        )
        assert s_out["status"] == "BLOCKED"
        assert s_out["error_code"] == "SCOPE_VIOLATION"
        assert s_out["coverage_receipt_keys"] == []

    # 5. Mid-execution runtime byte blowout triggers budget exhaustion cleanly without publishing.
    b_root = tmp_path / "runtime_budget"
    ImmutableCache(b_root, min_free_bytes=0)
    bp = FakeS3ParquetProvider()
    bp.put_object(
        kind="source",
        dex="hyperliquid",
        date=DAY1,
        rows=[{"time": DAY1_MS, "user": W1, "coin": "BTC"}],
        row_groups=rg,
        actual_bytes_per_request=90_000,  # Wire read far exceeds 50_000 budget!
    )
    bp.put_object(kind="source", dex="hyperliquid", date=DAY2, rows=[], row_groups=rg)
    b_out = acq.execute_bounded_acquisition(
        b_root, two_day_req(b_root), provider=bp, run_id="run-runtime-budget"
    )
    assert b_out["status"] == "BLOCKED"
    assert b_out["error_code"] == "BUDGET_EXHAUSTED"
    assert b_out["coverage_receipt_keys"] == []


def test_bounded_concurrency_cancellation_and_hash_verified_incremental_resume(
    tmp_path: Path,
) -> None:
    import threading
    import time

    root = tmp_path / "cache"
    ImmutableCache(root, min_free_bytes=0)

    class ConcurrentCancellableProvider(FakeS3ParquetProvider):
        def __init__(self, *, cancel_after_units: int | None = None, delay: float = 0.0) -> None:
            super().__init__(observable_remote_bytes=True)
            self._lock = threading.Lock()
            self.active = 0
            self.peak_active = 0
            self.cancel_after_units = cancel_after_units
            self.completed_scans = 0
            self.cancel_event = threading.Event()
            self.delay = delay

        def scan_unit(self, unit, *, cancel_event=None, budget_guard=None):
            if cancel_event is not None and cancel_event.is_set():
                from copytrade_pm.pm_acquisition_contracts import AcquisitionContractError

                raise AcquisitionContractError("EXECUTION_CANCELLED", "Cancelled before scan")
            with self._lock:
                self.active += 1
                self.peak_active = max(self.peak_active, self.active)
            try:
                if self.delay > 0:
                    time.sleep(self.delay)
                res = super().scan_unit(unit, cancel_event=cancel_event, budget_guard=budget_guard)
            finally:
                with self._lock:
                    self.active -= 1
            if self.cancel_after_units is not None:
                with self._lock:
                    self.completed_scans += 1
                    if self.completed_scans >= self.cancel_after_units:
                        self.cancel_event.set()
            return res

    rg = [
        {
            "row_group_id": 0,
            "num_rows": 10,
            "columns": {c: {"compressed_bytes": 100, "has_stats": False} for c in SOURCE_COLS},
        }
    ]
    base_acq = {
        "unit_kinds": ["source"],
        "allowed_dexes": list(DEXES),
        "projected_columns": {"source": list(SOURCE_COLS)},
        "budget": {
            "max_requests": 20,
            "max_remote_bytes": 100_000,
            "max_disk_bytes": 100_000,
            "max_workers": 3,
        },
    }
    req = _unit_request(root, acquisition=base_acq)

    # 1. Invalid max_workers fails closed before any remote request.
    p_unused = ConcurrentCancellableProvider()
    for dex in DEXES:
        for date in (DAY1, DAY2):
            p_unused.put_object(
                kind="source",
                dex=dex,
                date=date,
                rows=[
                    {
                        "time": DAY1_MS if date == DAY1 else DAY2_MS,
                        "user": W1,
                        "dex": dex,
                        "coin": "BTC",
                    }
                ],
                row_groups=rg,
            )
    with pytest.raises(ValueError, match="INVALID_MAX_WORKERS"):
        acq.execute_bounded_acquisition(root, req, provider=p_unused, run_id="bad-w", max_workers=0)
    with pytest.raises(ValueError, match="INVALID_MAX_WORKERS"):
        acq.execute_bounded_acquisition(
            root, req, provider=p_unused, run_id="bad-w2", max_workers=9
        )
    assert p_unused.total_requests == 0

    # 2. Bounded concurrency: 4 units with max_workers=3 shows real bounded parallelism (<=3).
    conc_root = tmp_path / "conc_cache"
    ImmutableCache(conc_root, min_free_bytes=0)
    p_conc = ConcurrentCancellableProvider(delay=0.04)
    p_conc.objects = p_unused.objects
    conc_out = acq.execute_bounded_acquisition(
        conc_root, req, provider=p_conc, run_id="run-conc", max_workers=3
    )
    assert conc_out["status"] == "COMPLETE"
    assert 2 <= conc_out["actual"]["max_observed_concurrency"] <= 3
    assert 2 <= p_conc.peak_active <= 3
    assert conc_out["actual"]["units_completed"] == 4

    # 3. Interruption/cancellation after 2 units seals those 2 cleanly and stops remaining 2.
    res_root = tmp_path / "resume_cache"
    ImmutableCache(res_root, min_free_bytes=0)
    p_cancel = ConcurrentCancellableProvider(cancel_after_units=2)
    p_cancel.objects = p_unused.objects
    first = acq.execute_bounded_acquisition(
        res_root,
        req,
        provider=p_cancel,
        run_id="run-interrupt",
        max_workers=1,
        cancel_event=p_cancel.cancel_event,
    )
    assert first["status"] == "BLOCKED"
    assert first["error_code"] == "EXECUTION_CANCELLED"
    assert first["actual"]["units_completed"] == 2
    assert first["actual"]["units_remaining"] == 2
    first_completed_ids = sorted(first["acquired_unit_keys"])
    assert len(first_completed_ids) == 2

    # 4. Resume completes ONLY missing 2 units, never rescanning old verified units!
    p_resume = ConcurrentCancellableProvider()
    p_resume.objects = p_unused.objects
    resumed = acq.execute_bounded_acquisition(
        res_root, req, provider=p_resume, run_id="run-interrupt", resume=True, max_workers=2
    )
    assert resumed["status"] == "COMPLETE"
    assert resumed["attempt"] == 2
    assert resumed["actual"]["units_reused"] == 2
    assert resumed["actual"]["units_completed"] == 2
    assert set(resumed["reused_unit_ids"]) == set(first_completed_ids)
    # 0 HEAD/scan calls for the 2 reused units: only 2 HEAD + 2 scan = 4 requests on resume!
    assert p_resume.total_requests == 4
    assert len(p_resume.head_calls) == 2
    assert len(p_resume.scan_calls) == 2
    scanned_ids = {f"{c['key'][0]}:{c['key'][1]}:{c['key'][2]}" for c in p_resume.scan_calls}
    assert scanned_ids.isdisjoint(set(first_completed_ids))
    assert len(resumed["acquired_unit_keys"]) == 4
    assert (
        resumed["cumulative"]["requests"]
        == first["actual"]["requests"] + resumed["actual"]["requests"]
    )
    assert resumed["cumulative"]["requests"] <= 20

    # 5. Resume falsifiers: scope/cap/input drift must fail closed with 0 remote calls.
    drift_cases: tuple[dict[str, Any], ...] = (
        {"wallets": [W1]},
        {"dexes": ["hyperliquid"]},
        {"utc_end": f"{DAY2}T00:00:00+00:00"},
        {"source_sha256": sha("source-drifted")},
    )
    for drift in drift_cases:
        p_fail = ConcurrentCancellableProvider()
        p_fail.objects = p_unused.objects
        drifted = acq.execute_bounded_acquisition(
            res_root,
            {**_unit_request(res_root, acquisition=base_acq), **drift},
            provider=p_fail,
            run_id="run-interrupt",
            resume=True,
        )
        assert drifted["status"] == "BLOCKED"
        assert drifted["error_code"] == "RESUME_BINDING_MISMATCH"
        assert p_fail.total_requests == 0

    raised_cap_acq = {
        **base_acq,
        "budget": {**base_acq["budget"], "max_requests": 999},
    }
    p_cap_drift = ConcurrentCancellableProvider()
    p_cap_drift.objects = p_unused.objects
    cap_drifted = acq.execute_bounded_acquisition(
        res_root,
        _unit_request(res_root, acquisition=raised_cap_acq),
        provider=p_cap_drift,
        run_id="run-interrupt",
        resume=True,
    )
    assert cap_drifted["status"] == "BLOCKED"
    assert cap_drifted["error_code"] == "RESUME_BINDING_MISMATCH"
    assert p_cap_drift.total_requests == 0

    # 6. Tampered prior acquired_unit fails closed on resume (never trusted or overwritten).
    victim_key = first["acquired_unit_keys"][first_completed_ids[0]]
    victim_data = res_root / "acquired_unit" / victim_key[:2] / f"{victim_key}.data"
    victim_data.write_bytes(b"corrupted-unit-bytes")
    p_tamper = ConcurrentCancellableProvider()
    p_tamper.objects = p_unused.objects
    tamper_out = acq.execute_bounded_acquisition(
        res_root, req, provider=p_tamper, run_id="run-interrupt", resume=True
    )
    assert tamper_out["status"] == "BLOCKED"
    assert tamper_out["error_code"] in {"CORRUPT_CACHE_SHA", "CORRUPT_RECEIPT"}
    assert p_tamper.total_requests == 0

    # 7. Unsealed orphan .data (crash before manifest) fails closed on resume.
    orphan_root = tmp_path / "orphan_cache"
    ImmutableCache(orphan_root, min_free_bytes=0)
    p_orphan = ConcurrentCancellableProvider(cancel_after_units=1)
    p_orphan.objects = p_unused.objects
    orph = acq.execute_bounded_acquisition(
        orphan_root,
        req,
        provider=p_orphan,
        run_id="run-orphan",
        max_workers=1,
        cancel_event=p_orphan.cancel_event,
    )
    assert orph["actual"]["units_completed"] == 1
    p_plan = acq.plan_bounded_acquisition(orphan_root, req, metadata_provider=p_orphan)
    missing_u = next(
        u for u in p_plan["missing_units"] if u["unit_id"] not in orph["acquired_unit_keys"]
    )
    orphan_deps = acq._unit_cache_deps(
        plan_binding_sha256=orph["plan_binding_sha256"],
        unit=missing_u,
        immutable_inputs=orph["immutable_inputs"],
    )
    orphan_key = ImmutableCache.identity(
        "acquired_unit", orphan_deps, version=acq.ACQUISITION_UNIT_SCHEMA
    )
    orphan_dir = orphan_root / "acquired_unit" / orphan_key[:2]
    orphan_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    (orphan_dir / f"{orphan_key}.data").write_bytes(b"partial-unsealed")
    p_orphan2 = ConcurrentCancellableProvider()
    p_orphan2.objects = p_unused.objects
    orph_res = acq.execute_bounded_acquisition(
        orphan_root, req, provider=p_orphan2, run_id="run-orphan", resume=True
    )
    assert orph_res["status"] == "BLOCKED"
    assert orph_res["error_code"] == "PARTIAL_IMMUTABLE_UNIT"
    assert p_orphan2.total_requests == 0


def test_metadata_fail_closed_multiwallet_resume_and_cross_study_market_reuse(
    tmp_path: Path,
) -> None:
    import threading

    from copytrade_pm import pm_cwsa_chapter2_gate as gate
    from copytrade_pm import pm_cwsa_chapter2_projection as projection
    from copytrade_pm.pm_acquisition_contracts import AcquisitionContractError
    from copytrade_pm.pm_offline_job_catalog import verify_coverage_receipt_key

    rg = [
        {
            "row_group_id": 0,
            "num_rows": 10,
            "columns": {c: {"compressed_bytes": 100, "has_stats": False} for c in SOURCE_COLS},
        }
    ]

    # 1. Missing unit metadata fails closed with REMOTE_METADATA_UNAVAILABLE; inline metadata plans.
    meta_root = tmp_path / "meta_cache"
    ImmutableCache(meta_root, min_free_bytes=0)
    base_req = _unit_request(
        meta_root,
        dexes=["hyperliquid"],
        wallets=[W1],
        utc_end=f"{DAY2}T00:00:00+00:00",
        acquisition={
            "unit_kinds": ["source"],
            "allowed_dexes": ["hyperliquid"],
            "projected_columns": {"source": list(SOURCE_COLS)},
            "budget": {"max_requests": 10, "max_remote_bytes": 50_000, "max_disk_bytes": 50_000},
        },
    )
    unavail = acq.plan_bounded_acquisition(meta_root, base_req)
    assert unavail["status"] == "BLOCKED"
    assert unavail["error_code"] == "REMOTE_METADATA_UNAVAILABLE"

    inline_req = {
        **base_req,
        "acquisition": {
            **base_req["acquisition"],
            "remote_objects": {
                f"source:hyperliquid:{DAY1}": {
                    "kind": "source",
                    "dex": "hyperliquid",
                    "date": DAY1,
                    "etag": '"inline-etag"',
                    "object_bytes": 1_000,
                    "row_groups": rg,
                    "estimated_filtered_return_rows": 1,
                    "estimated_output_bytes": 128,
                }
            },
        },
    }
    inline_plan = acq.plan_bounded_acquisition(meta_root, inline_req)
    assert inline_plan["status"] == "PLANNED"
    assert inline_plan["forecast"]["metadata_requests"] == 1
    assert inline_plan["forecast"]["remote_compressed_bytes"] == 600

    # 2. inspect_unit KeyError maps to REMOTE_OBJECT_MISSING.
    class MissingKeyProvider(FakeS3ParquetProvider):
        def inspect_unit(self, unit):
            self.total_requests += 1
            raise KeyError(unit["unit_id"])

    miss_out = acq.execute_bounded_acquisition(
        meta_root, base_req, provider=MissingKeyProvider(), run_id="run-key-miss"
    )
    assert miss_out["status"] == "BLOCKED"
    assert miss_out["error_code"] == "REMOTE_OBJECT_MISSING"

    # 3. require_observable_remote_bytes=True fails closed on unobservable provider.
    unobs_provider = FakeS3ParquetProvider(observable_remote_bytes=False)
    unobs_provider.put_object(
        kind="source",
        dex="hyperliquid",
        date=DAY1,
        rows=[{"time": DAY1_MS, "user": W1, "dex": "hyperliquid", "coin": "BTC"}],
        row_groups=rg,
    )
    obs_req = {
        **base_req,
        "acquisition": {
            **base_req["acquisition"],
            "budget": {
                "max_requests": 10,
                "max_remote_bytes": 50_000,
                "max_disk_bytes": 50_000,
                "require_observable_remote_bytes": True,
            },
        },
    }
    obs_root = tmp_path / "obs_cache"
    ImmutableCache(obs_root, min_free_bytes=0)
    obs_out = acq.execute_bounded_acquisition(
        obs_root, obs_req, provider=unobs_provider, run_id="run-req-obs"
    )
    assert obs_out["status"] == "BLOCKED"
    assert obs_out["error_code"] == "UNOBSERVABLE_REMOTE_BYTES"
    assert obs_out["acquired_unit_keys"] == {}

    # 4. Runtime disk-cap blowout refuses publishing oversized unit.
    disk_root = tmp_path / "disk_cache"
    ImmutableCache(disk_root, min_free_bytes=0)
    disk_provider = FakeS3ParquetProvider(observable_remote_bytes=True)
    disk_provider.put_object(
        kind="source",
        dex="hyperliquid",
        date=DAY1,
        rows=[{"time": DAY1_MS, "user": W1, "dex": "hyperliquid", "coin": "BTC"}],
        row_groups=rg,
        estimated_output_bytes=64,
    )
    disk_req = {
        **base_req,
        "acquisition": {
            **base_req["acquisition"],
            "budget": {"max_requests": 10, "max_remote_bytes": 50_000, "max_disk_bytes": 120},
        },
    }
    disk_out = acq.execute_bounded_acquisition(
        disk_root, disk_req, provider=disk_provider, run_id="run-runtime-disk"
    )
    assert disk_out["status"] == "BLOCKED"
    assert disk_out["error_code"] == "BUDGET_EXHAUSTED"
    assert disk_out["acquired_unit_keys"] == {}
    assert disk_out["coverage_receipt_keys"] == []

    # 5. source_verified/empty_verified omission and missing row timestamp fail closed.
    class UnverifiedProvider(FakeS3ParquetProvider):
        def __init__(self, drop_field: str) -> None:
            super().__init__(observable_remote_bytes=True)
            self.drop_field = drop_field

        def scan_unit(self, unit, **kw):
            res = super().scan_unit(unit, **kw)
            res[self.drop_field] = False
            return res

    for drop_field, row_list in (
        ("source_verified", [{"time": DAY1_MS, "user": W1, "dex": "hyperliquid", "coin": "BTC"}]),
        ("empty_verified", []),
    ):
        v_root = tmp_path / f"unver_{drop_field}"
        ImmutableCache(v_root, min_free_bytes=0)
        vp = UnverifiedProvider(drop_field)
        vp.put_object(kind="source", dex="hyperliquid", date=DAY1, rows=row_list, row_groups=rg)
        v_out = acq.execute_bounded_acquisition(
            v_root, base_req, provider=vp, run_id=f"run-{drop_field}"
        )
        assert v_out["status"] == "BLOCKED"
        assert v_out["error_code"] == "CORRUPT_REMOTE_PAGE"
        assert v_out["coverage_receipt_keys"] == []

    notime_root = tmp_path / "notime_cache"
    ImmutableCache(notime_root, min_free_bytes=0)
    np_provider = FakeS3ParquetProvider(observable_remote_bytes=True)
    np_provider.put_object(
        kind="source",
        dex="hyperliquid",
        date=DAY1,
        rows=[{"user": W1, "dex": "hyperliquid", "coin": "BTC"}],
        row_groups=rg,
    )
    notime_out = acq.execute_bounded_acquisition(
        notime_root, base_req, provider=np_provider, run_id="run-notime"
    )
    assert notime_out["status"] == "BLOCKED"
    assert notime_out["error_code"] == "SCOPE_VIOLATION"
    assert notime_out["coverage_receipt_keys"] == []

    # 6. Multi-wallet sparse unit marks populated W1 vs VERIFIED_EMPTY W2; unverified empty W2 stays missing.
    sparse_root = tmp_path / "sparse_cache"
    ImmutableCache(sparse_root, min_free_bytes=0)
    sp_provider = FakeS3ParquetProvider(observable_remote_bytes=True)
    sp_provider.put_object(
        kind="source",
        dex="hyperliquid",
        date=DAY1,
        rows=[{"time": DAY1_MS, "user": W1, "dex": "hyperliquid", "coin": "BTC"}],
        row_groups=rg,
    )
    multi_req = _unit_request(
        sparse_root,
        dexes=["hyperliquid"],
        wallets=[W1, W2],
        utc_end=f"{DAY2}T00:00:00+00:00",
        acquisition={
            "unit_kinds": ["source"],
            "allowed_dexes": ["hyperliquid"],
            "projected_columns": {"source": list(SOURCE_COLS)},
            "budget": {"max_requests": 10, "max_remote_bytes": 50_000, "max_disk_bytes": 50_000},
        },
    )
    sp_out = acq.execute_bounded_acquisition(
        sparse_root, multi_req, provider=sp_provider, run_id="run-sparse"
    )
    assert sp_out["status"] == "COMPLETE"
    assert len(sp_out["coverage_receipt_keys"]) == 2
    cov_docs = {
        doc["wallet"]: doc
        for doc in (
            verify_coverage_receipt_key(sparse_root, ck)[0]
            for ck in sp_out["coverage_receipt_keys"]
        )
    }
    assert cov_docs[W1]["row_count"] == 1 and cov_docs[W1]["empty_verified"] is False
    assert cov_docs[W2]["row_count"] == 0 and cov_docs[W2]["empty_verified"] is True
    multi_recheck = {**multi_req, "coverage_receipts": sp_out["coverage_receipt_keys"]}
    assert acq.plan_bounded_acquisition(sparse_root, multi_recheck)["acquisition_needed"] is False

    class UnverifiedEmptyW2Provider(FakeS3ParquetProvider):
        def scan_unit(self, unit, **kw):
            res = super().scan_unit(unit, **kw)
            res["unverified_empty_wallets"] = [W2]
            return res

    unver_w2_root = tmp_path / "unver_w2_cache"
    ImmutableCache(unver_w2_root, min_free_bytes=0)
    uw2p = UnverifiedEmptyW2Provider(observable_remote_bytes=True)
    uw2p.objects = sp_provider.objects
    uw2_out = acq.execute_bounded_acquisition(
        unver_w2_root, multi_req, provider=uw2p, run_id="run-uw2"
    )
    assert uw2_out["status"] == "COMPLETE"
    uw2_docs = {
        doc["wallet"]: doc
        for doc in (
            verify_coverage_receipt_key(unver_w2_root, ck)[0]
            for ck in uw2_out["coverage_receipt_keys"]
        )
    }
    assert uw2_docs[W2]["empty_verified"] is False
    uw2_recheck_req = {**multi_req, "coverage_receipts": uw2_out["coverage_receipt_keys"]}
    uw2_recheck = acq.plan_bounded_acquisition(
        unver_w2_root, uw2_recheck_req, metadata_provider=uw2p
    )
    assert uw2_recheck["acquisition_needed"] is True
    assert uw2_recheck["missing_units"][0]["target_wallets"] == [W2]

    # 7. Cross-study market unit reuse works via market_coverage receipt with 0 remote calls.
    mkt_root = tmp_path / "mkt_cache"
    ImmutableCache(mkt_root, min_free_bytes=0)
    mkt_rg = [
        {
            "row_group_id": 0,
            "num_rows": 5,
            "columns": {c: {"compressed_bytes": 40, "has_stats": False} for c in MARKET_COLS},
        }
    ]
    mkt_provider = FakeS3ParquetProvider(observable_remote_bytes=True)
    mkt_provider.put_object(
        kind="market",
        dex="hyperliquid",
        date=DAY1,
        rows=[
            {
                "ts_ms": DAY1_MS,
                "dex": "hyperliquid",
                "symbol": "BTC",
                "open": 100,
                "close": 101,
                "volume": 5,
            }
        ],
        row_groups=mkt_rg,
    )
    study_a = _unit_request(
        mkt_root,
        cohort="study-a",
        job_sha256=sha("job-a"),
        dexes=["hyperliquid"],
        wallets=[W1],
        utc_end=f"{DAY2}T00:00:00+00:00",
        acquisition={
            "unit_kinds": ["market"],
            "allowed_dexes": ["hyperliquid"],
            "projected_columns": {"market": list(MARKET_COLS)},
            "budget": {"max_requests": 10, "max_remote_bytes": 50_000, "max_disk_bytes": 50_000},
        },
    )
    study_a_out = acq.execute_bounded_acquisition(
        mkt_root, study_a, provider=mkt_provider, run_id="run-mkt-a"
    )
    assert study_a_out["status"] == "COMPLETE"
    study_b = {**study_a, "cohort": "study-b", "job_sha256": sha("job-b")}
    mkt_zero_provider = FakeS3ParquetProvider(observable_remote_bytes=True)
    study_b_plan = acq.plan_bounded_acquisition(
        mkt_root, study_b, metadata_provider=mkt_zero_provider
    )
    assert study_b_plan["acquisition_needed"] is False
    assert study_b_plan["reused_units"][0]["reuse_source"] == "market_coverage_receipt"
    study_b_exec = acq.execute_bounded_acquisition(
        mkt_root, study_b, provider=mkt_zero_provider, run_id="run-mkt-b"
    )
    assert study_b_exec["status"] == "COMPLETE"
    assert mkt_zero_provider.total_requests == 0

    # 8. Resume drift (as_of/policy/holdout), tampered coverage receipt, and resume HEAD budget cap.
    res_root = tmp_path / "resume_edge_cache"
    ImmutableCache(res_root, min_free_bytes=0)

    class CancelAfterFirstProvider(FakeS3ParquetProvider):
        def __init__(self, cancel_event: threading.Event, stop_after: int = 1) -> None:
            super().__init__(observable_remote_bytes=True)
            self.cancel_event = cancel_event
            self.stop_after = stop_after
            self.done = 0

        def scan_unit(self, unit, *, cancel_event=None, budget_guard=None):
            if cancel_event is not None and cancel_event.is_set():
                raise AcquisitionContractError("EXECUTION_CANCELLED", "Cancelled")
            res = super().scan_unit(unit, cancel_event=cancel_event, budget_guard=budget_guard)
            res["requests_made"] = 2
            self.done += 1
            if self.done >= self.stop_after:
                self.cancel_event.set()
            return res

    four_req = _unit_request(
        res_root,
        acquisition={
            "unit_kinds": ["source"],
            "allowed_dexes": list(DEXES),
            "projected_columns": {"source": list(SOURCE_COLS)},
            "budget": {"max_requests": 8, "max_remote_bytes": 50_000, "max_disk_bytes": 50_000},
        },
    )
    cancel_ev = threading.Event()
    p_four = CancelAfterFirstProvider(cancel_ev, stop_after=1)
    for dex in DEXES:
        for date in (DAY1, DAY2):
            p_four.put_object(
                kind="source",
                dex=dex,
                date=date,
                rows=[
                    {
                        "time": DAY1_MS if date == DAY1 else DAY2_MS,
                        "user": W1,
                        "dex": dex,
                        "coin": "BTC",
                    }
                ],
                row_groups=rg,
            )
    att1 = acq.execute_bounded_acquisition(
        res_root,
        four_req,
        provider=p_four,
        run_id="run-head-cap",
        max_workers=1,
        cancel_event=cancel_ev,
    )
    assert att1["status"] == "BLOCKED"
    assert att1["error_code"] == "EXECUTION_CANCELLED"
    assert att1["actual"]["units_completed"] == 1
    assert att1["actual"]["requests"] == 6

    # Drift checks: as_of, policy, and holdout must fail closed before remote calls.
    for key, val in (
        ("as_of", "2026-10-26T00:00:00+00:00"),
        ("policy", "changed_policy"),
    ):
        drifted_req = {**four_req, key: val}
        p_drift = FakeS3ParquetProvider()
        d_out = acq.execute_bounded_acquisition(
            res_root, drifted_req, provider=p_drift, run_id="run-head-cap", resume=True
        )
        assert d_out["error_code"] == "RESUME_BINDING_MISMATCH"
        assert p_drift.total_requests == 0
    holdout_drifted = {
        **four_req,
        "acquisition": {
            **four_req["acquisition"],
            "holdout": {
                "windows": [{"utc_start": DAY2 + "T00:00:00+00:00", "utc_end": TWO_DAY_END}],
                "forbid_overlap": True,
            },
        },
    }
    p_hdrift = FakeS3ParquetProvider()
    assert (
        acq.execute_bounded_acquisition(
            res_root, holdout_drifted, provider=p_hdrift, run_id="run-head-cap", resume=True
        )["error_code"]
        == "RESUME_BINDING_MISMATCH"
    )
    assert p_hdrift.total_requests == 0

    # Resume Attempt 2 has rem_requests_cap=2 with 3 missing units -> stops on 3rd HEAD (2 HEADs made).
    p_att2 = FakeS3ParquetProvider()
    p_att2.objects = p_four.objects
    att2 = acq.execute_bounded_acquisition(
        res_root, four_req, provider=p_att2, run_id="run-head-cap", resume=True
    )
    assert att2["status"] == "BLOCKED"
    assert att2["error_code"] == "BUDGET_EXHAUSTED"
    assert att2["actual"]["metadata_requests"] == 2
    assert len(p_att2.head_calls) == 2 and len(p_att2.scan_calls) == 0

    # Resume Attempt 3 sees prior_reqs=4 (att1=2 + att2=2) -> rem_requests_cap=0 -> 0 remote calls!
    p_att3 = FakeS3ParquetProvider()
    p_att3.objects = p_four.objects
    att3 = acq.execute_bounded_acquisition(
        res_root, four_req, provider=p_att3, run_id="run-head-cap", resume=True
    )
    assert att3["status"] == "BLOCKED"
    assert att3["error_code"] == "BUDGET_EXHAUSTED"
    assert p_att3.total_requests == 0

    # Tampered coverage_receipt on disk fails closed during resume verification.
    ck0 = att1["coverage_receipt_keys"][0]
    (res_root / "coverage_receipt" / ck0[:2] / f"{ck0}.data").write_bytes(b"TAMPERED")
    p_tamper = FakeS3ParquetProvider()
    tamper_res = acq.execute_bounded_acquisition(
        res_root, four_req, provider=p_tamper, run_id="run-head-cap", resume=True
    )
    assert tamper_res["error_code"] == "CORRUPT_RECEIPT"
    assert p_tamper.total_requests == 0

    # 9. Non-trivial Chapter 2 gate & projection inputs refuse trading authorization despite acquired coverage.
    fin_nontrivial = gate.assess_financial_runtime(
        service_active=True,
        signed_portfolios={"A"},
        finance_scans={"A": {"last_checkpoint_ms": 200}},
        source_changes={"A": 100},
        journal_cursors={"A": 100},
        latest_source_checkpoint_ms=100,
        modeled_effects={"A": 0},
    )
    assert fin_nontrivial.state == "BLOCKED_EVIDENCE"
    assert fin_nontrivial.detail == "NO_PROVEN_MODELED_FINANCIAL_EFFECT"
    assert gate.decide("premerge", [fin_nontrivial])["verdict"] != "PASS"
    proj_nontrivial = projection.project(
        source={
            "source_count": len(gate.EXPECTED_WALLETS),
            "latest_kinds": {m: "COMPLETE" for m in gate.EXPECTED_WALLETS},
            "head_sha256": sha("head"),
            "latest_checkpoint_ms": 1_000,
        },
        papers={"A": {"modeled_effects": 0}},
        verified_finance=set(),
        qualified_k=set(),
        release_sha="0" * 40,
        epoch="2026-11-13",
    )
    assert proj_nontrivial["trading_authorized"] is False
    assert proj_nontrivial["scientifically_qualified"] is False


def test_pit_holdout_market_units_nonqualification_and_cli_preflight(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    from copytrade_pm import pm_capabilities as capabilities
    from copytrade_pm import pm_cwsa_chapter2_gate as gate
    from copytrade_pm import pm_cwsa_chapter2_projection as projection
    from copytrade_pm import pm_operations
    from tests.test_pm_research_preflight import KNOWN_AFTER

    root = tmp_path / "cache"
    ImmutableCache(root, min_free_bytes=0)
    part_root = tmp_path / "partitions"

    rg_src = [
        {
            "row_group_id": 0,
            "num_rows": 10,
            "columns": {c: {"compressed_bytes": 100, "has_stats": False} for c in SOURCE_COLS},
        }
    ]
    rg_mkt = [
        {
            "row_group_id": 0,
            "num_rows": 10,
            "columns": {c: {"compressed_bytes": 50, "has_stats": False} for c in MARKET_COLS},
        }
    ]
    provider = FakeS3ParquetProvider(observable_remote_bytes=True)
    provider.put_object(
        kind="source",
        dex="hyperliquid",
        date=DAY1,
        rows=[{"time": DAY1_MS, "user": W1, "dex": "hyperliquid", "coin": "BTC"}],
        row_groups=rg_src,
        estimated_filtered_return_rows=1,
        estimated_output_bytes=256,
    )
    provider.put_object(
        kind="market",
        dex="hyperliquid",
        date=DAY1,
        rows=[
            {
                "ts_ms": DAY1_MS,
                "dex": "hyperliquid",
                "symbol": "BTC",
                "open": 100,
                "close": 101,
                "volume": 5,
            }
        ],
        row_groups=rg_mkt,
        estimated_filtered_return_rows=1,
        estimated_output_bytes=128,
    )

    # 1. Ex-post selection_known_at with require_pit=True fails closed with 0 remote calls.
    ex_post_req = _unit_request(
        root,
        dexes=["hyperliquid"],
        wallets=[W1],
        utc_end=f"{DAY2}T00:00:00+00:00",
        selection_known_at=KNOWN_AFTER,
        require_pit=True,
    )
    pit_out = acq.execute_bounded_acquisition(
        root, ex_post_req, provider=provider, run_id="pit-block"
    )
    assert pit_out["status"] == "BLOCKED"
    assert pit_out["error_code"] == "BLOCKED_EX_POST_COHORT_NOT_PIT"
    assert provider.total_requests == 0

    # 2. Holdout overlap fails closed with BLOCKED_HOLDOUT_VIOLATION and 0 remote calls.
    holdout_req = _unit_request(
        root,
        dexes=["hyperliquid"],
        wallets=[W1],
        utc_end=f"{DAY2}T00:00:00+00:00",
        acquisition={
            "unit_kinds": ["source"],
            "allowed_dexes": ["hyperliquid"],
            "projected_columns": {"source": list(SOURCE_COLS)},
            "budget": {"max_requests": 10, "max_remote_bytes": 50_000, "max_disk_bytes": 50_000},
            "holdout": {
                "windows": [{"utc_start": START, "utc_end": f"{DAY2}T00:00:00+00:00"}],
                "forbid_overlap": True,
            },
        },
    )
    hold_out = acq.execute_bounded_acquisition(
        root, holdout_req, provider=provider, run_id="hold-block"
    )
    assert hold_out["status"] == "BLOCKED"
    assert hold_out["error_code"] == "BLOCKED_HOLDOUT_VIOLATION"
    assert provider.total_requests == 0

    # 3. Purpose TRADING_AUTHORIZATION fails closed with 0 remote calls.
    auth_req = _unit_request(
        root,
        dexes=["hyperliquid"],
        wallets=[W1],
        utc_end=f"{DAY2}T00:00:00+00:00",
        purpose="TRADING_AUTHORIZATION",
    )
    auth_out = acq.execute_bounded_acquisition(
        root, auth_req, provider=provider, run_id="auth-block"
    )
    assert auth_out["status"] == "BLOCKED"
    assert auth_out["error_code"] == "REFUSED_NOT_REUSABLE_FOR_PURPOSE"
    assert provider.total_requests == 0

    # 4. Successful mixed source+market acquisition stays strictly nonqualified & nonauthoritative.
    mixed_req = _unit_request(
        root,
        dexes=["hyperliquid"],
        wallets=[W1],
        utc_end=f"{DAY2}T00:00:00+00:00",
        acquisition={
            "unit_kinds": ["source", "market"],
            "allowed_dexes": ["hyperliquid"],
            "projected_columns": {"source": list(SOURCE_COLS), "market": list(MARKET_COLS)},
            "budget": {"max_requests": 20, "max_remote_bytes": 50_000, "max_disk_bytes": 50_000},
            "holdout": {
                "windows": [{"utc_start": f"{DAY2}T00:00:00+00:00", "utc_end": TWO_DAY_END}],
                "wallets": [W2],
                "forbid_overlap": True,
            },
        },
    )
    ok_out = acq.execute_bounded_acquisition(root, mixed_req, provider=provider, run_id="mixed-ok")
    assert ok_out["status"] == "COMPLETE"
    assert set(ok_out["acquired_unit_keys"]) == {
        f"market:hyperliquid:{DAY1}",
        f"source:hyperliquid:{DAY1}",
    }
    assert ok_out["historical_oracle_only"] is True
    assert ok_out["scientifically_qualified"] is False
    assert ok_out["financial_certified_real"] is False
    assert ok_out["trading_authorized"] is False
    assert ok_out["executable_follower_pnl"] is False
    assert ok_out["campaign_auto_authorized"] is False
    assert ok_out["credential_collection_performed"] is False
    assert ok_out["service_scheduling_performed"] is False
    assert ok_out["paper_rollout_triggered"] is False
    assert all(v is False for v in ok_out["authority"].values())

    # Subsequent study with identical source inputs reuses published coverage receipts with 0 remote calls.
    recheck_provider = FakeS3ParquetProvider(observable_remote_bytes=True)
    recheck_req = _unit_request(
        root,
        receipts=ok_out["coverage_receipt_keys"],
        dexes=["hyperliquid"],
        wallets=[W1],
        utc_end=f"{DAY2}T00:00:00+00:00",
        acquisition={
            "unit_kinds": ["source"],
            "allowed_dexes": ["hyperliquid"],
            "projected_columns": {"source": list(SOURCE_COLS)},
            "budget": {"max_requests": 10, "max_remote_bytes": 50_000, "max_disk_bytes": 50_000},
        },
    )
    recheck_plan = acq.plan_bounded_acquisition(
        root, recheck_req, metadata_provider=recheck_provider
    )
    assert recheck_plan["acquisition_needed"] is False
    assert recheck_plan["missing_units"] == []
    assert recheck_plan["forecast"]["requests"] == 0
    assert recheck_provider.total_requests == 0

    # Acquired coverage never qualifies Chapter 2 runtime finance or projection.
    fin = gate.assess_financial_runtime(
        service_active=True,
        signed_portfolios=set(),
        finance_scans={},
        source_changes={"A": 100},
        journal_cursors={"A": 100},
        latest_source_checkpoint_ms=100,
        modeled_effects={"A": 0},
    )
    assert fin.state != "PASS"
    proj = projection.project(
        source={
            "source_count": len(gate.EXPECTED_WALLETS),
            "latest_kinds": {m: "BASELINE" for m in gate.EXPECTED_WALLETS},
            "head_sha256": sha("head"),
            "latest_checkpoint_ms": 1_000,
        },
        papers={},
        verified_finance=set(),
        qualified_k=set(),
        release_sha="0" * 40,
        epoch="2026-11-13",
    )
    assert proj["trading_authorized"] is False and proj["scientifically_qualified"] is False

    # 5. CLI read-only research preflight supports --partition-root and --plan-acquisition.
    _write_local_partition(
        part_root,
        kind="source",
        dex="hyperliquid",
        wallet=W1,
        date=DAY1,
        rows=[{"time": DAY1_MS, "user": W1, "dex": "hyperliquid"}],
    )
    cli_req = {
        **base_request(
            root,
            receipts=[],
            dexes=["hyperliquid"],
            wallets=[W1, W2],
            utc_start=START,
            utc_end=f"{DAY2}T00:00:00+00:00",
        ),
        "acquisition": {
            "unit_kinds": ["source"],
            "allowed_dexes": ["hyperliquid"],
            "projected_columns": {"source": list(SOURCE_COLS)},
            "budget": {"max_requests": 10, "max_remote_bytes": 5_000, "max_disk_bytes": 5_000},
            "remote_objects": {
                f"source:hyperliquid:{DAY1}": {
                    "etag": '"e1"',
                    "object_bytes": 25_000,
                    "schema_columns": list(SOURCE_COLS),
                    "row_groups": rg_src,
                    "estimated_filtered_return_rows": 1,
                    "estimated_output_bytes": 200,
                }
            },
        },
    }
    req_path = tmp_path / "cli_acq_req.json"
    req_path.write_text(json.dumps(cli_req))
    code = pm_operations.cli(
        [
            "research",
            "preflight",
            "--cache-root",
            str(root),
            "--request",
            str(req_path),
            "--partition-root",
            str(part_root),
            "--plan-acquisition",
        ]
    )
    assert code == 2  # Still blocked for missing W2 coverage, with full bounded plan attached!
    cli_out = json.loads(capsys.readouterr().out)
    acq_plan = cli_out["data"]["acquisition_plan"]
    assert acq_plan["status"] == "PLANNED"
    assert acq_plan["reused_local_partition_count"] == 1
    assert acq_plan["missing_units"][0]["target_wallets"] == [W2]
    assert acq_plan["forecast"]["remote_compressed_bytes"] == 600

    # Capability catalog validates cleanly after CLI updates.
    assert capabilities.validate(Path(__file__).resolve().parents[1])["status"] == "VERIFIED"
