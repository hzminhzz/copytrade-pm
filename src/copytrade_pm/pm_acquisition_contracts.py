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
from typing import Annotated, Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

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
