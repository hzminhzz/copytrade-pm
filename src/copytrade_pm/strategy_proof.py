"""Nonactivating Track B v2 original-proof reference and independent Track C check.

Reference SHA verifies only an immutable claim. Source packets, market quote
chain and original PM03 reducer must each be checked anew by the consumer.
"""

from __future__ import annotations

from contextlib import closing
from datetime import datetime
import json
import os
from pathlib import Path
import sqlite3
import stat
from typing import Literal

from pydantic import Field, model_validator

from .pm03_account import clock, digest
from .pm_private_io import atomic_private_output
from .production_manifest import canonical
from .strategy_finance import inspect_pm03_original
from .strategy_health import Strict, StrategyAssessment, canonical_report, utc
from .strategy_source_verify import verify_packet

SHA = r"^[a-f0-9]{64}$"
PATH = 2048


class MarketQuoteReference(Strict):
    instrument: str = Field(min_length=1, max_length=120)
    original_quote_id: str = Field(min_length=1, max_length=150)
    quote_payload_sha256: str = Field(pattern=SHA)
    source_known_at: datetime
    consumed_at: datetime

    @model_validator(mode="after")
    def causal(self):
        utc(self.source_known_at)
        utc(self.consumed_at)
        if self.source_known_at > self.consumed_at:
            raise ValueError("MARKET_RECEIPT_AFTER_DECISION")
        return self


class OriginalProofReference(Strict):
    schema_version: Literal["strategy_health_evidence_ref_v1"] = Field(
        default="strategy_health_evidence_ref_v1", alias="schema"
    )
    report_sha256: str = Field(pattern=SHA)
    strategy_sha256: str = Field(pattern=SHA)
    campaign_sha256: str = Field(pattern=SHA)
    source_account_sha256: str = Field(pattern=SHA)
    selection_seal_sha256: str = Field(pattern=SHA)
    k_policy_sha256: str = Field(pattern=SHA)
    k_version: str = Field(min_length=1, max_length=128)
    as_of: datetime
    selected_source_journal: str = Field(min_length=1, max_length=PATH)
    original_source_head_sha256: str = Field(pattern=SHA)
    source_after_cursor: int = Field(ge=0)
    selected_source_alias: str = Field(min_length=1, max_length=128)
    original_market_journal: str = Field(min_length=1, max_length=PATH)
    market_quote_refs: tuple[MarketQuoteReference, ...] = Field(default=(), max_length=10000)
    original_pm03_root: str = Field(min_length=1, max_length=PATH)
    original_pm03_head_sha256: str = Field(pattern=SHA)
    original_pm03_manifest_sha256: str = Field(pattern=SHA)
    underlying_class: Literal["RESEARCH_SYNTHETIC", "PROSPECTIVE_SHADOW", "UNKNOWN"]
    ref_sha256: str = Field(default="0" * 64, pattern=SHA)
    read_only: Literal[True] = True
    trading_authorized: Literal[False] = False
    active_k_changed: Literal[False] = False
    track_c_input_qualified: Literal[False] = False

    @model_validator(mode="after")
    def validate_ref(self):
        utc(self.as_of)
        for path in (
            self.selected_source_journal,
            self.original_market_journal,
            self.original_pm03_root,
        ):
            if not Path(path).is_absolute() or ".." in Path(path).parts:
                raise ValueError("TRACK_C_PRIVATE_PATH_INVALID")
        if len({(m.instrument, m.original_quote_id) for m in self.market_quote_refs}) != len(
            self.market_quote_refs
        ):
            raise ValueError("TRACK_C_MARKET_REF_DUPLICATE")
        if any(m.consumed_at > self.as_of for m in self.market_quote_refs):
            raise ValueError("TRACK_C_FUTURE_MARKET")
        return self


def _body(ref: OriginalProofReference) -> dict:
    return ref.model_dump(mode="json", exclude={"ref_sha256"})


def seal_reference(ref: OriginalProofReference) -> OriginalProofReference:
    if ref.ref_sha256 != "0" * 64:
        raise ValueError("TRACK_C_REFERENCE_ALREADY_SEALED")
    return ref.model_copy(update={"ref_sha256": digest(_body(ref))})


def verify_reference_hash(ref: OriginalProofReference) -> None:
    if ref.ref_sha256 != digest(_body(ref)):
        raise ValueError("TRACK_C_REFERENCE_HASH_INVALID")


def publish_reference(ref: OriginalProofReference, path: Path) -> None:
    verify_reference_hash(ref)
    atomic_private_output(path, canonical(ref.model_dump(mode="json")))


