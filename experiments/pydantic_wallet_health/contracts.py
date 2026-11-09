"""Read-only experiment contracts. No source, selection or financial authority."""

from __future__ import annotations

from decimal import Decimal
from hashlib import sha256
import json
from typing import Annotated, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator, model_validator

from copytrade_pm.pm_agent_trace_eval import _object, SENSITIVE

Amount = Annotated[str, Field(pattern=r"^-?(?:0|[1-9]\d*)(?:\.\d+)?$", max_length=48)]
Label = Literal[
    "WITHDRAWAL",
    "TOP_UP",
    "REALIZED_LOSS",
    "UNREALIZED_LOSS",
    "COST_DRAG",
    "LIQUIDATION",
    "INACTIVE_SOLVENT",
    "MIXED_FLOWS",
    "EQUITY_GAIN",
    "ACTIVE_NO_MATERIAL_CHANGE",
    "STALE_EVIDENCE",
    "INSUFFICIENT_EVIDENCE",
]
ABSTAIN = frozenset({"STALE_EVIDENCE", "INSUFFICIENT_EVIDENCE"})
CASH_KINDS = frozenset(
    {
        "DEPOSIT",
        "WITHDRAWAL",
        "REALIZED_PNL",
        "UNREALIZED_DELTA",
        "FEES",
        "FUNDING",
    }
)


def canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class ReceiptData(Strict):
    kind: Literal[
        "EQUITY_BEFORE",
        "EQUITY_AFTER",
        "DEPOSIT",
        "WITHDRAWAL",
        "REALIZED_PNL",
        "UNREALIZED_DELTA",
        "FEES",
        "FUNDING",
        "ACTIVITY",
        "COVERAGE",
        "LIQUIDATION",
    ]
    observed_at: AwareDatetime
    known_at: AwareDatetime
    window_start: AwareDatetime | None = None
    value: Amount | None = None
    count: Annotated[int, Field(ge=0)] | None = None
    complete: bool = False

    @model_validator(mode="after")
    def coherent(self):
        if self.observed_at > self.known_at:
            raise ValueError("RECEIPT_CLOCK_ORDER")
        aggregated = self.kind in CASH_KINDS or self.kind in {"ACTIVITY", "COVERAGE"}
        if aggregated != (self.window_start is not None):
            raise ValueError("RECEIPT_AGGREGATION_WINDOW")
        if self.window_start is not None and self.window_start >= self.observed_at:
            raise ValueError("RECEIPT_EMPTY_OR_REVERSED_WINDOW")
        numeric = self.kind in CASH_KINDS or self.kind.startswith("EQUITY_")
        if numeric != (self.value is not None):
            raise ValueError("RECEIPT_VALUE_REQUIRED_OR_FORBIDDEN")
        if (self.kind == "ACTIVITY") != (self.count is not None):
            raise ValueError("RECEIPT_ACTIVITY_COUNT")
        if self.value is not None:
            value = Decimal(self.value)
            if self.kind in {"WITHDRAWAL", "FEES"} and value > 0:
                raise ValueError("NEGATIVE_CONTRIBUTION_REQUIRED")
            if self.kind in {"DEPOSIT", "EQUITY_BEFORE", "EQUITY_AFTER"} and value < 0:
                raise ValueError("NONNEGATIVE_VALUE_REQUIRED")
        return self


class Evidence(Strict):
    receipt_id: Annotated[str, Field(pattern=r"^e\d{2}$")]
    raw: Annotated[str, Field(max_length=2048)]
    raw_sha: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]

    @model_validator(mode="after")
    def original_bytes(self):
        if sha256(self.raw.encode()).hexdigest() != self.raw_sha:
            raise ValueError("RAW_SHA_MISMATCH")
        json.loads(self.raw, object_pairs_hook=_object)
        ReceiptData.model_validate_json(self.raw)
        return self

    @property
    def data(self) -> ReceiptData:
        return ReceiptData.model_validate_json(self.raw)


class TaskInput(Strict):
    case_id: Annotated[str, Field(pattern=r"^c\d{3}$")]
    wallet_alias: Annotated[str, Field(pattern=r"^FAKE\d{3}$")]
    as_of: AwareDatetime
    receipts: Annotated[tuple[Evidence, ...], Field(max_length=32)]

    @model_validator(mode="after")
    def unique_receipts(self):
        ids = [r.receipt_id for r in self.receipts]
        if len(ids) != len(set(ids)):
            raise ValueError("DUPLICATE_RECEIPT")
        return self

    def pit_view(self) -> TaskInput:
        return self.model_copy(
            update={
                "receipts": tuple(
                    r
                    for r in self.receipts
                    if r.data.known_at <= self.as_of and r.data.observed_at <= self.as_of
                ),
            }
        )

    @property
    def input_sha(self) -> str:
        return sha256(canonical(self.model_dump(mode="json"))).hexdigest()


class ToolUse(Strict):
    name: Annotated[str, Field(pattern=r"^[a-z_]{1,40}$")]
    case_id: Annotated[str, Field(pattern=r"^c\d{3}$")]
    receipt_ids: tuple[Annotated[str, Field(pattern=r"^e\d{2}$")], ...] = ()
    read_only: bool


class Diagnosis(Strict):
    label: Label
    confidence: Annotated[float, Field(ge=0, le=1, allow_inf_nan=False)]
    evidence_ids: tuple[Annotated[str, Field(pattern=r"^e\d{2}$")], ...]
    edge_decay: Literal["INSUFFICIENT_EVIDENCE", "CLAIMED"] = "INSUFFICIENT_EVIDENCE"
    tool_calls: Annotated[tuple[ToolUse, ...], Field(max_length=32)] = ()
    trading_authorized: Literal[False] = False
    scientifically_qualified: Literal[False] = False

    @field_validator("trading_authorized", "scientifically_qualified", mode="before")
    @classmethod
    def no_authority(cls, value):
        if value is not False:
            raise ValueError("DIAGNOSTICS_HAVE_NO_AUTHORITY")
        return value

    @model_validator(mode="after")
    def abstention(self):
        if self.label in ABSTAIN and self.confidence > 0.5:
            raise ValueError("CONFIDENT_ABSTENTION")
        if len(set(self.evidence_ids)) != len(self.evidence_ids):
            raise ValueError("DUPLICATE_CITATION")
        return self


class CapturedAnswer(Strict):
    case_id: Annotated[str, Field(pattern=r"^c\d{3}$")]
    input_sha: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
    diagnosis: Diagnosis
    input_tokens: Annotated[int, Field(ge=0)] | None = None
    output_tokens: Annotated[int, Field(ge=0)] | None = None
    api_cost_usd: Amount | None = None

    @model_validator(mode="after")
    def cost(self):
        if self.api_cost_usd is not None and Decimal(self.api_cost_usd) < 0:
            raise ValueError("NEGATIVE_RESOURCE_COST")
        return self


class Capture(Strict):
    schema_version: Literal["wallet_diagnostic_capture_v1"] = Field(alias="schema")
    corpus_sha: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
    capture_kind: Literal["SYNTHETIC", "HOST_EXPORT"]
    model_id: Annotated[str, Field(pattern=r"^[A-Za-z0-9._:/-]{1,100}$")]
    answers: Annotated[tuple[CapturedAnswer, ...], Field(min_length=1, max_length=128)]

    @model_validator(mode="after")
    def safe_metadata(self):
        if SENSITIVE.search(self.model_id) or "0x" in self.model_id:
            raise ValueError("UNSAFE_MODEL_METADATA")
        return self
