"""Read-only, bounded discovery of *completed* canonical immutable job reports.

This reads only the existing pm_offline_job job_report content-addressed cache.
There is no new index, writer, heuristic report discovery or scientific gate.
A valid manifest+payload pair proves a stored report, not reliable follower PnL.
"""

from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
import re
import stat

from .pm_offline_cache import ImmutableCache, SCHEMA as CACHE_SCHEMA
from .pm_offline_job import REPORT

HEX = re.compile(r"^[0-9a-f]{64}$")
PREFIX = re.compile(r"^[0-9a-f]{2}$")
MAX_REPORTS = 500
MAX_REPORT_BYTES = 16 * 1024 * 1024
MAX_MANIFEST_BYTES = 64 * 1024


def _trusted_directory(path: Path) -> None:
    if path.is_symlink() or not path.is_dir() or stat.S_IMODE(path.stat().st_mode) & 0o077:
        raise ValueError("UNSAFE_RESEARCH_CACHE_DIRECTORY")


def _safe_json(path: Path, maximum: int) -> tuple[dict, bytes]:
    if path.is_symlink() or not path.is_file() or path.stat().st_size > maximum:
        raise ValueError("UNSAFE_OR_OVERSIZED_RESEARCH_REPORT")
    raw = path.read_bytes()
    try:
        parsed = json.loads(raw)
    except (UnicodeDecodeError, ValueError) as exc:
        raise ValueError("MALFORMED_RESEARCH_CACHE_OBJECT") from exc
    if not isinstance(parsed, dict):
        raise ValueError("INVALID_RESEARCH_CACHE_OBJECT")
    return parsed, raw


def _inspect(root: Path, key: str) -> dict:
    folder = root / "job_report" / key[:2]
    manifest, _ = _safe_json(folder / f"{key}.manifest.json", MAX_MANIFEST_BYTES)
    report, payload = _safe_json(folder / f"{key}.data", MAX_REPORT_BYTES)
    dependencies = manifest.get("dependencies")
    version = manifest.get("version")
    try:
        expected_key = ImmutableCache.identity("job_report", dependencies, version=version)
    except (TypeError, KeyError, ValueError) as exc:
        raise ValueError("INVALID_RESEARCH_CACHE_DEPENDENCIES") from exc
    if (
        manifest.get("schema") != CACHE_SCHEMA
        or manifest.get("kind") != "job_report"
        or manifest.get("key") != key
        or expected_key != key
        or version != REPORT
        or manifest.get("bytes") != len(payload)
        or manifest.get("sha256") != sha256(payload).hexdigest()
        or report.get("schema") != REPORT
        or report.get("job_sha256") != dependencies.get("job")
        or not isinstance(report.get("job_id"), str)
        or not re.fullmatch(r"[A-Za-z0-9_.-]{1,96}", report["job_id"])
        or report.get("job_kind") not in {"SEALED_SYNTHETIC_PM03", "HISTORICAL_ORACLE_NATIVE"}
        or report.get("scientifically_qualified") is not False
        or report.get("authorized_for_trading") is not False
        or report.get("deployed") is not False
        or report.get("financial_certified_real") is not False
    ):
        raise ValueError("RESEARCH_REPORT_INTEGRITY_OR_AUTHORITY_FAILED")
    return {
        "job_id": report["job_id"],
        "cache_key": key,
        "job_sha256": report["job_sha256"],
        "report_sha256": sha256(payload).hexdigest(),
        "input_binding_sha256": dependencies.get("input")
        if isinstance(dependencies.get("input"), str) and HEX.fullmatch(dependencies["input"])
        else None,
        "market_binding_sha256": dependencies.get("market")
        if isinstance(dependencies.get("market"), str) and HEX.fullmatch(dependencies["market"])
        else None,
        "source_fingerprints": {
            key: value
            for key, value in sorted((report.get("evidence") or {}).items())
            if key.endswith("_sha256") and isinstance(value, str) and HEX.fullmatch(value)
        }
        if isinstance(report.get("evidence"), dict)
        else {},
        "utc_start": None,
        "utc_end": None,
        "sealed_portfolio_id": None,
        "kind": report["job_kind"],
        "clock_basis": report.get("clock_basis"),
        "research_status": report.get("status"),
        "financial_status": report.get("financial_status"),
        "blockers": report.get("blockers", []),
        "engineering_path_verified": report.get("engineering_path_verified", False),
        "scientifically_qualified": False,
        "trading_authorized": False,
        "source_type": "VERIFIED_IMMUTABLE_JOB_REPORT",
    }