def read_reference(path: Path) -> OriginalProofReference:
    if path.is_symlink():
        raise ValueError("TRACK_C_REF_SYMLINK")
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        info = os.fstat(fd)
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_mode & 0o777 != 0o600
            or (not 0 < info.st_size <= 2_000_000)
        ):
            raise ValueError("TRACK_C_REF_UNSAFE_FILE")
        raw = os.read(fd, 2_000_001)
        if len(raw) != info.st_size:
            raise ValueError("TRACK_C_REF_TRUNCATED")
    finally:
        os.close(fd)
    ref = OriginalProofReference.model_validate_json(raw, strict=True)
    verify_reference_hash(ref)
    if canonical(ref.model_dump(mode="json")) != raw:
        raise ValueError("TRACK_C_REF_NONCANONICAL")
    return ref


def _original_market_quote(db_path: Path, quote: MarketQuoteReference) -> dict:
    """Inspect existing market_quote_receipts with original stream hash owner."""
    if db_path.is_symlink() or not db_path.is_file():
        raise ValueError("ORIGINAL_MARKET_JOURNAL_UNAVAILABLE")
    uri = "file:" + str(db_path.resolve()) + "?mode=ro"
    with closing(sqlite3.connect(uri, uri=True, timeout=5)) as db:
        db.execute("PRAGMA query_only=ON")
        db.execute("BEGIN")
        try:
            row = db.execute(
                "SELECT seq,quote_id,payload,payload_sha,prior_sha,chain_sha "
                "FROM market_quote_receipts WHERE instrument=? AND quote_id=?",
                (quote.instrument, quote.original_quote_id),
            ).fetchone()
            heads = db.execute(
                "SELECT cursor,chain_sha FROM market_quote_heads WHERE instrument=?",
                (quote.instrument,),
            ).fetchone()
            chain_rows = db.execute(
                "SELECT seq,quote_id,payload,payload_sha,prior_sha,chain_sha "
                "FROM market_quote_receipts WHERE instrument=? ORDER BY seq",
                (quote.instrument,),
            ).fetchall()
            db.execute("ROLLBACK")
        except sqlite3.DatabaseError as exc:
            raise ValueError("ORIGINAL_MARKET_RECEIPT_UNAVAILABLE") from exc
    if row is None or heads is None or not chain_rows or heads[0] != len(chain_rows):
        raise ValueError("ORIGINAL_MARKET_RECEIPT_UNAVAILABLE")
    previous = "0" * 64
    for index, receipt in enumerate(chain_rows, 1):
        seq, _quote_id, raw_payload, payload_hash, prior_sha, chain_sha = receipt
        if (
            seq != index
            or prior_sha != previous
            or digest(json.loads(raw_payload)) != payload_hash
            or chain_sha != digest([quote.instrument, seq, payload_hash, prior_sha])
            or _quote_id != payload_hash
        ):
            raise ValueError("ORIGINAL_MARKET_CHAIN_DIVERGENCE")
        previous = chain_sha
    if heads[1] != previous or row not in chain_rows:
        raise ValueError("ORIGINAL_MARKET_CHAIN_DIVERGENCE")
    seq, key, payload, payload_sha, prior, chain = row
    if payload_sha != quote.quote_payload_sha256:
        raise ValueError("ORIGINAL_MARKET_QUOTE_DIVERGENCE")
    decoded = json.loads(payload)
    observed = clock(decoded["first_known_at"])
    if observed != quote.source_known_at or observed > quote.consumed_at:
        raise ValueError("ORIGINAL_MARKET_QUOTE_CLOCK_MISMATCH")
    return decoded


def create_reference(
    report: StrategyAssessment,
    *,
    original_source_journal: Path,
    original_source_head_sha256: str,
    source_after_cursor: int,
    original_market_journal: Path,
    market_quote_refs: tuple[MarketQuoteReference, ...],
    original_pm03_root: Path,
    original_pm03_head_sha256: str,
    original_pm03_manifest_sha256: str,
) -> OriginalProofReference:
    canonical_report(report)
    if report.strategy.tier != "SELECTED":
        raise ValueError("DISCOVERY_HAS_NO_ORIGINAL_PROOF_REFERENCE")
    scope = report.strategy
    return seal_reference(
        OriginalProofReference(
            report_sha256=report.report_sha256,
            strategy_sha256=scope.strategy_sha256,
            campaign_sha256=digest(report.campaign.model_dump(mode="json")),
            source_account_sha256=scope.source_account_sha256,
            selection_seal_sha256=scope.selection_seal_sha256,
            k_policy_sha256=scope.k_policy_sha256,
            k_version=scope.k_version,
            as_of=report.as_of,
            selected_source_journal=str(original_source_journal.resolve()),
            original_source_head_sha256=original_source_head_sha256,
            source_after_cursor=source_after_cursor,
            selected_source_alias=scope.source_alias,
            original_market_journal=str(original_market_journal.resolve()),
            market_quote_refs=market_quote_refs,
            original_pm03_root=str(original_pm03_root.resolve()),
            original_pm03_head_sha256=original_pm03_head_sha256,
            original_pm03_manifest_sha256=original_pm03_manifest_sha256,
            underlying_class={
                "RESEARCH_SYNTHETIC": "RESEARCH_SYNTHETIC",
                "PROSPECTIVE_SHADOW": "PROSPECTIVE_SHADOW",
            }.get(report.follower_economics.evidence_class, "UNKNOWN"),
        )
    )


