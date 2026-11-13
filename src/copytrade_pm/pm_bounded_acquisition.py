"""Bounded remote research acquisition planning, cost forecasting, and verified recovery.

Owns bounded remote object/column/row-group cost estimation, read-only preflight
rechecking, concurrency- and budget-capped execution, and SHA-verified incremental
resumption on top of existing `ImmutableCache` and `pm_offline_job_catalog` reuse
contracts. Performs zero live credential collection, protected service mutation,
paper rollout, or trading authorization; retained outputs remain historical-only.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timedelta, UTC
from hashlib import sha256
import json
from pathlib import Path
import shutil
import threading
from time import perf_counter
from typing import Any

from .pm_acquisition_contracts import (
    MAX_ACQUISITION_WORKERS,
    AcquisitionContractError,
    BoundedAcquisitionBudget,
    epoch_ms,
    parse_acquisition_budget,
    predict_unit_cost,
    validate_parquet_framing,
    verify_local_immutable_partition,
)
from .pm_offline_cache import ImmutableCache
from .pm_offline_job_catalog import (
    AUTHORITY,
    COVERAGE_RECEIPT_SCHEMA,
    REUSE_SCHEMA,
    _canonical,
    _clock,
    _dexes,
    _sha,
    _token,
    _wallets,
    assess_reuse,
    load_verified_coverage_spans,
    sweep_coverage_intervals,
    verify_coverage_receipt_key,
)
from .pm_offline_manifest import ManifestBlocked

ACQUISITION_PLAN_SCHEMA = "pm_bounded_acquisition_plan_v1"
ACQUISITION_UNIT_SCHEMA = "pm_acquired_unit_v1"
ACQUISITION_RUN_SCHEMA = "pm_bounded_acquisition_run_v1"
ACQUISITION_ATTEMPT_SCHEMA = "pm_bounded_acquisition_attempt_v1"
MARKET_COVERAGE_SCHEMA = "pm_market_coverage_receipt_v1"
MAX_ACQUISITION_DAYS = 400
_TIME_FIELDS = ("time", "ts_ms", "time_ms", "timestamp_ms")


@dataclass(frozen=True)
class _PlanIdentity:
    immutable_inputs: dict[str, str]
    scope: dict[str, Any]
    request_context: dict[str, Any]
    budget: BoundedAcquisitionBudget
    acq: dict[str, Any]
    utc_start: datetime
    utc_end: datetime
    as_of: datetime
    unit_kinds: tuple[str, ...]
    allowed_dexes: tuple[str, ...]
    projected_columns: dict[str, tuple[str, ...]]


@dataclass(frozen=True)
class _PriorResumeState:
    stored_run: dict[str, Any]
    next_attempt: int
    verified_prior_units: dict[str, dict[str, Any]]
    prior_acquired_keys: dict[str, str]
    prior_cov_keys: list[str]
    prior_reqs: int
    prior_remote_read: int
    prior_comp_scanned: int
    prior_disk: int
    prior_obs: bool


@dataclass
class _BatchState:
    remote_bytes_observable: bool
    scan_requests: int = 0
    remote_bytes_read: int = 0
    compressed_scanned: int = 0
    disk_bytes: int = 0
    rows: int = 0
    reserved_reqs: int = 0
    reserved_bytes: int = 0
    reserved_disk: int = 0
    active_workers: int = 0
    max_observed_concurrency: int = 0
    completed: int = 0
    failed: int = 0
    cancelled: int = 0
    halted_error: tuple[str, str] | None = None
    new_acquired: dict[str, str] = field(default_factory=dict)
    new_covs: list[str] = field(default_factory=list)


def _iter_utc_days(start: datetime, end: datetime) -> list[tuple[str, datetime, datetime]]:
    days: list[tuple[str, datetime, datetime]] = []
    cur = start.date()
    last = (end - timedelta(microseconds=1)).date()
    while cur <= last:
        day_start = datetime(cur.year, cur.month, cur.day, tzinfo=UTC)
        span_start = max(start, day_start)
        span_end = min(end, day_start + timedelta(days=1))
        days.append((cur.isoformat(), span_start, span_end))
        cur += timedelta(days=1)
        if len(days) > MAX_ACQUISITION_DAYS:
            raise ValueError("ACQUISITION_WINDOW_EXCEEDS_MAX_DAYS")
    return days


def _validate_projected_columns(
    raw: object, unit_kinds: tuple[str, ...]
) -> dict[str, tuple[str, ...]]:
    out: dict[str, tuple[str, ...]] = {}
    if isinstance(raw, (list, tuple)):
        cols = tuple(raw)
        for kind in unit_kinds:
            out[kind] = cols
    elif isinstance(raw, dict):
        for kind in unit_kinds:
            if kind not in raw or not isinstance(raw[kind], (list, tuple)):
                raise ValueError(f"MISSING_PROJECTED_COLUMNS:{kind}")
            out[kind] = tuple(raw[kind])
    else:
        raise ValueError("INVALID_PROJECTED_COLUMNS")
    for kind, cols in out.items():
        if not cols or any(
            not isinstance(c, str) or not c.strip() or c.strip() == "*" for c in cols
        ):
            raise ValueError(f"INVALID_OR_WILDCARD_PROJECTION:{kind}")
        if len(set(cols)) != len(cols):
            raise ValueError(f"DUPLICATE_PROJECTED_COLUMN:{kind}")
    return out


def _base_non_authority_flags() -> dict[str, Any]:
    return {
        "authority": dict(AUTHORITY),
        "scientifically_qualified": False,
        "financial_certified_real": False,
        "trading_authorized": False,
        "executable_follower_pnl": False,
        "campaign_auto_authorized": False,
        "credential_collection_performed": False,
        "service_scheduling_performed": False,
        "paper_rollout_triggered": False,
    }


def _empty_forecast(head_requests_made: int = 0) -> dict[str, Any]:
    return {
        "requests": 0,
        "metadata_requests": head_requests_made,
        "scan_requests": 0,
        "remote_object_bytes": 0,
        "remote_compressed_bytes": 0,
        "disk_bytes": 0,
        "unit_count": 0,
        "estimated_filtered_return_rows": None,
        "selected_row_groups": 0,
        "stats_pruned_row_groups": 0,
    }


def _blocked_plan(
    *,
    code: str,
    reason: str,
    request_binding_sha256: str | None = None,
    plan_binding_sha256: str | None = None,
    immutable_inputs: dict[str, str] | None = None,
    reuse: dict[str, Any] | None = None,
    forecast: dict[str, Any] | None = None,
    head_requests_made: int = 0,
    detail: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "schema": ACQUISITION_PLAN_SCHEMA,
        "status": "BLOCKED",
        "state": code,
        "error_code": code,
        "reason": reason,
        "plan_ready": False,
        "acquisition_allowed": False,
        "acquisition_needed": None,
        "request_binding_sha256": request_binding_sha256,
        "plan_binding_sha256": plan_binding_sha256,
        "immutable_inputs": immutable_inputs or {},
        "reuse": reuse,
        "missing_units": [],
        "reused_units": [],
        "reused_local_partition_count": 0,
        "reused_coverage_receipt_count": 0,
        "reused_acquired_unit_count": 0,
        "scan_calls_made": 0,
        "head_requests_made": head_requests_made,
        "forecast": forecast or _empty_forecast(head_requests_made),
        "detail": detail or {},
        **_base_non_authority_flags(),
    }


def _classify_provider_error(exc: BaseException) -> tuple[str, str]:
    if isinstance(exc, AcquisitionContractError):
        return exc.code, str(exc)
    if isinstance(exc, PermissionError):
        msg = str(exc)
        return (
            ("PROVIDER_CREDENTIAL_FAILURE", msg)
            if "cred" in msg.lower()
            else (
                "PERMISSION_EXPIRED",
                msg,
            )
        )
    if isinstance(exc, KeyError):
        return "REMOTE_OBJECT_MISSING", f"Remote unit missing: {exc}"
    if isinstance(exc, TimeoutError):
        return "PROVIDER_TIMEOUT", str(exc)
    if isinstance(exc, OSError):
        return "PROVIDER_IO_FAILURE", str(exc)
    return "PROVIDER_FAILURE", str(exc)


def _extract_row_timestamp(row: dict[str, Any]) -> Any:
    for field_name in _TIME_FIELDS:
        if field_name in row and row[field_name] is not None:
            return row[field_name]
    return None


def _validate_scan_result(unit: dict[str, Any], scan_res: object) -> list[dict[str, Any]]:
    if not isinstance(scan_res, dict):
        raise AcquisitionContractError("CORRUPT_REMOTE_PAGE", "INVALID_SCAN_RESULT")
    for coord in ("kind", "dex", "date"):
        if coord in scan_res and scan_res[coord] != unit[coord]:
            raise AcquisitionContractError("SCOPE_VIOLATION", f"MISMATCHED_{coord.upper()}")
    expected_etag = unit.get("etag")
    if expected_etag is not None and scan_res.get("etag") != expected_etag:
        raise AcquisitionContractError("REMOTE_OBJECT_MUTATED", "ETAG_CHANGED_MID_READ")

    raw_bytes = scan_res.get("parquet_bytes")
    if raw_bytes is not None:
        if not isinstance(raw_bytes, (bytes, bytearray)):
            raise AcquisitionContractError("CORRUPT_REMOTE_PAGE", "INVALID_PARQUET_BUFFER")
        raw_buf = bytes(raw_bytes)
        validate_parquet_framing(raw_buf)
        declared_sha = scan_res.get("payload_sha256")
        if declared_sha is not None and sha256(raw_buf).hexdigest() != declared_sha:
            raise AcquisitionContractError("CORRUPT_REMOTE_PAGE", "PAYLOAD_SHA256_MISMATCH")

    if scan_res.get("source_verified") is not True:
        raise AcquisitionContractError("CORRUPT_REMOTE_PAGE", "UNVERIFIED_SOURCE_PAGE")

    rows = scan_res.get("rows")
    if not isinstance(rows, list):
        raise AcquisitionContractError("CORRUPT_REMOTE_PAGE", "INVALID_ROWS_LIST")
    if not rows and scan_res.get("empty_verified") is not True:
        raise AcquisitionContractError("CORRUPT_REMOTE_PAGE", "UNVERIFIED_EMPTY_RESPONSE")

    span_start_ms = epoch_ms(unit["utc_start"])
    span_end_ms = epoch_ms(unit["utc_end"])
    allowed_wallets = set(unit.get("target_wallets") or ())
    validated: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            raise AcquisitionContractError("CORRUPT_REMOTE_PAGE", "INVALID_ROW_TYPE")
        if "dex" in row and row["dex"] != unit["dex"]:
            raise AcquisitionContractError("SCOPE_VIOLATION", f"ROW_DEX_OUT_OF_SCOPE:{row['dex']}")
        if unit["kind"] == "source":
            row_wallet = row.get("user") if "user" in row else row.get("wallet")
            if not isinstance(row_wallet, str) or row_wallet not in allowed_wallets:
                raise AcquisitionContractError(
                    "SCOPE_VIOLATION", f"ROW_WALLET_OUT_OF_SCOPE:{row_wallet}"
                )
        row_ts = _extract_row_timestamp(row)
        if row_ts is None:
            raise AcquisitionContractError("SCOPE_VIOLATION", "ROW_TIME_MISSING")
        if type(row_ts) is not int or row_ts < span_start_ms or row_ts >= span_end_ms:
            raise AcquisitionContractError("SCOPE_VIOLATION", f"ROW_TIME_OUT_OF_SCOPE:{row_ts}")
        validated.append(row)
    return validated


def _available_disk_bytes(path: Path) -> int | None:
    cur = path
    while not cur.exists():
        if cur.is_symlink() or cur.parent == cur:
            return None
        cur = cur.parent
    if cur.is_symlink():
        return None
    try:
        return int(shutil.disk_usage(cur).free)
    except OSError:
        return None


def _unit_cache_deps(
    *,
    plan_binding_sha256: str,
    unit: dict[str, Any],
    immutable_inputs: dict[str, str],
) -> dict[str, str]:
    return {
        "plan_binding": plan_binding_sha256,
        "unit_id": sha256(unit["unit_id"].encode()).hexdigest(),
        "input": immutable_inputs["input_sha256"],
        "source": immutable_inputs["source_sha256"],
        "market": immutable_inputs["market_sha256"],
        "target_wallets": sha256(_canonical(list(unit["target_wallets"]))).hexdigest(),
        "projected_columns": sha256(_canonical(list(unit["projected_columns"]))).hexdigest(),
    }


def _market_coverage_deps(
    *,
    dex: str,
    day_str: str,
    immutable_inputs: dict[str, str],
    projected_columns: list[str],
) -> dict[str, str]:
    return {
        "input": immutable_inputs["input_sha256"],
        "source": immutable_inputs["source_sha256"],
        "market": immutable_inputs["market_sha256"],
        "dex": sha256(dex.encode()).hexdigest(),
        "day": sha256(day_str.encode()).hexdigest(),
        "projected_columns": sha256(_canonical(list(projected_columns))).hexdigest(),
    }


def _check_holdout_constraints(
    acq: dict[str, Any],
    *,
    wallets: list[str],
    utc_start: datetime,
    utc_end: datetime,
) -> str | None:
    holdout = acq.get("holdout")
    if holdout is None:
        return None
    if not isinstance(holdout, dict):
        raise ValueError("INVALID_HOLDOUT_CONFIG")
    forbid_overlap = holdout.get("forbid_overlap", True)
    if type(forbid_overlap) is not bool:
        raise ValueError("INVALID_HOLDOUT_FORBID_OVERLAP")
    raw_windows = holdout.get("windows") or []
    if not isinstance(raw_windows, (list, tuple)):
        raise ValueError("INVALID_HOLDOUT_WINDOWS")
    parsed_windows: list[tuple[datetime, datetime]] = []
    for win in raw_windows:
        if not isinstance(win, dict):
            raise ValueError("INVALID_HOLDOUT_WINDOW")
        h_start = _clock(win.get("utc_start"), "holdout.utc_start")
        h_end = _clock(win.get("utc_end"), "holdout.utc_end")
        if h_end <= h_start:
            raise ValueError("EMPTY_HOLDOUT_WINDOW")
        parsed_windows.append((h_start, h_end))
    raw_h_wallets = holdout.get("wallets") or []
    h_wallets = _wallets(raw_h_wallets) if raw_h_wallets else []
    if forbid_overlap:
        if any(utc_start < h_end and utc_end > h_start for h_start, h_end in parsed_windows):
            return "BLOCKED_HOLDOUT_VIOLATION"
        if h_wallets and (set(wallets) & set(h_wallets)):
            return "BLOCKED_HOLDOUT_VIOLATION"
    return None


def _compute_plan_identity(request: dict[str, Any]) -> _PlanIdentity:
    if not isinstance(request, dict):
        raise ValueError("INVALID_REQUEST")
    acq = request.get("acquisition") or {}
    if not isinstance(acq, dict):
        raise ValueError("INVALID_ACQUISITION_CONFIG")
    immutable_inputs = {
        "job_sha256": _sha(request.get("job_sha256"), "job_sha256"),
        "input_sha256": _sha(request.get("input_sha256"), "input_sha256"),
        "source_sha256": _sha(request.get("source_sha256"), "source_sha256"),
        "market_sha256": _sha(request.get("market_sha256"), "market_sha256"),
        "software_sha256": _sha(request.get("software_sha256"), "software_sha256"),
    }
    wallets = _wallets(request.get("wallets"))
    dexes = _dexes(request.get("dexes"))
    utc_start = _clock(request.get("utc_start"), "utc_start")
    utc_end = _clock(request.get("utc_end"), "utc_end")
    as_of = _clock(request.get("as_of"), "as_of")
    raw_kinds = acq.get("unit_kinds") or ["source"]
    if (
        not isinstance(raw_kinds, (list, tuple))
        or not raw_kinds
        or any(k not in {"source", "market"} for k in raw_kinds)
    ):
        raise ValueError("INVALID_UNIT_KINDS")
    unit_kinds = tuple(sorted(set(raw_kinds)))
    projected_columns = _validate_projected_columns(acq.get("projected_columns") or {}, unit_kinds)
    budget = parse_acquisition_budget(acq.get("budget") or {})
    raw_allowed = acq.get("allowed_dexes")
    allowed_dexes = tuple(_dexes(raw_allowed)) if raw_allowed is not None else tuple(dexes)

    known_raw = request.get("selection_known_at")
    sel_known = (
        _clock(known_raw, "SELECTION_KNOWN_AT").isoformat() if known_raw is not None else None
    )
    req_context = {
        "as_of": as_of.isoformat(),
        "cost_assumption": request.get("cost_assumption"),
        "policy": request.get("policy"),
        "report_schema": request.get("report_schema"),
        "selection_known_at": sel_known,
        "require_pit": request.get("require_pit", False),
        "purpose": request.get("purpose", "RESEARCH_PREFLIGHT"),
        "holdout": acq.get("holdout"),
    }
    scope = {
        "cohort": _token(request.get("cohort"), "cohort"),
        "wallets": wallets,
        "dexes": dexes,
        "utc_start": request["utc_start"],
        "utc_end": request["utc_end"],
        "allowed_dexes": list(allowed_dexes),
        "unit_kinds": list(unit_kinds),
        "projected_columns": {k: list(v) for k, v in sorted(projected_columns.items())},
    }
    return _PlanIdentity(
        immutable_inputs=immutable_inputs,
        scope=scope,
        request_context=req_context,
        budget=budget,
        acq=acq,
        utc_start=utc_start,
        utc_end=utc_end,
        as_of=as_of,
        unit_kinds=unit_kinds,
        allowed_dexes=allowed_dexes,
        projected_columns=projected_columns,
    )


def _load_json_from_cache(
    store: ImmutableCache,
    kind: str,
    deps: dict[str, str],
    version: str,
) -> tuple[dict[str, Any] | None, bytes | None, str | None]:
    if store.has_unsealed_payload(kind, deps, version=version):
        return None, None, "PARTIAL_IMMUTABLE_UNIT"
    try:
        raw = store.load(kind, deps, version=version)
    except ManifestBlocked as exc:
        msg = str(exc)
        if "CORRUPT_CACHE_SHA" in msg or "CACHE_DEPENDENCY_MISMATCH" in msg:
            return None, None, "CORRUPT_CACHE_SHA"
        return None, None, "CORRUPT_RECEIPT"
    if raw is None:
        return None, None, None
    try:
        doc = json.loads(raw.decode("utf-8"))
    except UnicodeDecodeError, json.JSONDecodeError:
        return None, None, "CORRUPT_CACHE_SHA"
    if not isinstance(doc, dict):
        return None, None, "CORRUPT_CACHE_SHA"
    return doc, raw, None


def _lookup_verified_market_coverage(
    root: Path,
    *,
    dex: str,
    day_str: str,
    immutable_inputs: dict[str, str],
    projected_cols: list[str],
    as_of: datetime,
) -> tuple[dict[str, Any] | None, str | None]:
    """Read and verify cross-study `market_coverage` without creating directories."""
    if not (root / "market_coverage").exists():
        return None, None
    if (root / "market_coverage").is_symlink() or root.is_symlink():
        return None, "CORRUPT_RECEIPT"
    store = ImmutableCache(root, min_free_bytes=0)
    mc_deps = _market_coverage_deps(
        dex=dex,
        day_str=day_str,
        immutable_inputs=immutable_inputs,
        projected_columns=projected_cols,
    )
    mcdoc, _, err = _load_json_from_cache(store, "market_coverage", mc_deps, MARKET_COVERAGE_SCHEMA)
    if err is not None:
        return None, err
    if mcdoc is None:
        return None, None
    if (
        mcdoc.get("schema") != MARKET_COVERAGE_SCHEMA
        or mcdoc.get("dex") != dex
        or mcdoc.get("date") != day_str
        or mcdoc.get("input_sha256") != immutable_inputs["input_sha256"]
        or mcdoc.get("source_sha256") != immutable_inputs["source_sha256"]
        or mcdoc.get("market_sha256") != immutable_inputs["market_sha256"]
        or mcdoc.get("source_verified") is not True
    ):
        return None, "CORRUPT_RECEIPT"
    row_count = mcdoc.get("row_count")
    if type(row_count) is not int or row_count < 0:
        return None, "CORRUPT_RECEIPT"
    if row_count == 0 and mcdoc.get("empty_verified") is not True:
        return None, "CORRUPT_RECEIPT"
    try:
        known_at = _clock(mcdoc.get("known_at"), "MARKET_KNOWN_AT")
    except ValueError:
        return None, "CORRUPT_RECEIPT"
    if known_at > as_of:
        return None, None
    mc_key = ImmutableCache.identity("market_coverage", mc_deps, version=MARKET_COVERAGE_SCHEMA)
    return {"key": mc_key, "doc": mcdoc}, None


def _local_reuse_entry(
    *,
    unit_key: str,
    kind: str,
    dex: str,
    day_str: str,
    local_hit: dict[str, Any],
    wallet: str | None = None,
) -> dict[str, Any]:
    entry: dict[str, Any] = {
        "unit_id": unit_key,
        "kind": kind,
        "dex": dex,
        "date": day_str,
    }
    if wallet is not None:
        entry["wallet"] = wallet
    entry.update(
        {
            "reuse_source": "local_immutable_partition",
            "sha256": local_hit["sha256"],
            "bytes": local_hit["bytes"],
            "rows": local_hit["rows"],
        }
    )
    return entry


def _resolve_source_unit(
    *,
    unit_key: str,
    dex: str,
    day_str: str,
    span_start: datetime,
    span_end: datetime,
    wallets: list[str],
    as_of: datetime,
    immutable_inputs: dict[str, str],
    partition_root: Path | None,
    cov_spans: dict[tuple[str, str], list[tuple[datetime, datetime, str]]],
) -> dict[str, Any]:
    reused: list[dict[str, Any]] = []
    cov_keys_used: set[str] = set()
    local_hits = 0
    missing_wallets: list[str] = []

    for wallet in wallets:
        if partition_root is not None:
            try:
                local_hit = verify_local_immutable_partition(
                    partition_root,
                    kind="source",
                    dex=dex,
                    wallet=wallet,
                    date=day_str,
                    as_of=as_of,
                    input_sha256=immutable_inputs["input_sha256"],
                    source_sha256=immutable_inputs["source_sha256"],
                    market_sha256=immutable_inputs["market_sha256"],
                )
            except AcquisitionContractError as exc:
                return {"error": (exc.code, str(exc), {"unit_id": unit_key, "wallet": wallet})}
            if local_hit["reusable"]:
                local_hits += 1
                reused.append(
                    _local_reuse_entry(
                        unit_key=unit_key,
                        kind="source",
                        dex=dex,
                        day_str=day_str,
                        local_hit=local_hit,
                        wallet=wallet,
                    )
                )
                continue
        covered, _, cov_keys = sweep_coverage_intervals(
            cov_spans.get((wallet, dex), []), span_start, span_end
        )
        if covered and cov_keys:
            cov_keys_used.update(cov_keys)
            reused.append(
                {
                    "unit_id": unit_key,
                    "kind": "source",
                    "dex": dex,
                    "date": day_str,
                    "wallet": wallet,
                    "reuse_source": "coverage_receipt",
                    "coverage_receipt_keys": cov_keys,
                }
            )
            continue
        missing_wallets.append(wallet)

    return {
        "error": None,
        "target_wallets": sorted(missing_wallets) if missing_wallets else None,
        "reused_entries": reused,
        "local_hits": local_hits,
        "cov_keys": cov_keys_used,
    }


def _resolve_market_unit(
    root: Path,
    *,
    unit_key: str,
    dex: str,
    day_str: str,
    projected_cols: list[str],
    as_of: datetime,
    immutable_inputs: dict[str, str],
    partition_root: Path | None,
) -> dict[str, Any]:
    if partition_root is not None:
        try:
            local_hit = verify_local_immutable_partition(
                partition_root,
                kind="market",
                dex=dex,
                wallet="all",
                date=day_str,
                as_of=as_of,
                input_sha256=immutable_inputs["input_sha256"],
                source_sha256=immutable_inputs["source_sha256"],
                market_sha256=immutable_inputs["market_sha256"],
            )
        except AcquisitionContractError as exc:
            return {"error": (exc.code, str(exc), {"unit_id": unit_key})}
        if local_hit["reusable"]:
            return {
                "error": None,
                "reused": True,
                "reused_entry": _local_reuse_entry(
                    unit_key=unit_key,
                    kind="market",
                    dex=dex,
                    day_str=day_str,
                    local_hit=local_hit,
                ),
                "local_hits": 1,
                "cov_keys": set(),
            }

    mc_hit, mc_err = _lookup_verified_market_coverage(
        root,
        dex=dex,
        day_str=day_str,
        immutable_inputs=immutable_inputs,
        projected_cols=projected_cols,
        as_of=as_of,
    )
    if mc_err is not None:
        return {
            "error": (
                mc_err,
                f"Corrupt market coverage receipt for {unit_key}",
                {"unit_id": unit_key},
            )
        }
    if mc_hit is not None:
        return {
            "error": None,
            "reused": True,
            "reused_entry": {
                "unit_id": unit_key,
                "kind": "market",
                "dex": dex,
                "date": day_str,
                "reuse_source": "market_coverage_receipt",
                "market_coverage_key": mc_hit["key"],
            },
            "local_hits": 0,
            "cov_keys": set(),
        }
    return {"error": None, "reused": False, "local_hits": 0, "cov_keys": set()}


def _collect_plan_units(
    root: Path,
    *,
    identity: _PlanIdentity,
    day_slices: list[tuple[str, datetime, datetime]],
    partition_root: Path | None,
    cov_spans: dict[tuple[str, str], list[tuple[datetime, datetime, str]]],
    verified_unit_digests: dict[str, dict[str, Any]] | None,
) -> dict[str, Any]:
    missing_units: list[dict[str, Any]] = []
    reused_units: list[dict[str, Any]] = []
    reused_local_partition_count = 0
    reused_cov_keys: set[str] = set()
    reused_acquired_unit_count = 0
    wallets: list[str] = identity.scope["wallets"]

    for kind in identity.unit_kinds:
        projected_cols = list(identity.projected_columns[kind])
        for dex in identity.scope["dexes"]:
            for day_str, span_start, span_end in day_slices:
                unit_key = f"{kind}:{dex}:{day_str}"
                prior_unit = (verified_unit_digests or {}).get(unit_key)
                if prior_unit is not None:
                    reused_acquired_unit_count += 1
                    reused_units.append(
                        {
                            "unit_id": unit_key,
                            "kind": kind,
                            "dex": dex,
                            "date": day_str,
                            "reuse_source": "acquired_unit",
                            "sha256": prior_unit["sha256"],
                            "target_wallets": list(prior_unit.get("target_wallets", wallets)),
                        }
                    )
                    continue

                if kind == "source":
                    src = _resolve_source_unit(
                        unit_key=unit_key,
                        dex=dex,
                        day_str=day_str,
                        span_start=span_start,
                        span_end=span_end,
                        wallets=wallets,
                        as_of=identity.as_of,
                        immutable_inputs=identity.immutable_inputs,
                        partition_root=partition_root,
                        cov_spans=cov_spans,
                    )
                    if src["error"] is not None:
                        return {"error": src["error"]}
                    reused_units.extend(src["reused_entries"])
                    reused_local_partition_count += src["local_hits"]
                    reused_cov_keys.update(src["cov_keys"])
                    if src["target_wallets"] is None:
                        continue
                    target_wallets = src["target_wallets"]
                else:
                    mkt = _resolve_market_unit(
                        root,
                        unit_key=unit_key,
                        dex=dex,
                        day_str=day_str,
                        projected_cols=projected_cols,
                        as_of=identity.as_of,
                        immutable_inputs=identity.immutable_inputs,
                        partition_root=partition_root,
                    )
                    if mkt["error"] is not None:
                        return {"error": mkt["error"]}
                    reused_local_partition_count += mkt["local_hits"]
                    reused_cov_keys.update(mkt["cov_keys"])
                    if mkt["reused"]:
                        reused_units.append(mkt["reused_entry"])
                        continue
                    target_wallets = []

                missing_units.append(
                    {
                        "unit_id": unit_key,
                        "kind": kind,
                        "dex": dex,
                        "date": day_str,
                        "utc_start": span_start.isoformat(),
                        "utc_end": span_end.isoformat(),
                        "target_wallets": target_wallets,
                        "projected_columns": projected_cols,
                    }
                )

    return {
        "error": None,
        "missing_units": missing_units,
        "reused_units": reused_units,
        "reused_local_partition_count": reused_local_partition_count,
        "reused_coverage_receipt_count": len(reused_cov_keys),
        "reused_acquired_unit_count": reused_acquired_unit_count,
    }


def _inspect_and_forecast_units(
    root: Path,
    *,
    missing_units: list[dict[str, Any]],
    acq: dict[str, Any],
    budget: BoundedAcquisitionBudget,
    metadata_provider: Any | None,
    effective_request_cap: int,
    min_free_bytes: int,
) -> tuple[dict[str, Any] | None, int, dict[str, Any] | None]:
    """Inspect remote unit metadata, predict pruned byte/request cost, and check budget caps."""
    head_requests_made = 0
    total_meta_requests = 0
    total_scan_requests = 0
    total_object_bytes = 0
    total_compressed_bytes = 0
    total_disk_bytes = 0
    total_selected_rgs = 0
    total_pruned_rgs = 0
    unit_row_estimates: list[int | None] = []
    remote_objects_map = acq.get("remote_objects") or {}

    for unit in missing_units:
        unit_id = unit["unit_id"]
        if metadata_provider is not None:
            if head_requests_made >= effective_request_cap:
                return (
                    None,
                    head_requests_made,
                    {
                        "code": "BUDGET_EXHAUSTED",
                        "reason": "Request budget exhausted during metadata inspection",
                        "detail": {"breach": "max_requests", "limit": effective_request_cap},
                    },
                )
            head_requests_made += 1
            try:
                meta = metadata_provider.inspect_unit(unit)
            except (
                AcquisitionContractError,
                PermissionError,
                TimeoutError,
                OSError,
                KeyError,
            ) as exc:
                err_code, err_msg = _classify_provider_error(exc)
                return (
                    None,
                    head_requests_made,
                    {"code": err_code, "reason": err_msg, "detail": {"unit_id": unit_id}},
                )
        elif isinstance(remote_objects_map, dict) and unit_id in remote_objects_map:
            meta = remote_objects_map[unit_id]
        else:
            return (
                None,
                head_requests_made,
                {
                    "code": "REMOTE_METADATA_UNAVAILABLE",
                    "reason": f"Remote metadata required to bound cost for {unit_id}",
                    "detail": {"unit_id": unit_id},
                },
            )

        try:
            cost = predict_unit_cost(unit, meta)
        except AcquisitionContractError as exc:
            return (
                None,
                head_requests_made,
                {"code": exc.code, "reason": str(exc), "detail": {"unit_id": unit_id}},
            )
        unit["etag"] = meta.get("etag") if isinstance(meta, dict) else None
        unit["object_bytes"] = cost["predicted_remote_object_bytes"]
        unit["cost"] = cost
        total_meta_requests += cost["metadata_requests"]
        total_scan_requests += cost["scan_requests"]
        total_object_bytes += cost["predicted_remote_object_bytes"]
        total_compressed_bytes += cost["predicted_remote_compressed_bytes"]
        total_disk_bytes += cost["predicted_disk_bytes"]
        total_selected_rgs += len(cost["selected_row_groups"])
        total_pruned_rgs += cost["stats_pruned_row_groups"]
        unit_row_estimates.append(cost["estimated_filtered_return_rows"])

    if not missing_units:
        estimated_filtered_rows: int | None = 0
    elif (
        unit_row_estimates
        and len(unit_row_estimates) == len(missing_units)
        and all(r is not None for r in unit_row_estimates)
    ):
        estimated_filtered_rows = sum(int(r) for r in unit_row_estimates if r is not None)
    else:
        estimated_filtered_rows = None

    forecast = {
        "requests": total_meta_requests + total_scan_requests,
        "metadata_requests": total_meta_requests,
        "scan_requests": total_scan_requests,
        "remote_object_bytes": total_object_bytes,
        "remote_compressed_bytes": total_compressed_bytes,
        "disk_bytes": total_disk_bytes,
        "unit_count": len(missing_units),
        "estimated_filtered_return_rows": estimated_filtered_rows,
        "selected_row_groups": total_selected_rgs,
        "stats_pruned_row_groups": total_pruned_rgs,
    }

    cap_checks = (
        ("max_requests", forecast["requests"], effective_request_cap),
        ("max_remote_bytes", forecast["remote_compressed_bytes"], budget.max_remote_bytes),
        ("max_disk_bytes", forecast["disk_bytes"], budget.max_disk_bytes),
    )
    for breach_name, predicted, limit in cap_checks:
        if predicted > limit:
            return (
                forecast,
                head_requests_made,
                {
                    "code": "BUDGET_EXHAUSTED",
                    "reason": f"Forecast exceeds {breach_name} cap",
                    "detail": {"breach": breach_name, "predicted": predicted, "limit": limit},
                },
            )

    disk_free = _available_disk_bytes(root)
    if disk_free is not None and disk_free - forecast["disk_bytes"] < min_free_bytes:
        return (
            forecast,
            head_requests_made,
            {
                "code": "INSUFFICIENT_DISK_HEADROOM",
                "reason": "Insufficient disk headroom for predicted local acquisition output",
                "detail": {"disk_free_bytes": disk_free, "min_free_bytes": min_free_bytes},
            },
        )
    return forecast, head_requests_made, None


def plan_bounded_acquisition(
    root: Path,
    request: dict,
    *,
    partition_root: Path | None = None,
    metadata_provider: Any | None = None,
    verified_unit_digests: dict[str, dict[str, Any]] | None = None,
    remaining_request_budget: int | None = None,
    reuse: dict[str, Any] | None = None,
    min_free_bytes: int = 0,
) -> dict[str, Any]:
    """Read-only preflight over declared scope, local partitions, and remote cost bounds."""
    if not isinstance(request, dict):
        raise ValueError("INVALID_REQUEST")
    acq = request.get("acquisition") or {}
    if not isinstance(acq, dict):
        raise ValueError("INVALID_ACQUISITION_CONFIG")

    if reuse is None:
        base_req = {k: v for k, v in request.items() if k != "acquisition"}
        reuse = assess_reuse(root, base_req)
    elif reuse.get("schema") != REUSE_SCHEMA:
        raise ValueError("INVALID_REUSE_RECEIPT")

    identity = _compute_plan_identity(request)
    budget = identity.budget
    plan_spec: dict[str, Any] = {
        "schema": ACQUISITION_PLAN_SCHEMA,
        "request_binding_sha256": reuse["request_binding_sha256"],
        "unit_kinds": identity.scope["unit_kinds"],
        "allowed_dexes": identity.scope["allowed_dexes"],
        "projected_columns": identity.scope["projected_columns"],
        "budget": budget.model_dump(),
    }
    if "holdout" in acq and acq["holdout"] is not None:
        plan_spec["holdout"] = acq["holdout"]
    plan_binding_sha256 = sha256(_canonical(plan_spec)).hexdigest()

    def _block(
        code: str,
        reason: str,
        *,
        forecast: dict[str, Any] | None = None,
        head_requests_made: int = 0,
        detail: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return _blocked_plan(
            code=code,
            reason=reason,
            request_binding_sha256=reuse["request_binding_sha256"],
            plan_binding_sha256=plan_binding_sha256,
            immutable_inputs=identity.immutable_inputs,
            reuse=reuse,
            forecast=forecast,
            head_requests_made=head_requests_made,
            detail=detail,
        )

    holdout_err = _check_holdout_constraints(
        acq,
        wallets=identity.scope["wallets"],
        utc_start=identity.utc_start,
        utc_end=identity.utc_end,
    )
    if reuse["state"] in {
        "REFUSED_NOT_REUSABLE_FOR_PURPOSE",
        "BLOCKED_EX_POST_COHORT_NOT_PIT",
        "CORRUPT_RECEIPT",
    }:
        return _block(reuse["state"], f"Preflight blocked by T13 reuse check: {reuse['state']}")

    if (
        request.get("require_pit") is True
        and reuse["pit"]["status"] != "SELECTION_KNOWN_BEFORE_WINDOW"
    ):
        return _block(
            "BLOCKED_EX_POST_COHORT_NOT_PIT",
            "Ex-post cohort cannot acquire remote data under require_pit=True",
        )
    if holdout_err is not None:
        return _block(holdout_err, "Study scope overlaps protected holdout split")

    disallowed = sorted(set(identity.scope["dexes"]) - set(identity.allowed_dexes))
    if disallowed:
        return _block(
            "BLOCKED_DISALLOWED_DEX",
            f"Requested DEX outside allowed scope: {disallowed}",
            detail={"disallowed_dexes": disallowed},
        )

    day_slices = _iter_utc_days(identity.utc_start, identity.utc_end)
    cov_spans, cov_err = load_verified_coverage_spans(
        root,
        list(request.get("coverage_receipts") or ()),
        as_of=identity.as_of,
        input_sha=identity.immutable_inputs["input_sha256"],
        source_sha=identity.immutable_inputs["source_sha256"],
    )
    if cov_err is not None:
        return _block(cov_err, "Corrupt or unverified coverage receipt encountered")

    collected = _collect_plan_units(
        root,
        identity=identity,
        day_slices=day_slices,
        partition_root=partition_root,
        cov_spans=cov_spans,
        verified_unit_digests=verified_unit_digests,
    )
    if collected["error"] is not None:
        err_code, err_reason, err_detail = collected["error"]
        return _block(err_code, err_reason, detail=err_detail)

    missing_units = collected["missing_units"]
    effective_request_cap = (
        budget.max_requests
        if remaining_request_budget is None
        else min(budget.max_requests, max(0, remaining_request_budget))
    )
    forecast, head_requests_made, inspect_block = _inspect_and_forecast_units(
        root,
        missing_units=missing_units,
        acq=acq,
        budget=budget,
        metadata_provider=metadata_provider,
        effective_request_cap=effective_request_cap,
        min_free_bytes=min_free_bytes,
    )
    if inspect_block is not None:
        return _block(
            inspect_block["code"],
            inspect_block["reason"],
            forecast=forecast,
            head_requests_made=head_requests_made,
            detail=inspect_block["detail"],
        )

    return {
        "schema": ACQUISITION_PLAN_SCHEMA,
        "status": "PLANNED",
        "state": "PLANNED" if missing_units else "REUSED_NO_MISSING_UNITS",
        "error_code": None,
        "plan_ready": True,
        "acquisition_allowed": True,
        "acquisition_needed": bool(missing_units),
        "request_binding_sha256": reuse["request_binding_sha256"],
        "plan_binding_sha256": plan_binding_sha256,
        "budget": budget.model_dump(),
        "immutable_inputs": identity.immutable_inputs,
        "reuse": reuse,
        "pit": reuse["pit"],
        "missing_units": missing_units,
        "reused_units": collected["reused_units"],
        "reused_local_partition_count": collected["reused_local_partition_count"],
        "reused_coverage_receipt_count": collected["reused_coverage_receipt_count"],
        "reused_acquired_unit_count": collected["reused_acquired_unit_count"],
        "scan_calls_made": 0,
        "head_requests_made": head_requests_made,
        "forecast": forecast,
        **_base_non_authority_flags(),
    }


def _prepare_unit_artifacts(
    *,
    plan_binding_sha256: str,
    unit: dict[str, Any],
    scan_result: dict[str, Any],
    rows: list[dict[str, Any]],
    immutable_inputs: dict[str, str],
) -> tuple[
    bytes,
    dict[str, str],
    list[tuple[bytes, dict[str, str]]],
    tuple[bytes, dict[str, str]] | None,
    int,
]:
    deps = _unit_cache_deps(
        plan_binding_sha256=plan_binding_sha256,
        unit=unit,
        immutable_inputs=immutable_inputs,
    )
    unit_key = ImmutableCache.identity("acquired_unit", deps, version=ACQUISITION_UNIT_SCHEMA)

    cov_items: list[tuple[bytes, dict[str, str]]] = []
    cov_keys: list[str] = []
    market_cov_item: tuple[bytes, dict[str, str]] | None = None
    market_cov_key: str | None = None
    disk_bytes = 0

    if unit["kind"] == "source":
        by_wallet: dict[str, list[dict]] = {w: [] for w in unit["target_wallets"]}
        for row in rows:
            row_wallet = row.get("user") if "user" in row else row.get("wallet")
            by_wallet[str(row_wallet)].append(row)
        unverified_empty = set(scan_result.get("unverified_empty_wallets") or ())
        for wallet in unit["target_wallets"]:
            w_rows = by_wallet[wallet]
            if w_rows:
                empty_verified = False
            elif not rows:
                empty_verified = scan_result.get("empty_verified") is True
            else:
                empty_verified = wallet not in unverified_empty
            cov_payload = {
                "schema": COVERAGE_RECEIPT_SCHEMA,
                "wallet": wallet,
                "dex": unit["dex"],
                "utc_start": unit["utc_start"],
                "utc_end": unit["utc_end"],
                "known_at": unit["utc_start"],
                "input_sha256": immutable_inputs["input_sha256"],
                "source_sha256": immutable_inputs["source_sha256"],
                "collected": True,
                "blocked": False,
                "source_verified": True,
                "empty_verified": empty_verified,
                "row_count": len(w_rows),
            }
            cov_bytes = _canonical(cov_payload)
            cov_deps = {
                "input": immutable_inputs["input_sha256"],
                "source": immutable_inputs["source_sha256"],
                "span": sha256(cov_bytes).hexdigest(),
            }
            cov_key = ImmutableCache.identity(
                "coverage_receipt", cov_deps, version=COVERAGE_RECEIPT_SCHEMA
            )
            cov_items.append((cov_bytes, cov_deps))
            cov_keys.append(cov_key)
            disk_bytes += len(cov_bytes)
    else:
        mc_deps = _market_coverage_deps(
            dex=unit["dex"],
            day_str=unit["date"],
            immutable_inputs=immutable_inputs,
            projected_columns=list(unit["projected_columns"]),
        )
        mc_payload = {
            "schema": MARKET_COVERAGE_SCHEMA,
            "kind": "market",
            "dex": unit["dex"],
            "date": unit["date"],
            "utc_start": unit["utc_start"],
            "utc_end": unit["utc_end"],
            "known_at": unit["utc_start"],
            "input_sha256": immutable_inputs["input_sha256"],
            "source_sha256": immutable_inputs["source_sha256"],
            "market_sha256": immutable_inputs["market_sha256"],
            "projected_columns": list(unit["projected_columns"]),
            "unit_id": unit["unit_id"],
            "acquired_unit_key": unit_key,
            "source_verified": True,
            "empty_verified": len(rows) == 0 and scan_result.get("empty_verified") is True,
            "row_count": len(rows),
        }
        mc_bytes = _canonical(mc_payload)
        market_cov_key = ImmutableCache.identity(
            "market_coverage", mc_deps, version=MARKET_COVERAGE_SCHEMA
        )
        market_cov_item = (mc_bytes, mc_deps)
        disk_bytes += len(mc_bytes)

    unit_payload_doc: dict[str, Any] = {
        "schema": ACQUISITION_UNIT_SCHEMA,
        "unit_id": unit["unit_id"],
        "kind": unit["kind"],
        "dex": unit["dex"],
        "date": unit["date"],
        "utc_start": unit["utc_start"],
        "utc_end": unit["utc_end"],
        "target_wallets": list(unit["target_wallets"]),
        "projected_columns": list(unit["projected_columns"]),
        "etag": scan_result.get("etag"),
        "remote_payload_sha256": scan_result.get("payload_sha256"),
        "coverage_receipt_keys": cov_keys,
        "market_coverage_key": market_cov_key,
        "row_count": len(rows),
        "rows": rows,
        "historical_oracle_only": True,
    }
    content = _canonical(unit_payload_doc)
    disk_bytes += len(content)
    return content, deps, cov_items, market_cov_item, disk_bytes


def _publish_unit_and_coverage(
    store: ImmutableCache,
    *,
    content: bytes,
    deps: dict[str, str],
    cov_items: list[tuple[bytes, dict[str, str]]],
    market_cov_item: tuple[bytes, dict[str, str]] | None,
) -> tuple[str, list[str]]:
    pub = store.publish("acquired_unit", deps, version=ACQUISITION_UNIT_SCHEMA, content=content)
    cov_keys: list[str] = []
    for cov_bytes, cov_deps in cov_items:
        cov_pub = store.publish(
            "coverage_receipt", cov_deps, version=COVERAGE_RECEIPT_SCHEMA, content=cov_bytes
        )
        cov_keys.append(cov_pub["key"])
    if market_cov_item is not None:
        mc_bytes, mc_deps = market_cov_item
        store.publish("market_coverage", mc_deps, version=MARKET_COVERAGE_SCHEMA, content=mc_bytes)
    return pub["key"], cov_keys


def _build_actual(
    root: Path,
    *,
    t0: float,
    metadata_requests: int = 0,
    scan_requests: int = 0,
    remote_bytes_read: int | None = None,
    remote_bytes_observable: bool = True,
    compressed_scanned: int = 0,
    disk_bytes_written: int = 0,
    returned_rows: int = 0,
    units_planned: int = 0,
    units_reused: int = 0,
    units_completed: int = 0,
    units_failed: int = 0,
    units_cancelled: int = 0,
    max_observed_concurrency: int = 0,
) -> dict[str, Any]:
    return {
        "requests": metadata_requests + scan_requests,
        "metadata_requests": metadata_requests,
        "scan_requests": scan_requests,
        "remote_bytes_read": remote_bytes_read,
        "remote_bytes_observable": remote_bytes_observable,
        "remote_compressed_bytes_scanned": compressed_scanned,
        "disk_bytes_written": disk_bytes_written,
        "disk_free_bytes_after": _available_disk_bytes(root),
        "returned_rows": returned_rows,
        "units_planned": units_planned,
        "units_reused": units_reused,
        "units_completed": units_completed,
        "units_failed": units_failed,
        "units_cancelled": units_cancelled,
        "units_remaining": units_planned - units_completed,
        "max_observed_concurrency": max_observed_concurrency,
        "duration_ms": round((perf_counter() - t0) * 1000, 3),
    }


def _build_comparison(
    *,
    forecast: dict[str, Any],
    actual: dict[str, Any],
    within_budget: bool,
) -> dict[str, Any]:
    actual_remote = actual["remote_bytes_read"]
    return {
        "requests_delta": int(actual["requests"]) - int(forecast["requests"]),
        "remote_bytes_delta": (
            int(actual_remote) - int(forecast["remote_compressed_bytes"])
            if actual_remote is not None
            else None
        ),
        "remote_compressed_bytes_delta": (
            int(actual["remote_compressed_bytes_scanned"])
            - int(forecast["remote_compressed_bytes"])
        ),
        "disk_bytes_delta": int(actual["disk_bytes_written"]) - int(forecast["disk_bytes"]),
        "within_budget": within_budget,
    }


def _build_cumulative(
    prior: _PriorResumeState | None,
    *,
    total_requests: int,
    actual_remote_read: int | None,
    batch: _BatchState,
    budget: BoundedAcquisitionBudget,
    stop_code: str | None,
) -> dict[str, Any]:
    prior_reqs = prior.prior_reqs if prior else 0
    prior_remote = prior.prior_remote_read if prior else 0
    prior_comp = prior.prior_comp_scanned if prior else 0
    prior_disk = prior.prior_disk if prior else 0
    prior_obs = prior.prior_obs if prior else batch.remote_bytes_observable

    cum_obs = prior_obs and batch.remote_bytes_observable
    cum_requests = prior_reqs + total_requests
    cum_remote_read: int | None = (prior_remote + (actual_remote_read or 0)) if cum_obs else None
    cum_comp = prior_comp + batch.compressed_scanned
    cum_disk = prior_disk + batch.disk_bytes
    cum_eff_bytes = cum_remote_read if cum_remote_read is not None else cum_comp
    within_budget = (
        cum_requests <= budget.max_requests
        and cum_eff_bytes <= budget.max_remote_bytes
        and cum_disk <= budget.max_disk_bytes
        and stop_code != "BUDGET_EXHAUSTED"
    )
    return {
        "requests": cum_requests,
        "remote_bytes_read": cum_remote_read,
        "remote_compressed_bytes_scanned": cum_comp,
        "disk_bytes_written": cum_disk,
        "within_budget": within_budget,
    }


def _blocked_execution_result(
    *,
    code: str,
    reason: str,
    run_id: str | None,
    attempt: int,
    request_binding_sha256: str | None,
    plan_binding_sha256: str | None,
    immutable_inputs: dict[str, str],
    forecast: dict[str, Any],
    actual: dict[str, Any],
    acquired_keys: dict[str, str] | None = None,
    cov_keys: list[str] | None = None,
    reused_unit_ids: list[str] | None = None,
    cumulative: dict[str, Any] | None = None,
    within_budget: bool = False,
) -> dict[str, Any]:
    out: dict[str, Any] = {
        "schema": ACQUISITION_RUN_SCHEMA,
        "status": "BLOCKED",
        "state": code,
        "error_code": code,
        "reason": reason,
        "run_id": run_id,
        "attempt": attempt,
        "request_binding_sha256": request_binding_sha256,
        "plan_binding_sha256": plan_binding_sha256,
        "immutable_inputs": immutable_inputs,
        "forecast": forecast,
        "actual": actual,
        "comparison": _build_comparison(
            forecast=forecast, actual=actual, within_budget=within_budget
        ),
        "acquired_unit_keys": acquired_keys or {},
        "coverage_receipt_keys": cov_keys or [],
        "reused_unit_ids": reused_unit_ids or [],
        **_base_non_authority_flags(),
        "historical_oracle_only": True,
    }
    if cumulative is not None:
        out["cumulative"] = cumulative
    return out


def _verify_prior_units(
    root: Path,
    store: ImmutableCache,
    *,
    stored_run: dict[str, Any],
    stored_inputs: dict[str, str],
    as_of: datetime,
) -> tuple[dict[str, dict[str, Any]], dict[str, str], list[str], tuple[str, str] | None]:
    verified_prior_units: dict[str, dict[str, Any]] = {}
    prior_acquired_keys: dict[str, str] = {}
    recovered_cov_keys: list[str] = []

    for punit in list(stored_run.get("planned_units") or []):
        unit_deps = _unit_cache_deps(
            plan_binding_sha256=stored_run["plan_binding_sha256"],
            unit=punit,
            immutable_inputs=stored_inputs,
        )
        udoc, uraw, uerr = _load_json_from_cache(
            store, "acquired_unit", unit_deps, ACQUISITION_UNIT_SCHEMA
        )
        if uerr is not None:
            return {}, {}, [], (uerr, f"Corrupt or unsealed prior unit {punit['unit_id']}")
        if udoc is None or uraw is None:
            continue
        if udoc.get("unit_id") != punit["unit_id"]:
            return (
                {},
                {},
                [],
                ("CORRUPT_CACHE_SHA", f"Unit payload ID mismatch for {punit['unit_id']}"),
            )

        ukey = ImmutableCache.identity("acquired_unit", unit_deps, version=ACQUISITION_UNIT_SCHEMA)
        if udoc.get("kind") == "source":
            for ck in udoc.get("coverage_receipt_keys") or []:
                try:
                    verify_coverage_receipt_key(root, ck)
                except ValueError, OSError, TypeError, KeyError, AttributeError:
                    return {}, {}, [], ("CORRUPT_RECEIPT", f"Corrupt prior coverage receipt {ck}")
                if ck not in recovered_cov_keys:
                    recovered_cov_keys.append(ck)
        elif udoc.get("kind") == "market":
            mc_hit, mc_err = _lookup_verified_market_coverage(
                root,
                dex=str(udoc.get("dex")),
                day_str=str(udoc.get("date")),
                immutable_inputs=stored_inputs,
                projected_cols=list(udoc.get("projected_columns") or []),
                as_of=as_of,
            )
            if mc_err is not None or mc_hit is None:
                return (
                    {},
                    {},
                    [],
                    (mc_err or "CORRUPT_RECEIPT", f"Missing/corrupt market receipt for {ukey}"),
                )

        verified_prior_units[punit["unit_id"]] = {
            "key": ukey,
            "sha256": sha256(uraw).hexdigest(),
            "target_wallets": list(udoc.get("target_wallets") or []),
        }
        prior_acquired_keys[punit["unit_id"]] = ukey
    return verified_prior_units, prior_acquired_keys, recovered_cov_keys, None


def _sum_prior_attempts(
    store: ImmutableCache,
    *,
    run_id_digest: str,
    plan_binding_sha256: str,
    observable_default: bool,
    recovered_cov_keys: list[str],
) -> tuple[dict[str, Any] | None, tuple[int, str, str] | None]:
    attempt_idx = 1
    prior_reqs = 0
    prior_remote_read = 0
    prior_comp_scanned = 0
    prior_disk = 0
    prior_obs = observable_default
    prior_cov_keys = list(recovered_cov_keys)

    while attempt_idx <= 1000:
        att_deps = {
            "run_id": run_id_digest,
            "plan_binding": plan_binding_sha256,
            "attempt": sha256(str(attempt_idx).encode()).hexdigest(),
        }
        adoc, _, aerr = _load_json_from_cache(
            store, "acquisition_attempt", att_deps, ACQUISITION_ATTEMPT_SCHEMA
        )
        if aerr is not None:
            return None, (attempt_idx, aerr, f"Corrupt attempt checkpoint {attempt_idx}")
        if adoc is None:
            break
        att_actual = adoc.get("actual") or {}
        prior_reqs += int(att_actual.get("requests", 0))
        prior_comp_scanned += int(att_actual.get("remote_compressed_bytes_scanned", 0))
        prior_disk += int(att_actual.get("disk_bytes_written", 0))
        if att_actual.get("remote_bytes_read") is None:
            prior_obs = False
        else:
            prior_remote_read += int(att_actual["remote_bytes_read"])
        for ck in adoc.get("coverage_receipt_keys") or []:
            if ck not in prior_cov_keys:
                prior_cov_keys.append(ck)
        attempt_idx += 1

    return {
        "next_attempt": attempt_idx,
        "prior_cov_keys": prior_cov_keys,
        "prior_reqs": prior_reqs,
        "prior_remote_read": prior_remote_read,
        "prior_comp_scanned": prior_comp_scanned,
        "prior_disk": prior_disk,
        "prior_obs": prior_obs,
    }, None


def _load_resume_state(
    root: Path,
    store: ImmutableCache,
    *,
    run_id: str,
    identity: _PlanIdentity,
    t0: float,
    observable_default: bool,
) -> tuple[_PriorResumeState | None, dict[str, Any] | None]:
    run_deps = {"run_id": sha256(run_id.encode()).hexdigest()}
    stored_run, _, run_err = _load_json_from_cache(
        store, "acquisition_run", run_deps, ACQUISITION_RUN_SCHEMA
    )
    zero_actual = _build_actual(
        root,
        t0=t0,
        remote_bytes_read=0 if observable_default else None,
        remote_bytes_observable=observable_default,
    )

    def _fail(
        code: str,
        reason: str,
        *,
        attempt: int = 1,
        req_sha: str | None = None,
        plan_sha: str | None = None,
        forecast: dict[str, Any] | None = None,
    ) -> tuple[None, dict[str, Any]]:
        return None, _blocked_execution_result(
            code=code,
            reason=reason,
            run_id=run_id,
            attempt=attempt,
            request_binding_sha256=req_sha,
            plan_binding_sha256=plan_sha,
            immutable_inputs=identity.immutable_inputs,
            forecast=forecast or _empty_forecast(),
            actual=zero_actual,
        )

    if run_err is not None:
        return _fail(run_err, "Corrupt or unsealed acquisition run record")
    if stored_run is None:
        return _fail("ACQUISITION_RUN_NOT_FOUND", f"Cannot resume unknown run_id={run_id}")

    stored_scope = stored_run.get("scope") or {}
    stored_budget = stored_run.get("budget") or {}
    stored_context = stored_run.get("request_context") or {}
    cur_budget = identity.budget.model_dump()
    stored_inputs = stored_run.get("immutable_inputs") or {}

    scope_match = all(
        stored_scope.get(k, identity.scope[k]) == identity.scope[k] for k in identity.scope
    )
    budget_match = all(
        stored_budget.get(cap) == cur_budget.get(cap)
        for cap in ("max_requests", "max_remote_bytes", "max_disk_bytes")
    )
    context_match = stored_context == identity.request_context if stored_context else True
    if not (
        scope_match
        and budget_match
        and context_match
        and stored_inputs == identity.immutable_inputs
    ):
        return _fail(
            "RESUME_BINDING_MISMATCH",
            "Resume scope, resource cap, context, or immutable input digest drifted",
            req_sha=stored_run.get("request_binding_sha256"),
            plan_sha=stored_run.get("plan_binding_sha256"),
            forecast=stored_run.get("forecast"),
        )

    verified_prior_units, prior_acquired_keys, recovered_cov_keys, unit_err = _verify_prior_units(
        root,
        store,
        stored_run=stored_run,
        stored_inputs=stored_inputs,
        as_of=identity.as_of,
    )
    if unit_err is not None:
        return _fail(
            unit_err[0],
            unit_err[1],
            req_sha=stored_run.get("request_binding_sha256"),
            plan_sha=stored_run.get("plan_binding_sha256"),
            forecast=stored_run.get("forecast"),
        )

    attempt_summary, att_err = _sum_prior_attempts(
        store,
        run_id_digest=run_deps["run_id"],
        plan_binding_sha256=stored_run["plan_binding_sha256"],
        observable_default=observable_default,
        recovered_cov_keys=recovered_cov_keys,
    )
    if att_err is not None or attempt_summary is None:
        att_idx, err_code, err_reason = att_err or (1, "CORRUPT_RECEIPT", "Attempt read failed")
        return _fail(
            err_code,
            err_reason,
            attempt=att_idx,
            req_sha=stored_run.get("request_binding_sha256"),
            plan_sha=stored_run.get("plan_binding_sha256"),
            forecast=stored_run.get("forecast"),
        )

    return _PriorResumeState(
        stored_run=stored_run,
        verified_prior_units=verified_prior_units,
        prior_acquired_keys=prior_acquired_keys,
        **attempt_summary,
    ), None


def _execute_unit_batch(
    missing_units: list[dict[str, Any]],
    *,
    provider: Any,
    store: ImmutableCache,
    plan_binding_for_units: str,
    immutable_inputs: dict[str, str],
    budget: BoundedAcquisitionBudget,
    meta_reqs_done: int,
    rem_requests_cap: int,
    rem_remote_cap: int,
    rem_disk_cap: int,
    observable_default: bool,
    effective_workers: int,
    cancel_event: Any | None,
) -> _BatchState:
    coord_lock = threading.Lock()
    state = _BatchState(remote_bytes_observable=observable_default)

    def _run_unit(unit: dict[str, Any]) -> None:
        unit_cost = unit.get("cost") or {}
        est_reqs = int(unit_cost.get("scan_requests", 1))
        est_bytes = int(unit_cost.get("predicted_remote_compressed_bytes", 0))
        est_disk = int(unit_cost.get("predicted_disk_bytes", 0))

        with coord_lock:
            if state.halted_error is not None:
                return
            if cancel_event is not None and cancel_event.is_set():
                state.cancelled += 1
                state.halted_error = ("EXECUTION_CANCELLED", "Execution cancelled")
                return
            cur_eff_bytes = (
                state.remote_bytes_read
                if state.remote_bytes_observable
                else state.compressed_scanned
            )
            if (
                meta_reqs_done + state.scan_requests + state.reserved_reqs + est_reqs
                > rem_requests_cap
                or cur_eff_bytes + state.reserved_bytes + est_bytes > rem_remote_cap
                or state.disk_bytes + state.reserved_disk + est_disk > rem_disk_cap
            ):
                state.failed += 1
                state.halted_error = ("BUDGET_EXHAUSTED", "Runtime budget cap reached")
                return
            state.reserved_reqs += est_reqs
            state.reserved_bytes += est_bytes
            state.reserved_disk += est_disk
            state.active_workers += 1
            state.max_observed_concurrency = max(
                state.max_observed_concurrency, state.active_workers
            )

        def _budget_guard(*, delta_requests: int = 0, delta_remote_bytes: int = 0) -> None:
            if delta_requests < 0 or delta_remote_bytes < 0:
                raise AcquisitionContractError("CORRUPT_REMOTE_PAGE", "NEGATIVE_RESOURCE_USAGE")
            with coord_lock:
                if cancel_event is not None and cancel_event.is_set():
                    raise AcquisitionContractError("EXECUTION_CANCELLED", "Execution cancelled")
                if state.halted_error is not None:
                    raise AcquisitionContractError(state.halted_error[0], state.halted_error[1])
                other_res_reqs = state.reserved_reqs - est_reqs
                other_res_bytes = state.reserved_bytes - est_bytes
                cur_eff = (
                    state.remote_bytes_read
                    if state.remote_bytes_observable
                    else state.compressed_scanned
                )
                if (
                    meta_reqs_done + state.scan_requests + other_res_reqs + delta_requests
                    > rem_requests_cap
                ):
                    raise AcquisitionContractError(
                        "BUDGET_EXHAUSTED", "Runtime request budget exceeded"
                    )
                if cur_eff + other_res_bytes + delta_remote_bytes > rem_remote_cap:
                    raise AcquisitionContractError(
                        "BUDGET_EXHAUSTED", "Runtime remote byte budget exceeded"
                    )

        released_res = False
        try:
            scan_res = provider.scan_unit(
                unit, cancel_event=cancel_event, budget_guard=_budget_guard
            )
            validated_rows = _validate_scan_result(unit, scan_res)
            scan_reqs = scan_res.get("requests_made", 1)
            comp_scanned = scan_res.get("compressed_bytes_scanned", 0)
            if type(scan_reqs) is not int or scan_reqs < 0:
                raise AcquisitionContractError("CORRUPT_REMOTE_PAGE", "INVALID_REQUESTS_MADE")
            if type(comp_scanned) is not int or comp_scanned < 0:
                raise AcquisitionContractError("CORRUPT_REMOTE_PAGE", "INVALID_COMPRESSED_BYTES")
            wire_read = scan_res.get("remote_bytes_read")
            if wire_read is not None and (type(wire_read) is not int or wire_read < 0):
                raise AcquisitionContractError("CORRUPT_REMOTE_PAGE", "INVALID_REMOTE_BYTES_READ")

            content, deps, cov_items, market_cov_item, unit_disk_bytes = _prepare_unit_artifacts(
                plan_binding_sha256=plan_binding_for_units,
                unit=unit,
                scan_result=scan_res,
                rows=validated_rows,
                immutable_inputs=immutable_inputs,
            )

            with coord_lock:
                state.reserved_reqs -= est_reqs
                state.reserved_bytes -= est_bytes
                state.reserved_disk -= est_disk
                released_res = True

                next_reqs = meta_reqs_done + state.scan_requests + scan_reqs
                next_comp = state.compressed_scanned + comp_scanned
                if wire_read is None:
                    if budget.require_observable_remote_bytes:
                        raise AcquisitionContractError(
                            "UNOBSERVABLE_REMOTE_BYTES", "Observable remote bytes required"
                        )
                    state.remote_bytes_observable = False
                    next_remote = next_comp
                else:
                    next_remote = (
                        state.remote_bytes_read + wire_read
                        if state.remote_bytes_observable
                        else next_comp
                    )
                if next_reqs > rem_requests_cap or next_remote > rem_remote_cap:
                    state.scan_requests += scan_reqs
                    state.compressed_scanned = next_comp
                    if wire_read is not None:
                        state.remote_bytes_read += wire_read
                    raise AcquisitionContractError("BUDGET_EXHAUSTED", "Runtime budget exceeded")
                if state.disk_bytes + unit_disk_bytes > rem_disk_cap:
                    raise AcquisitionContractError(
                        "BUDGET_EXHAUSTED", "Runtime disk budget exceeded"
                    )

                unit_key, unit_cov_keys = _publish_unit_and_coverage(
                    store,
                    content=content,
                    deps=deps,
                    cov_items=cov_items,
                    market_cov_item=market_cov_item,
                )
                state.scan_requests += scan_reqs
                state.compressed_scanned = next_comp
                if wire_read is not None:
                    state.remote_bytes_read += wire_read
                state.disk_bytes += unit_disk_bytes
                state.rows += len(validated_rows)
                state.new_acquired[unit["unit_id"]] = unit_key
                state.new_covs.extend(unit_cov_keys)
                state.completed += 1
        except (
            AcquisitionContractError,
            PermissionError,
            TimeoutError,
            OSError,
            KeyError,
            ManifestBlocked,
        ) as exc:
            if isinstance(exc, ManifestBlocked):
                err_code, err_msg = "INSUFFICIENT_DISK_HEADROOM", str(exc)
            else:
                err_code, err_msg = _classify_provider_error(exc)
            with coord_lock:
                if not released_res:
                    state.reserved_reqs -= est_reqs
                    state.reserved_bytes -= est_bytes
                    state.reserved_disk -= est_disk
                if err_code == "EXECUTION_CANCELLED":
                    state.cancelled += 1
                else:
                    state.failed += 1
                if state.halted_error is None:
                    state.halted_error = (err_code, err_msg)
        finally:
            with coord_lock:
                state.active_workers -= 1

    if effective_workers == 1 or len(missing_units) <= 1:
        for unit in missing_units:
            _run_unit(unit)
            if state.halted_error is not None:
                break
    else:
        with ThreadPoolExecutor(max_workers=effective_workers) as pool:
            futures = [pool.submit(_run_unit, unit) for unit in missing_units]
            for fut in futures:
                fut.result()
    return state


def _publish_attempt_checkpoint(
    store: ImmutableCache,
    *,
    run_id: str,
    run_id_digest: str,
    attempt_num: int,
    plan_binding_sha256: str,
    stop_code: str | None,
    all_acquired: dict[str, str],
    all_covs: list[str],
    actual: dict[str, Any],
) -> None:
    attempt_doc = {
        "schema": ACQUISITION_ATTEMPT_SCHEMA,
        "run_id": run_id,
        "attempt": attempt_num,
        "plan_binding_sha256": plan_binding_sha256,
        "status": "BLOCKED" if stop_code is not None else "COMPLETE",
        "error_code": stop_code,
        "completed_unit_ids": sorted(all_acquired),
        "coverage_receipt_keys": all_covs,
        "actual": actual,
    }
    attempt_deps = {
        "run_id": run_id_digest,
        "plan_binding": plan_binding_sha256,
        "attempt": sha256(str(attempt_num).encode()).hexdigest(),
    }
    store.publish(
        "acquisition_attempt",
        attempt_deps,
        version=ACQUISITION_ATTEMPT_SCHEMA,
        content=_canonical(attempt_doc),
    )


def execute_bounded_acquisition(
    root: Path,
    request: dict,
    *,
    provider: Any,
    partition_root: Path | None = None,
    run_id: str | None = None,
    resume: bool = False,
    max_workers: int | None = None,
    cancel_event: Any | None = None,
    min_free_bytes: int = 0,
) -> dict[str, Any]:
    """Execute or resume bounded remote acquisition under strict caps and SHA verification."""
    t0 = perf_counter()
    if provider is None:
        raise ValueError("ACQUISITION_PROVIDER_REQUIRED")

    identity = _compute_plan_identity(request)
    budget = identity.budget
    effective_workers = budget.max_workers if max_workers is None else max_workers
    if type(effective_workers) is not int or not 1 <= effective_workers <= MAX_ACQUISITION_WORKERS:
        raise ValueError("INVALID_MAX_WORKERS")

    observable_default = bool(getattr(provider, "observable_remote_bytes", True))
    store: ImmutableCache | None = None
    resume_state: _PriorResumeState | None = None
    effective_run_id = run_id

    if resume:
        if not effective_run_id:
            raise ValueError("RESUME_RUN_ID_REQUIRED")
        store = ImmutableCache(
            root,
            max_object_bytes=max(budget.max_disk_bytes, 64 * 1024 * 1024),
            min_free_bytes=min_free_bytes,
        )
        resume_state, blocked = _load_resume_state(
            root,
            store,
            run_id=effective_run_id,
            identity=identity,
            t0=t0,
            observable_default=observable_default,
        )
        if blocked is not None:
            return blocked

    verified_prior = resume_state.verified_prior_units if resume_state else None
    prior_reqs = resume_state.prior_reqs if resume_state else 0
    rem_requests_cap = budget.max_requests - prior_reqs
    plan = plan_bounded_acquisition(
        root,
        request,
        partition_root=partition_root,
        metadata_provider=provider,
        verified_unit_digests=verified_prior,
        remaining_request_budget=rem_requests_cap if resume else None,
        min_free_bytes=min_free_bytes,
    )
    meta_reqs_done = int(plan["head_requests_made"])
    attempt_num = resume_state.next_attempt if resume_state else 1
    prior_remote_read = resume_state.prior_remote_read if resume_state else 0
    prior_comp_scanned = resume_state.prior_comp_scanned if resume_state else 0
    prior_disk = resume_state.prior_disk if resume_state else 0
    prior_obs = resume_state.prior_obs if resume_state else observable_default
    prior_acquired = dict(resume_state.prior_acquired_keys) if resume_state else {}
    prior_covs = list(resume_state.prior_cov_keys) if resume_state else []
    reused_ids = sorted(verified_prior) if verified_prior else []
    plan_binding_for_units = (
        resume_state.stored_run["plan_binding_sha256"]
        if resume_state
        else plan["plan_binding_sha256"]
    )
    if effective_run_id is None:
        effective_run_id = f"run-{plan_binding_for_units[:16]}"
    run_id_digest = sha256(effective_run_id.encode()).hexdigest()

    if plan["status"] != "PLANNED":
        blocked_actual = _build_actual(
            root,
            t0=t0,
            metadata_requests=meta_reqs_done,
            remote_bytes_read=0 if observable_default else None,
            remote_bytes_observable=observable_default,
            units_planned=len(plan["missing_units"]),
            units_reused=len(plan["reused_units"]),
        )
        if resume and store is not None and meta_reqs_done > 0:
            _publish_attempt_checkpoint(
                store,
                run_id=effective_run_id,
                run_id_digest=run_id_digest,
                attempt_num=attempt_num,
                plan_binding_sha256=plan_binding_for_units,
                stop_code=plan["error_code"],
                all_acquired=prior_acquired,
                all_covs=prior_covs,
                actual=blocked_actual,
            )
        return _blocked_execution_result(
            code=plan["error_code"],
            reason=plan["reason"],
            run_id=effective_run_id if resume else run_id,
            attempt=attempt_num,
            request_binding_sha256=plan["request_binding_sha256"],
            plan_binding_sha256=plan_binding_for_units,
            immutable_inputs=plan["immutable_inputs"],
            forecast=plan["forecast"],
            actual=blocked_actual,
            acquired_keys=prior_acquired,
            cov_keys=prior_covs,
            reused_unit_ids=reused_ids,
        )

    if store is None:
        store = ImmutableCache(
            root,
            max_object_bytes=max(budget.max_disk_bytes, 64 * 1024 * 1024),
            min_free_bytes=min_free_bytes,
        )

    run_deps = {"run_id": run_id_digest}
    if not resume:
        run_doc = {
            "schema": ACQUISITION_RUN_SCHEMA,
            "run_id": effective_run_id,
            "request_binding_sha256": plan["request_binding_sha256"],
            "plan_binding_sha256": plan["plan_binding_sha256"],
            "scope": identity.scope,
            "request_context": identity.request_context,
            "budget": plan["budget"],
            "immutable_inputs": plan["immutable_inputs"],
            "planned_unit_ids": [u["unit_id"] for u in plan["missing_units"]],
            "planned_units": plan["missing_units"],
            "forecast": plan["forecast"],
        }
        try:
            store.publish(
                "acquisition_run",
                run_deps,
                version=ACQUISITION_RUN_SCHEMA,
                content=_canonical(run_doc),
            )
        except ManifestBlocked as exc:
            if "IMMUTABLE_CACHE_KEY_CONFLICT" in str(exc):
                raise AcquisitionContractError(
                    "ACQUISITION_RUN_ALREADY_EXISTS",
                    "Run ID already exists; pass resume=True to resume",
                ) from exc
            raise

    missing_units = list(plan["missing_units"])
    prior_effective_bytes = prior_remote_read if prior_obs else prior_comp_scanned
    rem_remote_cap = budget.max_remote_bytes - prior_effective_bytes
    rem_disk_cap = budget.max_disk_bytes - prior_disk
    if missing_units and (
        meta_reqs_done + int(plan["forecast"]["scan_requests"]) > rem_requests_cap
        or int(plan["forecast"]["remote_compressed_bytes"]) > rem_remote_cap
        or int(plan["forecast"]["disk_bytes"]) > rem_disk_cap
    ):
        cum_blocked_actual = _build_actual(
            root,
            t0=t0,
            metadata_requests=meta_reqs_done,
            remote_bytes_read=0 if observable_default else None,
            remote_bytes_observable=observable_default,
            units_planned=len(missing_units),
            units_reused=len(plan["reused_units"]),
        )
        _publish_attempt_checkpoint(
            store,
            run_id=effective_run_id,
            run_id_digest=run_id_digest,
            attempt_num=attempt_num,
            plan_binding_sha256=plan_binding_for_units,
            stop_code="BUDGET_EXHAUSTED",
            all_acquired=prior_acquired,
            all_covs=prior_covs,
            actual=cum_blocked_actual,
        )
        return _blocked_execution_result(
            code="BUDGET_EXHAUSTED",
            reason="Cumulative budget across resume attempts exhausted",
            run_id=effective_run_id,
            attempt=attempt_num,
            request_binding_sha256=plan["request_binding_sha256"],
            plan_binding_sha256=plan_binding_for_units,
            immutable_inputs=plan["immutable_inputs"],
            forecast=plan["forecast"],
            actual=cum_blocked_actual,
            acquired_keys=prior_acquired,
            cov_keys=prior_covs,
            reused_unit_ids=reused_ids,
        )

    batch = _execute_unit_batch(
        missing_units,
        provider=provider,
        store=store,
        plan_binding_for_units=plan_binding_for_units,
        immutable_inputs=plan["immutable_inputs"],
        budget=budget,
        meta_reqs_done=meta_reqs_done,
        rem_requests_cap=rem_requests_cap,
        rem_remote_cap=rem_remote_cap,
        rem_disk_cap=rem_disk_cap,
        observable_default=observable_default,
        effective_workers=effective_workers,
        cancel_event=cancel_event,
    )

    stop_info = batch.halted_error
    stop_code = stop_info[0] if stop_info else None
    stop_reason = stop_info[1] if stop_info else None
    total_requests = meta_reqs_done + batch.scan_requests
    actual_remote_read: int | None = (
        batch.remote_bytes_read if batch.remote_bytes_observable else None
    )
    forecast = plan["forecast"]

    all_acquired = dict(prior_acquired)
    all_acquired.update(dict(sorted(batch.new_acquired.items())))
    all_covs = list(prior_covs)
    for ck in batch.new_covs:
        if ck not in all_covs:
            all_covs.append(ck)

    actual = _build_actual(
        root,
        t0=t0,
        metadata_requests=meta_reqs_done,
        scan_requests=batch.scan_requests,
        remote_bytes_read=actual_remote_read,
        remote_bytes_observable=batch.remote_bytes_observable,
        compressed_scanned=batch.compressed_scanned,
        disk_bytes_written=batch.disk_bytes,
        returned_rows=batch.rows,
        units_planned=len(missing_units),
        units_reused=len(plan["reused_units"]),
        units_completed=batch.completed,
        units_failed=batch.failed,
        units_cancelled=batch.cancelled,
        max_observed_concurrency=batch.max_observed_concurrency,
    )
    cumulative = _build_cumulative(
        resume_state,
        total_requests=total_requests,
        actual_remote_read=actual_remote_read,
        batch=batch,
        budget=budget,
        stop_code=stop_code,
    )
    _publish_attempt_checkpoint(
        store,
        run_id=effective_run_id,
        run_id_digest=run_id_digest,
        attempt_num=attempt_num,
        plan_binding_sha256=plan_binding_for_units,
        stop_code=stop_code,
        all_acquired=all_acquired,
        all_covs=all_covs,
        actual=actual,
    )

    if stop_code is not None:
        return _blocked_execution_result(
            code=stop_code,
            reason=stop_reason or stop_code,
            run_id=effective_run_id,
            attempt=attempt_num,
            request_binding_sha256=plan["request_binding_sha256"],
            plan_binding_sha256=plan_binding_for_units,
            immutable_inputs=plan["immutable_inputs"],
            forecast=forecast,
            actual=actual,
            acquired_keys=all_acquired,
            cov_keys=all_covs,
            reused_unit_ids=reused_ids,
            cumulative=cumulative,
            within_budget=cumulative["within_budget"],
        )

    return {
        "schema": ACQUISITION_RUN_SCHEMA,
        "status": "COMPLETE",
        "state": "COMPLETE",
        "error_code": None,
        "reason": None,
        "run_id": effective_run_id,
        "attempt": attempt_num,
        "request_binding_sha256": plan["request_binding_sha256"],
        "plan_binding_sha256": plan_binding_for_units,
        "immutable_inputs": plan["immutable_inputs"],
        "forecast": forecast,
        "actual": actual,
        "cumulative": cumulative,
        "comparison": _build_comparison(
            forecast=forecast, actual=actual, within_budget=cumulative["within_budget"]
        ),
        "acquired_unit_keys": all_acquired,
        "coverage_receipt_keys": all_covs,
        "reused_unit_ids": reused_ids,
        **_base_non_authority_flags(),
        "historical_oracle_only": True,
    }
