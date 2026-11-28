"""Verified independent market evidence for canonical paper consumption."""

from __future__ import annotations

from typing import Any

from dataclasses import dataclass
from decimal import Decimal
import json
import sqlite3
from typing import Mapping

from .pm03_account import Instrument, digest
from .pm_forward_ccxt_market import NativeMarket, parse_ccxt_market
from .pm_forward_journal import PaperJournal


@dataclass(frozen=True)
class PaperPortfolioSpec:
    """Only reviewed, selected-account fixed-k research scenarios may run."""

    registry_id: str
    source_ids: tuple[str, ...]
    full_aliases: tuple[str, ...]
    k_by_pod: tuple[str, ...]
    losses: tuple[str, ...]
    sizing_evidence: str
    nominal_risk: str = "600"

    def __post_init__(self) -> None:
        n = len(self.source_ids)
        if (
            not n
            or any(
                len(seq) != n
                for seq in (
                    self.full_aliases,
                    self.k_by_pod,
                    self.losses,
                )
            )
            or len(set(self.source_ids)) != n
            or len(set(self.full_aliases)) != n
        ):
            raise ValueError("INVALID_PAPER_PORTFOLIO_PROFILE")
        if sum((Decimal(value) for value in self.losses), Decimal("0")) != Decimal(
            self.nominal_risk
        ):
            raise ValueError("PAPER_PORTFOLIO_NOMINAL_RISK_MISMATCH")
        if any(Decimal(k) <= 0 for k in self.k_by_pod):
            raise ValueError("INVALID_PAPER_PORTFOLIO_K")

    @property
    def k(self) -> dict[str, str]:
        return dict(zip(self.source_ids, self.k_by_pod, strict=True))

    @property
    def risk(self) -> dict[str, str]:
        return dict(zip(self.source_ids, self.losses, strict=True))

    @property
    def registry_aliases(self) -> dict[str, str]:
        return dict(zip(self.source_ids, self.full_aliases, strict=True))


def read_quote(conn: sqlite3.Connection, inst: str) -> dict[str, Any] | None:
    row = conn.execute(
        "SELECT seq,quote_id,payload,payload_sha,prior_sha,chain_sha,event_at,known_at "
        "FROM market_quote_receipts WHERE instrument=? ORDER BY seq DESC LIMIT 1",
        (inst,),
    ).fetchone()
    if row is None:
        return None
    seq, qid, raw, sha, prior, head, source_at, known_at = row
    quote: dict[str, Any] = json.loads(raw)
    if (
        quote.get("instrument") != inst
        or digest(quote) != sha
        or head != digest([inst, seq, sha, prior])
        or quote.get("source_event_at") != source_at
        or quote.get("first_known_at") != known_at
    ):
        raise ValueError("OBSERVED_MARKET_QUOTE_INTEGRITY_FAILURE")
    PaperJournal.validate_market_quote(quote)
    predecessor = (
        conn.execute(
            "SELECT chain_sha FROM market_quote_receipts WHERE instrument=? AND seq=?",
            (inst, seq - 1),
        ).fetchone()
        if seq > 1
        else ("0" * 64,)
    )
    if predecessor is None or prior != predecessor[0]:
        raise ValueError("OBSERVED_MARKET_QUOTE_PREDECESSOR_MISMATCH")
    return quote


def candidate_market(
    inst: Instrument, catalog: Mapping[str, dict[str, Any]], quote: dict[str, Any]
) -> NativeMarket:
    """Verify current native contract metadata against ORIGINAL quote catalog SHA."""
    for raw in catalog.values():
        info = raw.get("info") or {}
        name = info.get("name")
        if inst.market == "mainnet:perp:default" and name != inst.symbol:
            continue
        if (
            inst.market != "mainnet:perp:default"
            and quote.get("schema") != "paper_vike_minute_estimated_quote_v1"
        ):
            # HIP-3 L2 sessions are not independently attested.
            raise ValueError("HIP3_SESSION_NOT_ATTESTED_FOR_PAPER")
        try:
            resolved = parse_ccxt_market(
                raw,
                first_known_at=quote["market_known_at"],
                expected=inst,
            )
        except ValueError, KeyError, TypeError:
            continue
        if quote.get("schema") == "paper_vike_minute_estimated_quote_v1":
            # Provider price observations do NOT attest executable market depth.
            # Require verified, active native metadata and identity separately.
            if not resolved.active:
                raise ValueError("VIKE_NATIVE_MARKET_INACTIVE")
        elif resolved.catalog_sha != quote.get("catalog_sha") or not resolved.session_eligible:
            raise ValueError("QUOTE_CATALOG_DRIFT_OR_SESSION_NOT_ELIGIBLE")
        return resolved
    raise ValueError("VERIFIED_NATIVE_MARKET_CATALOG_MISSING")