def verify_originals_for_track_c(
    ref: OriginalProofReference,
    report: StrategyAssessment,
    *,
    signed_packet: dict,
    source_public_key,
    selected: dict[str, str],
    pinned_source_journal: Path,
    pinned_market_journal: Path,
    pinned_pm03_root: Path,
) -> dict:
    """Read-only provenance inspection; never converts into Track C FinanceWindow."""
    verify_reference_hash(ref)
    canonical_report(report)
    if (
        ref.report_sha256 != report.report_sha256
        or ref.strategy_sha256 != report.strategy.strategy_sha256
        or ref.campaign_sha256 != digest(report.campaign.model_dump(mode="json"))
        or ref.k_version != report.strategy.k_version
        or ref.k_policy_sha256 != report.strategy.k_policy_sha256
        or ref.source_account_sha256 != report.strategy.source_account_sha256
        or ref.selection_seal_sha256 != report.strategy.selection_seal_sha256
        or ref.as_of != report.as_of
        or ref.selected_source_alias != report.strategy.source_alias
    ):
        raise ValueError("TRACK_C_REPORT_STRATEGY_POLICY_DRIFT")
    bindings = (
        (ref.selected_source_journal, pinned_source_journal),
        (ref.original_market_journal, pinned_market_journal),
        (ref.original_pm03_root, pinned_pm03_root),
    )
    if any(path != str(pinned.resolve()) or pinned.is_symlink() for path, pinned in bindings):
        raise ValueError("TRACK_C_ORIGINAL_PATH_NOT_OPERATOR_PINNED")
    observed = verify_packet(
        signed_packet,
        source_public_key,
        selected=selected,
        original_journal=pinned_source_journal,
        after={ref.selected_source_alias: ref.source_after_cursor},
        as_of=ref.as_of,
        policy_version=ref.k_version,
        frozen_k=str(report.strategy.frozen_k),
    )
    if observed["verified_original_journal_sha256"] != ref.original_source_head_sha256:
        raise ValueError("TRACK_C_ORIGINAL_SOURCE_HEAD_DIVERGED")
    original_ids = {x["opportunity_id"] for x in observed["opportunities"]}
    report_ids = {x.opportunity_id for x in report.opportunities}
    if not report_ids <= original_ids:
        raise ValueError("TRACK_C_ORIGINAL_SOURCE_NOT_MATCHED")
    originals = inspect_pm03_original(
        pinned_pm03_root,
        as_of=ref.as_of,
        expected_head=ref.original_pm03_head_sha256,
    )
    if originals["manifest_sha256"] != ref.original_pm03_manifest_sha256:
        raise ValueError("TRACK_C_ORIGINAL_PM03_MANIFEST_CHANGED")
    if (
        ref.underlying_class
        != {
            "RESEARCH_SYNTHETIC": "RESEARCH_SYNTHETIC",
            "PROSPECTIVE_OBSERVED": "PROSPECTIVE_SHADOW",
            "HISTORICAL_HINDSIGHT": "UNKNOWN",
        }[originals["mode"]]
    ):
        raise ValueError("TRACK_C_ORIGINAL_FINANCE_EVIDENCE_CLASS_MISMATCH")
    checked_quotes = [
        _original_market_quote(pinned_market_journal, row) for row in ref.market_quote_refs
    ]
    # Even genuine quote hashes do not prove fill-side/fee/funding/broker
    # completeness or make a financial window independently calibrated.
    return {
        "schema": "track_c_strategy_health_original_verification_v1",
        "source_original_reverified": True,
        "pm03_original_replay_verified": True,
        "market_original_receipts_verified": len(checked_quotes),
        "evidence_class": ref.underlying_class,
        "original_report_sha256": ref.report_sha256,
        "original_finance_head_sha256": originals["ledger_head_sha256"],
        "independent_follower_economics_qualified": False,
        "research_finance_window_admitted": False,
        "scientific_qualification": False,
        "trading_authorized": False,
        "active_k_changed": False,
        "blockers": [
            "INDEPENDENT_PROSPECTIVE_PROOF_ADAPTER_NOT_INSTALLED",
            "RUNTIME_RELEASE_CONSUMER_NOT_VERSION_AWARE",
            "INDEPENDENT_MARKET_FEE_FUNDING_MATCHING_NOT_QUALIFIED",
        ],
    }
