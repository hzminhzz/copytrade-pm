"""Read-only, bounded discovery of *completed* canonical immutable job reports.

This reads only the existing pm_offline_job job_report content-addressed cache.
There is no new index, writer, heuristic report discovery or scientific gate.
A valid manifest+payload pair proves a stored report, not reliable follower PnL.
"""

from __future__ import annotations

from datetime import datetime, UTC
from hashlib import sha256
import json
import os
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


def _read_verified_object(
    root: Path,
    kind: str,
    key: str,
    expected_version: str | None,
    max_payload_bytes: int,
) -> tuple[dict, dict, bytes] | None:
    """Verify manifest+payload integrity for one cached object without creating directories."""
    folder = root / kind / key[:2]
    if not any(
        os.path.lexists(folder / f"{key}{suffix}") for suffix in (".manifest.json", ".data")
    ):
        return None
    _trusted_directory(folder)
    manifest, _ = _safe_json(folder / f"{key}.manifest.json", MAX_MANIFEST_BYTES)
    payload, raw = _safe_json(folder / f"{key}.data", max_payload_bytes)
    dependencies = manifest.get("dependencies")
    version = manifest.get("version")
    try:
        expected_key = ImmutableCache.identity(kind, dependencies, version=version)
    except (TypeError, KeyError, ValueError) as exc:
        raise ValueError("INVALID_RESEARCH_CACHE_DEPENDENCIES") from exc
    if (
        manifest.get("schema") != CACHE_SCHEMA
        or manifest.get("kind") != kind
        or manifest.get("key") != key
        or expected_key != key
        or not isinstance(version, str)
        or not version
        or (expected_version is not None and version != expected_version)
        or manifest.get("bytes") != len(raw)
        or manifest.get("sha256") != sha256(raw).hexdigest()
    ):
        raise ValueError("RESEARCH_CACHE_INTEGRITY_FAILED")
    return manifest, payload, raw


