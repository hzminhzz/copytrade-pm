"""Domain-owned acquisition receipts; never a financial or scientific authority."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from hashlib import sha256
import gzip
import io
import json
import os
from pathlib import Path
import re
import stat
import struct
from typing import Annotated, Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

SHA = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
GenerationId = Annotated[str, Field(pattern=r"^[0-9a-f]{32}$")]
MAX_RAW = 8 * 1024 * 1024


class Receipt(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)


class AcquisitionGeneration(Receipt):
    schema_name: Literal["pm_acquisition_generation_v1"] = Field(
        default="pm_acquisition_generation_v1", alias="schema"
    )
    generation_id: GenerationId
    kind: Literal["HYPERX_GAP", "HL_LEDGER_BACKFILL"]
    directory_name: Annotated[str, Field(pattern=r"^[a-zA-Z0-9_-]{8,81}$")]
    created_at: str
    historical_first_known: Literal[False] = False

    @field_validator("created_at")
    @classmethod
    def aware_clock(cls, value: str) -> str:
        if datetime.fromisoformat(value).utcoffset() is None:
            raise ValueError("ACQUISITION_AWARE_CLOCK_REQUIRED")
        return value


class HyperXPageReceipt(Receipt):
    schema_name: Literal["pm01_hyperx_gap_generation_page_v2"] = Field(alias="schema")
    generation_id: GenerationId
    alias: str
    coin: str
    page: Annotated[int, Field(ge=1, le=4)]
    sha256: SHA
    frozen_research_cutoff_ms: Annotated[int, Field(gt=0)]
    retrieved_at_utc: str
    validation: dict[str, Any]
    rate_budget_remaining: str | int | None
    historical_first_known: Literal[False] = False

    _clock = field_validator("retrieved_at_utc")(AcquisitionGeneration.aware_clock.__func__)


class LedgerPageReceipt(Receipt):
    schema_name: Literal["e4_historical_page_v2"] = Field(alias="schema")
    generation_id: GenerationId
    alias: str
    page: Annotated[int, Field(ge=0, lt=60)]
    source: Literal["OFFICIAL_HL_INFO"]
    kind: Literal["userFunding", "userNonFundingLedgerUpdates"]
    query_window_start_ms: int
    query_window_end_ms: int
    locally_requested_at: str
    first_locally_received_at: str
    sha256: SHA
    rows: Annotated[int, Field(ge=0, le=500)]
    new_unique_rows: Annotated[int, Field(ge=0, le=500)]
    first_row_ms: int | None
    last_row_ms: int | None
    historical_first_known: Literal[False]

    _clocks = field_validator("locally_requested_at", "first_locally_received_at")(
        AcquisitionGeneration.aware_clock.__func__
    )

    @model_validator(mode="after")
    def ordering(self) -> LedgerPageReceipt:
        if (
            self.query_window_start_ms > self.query_window_end_ms
            or self.new_unique_rows > self.rows
            or datetime.fromisoformat(self.locally_requested_at)
            > datetime.fromisoformat(self.first_locally_received_at)
        ):
            raise ValueError("ACQUISITION_RECEIPT_ORDER")
        return self


def sync_publication(path: Path) -> None:
    """Persist newly linked files and all ancestor directory entries."""
    directory = path.parent
    while True:
        fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
        if directory == directory.parent:
            return
        directory = directory.parent


def canonical(receipt: Receipt) -> bytes:
    return json.dumps(
        receipt.model_dump(by_alias=True), sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode()


def _object_pairs(pairs: list[tuple[str, object]]) -> dict:
    out = {}
    for key, value in pairs:
        if key in out:
            raise ValueError("DUPLICATE_ACQUISITION_JSON_FIELD")
        out[key] = value
    return out


def parse(raw: bytes) -> Any:
    return json.loads(raw, object_pairs_hook=_object_pairs)


def _read(path: Path, limit: int) -> bytes:
    with os.fdopen(os.open(path, os.O_RDONLY | os.O_NOFOLLOW), "rb") as stream:
        if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
            raise ValueError("ACQUISITION_REGULAR_FILE_REQUIRED")
        raw = stream.read(limit + 1)
    if len(raw) > limit:
        raise ValueError("ACQUISITION_PAGE_TOO_LARGE")
    return raw


def read_generation(root: Path, kind: str) -> AcquisitionGeneration | None:
    path = root / "acquisition-generation.json"
    if not path.exists():
        return None
    raw = _read(path, 65536)
    receipt = AcquisitionGeneration.model_validate(parse(raw))
    if receipt.kind != kind or receipt.directory_name != root.name:
        raise ValueError("ACQUISITION_GENERATION_IDENTITY_MISMATCH")
    return receipt


def begin_generation(
    root: Path, kind: str, publish: Callable[[Path, bytes], object], *, resume: bool = False
) -> AcquisitionGeneration:
    old = read_generation(root, kind)
    if old is not None:
        if not resume:
            raise ValueError("ACQUISITION_GENERATION_ALREADY_EXISTS")
        return old
    if any(root.iterdir()):
        raise ValueError("LEGACY_GENERATION_READ_ONLY_NEW_GENERATION_REQUIRED")
    receipt = AcquisitionGeneration(
        generation_id=uuid4().hex,
        kind=kind,
        directory_name=root.name,
        created_at=datetime.now(UTC).isoformat(),
    )
    publish(root / "acquisition-generation.json", canonical(receipt))
    return receipt


def verify_raw(data: object, raw: bytes, signature: str) -> None:
    if len(raw) > MAX_RAW or sha256(raw).hexdigest() != signature or parse(raw) != data:
        raise ValueError("ACQUISITION_RAW_DIGEST_OR_BODY_CONFLICT")


def read_hyperx_pages(directory: Path, alias: str, coin: str) -> list[dict]:
    if not directory.exists():
        return []
    files = list(directory.glob("page-*"))
    indices = set()
    for path in files:
        match = re.fullmatch(r"page-([0-9]{5})\.(json\.gz|meta\.json)", path.name)
        if not match:
            raise ValueError("INVALID_GENERATION_PAGE_NAME")
        indices.add(int(match[1]))
    if not indices:
        return []
    if max(indices) > 4 or min(indices) != 1 or indices != set(range(1, max(indices) + 1)):
        raise ValueError("MISSING_OR_UNBOUNDED_GENERATION_PAGE")
    generation = read_generation(directory.parent.parent, "HYPERX_GAP")
    pages = []
    tids = set()
    for number in sorted(indices):
        archive = directory / f"page-{number:05d}.json.gz"
        sidecar = directory / f"page-{number:05d}.meta.json"
        if not archive.is_file() or not sidecar.is_file():
            raise ValueError("PARTIAL_IMMUTABLE_SOURCE_PAIR")
        if archive.is_symlink() or sidecar.is_symlink():
            raise ValueError("SYMLINK_ACQUISITION_PAGE")
        with gzip.GzipFile(fileobj=io.BytesIO(_read(archive, MAX_RAW + 65536))) as stream:
            raw = stream.read(MAX_RAW + 1)
        meta_raw = _read(sidecar, 65536)
        if len(raw) > MAX_RAW or len(meta_raw) > 65536:
            raise ValueError("ACQUISITION_PAGE_TOO_LARGE")
        meta = parse(meta_raw)
        if not isinstance(meta, dict):
            raise ValueError("INVALID_ACQUISITION_METADATA")
        schema = meta.get("schema", "pm01_hyperx_gap_generation_page_v1")
        if schema == "pm01_hyperx_gap_generation_page_v2":
            receipt = HyperXPageReceipt.model_validate(meta)
            if generation is None or receipt.generation_id != generation.generation_id:
                raise ValueError("SOURCE_GENERATION_IDENTITY_MISMATCH")
        elif schema != "pm01_hyperx_gap_generation_page_v1" or generation is not None:
            raise ValueError("UNKNOWN_OR_UNBOUND_SOURCE_GENERATION_SCHEMA")
        if (
            meta.get("sha256") != sha256(raw).hexdigest()
            or meta.get("alias") != alias
            or meta.get("coin") != coin
            or type(meta.get("page")) is not int
            or meta["page"] != number
        ):
            raise ValueError("SOURCE_GENERATION_HASH_OR_IDENTITY_DRIFT")
        obj = parse(raw)
        if (
            not isinstance(obj, dict)
            or type(obj.get("page")) is not int
            or obj["page"] != number
            or type(obj.get("page_size")) is not int
            or obj["page_size"] != 2000
            or type(obj.get("has_more")) is not bool
            or not isinstance(obj.get("fills"), list)
            or len(obj["fills"]) > 2000
            or (number < max(indices) and not obj["has_more"])
        ):
            raise ValueError("UNVERIFIED_SOURCE_PAGINATION")
        for row in obj["fills"]:
            if not isinstance(row, dict) or type(row.get("tid")) is not int:
                raise ValueError("MISSING_FRESH_RECEIPT_ID")
            if row["tid"] in tids:
                raise ValueError("DUPLICATE_FRESH_RECEIPT_ID")
            tids.add(row["tid"])
        pages.append(obj)
    return pages


def read_ledger_page(root: Path, alias: str, tag: str, number: int) -> list[dict]:
    generation = read_generation(root, "HL_LEDGER_BACKFILL")
    if generation is None or tag not in {"funding", "collateral"}:
        raise ValueError("UNBOUND_LEDGER_GENERATION")
    suffix = Path(alias) / tag / f"page-{number:03d}.json"
    raw = _read(root / "raw" / suffix, MAX_RAW)
    receipt = LedgerPageReceipt.model_validate(parse(_read(root / "metadata" / suffix, 65536)))
    kind = "userFunding" if tag == "funding" else "userNonFundingLedgerUpdates"
    if (
        receipt.generation_id != generation.generation_id
        or receipt.alias != alias
        or receipt.page != number
        or receipt.kind != kind
    ):
        raise ValueError("LEDGER_GENERATION_IDENTITY_MISMATCH")
    rows = parse(raw)
    verify_raw(rows, raw, receipt.sha256)
    if not isinstance(rows, list) or len(rows) != receipt.rows:
        raise ValueError("LEDGER_RECEIPT_ROW_MISMATCH")
    return rows


MAX_ACQUISITION_WORKERS = 8
MAX_LOCAL_PARTITION_BYTES = 256 * 1024 * 1024
LOCAL_PARTITION_SCHEMA = "pm_local_immutable_partition_v1"
PARQUET_MAGIC = b"PAR1"
_HEX64 = re.compile(r"^[0-9a-f]{64}$")
_SAFE_PART = re.compile(r"^[A-Za-z0-9._-]+$")
_DAY_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class AcquisitionContractError(ValueError):
    """Typed contract/integrity failure for bounded research acquisition."""

    def __init__(self, code: str, message: str | None = None) -> None:
        super().__init__(message or code)
        self.code = code


class BoundedAcquisitionBudget(BaseModel):
    """Strict non-boolean resource limits for bounded remote acquisition."""

    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)

    max_requests: int = Field(ge=0)
    max_remote_bytes: int = Field(ge=0)
    max_disk_bytes: int = Field(ge=0)
    max_workers: int = Field(default=1, ge=1, le=MAX_ACQUISITION_WORKERS)
    require_observable_remote_bytes: bool = False


def parse_acquisition_budget(raw: object) -> BoundedAcquisitionBudget:
    """Validate acquisition budget strictly; booleans and unknown fields fail."""
    if not isinstance(raw, dict):
        raise ValueError("INVALID_ACQUISITION_BUDGET")
    try:
        return BoundedAcquisitionBudget.model_validate(raw)
    except ValidationError as exc:
        raise ValueError(f"INVALID_ACQUISITION_BUDGET:{exc.errors()[0]['loc']}") from exc


def validate_parquet_framing(data: bytes) -> int:
    """Verify PAR1 magic header/footer and footer length bounds in pure Python."""
    if len(data) < 12 or data[:4] != PARQUET_MAGIC or data[-4:] != PARQUET_MAGIC:
        raise AcquisitionContractError("CORRUPT_REMOTE_PAGE", "CORRUPT_PARQUET_FRAMING")
    (footer_len,) = struct.unpack("<I", data[-8:-4])
    if footer_len > len(data) - 12:
        raise AcquisitionContractError("CORRUPT_REMOTE_PAGE", "CORRUPT_PARQUET_FOOTER_LENGTH")
    return footer_len


def _check_no_symlink_ancestors(root: Path, leaf: Path) -> None:
    if root.is_symlink():
        raise AcquisitionContractError("CORRUPT_LOCAL_PARTITION", "SYMLINK_PARTITION_ROOT")
    rel = leaf.relative_to(root)
    cur = root
    for part in rel.parts:
        cur = cur / part
        if cur.is_symlink():
            raise AcquisitionContractError("CORRUPT_LOCAL_PARTITION", f"SYMLINK_PATH:{part}")


def parse_utc_clock(value: object) -> datetime:
    """Parse an explicit timezone-aware ISO UTC clock or raise CORRUPT_LOCAL_PARTITION."""
    if not isinstance(value, str) or not value:
        raise AcquisitionContractError("CORRUPT_LOCAL_PARTITION", "INVALID_PARTITION_CLOCK")
    try:
        dt = datetime.fromisoformat(value)
    except ValueError as exc:
        raise AcquisitionContractError(
            "CORRUPT_LOCAL_PARTITION", "INVALID_PARTITION_CLOCK"
        ) from exc
    if dt.tzinfo is None or dt.utcoffset() is None:
        raise AcquisitionContractError("CORRUPT_LOCAL_PARTITION", "NAIVE_PARTITION_CLOCK")
    return dt.astimezone(UTC)


def epoch_ms(iso_clock: str) -> int:
    """Convert an ISO UTC timestamp string to integer epoch milliseconds."""
    return int(datetime.fromisoformat(iso_clock).astimezone(UTC).timestamp() * 1000)


def _hive_partition_folder(
    partition_root: Path, *, kind: str, dex: str, wallet: str, date: str
) -> Path:
    year, month, day = date.split("-")
    hive_tail = Path(f"year={year}") / f"month={month}" / f"day={day}"
    if kind == "source":
        return partition_root / "source" / dex / wallet / hive_tail
    return partition_root / "market" / dex / hive_tail


def verify_local_immutable_partition(
    partition_root: Path,
    *,
    kind: str,
    dex: str,
    wallet: str,
    date: str,
    as_of: datetime,
    input_sha256: str,
    source_sha256: str,
    market_sha256: str,
) -> dict[str, Any]:
    """Verify an existing local Hive immutable partition without creating or mutating files."""
    if (
        kind not in {"source", "market"}
        or not _SAFE_PART.fullmatch(dex)
        or not _SAFE_PART.fullmatch(wallet)
        or not _DAY_RE.fullmatch(date)
    ):
        raise ValueError("INVALID_LOCAL_PARTITION_COORDINATES")
    if partition_root.is_symlink():
        raise AcquisitionContractError("CORRUPT_LOCAL_PARTITION", "SYMLINK_PARTITION_ROOT")
    if not partition_root.exists():
        return {"present": False, "reusable": False}
    if not partition_root.is_dir():
        raise AcquisitionContractError("CORRUPT_LOCAL_PARTITION", "NON_DIR_PARTITION_ROOT")

    folder = _hive_partition_folder(partition_root, kind=kind, dex=dex, wallet=wallet, date=date)
    _check_no_symlink_ancestors(partition_root, folder)
    if not folder.exists():
        return {"present": False, "reusable": False}
    if not folder.is_dir():
        raise AcquisitionContractError("CORRUPT_LOCAL_PARTITION", "NON_DIR_PARTITION_FOLDER")

    data_candidates = [folder / "data.parquet", folder / "data.json"]
    sidecar_candidates = [folder / "source.json", folder / "manifest.json"]
    for cand in (*data_candidates, *sidecar_candidates):
        if cand.is_symlink():
            raise AcquisitionContractError("CORRUPT_LOCAL_PARTITION", "SYMLINK_PARTITION_FILE")

    data_files = [p for p in data_candidates if p.exists()]
    sidecars = [p for p in sidecar_candidates if p.exists()]
    if not data_files and not sidecars:
        if any(folder.iterdir()):
            raise AcquisitionContractError(
                "CORRUPT_LOCAL_PARTITION", "UNRECOGNIZED_PARTITION_FILES"
            )
        return {"present": False, "reusable": False}
    if len(data_files) != 1 or len(sidecars) != 1:
        raise AcquisitionContractError("CORRUPT_LOCAL_PARTITION", "INCOMPLETE_PARTITION_PAIR")

    data_path = data_files[0]
    sidecar_path = sidecars[0]
    st_data = data_path.lstat()
    st_side = sidecar_path.lstat()
    if (
        stat.S_ISLNK(st_data.st_mode)
        or not stat.S_ISREG(st_data.st_mode)
        or stat.S_ISLNK(st_side.st_mode)
        or not stat.S_ISREG(st_side.st_mode)
    ):
        raise AcquisitionContractError("CORRUPT_LOCAL_PARTITION", "UNSAFE_PARTITION_FILE")
    if st_data.st_size > MAX_LOCAL_PARTITION_BYTES or st_side.st_size > 1024 * 1024:
        raise AcquisitionContractError("CORRUPT_LOCAL_PARTITION", "OVERSIZED_PARTITION_FILE")

    try:
        meta = json.loads(
            sidecar_path.read_bytes().decode("utf-8"), object_pairs_hook=_object_pairs
        )
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise AcquisitionContractError(
            "CORRUPT_LOCAL_PARTITION", "CORRUPT_PARTITION_SIDECAR"
        ) from exc
    if not isinstance(meta, dict) or meta.get("schema") != LOCAL_PARTITION_SCHEMA:
        raise AcquisitionContractError("CORRUPT_LOCAL_PARTITION", "INVALID_PARTITION_SCHEMA")

    for req_key in (
        "kind",
        "dex",
        "wallet",
        "date",
        "known_at",
        "input_sha256",
        "source_sha256",
        "sha256",
    ):
        if req_key not in meta:
            raise AcquisitionContractError("CORRUPT_LOCAL_PARTITION", f"MISSING_META:{req_key}")
    if (
        meta.get("kind") != kind
        or meta.get("dex") != dex
        or meta.get("wallet") != wallet
        or meta.get("date") != date
    ):
        raise AcquisitionContractError("CORRUPT_LOCAL_PARTITION", "PARTITION_COORDINATE_MISMATCH")

    declared_sha = meta.get("sha256")
    declared_bytes = meta.get("bytes")
    declared_rows = meta.get("rows")
    if (
        not isinstance(declared_sha, str)
        or not _HEX64.fullmatch(declared_sha)
        or type(declared_bytes) is not int
        or declared_bytes < 0
        or type(declared_rows) is not int
        or declared_rows < 0
    ):
        raise AcquisitionContractError("CORRUPT_LOCAL_PARTITION", "INVALID_PARTITION_COUNTS")
    for sha_field in ("input_sha256", "source_sha256"):
        val = meta.get(sha_field)
        if not isinstance(val, str) or not _HEX64.fullmatch(val):
            raise AcquisitionContractError(
                "CORRUPT_LOCAL_PARTITION", f"INVALID_META_{sha_field.upper()}"
            )
    if "market_sha256" in meta:
        mval = meta["market_sha256"]
        if not isinstance(mval, str) or not _HEX64.fullmatch(mval):
            raise AcquisitionContractError("CORRUPT_LOCAL_PARTITION", "INVALID_META_MARKET_SHA256")

    raw = data_path.read_bytes()
    actual_sha = sha256(raw).hexdigest()
    if len(raw) != declared_bytes or actual_sha != declared_sha:
        raise AcquisitionContractError("CORRUPT_LOCAL_PARTITION", "CORRUPT_PARTITION_SHA")
    if data_path.suffix == ".parquet":
        try:
            validate_parquet_framing(raw)
        except AcquisitionContractError as exc:
            raise AcquisitionContractError("CORRUPT_LOCAL_PARTITION", str(exc)) from exc

    known_at = parse_utc_clock(meta["known_at"])
    expected_digest_ok = meta["input_sha256"] == input_sha256 and (
        meta["source_sha256"] == source_sha256
        if kind == "source"
        else meta.get("market_sha256") == market_sha256
    )
    if not expected_digest_ok:
        return {
            "present": True,
            "reusable": False,
            "reason": "INPUT_OR_SOURCE_BINDING_MISMATCH",
            "sha256": actual_sha,
        }
    if known_at > as_of:
        return {
            "present": True,
            "reusable": False,
            "reason": "KNOWN_AFTER_AS_OF",
            "sha256": actual_sha,
        }
    return {
        "present": True,
        "reusable": True,
        "kind": kind,
        "dex": dex,
        "wallet": wallet,
        "date": date,
        "known_at": meta["known_at"],
        "input_sha256": meta["input_sha256"],
        "source_sha256": meta["source_sha256"],
        "market_sha256": meta.get("market_sha256"),
        "sha256": actual_sha,
        "bytes": declared_bytes,
        "rows": declared_rows,
        "path": str(data_path),
    }


def _strict_nonneg_int(value: object, code: str, field: str) -> int:
    if type(value) is not int or value < 0:
        raise AcquisitionContractError(code, f"INVALID_{field.upper()}")
    return value


def _row_group_pruned(rg: dict[str, Any], unit: dict[str, Any]) -> bool:
    columns = rg.get("columns") or {}
    if unit.get("kind") == "source":
        target_wallets = set(unit.get("target_wallets") or ())
        if target_wallets:
            u_meta = columns.get("user") or columns.get("wallet") or {}
            if isinstance(u_meta, dict) and u_meta.get("has_stats") is True:
                present = u_meta.get("wallets_present")
                if isinstance(present, (list, tuple, set)):
                    if target_wallets.isdisjoint(set(present)):
                        return True
                cmin, cmax = u_meta.get("min"), u_meta.get("max")
                if isinstance(cmin, str) and isinstance(cmax, str):
                    if all(w < cmin or w > cmax for w in target_wallets):
                        return True
    t_meta = columns.get("time") or columns.get("ts_ms") or {}
    if isinstance(t_meta, dict) and t_meta.get("has_stats") is True:
        tmin, tmax = t_meta.get("min"), t_meta.get("max")
        if (
            type(tmin) is int
            and type(tmax) is int
            and unit.get("utc_start")
            and unit.get("utc_end")
        ):
            s_ms = epoch_ms(unit["utc_start"])
            e_ms = epoch_ms(unit["utc_end"])
            if tmax < s_ms or tmin >= e_ms:
                return True
    return False


def predict_unit_cost(unit: dict[str, Any], meta: object) -> dict[str, Any]:
    """Predict remote column/row-group compressed-byte cost and requests for one unit."""
    if not isinstance(meta, dict):
        raise AcquisitionContractError("CORRUPT_REMOTE_PAGE", "INVALID_REMOTE_METADATA")
    object_bytes = _strict_nonneg_int(
        meta.get("object_bytes", 0), "CORRUPT_REMOTE_PAGE", "object_bytes"
    )
    meta_reqs = _strict_nonneg_int(
        meta.get("metadata_requests", 1), "CORRUPT_REMOTE_PAGE", "metadata_requests"
    )
    projected_columns = tuple(unit["projected_columns"])

    schema_cols = meta.get("schema_columns")
    if schema_cols is not None:
        if not isinstance(schema_cols, (list, tuple)) or any(
            not isinstance(c, str) for c in schema_cols
        ):
            raise AcquisitionContractError("CORRUPT_REMOTE_PAGE", "INVALID_SCHEMA_COLUMNS")
        missing_cols = sorted(set(projected_columns) - set(schema_cols))
        if missing_cols:
            raise AcquisitionContractError(
                "CORRUPT_REMOTE_PAGE", f"MISSING_PROJECTED_COLUMNS:{','.join(missing_cols)}"
            )

    raw_rgs = meta.get("row_groups")
    if not isinstance(raw_rgs, (list, tuple)):
        raise AcquisitionContractError("CORRUPT_REMOTE_PAGE", "INVALID_ROW_GROUPS")

    selected_rg_ids: list[int] = []
    pruned_rg_ids: list[int] = []
    compressed_bytes = 0
    for rg in raw_rgs:
        if not isinstance(rg, dict):
            raise AcquisitionContractError("CORRUPT_REMOTE_PAGE", "INVALID_ROW_GROUP_ENTRY")
        rg_id = _strict_nonneg_int(rg.get("row_group_id"), "CORRUPT_REMOTE_PAGE", "row_group_id")
        _strict_nonneg_int(rg.get("num_rows", 0), "CORRUPT_REMOTE_PAGE", "num_rows")
        cols_meta = rg.get("columns")
        if not isinstance(cols_meta, dict):
            raise AcquisitionContractError("CORRUPT_REMOTE_PAGE", "INVALID_ROW_GROUP_COLUMNS")
        for col in projected_columns:
            if col not in cols_meta or not isinstance(cols_meta[col], dict):
                raise AcquisitionContractError("CORRUPT_REMOTE_PAGE", f"MISSING_RG_COLUMN:{col}")
            _strict_nonneg_int(
                cols_meta[col].get("compressed_bytes"), "CORRUPT_REMOTE_PAGE", "compressed_bytes"
            )
        if _row_group_pruned(rg, unit):
            pruned_rg_ids.append(rg_id)
            continue
        selected_rg_ids.append(rg_id)
        for col in projected_columns:
            compressed_bytes += int(cols_meta[col]["compressed_bytes"])

    range_per_rg = bool(meta.get("range_per_row_group", False))
    scan_reqs = (
        len(selected_rg_ids) if range_per_rg else (1 if (selected_rg_ids or not raw_rgs) else 0)
    )

    est_rows_raw = meta.get("estimated_filtered_return_rows")
    if est_rows_raw is not None:
        est_rows: int | None = _strict_nonneg_int(
            est_rows_raw, "CORRUPT_REMOTE_PAGE", "estimated_filtered_return_rows"
        )
    else:
        est_rows = None

    est_out_raw = meta.get("estimated_output_bytes")
    if est_out_raw is not None:
        predicted_disk_bytes = _strict_nonneg_int(
            est_out_raw, "CORRUPT_REMOTE_PAGE", "estimated_output_bytes"
        )
    elif est_rows is not None:
        predicted_disk_bytes = est_rows * 256
    else:
        predicted_disk_bytes = compressed_bytes

    return {
        "metadata_requests": meta_reqs,
        "scan_requests": scan_reqs,
        "predicted_requests": meta_reqs + scan_reqs,
        "predicted_remote_object_bytes": object_bytes,
        "predicted_remote_compressed_bytes": compressed_bytes,
        "predicted_disk_bytes": predicted_disk_bytes,
        "selected_row_groups": selected_rg_ids,
        "stats_pruned_row_groups": len(pruned_rg_ids),
        "estimated_filtered_return_rows": est_rows,
    }