def list_reports(
    root: Path,
    *,
    job_id: str | None = None,
    cache_key: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> dict:
    """Enumerate SHA-verified records from an explicitly chosen cache root."""
    if not 1 <= limit <= 200 or not 0 <= offset <= 10000:
        raise ValueError("INVALID_RESEARCH_CATALOG_WINDOW")
    if job_id is not None and not re.fullmatch(r"[A-Za-z0-9_.-]{1,96}", job_id):
        raise ValueError("INVALID_RESEARCH_JOB_ID")
    if cache_key is not None and not HEX.fullmatch(cache_key):
        raise ValueError("INVALID_RESEARCH_CACHE_KEY")
    root = Path(root)
    _trusted_directory(root)
    namespace = root / "job_report"
    if not namespace.exists():
        return {
            "schema": "pm_offline_verified_job_catalog_v1",
            "scope": "EXPLICIT_CACHE_ROOT_ONLY",
            "total": 0,
            "reports": [],
            "status": "NO_CANONICAL_REPORTS_AT_ROOT",
        }
    _trusted_directory(namespace)
    records = []
    folders = sorted(namespace.iterdir())
    if len(folders) > 256:
        raise ValueError("RESEARCH_CATALOG_FOLDER_BUDGET_EXCEEDED")
    for folder in folders:
        _trusted_directory(folder)
        if not PREFIX.fullmatch(folder.name):
            raise ValueError("INVALID_RESEARCH_CATALOG_NAMESPACE")
        files = sorted(folder.iterdir())
        if len(files) > MAX_REPORTS * 2:
            raise ValueError("RESEARCH_CATALOG_FILE_BUDGET_EXCEEDED")
        for file in files:
            if file.name.endswith(".data"):
                # Object existence must be paired with a signed-size manifest.
                key = file.name.removesuffix(".data")
                if not HEX.fullmatch(key) or key[:2] != folder.name:
                    raise ValueError("INVALID_RESEARCH_REPORT_KEY")
                if not (folder / f"{key}.manifest.json").is_file():
                    raise ValueError("ORPHANED_RESEARCH_REPORT_PAYLOAD")
                continue
            if not file.name.endswith(".manifest.json"):
                raise ValueError("UNKNOWN_RESEARCH_CATALOG_FILE")
            key = file.name.removesuffix(".manifest.json")
            if not HEX.fullmatch(key) or key[:2] != folder.name:
                raise ValueError("INVALID_RESEARCH_REPORT_KEY")
            records.append(_inspect(root, key))
            if len(records) > MAX_REPORTS:
                raise ValueError("RESEARCH_CATALOG_REPORT_BUDGET_EXCEEDED")
    selected = [
        item
        for item in records
        if (job_id is None or item["job_id"] == job_id)
        and (cache_key is None or item["cache_key"] == cache_key)
    ]
    selected.sort(key=lambda x: (x["job_id"], x["cache_key"]))
    if job_id is not None and len(selected) > 1 and cache_key is None:
        raise ValueError("AMBIGUOUS_RESEARCH_JOB_ID_SPECIFY_CACHE_KEY")
    return {
        "schema": "pm_offline_verified_job_catalog_v1",
        "scope": "EXPLICIT_CACHE_ROOT_ONLY",
        "status": "VERIFIED" if selected else "NOT_FOUND",
        "total": len(selected),
        "limit": limit,
        "offset": offset,
        "reports": selected[offset : offset + limit],
        "coverage": "ONLY_SHA_VERIFIED_PM_OFFLINE_JOB_REPORTS_NOT_ALL_RESEARCH",
        "scientifically_qualified": False,
        "trading_authorized": False,
    }