def _validate_and_summarize_report(
    manifest: dict,
    report: dict,
    payload: bytes,
    key: str,
    expected_version: str,
) -> dict:
    dependencies = manifest["dependencies"]
    if (
        report.get("schema") != expected_version
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
            fkey: value
            for fkey, value in sorted((report.get("evidence") or {}).items())
            if fkey.endswith("_sha256") and isinstance(value, str) and HEX.fullmatch(value)
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


def _inspect(root: Path, key: str) -> dict:
    entry = _read_verified_object(root, "job_report", key, REPORT, MAX_REPORT_BYTES)
    if entry is None:
        raise ValueError("MISSING_RESEARCH_REPORT")
    manifest, report, payload = entry
    return _validate_and_summarize_report(manifest, report, payload, key, REPORT)


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


# ---------------------------------------------------------------------------
# Reuse preflight (#347). Read-only decision over the SAME cache; no new store.
# ---------------------------------------------------------------------------
REUSE_SCHEMA = "pm_research_reuse_preflight_v1"
COVERAGE_RECEIPT_SCHEMA = "pm_coverage_receipt_v1"
MAX_COVERAGE_BYTES = 1024 * 1024
HEX_ADDRESS = re.compile(r"^0x[0-9a-f]+$")
SAFE_TOKEN = re.compile(r"^[A-Za-z0-9_.:/@-]{1,128}$")
DEPENDENCIES = (
    ("job", "job_sha256"),
    ("input", "input_sha256"),
    ("market", "market_sha256"),
    ("software", "software_sha256"),
)
NON_REUSABLE_PURPOSES = frozenset(
    {
        "ACCOUNT_BALANCE",
        "QUOTE",
        "HALT_CLEARANCE",
        "COPY_MANDATE",
        "PAPER_FINANCIAL_PROOF",
        "TRADING_AUTHORIZATION",
    }
)
AUTHORITY = {
    name: False
    for name in (
        "fresh_account_balance",
        "fresh_quote",
        "halt_clearance",
        "copy_mandate",
        "paper_financial_proof",
        "trading_authorization",
    )
}
HISTORY_LIMIT = 100
SCAN_LIMIT = 2000
MAX_LINEAGE_KEYS = 500


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def _clock(value: object, name: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value)  # type: ignore[arg-type]
    except (TypeError, ValueError) as exc:
        raise ValueError(f"INVALID_REUSE_{name}") from exc
    if parsed.tzinfo is None:
        raise ValueError(f"NAIVE_REUSE_{name}")
    return parsed.astimezone(UTC)


def _iso_or_none(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    try:
        return _clock(value, "ISO").isoformat()
    except ValueError:
        return None


def _sha(value: object, field: str) -> str:
    if not isinstance(value, str) or not HEX.fullmatch(value):
        raise ValueError(f"INVALID_REUSE_{field.upper()}")
    return value


def _token(value: object, field: str) -> str:
    if not isinstance(value, str) or not SAFE_TOKEN.fullmatch(value):
        raise ValueError(f"INVALID_REUSE_{field.upper()}")
    return value


def _wallets(values: object) -> list[str]:
    if not isinstance(values, list) or not values or len(values) > 1000:
        raise ValueError("INVALID_REUSE_WALLETS")
    for item in values:
        if (
            not isinstance(item, str)
            or not item
            or item != item.strip()
            or any(c.isspace() for c in item)
        ):
            raise ValueError("INVALID_REUSE_WALLET")
        if item.lower().startswith("0x"):
            if not HEX_ADDRESS.fullmatch(item):
                raise ValueError("UNNORMALIZED_OR_INVALID_WALLET_ADDRESS")
        elif not SAFE_TOKEN.fullmatch(item):
            raise ValueError("INVALID_REUSE_WALLET_ALIAS")
    return sorted(set(values))


def _dexes(values: object) -> list[str]:
    if not isinstance(values, list) or not values or len(values) > 1000:
        raise ValueError("INVALID_REUSE_DEXES")
    return sorted({_token(item, "dex") for item in values})


def _cost_assumption(value: object) -> str | dict:
    if isinstance(value, str):
        if not value or value != value.strip() or len(value) > 256:
            raise ValueError("INVALID_REUSE_COST_ASSUMPTION")
        return value
    if isinstance(value, dict) and value:
        try:
            encoded = _canonical(value)
        except (TypeError, ValueError) as exc:
            raise ValueError("INVALID_REUSE_COST_ASSUMPTION") from exc
        if len(encoded) <= 4096:
            return value
    raise ValueError("INVALID_REUSE_COST_ASSUMPTION")


def _lineage_keys(value: object, field: str) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list) or len(value) > MAX_LINEAGE_KEYS:
        raise ValueError(f"INVALID_{field.upper()}")
    for item in value:
        if not isinstance(item, str) or not HEX.fullmatch(item):
            raise ValueError(f"INVALID_{field.upper()}_KEY")
    return list(dict.fromkeys(value))


def _verify_coverage_receipt(
    root: Path, key: str
) -> tuple[dict, datetime, datetime, datetime, str]:
    entry = _read_verified_object(
        root, "coverage_receipt", key, COVERAGE_RECEIPT_SCHEMA, MAX_COVERAGE_BYTES
    )
    if entry is None:
        raise ValueError("MISSING_COVERAGE_RECEIPT")
    manifest, payload, _ = entry
    if payload.get("schema") != COVERAGE_RECEIPT_SCHEMA:
        raise ValueError("INVALID_COVERAGE_RECEIPT_SCHEMA")
    wallet = _wallets([payload.get("wallet")])[0]
    dex = _token(payload.get("dex"), "RECEIPT_DEX")
    start = _clock(payload.get("utc_start"), "RECEIPT_START")
    stop = _clock(payload.get("utc_end"), "RECEIPT_END")
    known = _clock(payload.get("known_at"), "RECEIPT_KNOWN_AT")
    if stop <= start:
        raise ValueError("INVALID_COVERAGE_RECEIPT_WINDOW")
    input_sha = _sha(payload.get("input_sha256"), "RECEIPT_INPUT")
    source_sha = _sha(payload.get("source_sha256"), "RECEIPT_SOURCE")
    deps = manifest["dependencies"]
    if deps.get("input") != input_sha or deps.get("source") != source_sha:
        raise ValueError("COVERAGE_RECEIPT_DEPENDENCY_MISMATCH")
    collected = payload.get("collected")
    blocked = payload.get("blocked")
    source_verified = payload.get("source_verified")
    empty_verified = payload.get("empty_verified")
    row_count = payload.get("row_count")
    if (
        type(collected) is not bool
        or type(blocked) is not bool
        or type(source_verified) is not bool
        or type(empty_verified) is not bool
        or type(row_count) is not int
        or row_count < 0
        or (row_count > 0 and empty_verified)
    ):
        raise ValueError("INVALID_COVERAGE_RECEIPT_FLAGS")
    if blocked or not collected:
        status = "UNCOLLECTED_OR_BLOCKED"
    elif row_count == 0:
        status = (
            "VERIFIED_EMPTY" if (source_verified and empty_verified) else "UNCOLLECTED_OR_BLOCKED"
        )
    else:
        status = "VERIFIED_DATA" if source_verified else "UNCOLLECTED_OR_BLOCKED"
    normalized = {**payload, "wallet": wallet, "dex": dex}
    return normalized, start, stop, known, status


def sweep_coverage_intervals(
    spans: list[tuple[datetime, datetime, str]], begin: datetime, end: datetime
) -> tuple[bool, list[str], list[str]]:
    """Return (covered, all_overlapping_tags, minimal_covering_tags) over [begin, end)."""
    cursor = begin
    all_tags: list[str] = []
    minimal_tags: list[str] = []
    for start, stop, tag in sorted(spans):
        if start >= end:
            break
        if start > cursor:
            return False, [], []
        if stop > begin:
            all_tags.append(tag)
        if stop > cursor and cursor < end:
            minimal_tags.append(tag)
            cursor = stop
    return cursor >= end, all_tags, minimal_tags


def verify_coverage_receipt_key(
    root: Path, key: str
) -> tuple[dict, datetime, datetime, datetime, str]:
    """Read and SHA-verify a single `coverage_receipt` entry from ImmutableCache."""
    if not isinstance(key, str) or not HEX.fullmatch(key):
        raise ValueError("INVALID_COVERAGE_RECEIPT_KEY")
    return _verify_coverage_receipt(root, key)


def load_verified_coverage_spans(
    root: Path,
    receipt_keys: list[str],
    *,
    as_of: datetime,
    input_sha: str,
    source_sha: str,
) -> tuple[dict[tuple[str, str], list[tuple[datetime, datetime, str]]], str | None]:
    """Verify caller-supplied coverage receipts for read-only span lookup."""
    spans: dict[tuple[str, str], list[tuple[datetime, datetime, str]]] = {}
    if not root.exists():
        return spans, None
    for key in receipt_keys:
        try:
            payload, r_start, r_end, r_known, status = verify_coverage_receipt_key(root, key)
        except ValueError, OSError, TypeError, KeyError, AttributeError:
            return spans, "CORRUPT_RECEIPT"
        if r_known > as_of:
            continue
        if payload.get("input_sha256") != input_sha or payload.get("source_sha256") != source_sha:
            continue
        if status in {"VERIFIED_DATA", "VERIFIED_EMPTY"}:
            spans.setdefault((payload["wallet"], payload["dex"]), []).append((r_start, r_end, key))
    return spans, None


def _coverage_state(
    root: Path, request: dict, wallets: list[str], dexes: list[str], begin, end, as_of
) -> tuple[str | None, str, dict]:
    """Verify SHA-bound on-disk coverage_receipt artifacts for the exact scope."""
    receipt_keys = request.get("coverage_receipts")
    if (
        not isinstance(receipt_keys, list)
        or len(receipt_keys) > 10_000
        or any(not isinstance(k, str) or not HEX.fullmatch(k) for k in receipt_keys)
    ):
        raise ValueError("INVALID_REUSE_COVERAGE_RECEIPTS")
    keys = sorted(set(receipt_keys))
    coverage_sha = sha256(_canonical(keys)).hexdigest()
    summary: dict[str, object] = {
        "receipt_count": len(keys),
        "verified_data_receipts": 0,
        "verified_empty_receipts": 0,
        "blocked_or_uncollected_receipts": 0,
    }
    if not keys:
        return "UNCOLLECTED_OR_BLOCKED_PERIOD", coverage_sha, summary
    by_pair: dict[tuple[str, str], list] = {(w, d): [] for w in wallets for d in dexes}
    verified_digests: list[dict[str, str]] = []
    for key in keys:
        try:
            payload, start, stop, known, status = _verify_coverage_receipt(root, key)
        except ValueError, OSError, TypeError, KeyError, AttributeError:
            summary["corrupt_receipt_key"] = key
            return "CORRUPT_RECEIPT", coverage_sha, summary
        verified_digests.append(
            {
                "key": key,
                "input_sha256": payload["input_sha256"],
                "source_sha256": payload["source_sha256"],
            }
        )
        if status == "VERIFIED_DATA":
            summary["verified_data_receipts"] = int(summary["verified_data_receipts"]) + 1
        elif status == "VERIFIED_EMPTY":
            summary["verified_empty_receipts"] = int(summary["verified_empty_receipts"]) + 1
        else:
            summary["blocked_or_uncollected_receipts"] = (
                int(summary["blocked_or_uncollected_receipts"]) + 1
            )
        pair = (payload["wallet"], payload["dex"])
        if (
            pair in by_pair
            and known <= as_of
            and payload["input_sha256"] == request["input_sha256"]
            and payload["source_sha256"] == request["source_sha256"]
        ):
            by_pair[pair].append((start, stop, status))
    coverage_sha = sha256(_canonical(verified_digests)).hexdigest()
    statuses: set[str] = set()
    for spans in by_pair.values():
        covered, overlap_statuses, _ = sweep_coverage_intervals(spans, begin, end)
        if not covered:
            return "INCOMPLETE_WALLET_DEX_SCOPE", coverage_sha, summary
        statuses.update(overlap_statuses)
    if "UNCOLLECTED_OR_BLOCKED" in statuses:
        return "UNCOLLECTED_OR_BLOCKED_PERIOD", coverage_sha, summary
    if statuses == {"VERIFIED_EMPTY"}:
        return "VERIFIED_EMPTY", coverage_sha, summary
    return None, coverage_sha, summary


def _manifests(root: Path) -> tuple[list[tuple[str, dict, str | None]], bool]:
    """Tolerant, bounded scan of OTHER entries: ((key, dependencies, version), complete).

    Unsafe, unreadable or malformed unrelated entries are skipped and mark the scan
    incomplete; they never fail a request whose own binding is intact.
    """
    namespace = root / "job_report"
    found: list[tuple[str, dict, str | None]] = []
    if not namespace.is_dir():
        return found, True
    _trusted_directory(namespace)
    complete = True
    folders = sorted(namespace.iterdir())
    if len(folders) > 256:
        folders, complete = folders[:256], False
    for folder in folders:
        try:
            if not PREFIX.fullmatch(folder.name):
                raise ValueError("INVALID_RESEARCH_CATALOG_NAMESPACE")
            _trusted_directory(folder)
            files = sorted(folder.glob("*.manifest.json"))
        except ValueError, OSError:
            complete = False
            continue
        if len(files) > MAX_REPORTS:
            files, complete = files[:MAX_REPORTS], False
        for file in files:
            if len(found) >= SCAN_LIMIT:
                return found, False
            key = file.name.removesuffix(".manifest.json")
            try:
                manifest, _ = _safe_json(file, MAX_MANIFEST_BYTES)
            except ValueError, OSError:
                complete = False
                continue
            deps = manifest.get("dependencies")
            if (
                HEX.fullmatch(key)
                and isinstance(deps, dict)
                and all(isinstance(k, str) and isinstance(v, str) for k, v in deps.items())
            ):
                found.append((key, deps, manifest.get("version")))
            else:
                complete = False
    return found, complete


def _safe_inspect(root: Path, key: str) -> dict:
    try:
        entry = _read_verified_object(root, "job_report", key, None, MAX_REPORT_BYTES)
        if entry is None:
            return {"cache_key": key, "integrity": "CORRUPT_RECEIPT"}
        manifest, payload, raw = entry
        version = manifest["version"]
        return _validate_and_summarize_report(manifest, payload, raw, key, version)
    except ValueError, OSError, TypeError, KeyError, AttributeError:
        return {"cache_key": key, "integrity": "CORRUPT_RECEIPT"}


def _safe_depends_on(root: Path, key: str) -> tuple[list[str], bool]:
    folder = root / "job_report" / key[:2]
    try:
        _trusted_directory(folder)
        payload, _ = _safe_json(folder / f"{key}.data", MAX_REPORT_BYTES)
        return _lineage_keys(payload.get("depends_on_cache_keys"), "depends_on_cache_keys"), True
    except ValueError, OSError, TypeError, KeyError, AttributeError:
        return [], False


def _binding_mismatches(
    manifest: dict, payload: dict, artifact_scope: dict, artifact_binding: str
) -> list[str]:
    deps = manifest.get("dependencies", {})
    checks = {
        "cohort": payload.get("cohort") == artifact_scope["cohort"],
        "wallets": payload.get("wallets") == artifact_scope["wallets"],
        "dexes": payload.get("dexes") == artifact_scope["dexes"],
        "utc_start": _iso_or_none(payload.get("utc_start")) == artifact_scope["utc_start"],
        "utc_end": _iso_or_none(payload.get("utc_end")) == artifact_scope["utc_end"],
        "as_of": _iso_or_none(payload.get("as_of")) == artifact_scope["as_of"],
        "source_sha256": payload.get("source_sha256") == artifact_scope["source_sha256"]
        and ("source" not in deps or deps["source"] == artifact_scope["source_sha256"]),
        "cost_assumption": payload.get("cost_assumption") == artifact_scope["cost_assumption"],
        "policy": payload.get("policy") == artifact_scope["policy"],
        "report_schema": payload.get("schema") == artifact_scope["report_schema"]
        and manifest.get("version") == artifact_scope["report_schema"],
        "scope_binding": "scope" not in deps or deps["scope"] == artifact_binding,
    }
    return sorted(field for field, ok in checks.items() if not ok)


def _requested_report(
    root: Path,
    scoped_key: str,
    base_key: str,
    artifact_scope: dict,
    artifact_binding: str,
    ex_post: bool,
) -> tuple[str, dict | None, str, list[str], list[str]]:
    """Inspect the requested report key (scoped first, then legacy fallback) and verify all bindings."""
    target = scoped_key
    scoped_folder = root / "job_report" / scoped_key[:2]
    base_folder = root / "job_report" / base_key[:2]
    if any(
        os.path.lexists(scoped_folder / f"{scoped_key}{suffix}")
        for suffix in (".manifest.json", ".data")
    ):
        target = scoped_key
    elif any(
        os.path.lexists(base_folder / f"{base_key}{suffix}")
        for suffix in (".manifest.json", ".data")
    ):
        target = base_key
    else:
        return scoped_key, None, "CACHE_MISS", [], []
    try:
        entry = _read_verified_object(
            root, "job_report", target, artifact_scope["report_schema"], MAX_REPORT_BYTES
        )
        if entry is None:
            return target, None, "CACHE_MISS", [], []
        manifest, payload, raw = entry
        summary = _validate_and_summarize_report(
            manifest, payload, raw, target, artifact_scope["report_schema"]
        )
        supersedes = _lineage_keys(payload.get("supersedes"), "supersedes")
        depends_on = _lineage_keys(payload.get("depends_on_cache_keys"), "depends_on_cache_keys")
        if payload.get("clock_basis") == "PROSPECTIVE_FIRST_KNOWN":
            rep_known = payload.get("selection_known_at")
            if ex_post or (
                rep_known is not None
                and _clock(artifact_scope["utc_start"], "UTC_START")
                < _clock(rep_known, "REPORT_SELECTION_KNOWN_AT")
            ):
                return target, None, "CORRUPT_RECEIPT", [], []
    except ValueError, OSError, TypeError, KeyError, AttributeError:
        return target, None, "CORRUPT_RECEIPT", [], []
    mismatches = _binding_mismatches(manifest, payload, artifact_scope, artifact_binding)
    summary = {
        **summary,
        "cohort": payload.get("cohort"),
        "policy": payload.get("policy"),
        "source_sha256": payload.get("source_sha256"),
        "cost_assumption": payload.get("cost_assumption"),
        "utc_start": _iso_or_none(payload.get("utc_start")),
        "utc_end": _iso_or_none(payload.get("utc_end")),
        "as_of": _iso_or_none(payload.get("as_of")),
        "dexes": payload.get("dexes"),
        "wallets_count": len(payload["wallets"])
        if isinstance(payload.get("wallets"), list)
        else None,
        "supersedes": supersedes,
        "depends_on_cache_keys": depends_on,
    }
    state = "INVALIDATED_BINDING_CHANGED" if mismatches else "VERIFIED_CACHE_HIT"
    return target, summary, state, mismatches, supersedes


def assess_reuse(root: Path, request: dict) -> dict:
    """Decide whether immutable research evidence may be reused for an exact scope.

    Reuses the existing ``ImmutableCache`` directory layout (`job_report` and
    `coverage_receipt`) strictly read-only without creating a separate store or
    mutating cache contents. Coverage is proven only by SHA-verified on-disk
    `coverage_receipt` artifacts bound to the request's `input_sha256`,
    `source_sha256`, and `as_of` cutoff. Cached reports must also attest all
    scope and provenance bindings (`cohort`, `wallets`, `dexes`, `utc_start`,
    `utc_end`, `as_of`, `source_sha256`, `cost_assumption`, `policy`, `schema`).

    Never serves fresh balance, quote, HALT, mandate, paper finance or trading
    authority and never infers a prospective first-known event.
    """
    if not isinstance(request, dict):
        raise ValueError("INVALID_REUSE_REQUEST")
    cohort = _token(request.get("cohort"), "cohort")
    wallets = _wallets(request.get("wallets"))
    dexes = _dexes(request.get("dexes"))
    begin = _clock(request.get("utc_start"), "UTC_START")
    end = _clock(request.get("utc_end"), "UTC_END")
    as_of = _clock(request.get("as_of"), "AS_OF")
    if end <= begin or as_of < end:
        raise ValueError("NONCAUSAL_REUSE_WINDOW")
    deps = {name: _sha(request.get(field), field) for name, field in DEPENDENCIES}
    source_sha = _sha(request.get("source_sha256"), "source_sha256")
    cost_assumption = _cost_assumption(request.get("cost_assumption"))
    schema, policy = request.get("report_schema"), request.get("policy")
    if not isinstance(schema, str) or not schema or not isinstance(policy, str) or not policy:
        raise ValueError("INVALID_REUSE_SCHEMA_OR_POLICY")
    purpose = request.get("purpose", "RESEARCH_PREFLIGHT")
    if purpose != "RESEARCH_PREFLIGHT" and purpose not in NON_REUSABLE_PURPOSES:
        raise ValueError("INVALID_REUSE_PURPOSE")
    require_pit = request.get("require_pit", False)
    if type(require_pit) is not bool:
        raise ValueError("INVALID_REUSE_REQUIRE_PIT")
    known_at = request.get("selection_known_at")
    selection = None if known_at is None else _clock(known_at, "SELECTION_KNOWN_AT")
    ex_post = selection is None or begin < selection
    artifact_scope = {
        "cohort": cohort,
        "wallets": wallets,
        "dexes": dexes,
        "utc_start": begin.isoformat(),
        "utc_end": end.isoformat(),
        "as_of": as_of.isoformat(),
        **{field: deps[name] for name, field in DEPENDENCIES},
        "source_sha256": source_sha,
        "cost_assumption": cost_assumption,
        "policy": policy,
        "report_schema": schema,
    }
    artifact_binding = sha256(_canonical(artifact_scope)).hexdigest()
    request_scope = {
        **artifact_scope,
        "selection_known_at": None if selection is None else selection.isoformat(),
        "purpose": purpose,
        "require_pit": require_pit,
    }
    root = Path(root)
    _trusted_directory(root)
    coverage, coverage_sha, coverage_summary = _coverage_state(
        root, request, wallets, dexes, begin, end, as_of
    )
    scoped_deps = {**deps, "source": source_sha, "scope": artifact_binding}
    scoped_key = ImmutableCache.identity("job_report", scoped_deps, version=schema)
    base_key = ImmutableCache.identity("job_report", deps, version=schema)
    entries, scan_complete = _manifests(root)
    report = None
    expected_key = scoped_key
    mismatches: list[str] = []
    supersedes: list[str] = []
    if purpose in NON_REUSABLE_PURPOSES:
        state = "REFUSED_NOT_REUSABLE_FOR_PURPOSE"
    elif coverage in {
        "CORRUPT_RECEIPT",
        "UNCOLLECTED_OR_BLOCKED_PERIOD",
        "INCOMPLETE_WALLET_DEX_SCOPE",
    }:
        state = coverage
    elif require_pit and ex_post:
        state = "BLOCKED_EX_POST_COHORT_NOT_PIT"
    elif coverage == "VERIFIED_EMPTY":
        state = "VERIFIED_EMPTY"
    else:
        expected_key, report, state, mismatches, supersedes = _requested_report(
            root, scoped_key, base_key, artifact_scope, artifact_binding, ex_post
        )
    stale_candidates: dict[str, tuple[dict, str | None, str]] = {}
    for key, sdeps, ver in entries:
        if key != expected_key and (sdeps.get("job") == deps["job"] or key in supersedes):
            stale_candidates[key] = (sdeps, ver, "SUPERSEDED" if key in supersedes else "SAME_JOB")
    for s_key in supersedes:
        if s_key != expected_key and s_key not in stale_candidates:
            stale_candidates[s_key] = ({}, None, "SUPERSEDED")
    if stale_candidates and state == "CACHE_MISS":
        state = "INVALIDATED_BINDING_CHANGED"
    prior: list[dict] = []
    changed_values: set[tuple[str, str]] = set()
    stale_keys = sorted(stale_candidates)
    for key in stale_keys[:HISTORY_LIMIT]:
        stale_deps, version, relation = stale_candidates[key]
        changed = sorted(
            {n for n in scoped_deps if stale_deps and stale_deps.get(n) != scoped_deps[n]}
            | ({"report_schema"} if version is not None and version != schema else set())
        )
        changed_values |= {(n, stale_deps[n]) for n in changed if n in stale_deps}
        prior.append(
            {**_safe_inspect(root, key), "changed_dependencies": changed, "relation": relation}
        )
    dependents: list[dict] = []
    invalidated_keys = set(stale_keys) | (set(supersedes) - {expected_key})
    if invalidated_keys and (
        state == "INVALIDATED_BINDING_CHANGED" or (state == "VERIFIED_CACHE_HIT" and supersedes)
    ):
        for key, other, _ in entries:
            if key == expected_key or key in invalidated_keys:
                continue
            dep_keys, ok = _safe_depends_on(root, key)
            if not ok:
                scan_complete = False
            if set(dep_keys) & invalidated_keys:
                dependents.append(
                    {
                        "cache_key": key,
                        "job_sha256": other.get("job"),
                        "reason": "DEPENDS_ON_SUPERSEDED_OR_STALE_REPORT",
                    }
                )
            elif (
                state == "INVALIDATED_BINDING_CHANGED"
                and other.get("job") != deps["job"]
                and any(other.get(n) == v for n, v in changed_values)
            ):
                dependents.append(
                    {
                        "cache_key": key,
                        "job_sha256": other.get("job"),
                        "reason": "SHARED_CHANGED_DEPENDENCY",
                    }
                )
    hit = state == "VERIFIED_CACHE_HIT"
    return {
        "schema": REUSE_SCHEMA,
        "state": state,
        "reusable": hit,
        "reusable_as": "EX_POST_RESEARCH_EVIDENCE_ONLY" if ex_post else "RESEARCH_EVIDENCE_ONLY",
        "acquisition_needed": None
        if state == "REFUSED_NOT_REUSABLE_FOR_PURPOSE"
        else state not in {"VERIFIED_CACHE_HIT", "VERIFIED_EMPTY"},
        "artifact_binding_sha256": artifact_binding,
        "request_binding_sha256": sha256(_canonical(request_scope)).hexdigest(),
        "coverage_sha256": coverage_sha,
        "coverage_basis": "SHA_VERIFIED_IMMUTABLE_COVERAGE_RECEIPTS",
        "coverage_summary": coverage_summary,
        "cache_key": expected_key,
        "mismatch_fields": mismatches,
        "report": report,
        "prior_reports": prior,
        "prior_reports_truncated": len(stale_keys) > HISTORY_LIMIT,
        "dependent_results_needing_refresh": dependents[:HISTORY_LIMIT],
        "dependent_results_truncated": len(dependents) > HISTORY_LIMIT,
        "history_scan_complete": scan_complete,
        "pit": {
            "status": "EX_POST_FIXED_COHORT_NOT_PIT"
            if ex_post
            else "SELECTION_KNOWN_BEFORE_WINDOW",
            "selection_known_at": request_scope["selection_known_at"],
            "require_pit": require_pit,
            "prospective_first_known_event_inferred": False,
            "executable_follower_pnl": False,
        },
        "authority": dict(AUTHORITY),
        "scientifically_qualified": False,
        "trading_authorized": False,
    }
