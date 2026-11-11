"""Read-only public Hyperliquid source -> native PM03/PM04 forward PAPER experiment.

This deliberately has no broker dependency or order API. It consumes only
locally first-known receipts that arrive AFTER run creation, and records
modeled, top-of-book, risk-limited virtual fills in an isolated ShadowRun.
It is NOT the protected Guardian, real demo execution, or paper qualification.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from contextlib import closing, contextmanager
from datetime import UTC, datetime
from decimal import Decimal, ROUND_DOWN
import fcntl
from hashlib import sha256
import json
import os
from pathlib import Path
import sqlite3
import time
from typing import Iterator, Mapping

from .pm03_account import Instrument, Rulebook, clock, digest, number
from .pm03_memory import Event
from .pm03_run import ShadowRun
from .pm_fixed_k_source_scope import (
    assess_selected_parent_perp_scope,
    verified_source_native_marks,
)
from .pm_exposure_sizing import target_from_fixed_k
from .pm_forward_ccxt_market import NativeMarket, parse_ccxt_market
from .pm_forward_journal import PaperJournal
from .pm_forward_portfolios import FrozenPaperPortfolio, P1
from .pm_forward_single_shot import POLICY_VERSION, ESTIMATED_POLICY_VERSION
from .pm_vike_minute import SCHEMA as VIKE_MINUTE_SCHEMA
from .pm_vike_market_catalog import (
    NativePaperContract,
    load_propr_catalog,
    official_paper_contracts,
)
from .pm_forward_stream_journal import verify_official_position_transition

P1_K = {"S035": "0.0282", "S051": "0.0430", "S053": "0.0296"}
P1_REGISTRY_ALIASES = {"S035": "S035-ENA", "S051": "S051-BTC", "S053": "S053-HYPE"}
DEFAULT_REGISTRY = Path("/home/quant/.local/share/copytrade/registry/wallet_registry.sqlite")
SCHEMA = "observed_fixed_k_p1_single_shot_v3"
VIKE_PAPER_SCHEMA = "observed_fixed_k_vike_minute_estimated_v4"
SOURCE_NATIVE_MARK_SCHEMA = "observed_fixed_k_native_mark_v1"
SOURCE_NATIVE_MARK_POLICY = "future_fixed_k_independent_native_mark_v1"
CAPACITY_BASIS = "DISPLAYED_L2_TOP_LEVEL"
MAX_SOURCE_AGE = 180
MAX_QUOTE_AGE = 30


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
    def reference_sha(self) -> str:
        return FrozenPaperPortfolio(self.registry_id, self.source_ids).sha

    @property
    def k(self) -> dict[str, str]:
        return dict(zip(self.source_ids, self.k_by_pod, strict=True))

    @property
    def risk(self) -> dict[str, str]:
        return dict(zip(self.source_ids, self.losses, strict=True))

    @property
    def registry_aliases(self) -> dict[str, str]:
        return dict(zip(self.source_ids, self.full_aliases, strict=True))


# Only separately frozen virtual-paper studies with an explicit bounded
# execution scenario are included. Never infer authority from any registry
# portfolio name or auto-admit NON_EXECUTABLE_SIGNED_RESEARCH references.
PAPER_PROFILES = {
    "P1": PaperPortfolioSpec(
        "P1",
        P1.members,
        ("S035-ENA", "S051-BTC", "S053-HYPE"),
        ("0.0282", "0.0430", "0.0296"),
        ("200", "200", "200"),
        "EXISTING_P1_V3_PAPER_REFERENCE",
    ),
    "P14": PaperPortfolioSpec(
        "P14",
        ("S035", "S051", "S053", "S064", "Whale_0x5f94"),
        ("S035-ENA", "S051-BTC", "S053-HYPE", "S064-xyz:BRENTOIL", "Whale_0x5f94"),
        ("0.0169", "0.0258", "0.0178", "0.0191", "0.00011"),
        ("120", "120", "120", "120", "120"),
        "GEMINI_PHASE3_REFERENCE_PAPER_SCENARIO",
    ),
    "P16": PaperPortfolioSpec(
        "P16",
        ("S035", "S051", "S053", "Whale_0x5f94"),
        ("S035-ENA", "S051-BTC", "S053-HYPE", "Whale_0x5f94"),
        # Explicit research-only derivation from P1/P14 fixed-k references:
        # 30/30/25/15 percent of the equal $600 nominal risk.
        ("0.02538", "0.0387", "0.0222", "0.0000825"),
        ("180", "180", "150", "90"),
        "DERIVED_PHASE3_P16_CONTROL_SCENARIO_NOT_APPROVED_EXECUTION_K",
    ),
}


def _verify_portfolio_selection(
    registry_db: Path,
    profile: PaperPortfolioSpec,
    *,
    as_of: str,
) -> dict[str, str | int]:
    """Verify immutable portfolio definition from SQLite, not only alias names."""
    from .wallet_registry_portfolios import select_asof

    with closing(_readonly(registry_db)) as db:
        db.execute("BEGIN")
        try:
            if (
                profile.registry_id == "P1"
                and not db.execute(
                    "SELECT 1 FROM sqlite_master WHERE type='table' AND name='portfolio_seals'"
                ).fetchone()
            ):
                # Legacy unit fixtures contain verified P1 wallet aliases,
                # but no registry portfolio tables. Do NOT mislabel this SHA
                # as a verified registry definition in source evidence.
                return {
                    "portfolio_id": "P1",
                    "version": 0,
                    "definition_sha256": None,
                    "validation": "LEGACY_P1_TEST_FIXTURE_ONLY",
                }
            selected = select_asof(db, profile.registry_id, as_of)
            if (
                selected.get("state") == "UNKNOWN_AT_ASOF"
                or not selected.get("alias_resolution_complete")
                or not selected.get("sizing_contract", "").startswith(
                    profile.registry_id + "_VIRTUAL_10000_USD_"
                )
                or set(selected.get("members", ())) != set(profile.full_aliases)
                or len(selected.get("members", ())) != len(profile.full_aliases)
                or not selected.get("definition_sha256")
            ):
                raise ValueError("PAPER_PORTFOLIO_SEAL_OR_SIZING_MISMATCH")
        finally:
            db.execute("ROLLBACK")
    return {
        "portfolio_id": profile.registry_id,
        "version": selected["version"],
        "definition_sha256": selected["definition_sha256"],
    }


def now_utc() -> str:
    return datetime.now(UTC).isoformat(timespec="microseconds")


def _readonly(path: Path) -> sqlite3.Connection:
    if path.is_symlink() or not path.is_file():
        raise ValueError("SOURCE_TAPE_MUST_EXIST_AND_NOT_BE_SYMLINK")
    conn = sqlite3.connect("file:" + str(path.resolve()) + "?mode=ro", uri=True, timeout=2)
    conn.execute("PRAGMA query_only=ON")
    return conn


def _prestart_source_cursor(db: sqlite3.Connection, alias: str, durable_seen: int) -> int:
    """Fence every source receipt known before this process starts, in O(log N).

    Historical receipts from a stopped consumer's downtime must not be
    replayed as fresh T+300 signals. A genuine future source receipt after
    the startup fence is eligible for ordinary causal/scope checks. This
    avoids assuming all historical JSON clocks are indexable or monotonic.
    """
    if type(durable_seen) is not int or durable_seen < 0:
        raise ValueError("PAPER_DURABLE_SOURCE_CURSOR_INVALID")
    row = db.execute(
        "SELECT seq FROM source_receipts WHERE source_id=? ORDER BY seq DESC LIMIT 1",
        (alias,),
    ).fetchone()
    cutoff = int(row[0]) if row is not None else 0
    if cutoff < durable_seen:
        raise ValueError("PAPER_ORIGINAL_SOURCE_CURSOR_REGRESSED")
    return cutoff


def _sealed_p1_accounts(
    registry_db: Path,
    *,
    as_of: str,
    aliases: Mapping[str, str] | None = None,
) -> dict[str, str]:
    """Pin canonical source-account identity once; never use a display label as ownership."""
    selected: dict[str, str] = {}
    with closing(_readonly(registry_db)) as db:
        db.execute("BEGIN")
        try:
            for alias, full in (aliases or P1_REGISTRY_ALIASES).items():
                rows = db.execute(
                    "SELECT DISTINCT w.address FROM wallets w JOIN wallet_aliases a "
                    "ON a.wallet_id=w.wallet_id "
                    "WHERE a.alias=? AND a.known_at<=?",
                    (full, as_of),
                ).fetchall()
                if len(rows) != 1:
                    raise ValueError("SELECTED_P1_CANONICAL_ACCOUNT_NOT_UNIQUE:" + alias)
                selected[alias] = sha256(rows[0][0].lower().encode()).hexdigest()
        finally:
            db.execute("ROLLBACK")
    return selected


@contextmanager
def _exclusive_runner(root: Path, run_id: str) -> Iterator[None]:
    if (
        not run_id
        or len(run_id) > 64
        or any(
            c not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-"
            for c in run_id
        )
    ):
        raise ValueError("INVALID_PAPER_RUN_ID")
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    if root.is_symlink() or root.stat().st_mode & 0o077:
        raise ValueError("PAPER_ROOT_MUST_BE_PRIVATE")
    fd = os.open(root / (run_id + ".runner.lock"), os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        yield
    except BlockingIOError as exc:
        raise ValueError("PAPER_RUN_ALREADY_HAS_A_PROCESS") from exc
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)


def _read_source(conn: sqlite3.Connection, alias: str, seq: int | None = None) -> dict | None:
    query = (
        "SELECT seq,receipt_id,payload,receipt_sha,prior_sha,chain_sha "
        "FROM source_receipts WHERE source_id=?"
    )
    if seq is None:
        query += " ORDER BY seq DESC LIMIT 1"
        args = (alias,)
    else:
        query += " AND seq=?"
        args = (alias, seq)
    row = conn.execute(query, args).fetchone()
    if row is None:
        return None
    seq, rid, raw, sha, prior, head = row
    receipt = json.loads(raw)
    book = receipt.get("source_book")
    if (
        receipt.get("schema") not in ("paper_first_known_source_v1", "paper_first_known_source_v2")
        or receipt.get("source_id") != alias
        or receipt.get("payload_sha") != (book or {}).get("snapshot_sha")
        or not isinstance(book, dict)
        or digest({k: v for k, v in book.items() if k != "snapshot_sha"}) != book["snapshot_sha"]
        or digest(receipt) != sha
        or head != digest([alias, seq, rid, prior, sha])
        or book.get("wallet_id") != alias
    ):
        raise ValueError("OBSERVED_SOURCE_RECEIPT_INTEGRITY_FAILURE")
    if not (
        clock(receipt["source_event_at"])
        <= clock(receipt["first_known_at"])
        <= clock(receipt["captured_at"])
    ):
        raise ValueError("OBSERVED_SOURCE_RECEIPT_CLOCK_INVALID")
    predecessor = (
        conn.execute(
            "SELECT chain_sha FROM source_receipts WHERE source_id=? AND seq=?",
            (alias, seq - 1),
        ).fetchone()
        if seq > 1
        else ("0" * 64,)
    )
    if predecessor is None or prior != predecessor[0]:
        raise ValueError("OBSERVED_SOURCE_RECEIPT_PREDECESSOR_MISMATCH")
    return {
        "seq": seq,
        "receipt_id": rid,
        "sha": sha,
        "chain_sha": head,
        "receipt": receipt,
        "book": book,
    }


def _read_quote(conn: sqlite3.Connection, inst: str) -> dict | None:
    row = conn.execute(
        "SELECT seq,quote_id,payload,payload_sha,prior_sha,chain_sha,event_at,known_at "
        "FROM market_quote_receipts WHERE instrument=? ORDER BY seq DESC LIMIT 1",
        (inst,),
    ).fetchone()
    if row is None:
        return None
    seq, qid, raw, sha, prior, head, source_at, known_at = row
    quote = json.loads(raw)
    if (
        quote.get("instrument") != inst
        or digest(quote) != sha
        or head != digest([inst, seq, sha, prior])
        or quote.get("source_event_at") != source_at
        or quote.get("first_known_at") != known_at
    ):
        raise ValueError("OBSERVED_MARKET_QUOTE_INTEGRITY_FAILURE")
    PaperJournal._validate_market_quote(quote)
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


def _read_vike_minute(conn: sqlite3.Connection, inst: str) -> dict | None:
    """Read the independent minute-price chain without pretending it is L2."""
    from .pm_vike_minute import validate_observation

    row = conn.execute(
        "SELECT seq,payload,payload_sha,prior_sha,chain_sha,event_at,known_at "
        "FROM vike_minute_receipts WHERE instrument=? ORDER BY seq DESC LIMIT 1",
        (inst,),
    ).fetchone()
    if row is None:
        return None
    seq, raw, sha, prior, chain, source_at, known_at = row
    observation = json.loads(raw)
    predecessor = (
        conn.execute(
            "SELECT chain_sha FROM vike_minute_receipts WHERE instrument=? AND seq=?",
            (inst, seq - 1),
        ).fetchone()
        if seq > 1
        else ("0" * 64,)
    )
    if (
        observation.get("schema") != VIKE_MINUTE_SCHEMA
        or observation.get("first_known_at") != known_at
        or observation.get("bar_start_at") != source_at
        or digest({k: v for k, v in observation.items() if k != "observation_sha"})
        != observation.get("observation_sha")
        or digest(observation) != sha
        or predecessor is None
        or prior != predecessor[0]
        or chain != digest([inst, seq, sha, prior])
    ):
        raise ValueError("PAPER_VIKE_MINUTE_RECEIPT_INTEGRITY_FAILURE")
    validate_observation(observation)
    return {
        "schema": "paper_vike_minute_estimated_quote_v1",
        "instrument": inst,
        "first_known_at": known_at,
        "source_event_at": source_at,
        "market_known_at": known_at,
        "mid_quote": observation["price"],
        "vike_observation": observation,
    }


def load_ccxt_catalog(injected: Mapping[str, dict] | None = None) -> dict[str, dict]:
    """One-time public REST metadata only; never open additional user WS slots."""
    if injected is not None:
        return dict(injected)
    try:
        from importlib import import_module

        ccxt = import_module("ccxt")  # optional public market metadata only
    except ImportError as exc:
        raise ValueError("CCXT_MARKET_STREAM_EXTRA_REQUIRED") from exc
    exchange = ccxt.hyperliquid(
        {
            "enableRateLimit": True,
            "headers": {"User-Agent": "OpenAI File Downloader, XaiImageApiFetch/1.0"},
            "options": {"defaultType": "swap"},
        }
    )
    try:
        return exchange.load_markets()
    finally:
        exchange.close()


def _candidate_market(inst: Instrument, catalog: Mapping[str, dict], quote: dict) -> NativeMarket:
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


def _policy(
    profile: PaperPortfolioSpec | None = None,
    *,
    price_mode: str = "l2",
) -> dict:
    profile = profile or PAPER_PROFILES["P1"]
    if price_mode not in ("l2", "vike_minute"):
        raise ValueError("PAPER_PRICE_MODE_UNSUPPORTED")
    return {
        "schema": "pm04_research_policy_v1",
        "version": ESTIMATED_POLICY_VERSION if price_mode == "vike_minute" else POLICY_VERSION,
        "approval_reference": "docs/decisions/2026-11-03-gemini-phase3-adoption-180d.md",
        "pods": {
            alias: {
                "budget_ref": (
                    "p1_observed_paper_" + alias
                    if profile.registry_id == "P1"
                    else profile.registry_id.lower() + "_paper_" + alias
                ),
                "daily_loss": format(Decimal(profile.risk[alias]) * Decimal("0.75"), "f")
                .rstrip("0")
                .rstrip("."),
                "max_drawdown": profile.risk[alias],
                "stress_loss": profile.risk[alias],
            }
            for alias in profile.source_ids
        },
        "fixed_k_by_pod": profile.k,
        "follower_allocations": {
            alias: str(Decimal("9000") / len(profile.source_ids)) for alias in profile.source_ids
        },
        "nominal_portfolio_risk": profile.nominal_risk,
        "max_gross_notional": "20000",
        "max_instrument_fraction_equity": "0.5",
        "max_stress_loss": "700",
        "reserve": "10",
        "max_signal_age_seconds": 600,
        "broker_max_age_seconds": 300,
        "reconcile_tolerance": "0.001",
        "batch_seconds": 300,
        "execution_policy": "ASYMMETRIC",
        "broker_required": False,
    }


def _costs() -> dict:
    return {
        "fee_bps": "5",
        "full_spread_bps": "0",
        "slippage_bps": "2",
        "impact_bps_at_full_participation": "0",
        "max_participation": "0.1",
        "max_age_seconds": MAX_QUOTE_AGE,
        "latency_seconds": 0,
    }


def _market_observation(quote: dict, market: NativeMarket, *, at: str) -> dict:
    if quote.get("schema") == "paper_vike_minute_estimated_quote_v1":
        age = (clock(at) - clock(quote["first_known_at"])).total_seconds()
        if not 0 <= age <= MAX_QUOTE_AGE:
            raise ValueError("VIKE_MINUTE_QUOTE_STALE_OR_FUTURE")
        return {
            "instrument": quote["instrument"],
            "event_at": quote["source_event_at"],
            "first_known_at": quote["first_known_at"],
            "mark": quote["mid_quote"],
            "volume_base": quote["vike_observation"]["volume_base"],
            "quality": "ESTIMATED_TRADE_PRICE_ONLY",
            "supported": True,
            "capacity_basis": "MINUTE_VOLUME_PARTICIPATION_ESTIMATE",
            "quantity_step": str(market.amount_step),
            "minimum_notional": str(market.minimum_notional),
        }
    if quote.get("session_trust") != "LIVE_DEFAULT_PERP_TWO_SIDED_ONLY":
        raise ValueError("UNATTESTED_QUOTE_SESSION")
    age = (clock(at) - clock(quote["first_known_at"])).total_seconds()
    if not 0 <= age <= MAX_QUOTE_AGE:
        raise ValueError("QUOTE_STALE_OR_FUTURE")
    return {
        "instrument": quote["instrument"],
        "event_at": quote["source_event_at"],
        "first_known_at": quote["first_known_at"],
        "mark": quote["mid_quote"],
        "volume_base": None,
        "quality": "VERIFIED_QUOTE",
        "supported": True,
        "capacity_basis": CAPACITY_BASIS,
        "best_bid": quote["best_bid"],
        "best_ask": quote["best_ask"],
        "bid_size": quote["bid_size"],
        "ask_size": quote["ask_size"],
        "quantity_step": str(market.amount_step),
        "minimum_notional": str(market.minimum_notional),
    }


def _event(
    run: ShadowRun,
    kind: str,
    event_id: str,
    at: str,
    source_at: str,
    payload: dict,
    *,
    first_known_at: str | None = None,
) -> Event:
    return Event(
        event_id=event_id,
        kind=kind,
        source_event_at=source_at,
        first_known_at=first_known_at or at,
        decision_at=at,
        hypothetical_fill_at=at,
        source_sha=digest(payload),
        payload={
            "run_id": run.manifest["run_id"],
            "rulebook_sha": run.account.rulebook.sha,
            "input": payload,
            "order_route": "NONE",
            "evidence_class": (
                "OFFICIAL_NATIVE_SOURCE_MARK_MODELED_FOLLOWER_ONLY"
                if run.account.rulebook.version == SOURCE_NATIVE_MARK_SCHEMA
                else "PUBLIC_FIRST_KNOWN_ESTIMATED_VIKE_MINUTE_ONLY"
                if run.account.rulebook.version == VIKE_PAPER_SCHEMA
                else "PUBLIC_FIRST_KNOWN_MODELED_L2_ONLY"
            ),
        },
    )


def _risk_inputs(observations: list[dict], quotes: Mapping[str, dict]) -> dict:
    return {
        "observations": observations,
        "l2_quote_shas": {key: digest(quote) for key, quote in sorted(quotes.items())},
        "shocks": [
            {row["instrument"]: "-0.05" for row in observations},
            {row["instrument"]: "0.05" for row in observations},
        ],
        "evidence": {
            # Trust is the locally verified receipt-chain contract, NOT a
            # cryptographically signed exchange order execution attestation.
            "trusted": True,
            "account_state_known": True,
            "market_state_known": True,
            "market_coverage_valid": True,
            "pending_unknown_orders": False,
            "input_status": "RESEARCH_SYNTHETIC",
            "pm02_qualified": False,
            "hedge_break_loss": "10",
        },
        "costs": _costs(),
    }


class ObservedP1Paper:
    """A research-only consumer; private PM03 ledger owns every paper dollar."""

    def __init__(
        self,
        *,
        source_db: Path,
        state_root: Path,
        run_id: str,
        catalog: Mapping[str, dict],
        registry_db: Path = DEFAULT_REGISTRY,
        started_at: str | None = None,
        portfolio_id: str = "P1",
        price_mode: str = "l2",
        price_db: Path | None = None,
        native_contracts: Mapping[str, NativePaperContract] | None = None,
        study_profile: PaperPortfolioSpec | None = None,
        study_seal: Mapping[str, object] | None = None,
        study_accounts: Mapping[str, str] | None = None,
        source_mark_age_seconds: int | None = None,
        source_startup_policy: str = "AS_OF_RUN_START",
        paper_risk_profile: str = "LEGACY_STATIC_10PCT",
    ) -> None:
        # Existing three registry-sealed profiles remain the default. Other
        # scenarios require an explicit, independently checked private campaign.
        if study_profile is None:
            if portfolio_id not in PAPER_PROFILES:
                raise ValueError("PAPER_PORTFOLIO_HAS_NO_APPROVED_RESEARCH_SCENARIO")
            self.profile = PAPER_PROFILES[portfolio_id]
        else:
            if study_profile.registry_id != portfolio_id:
                raise ValueError("V4_CAMPAIGN_PROFILE_PORTFOLIO_MISMATCH")
            if portfolio_id in PAPER_PROFILES:
                if study_profile != PAPER_PROFILES[portfolio_id] or study_seal is not None:
                    raise ValueError("V4_CAMPAIGN_CANNOT_OVERRIDE_REGISTRY_PROFILE")
            else:
                from .pm_v4_sixteen_scenarios import MANIFEST_SHA256

                if (
                    study_seal is None
                    or study_seal.get("source_manifest_sha256") != MANIFEST_SHA256
                    or study_seal.get("portfolio_id") != portfolio_id
                    or study_seal.get("selection_kind")
                    != "UNSIGNED_PROSPECTIVE_PAPER_SCENARIO_NOT_SQLITE_SELECTION"
                    or study_accounts is None
                    or set(study_accounts) != set(study_profile.source_ids)
                    or any(
                        not isinstance(value, str)
                        or len(value) != 64
                        or any(char not in "0123456789abcdef" for char in value)
                        for value in study_accounts.values()
                    )
                ):
                    raise ValueError("V4_CAMPAIGN_EXTERNAL_STUDY_NOT_VERIFIED")
            self.profile = study_profile
        self.members = self.profile.source_ids
        self.portfolio_id = portfolio_id
        if paper_risk_profile not in ("LEGACY_STATIC_10PCT", "CHALLENGE_TRAILING_8PCT"):
            raise ValueError("PAPER_RISK_PROFILE_UNSUPPORTED")
        self.paper_risk_profile = paper_risk_profile
        risk_source = (
            f"{self.portfolio_id}_20261111_TRAILING_8PCT_RESEARCH_NOT_PROP_CONTRACT"
            if paper_risk_profile == "CHALLENGE_TRAILING_8PCT"
            else f"{self.portfolio_id}_20261103_RISK_REFERENCE_NOT_PROP_CONTRACT"
        )
        if source_startup_policy not in ("AS_OF_RUN_START", "NO_DOWNTIME_REPLAY"):
            raise ValueError("PAPER_SOURCE_STARTUP_POLICY_UNSUPPORTED")
        self.source_startup_policy = source_startup_policy
        if price_mode not in ("l2", "vike_minute"):
            raise ValueError("PAPER_PRICE_MODE_UNSUPPORTED")
        self.price_mode = price_mode
        if source_mark_age_seconds is not None and (
            type(source_mark_age_seconds) is not int or source_mark_age_seconds <= 0
        ):
            raise ValueError("SOURCE_MARK_AGE_POLICY_UNVERIFIED")
        # Future-only semantic version: historic run manifests keep their
        # midpoint pricing and exact SHA; there is no silent restatement.
        self.source_mark_age_seconds = source_mark_age_seconds
        self.schema = (
            SOURCE_NATIVE_MARK_SCHEMA
            if source_mark_age_seconds is not None
            else VIKE_PAPER_SCHEMA
            if price_mode == "vike_minute"
            else SCHEMA
        )
        self.source_db = Path(source_db)
        self.price_db = Path(price_db) if price_db is not None else self.source_db
        if price_mode == "vike_minute" and price_db is None:
            raise ValueError("VIKE_MINUTE_REQUIRES_ISOLATED_PRICE_JOURNAL")
        self.registry_db = Path(registry_db)
        self.catalog = dict(catalog)
        self.native_contracts = dict(native_contracts or {})
        if self.native_contracts and price_mode != "vike_minute":
            raise ValueError("NATIVE_PAPER_CONTRACTS_REQUIRE_VIKE_ESTIMATED_MODE")
        base = Path(state_root)
        if base.is_symlink() or (base.exists() and base.stat().st_mode & 0o077):
            raise ValueError("PAPER_ROOT_MUST_BE_PRIVATE")
        base.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.run_id = run_id
        saved = base / run_id / "manifest.json"
        if saved.exists():
            manifest = json.loads(saved.read_text())
            if (
                manifest.get("pm01_sha") != self.profile.reference_sha
                or not isinstance(manifest.get("pm02_sha"), str)
                or manifest["rulebook"].get("program") != f"{self.portfolio_id}_10000_VIRTUAL_PAPER"
                or manifest.get("mode") != "RESEARCH_SYNTHETIC"
                or manifest["rulebook"].get("version") != self.schema
                or manifest["rulebook"].get("source") != risk_source
            ):
                raise ValueError("PAPER_RESTART_MANIFEST_POLICY_DRIFT")
            started_at = manifest["started_at"]
            rulebook = Rulebook.from_dict(manifest["rulebook"])
            market_sha = manifest["market_manifest_sha"]
            if self.native_contracts:
                current_market_sha = digest(
                    {
                        key: {
                            "catalog_sha": row.catalog_sha,
                            "amount_step": str(row.amount_step),
                            "minimum_notional": str(row.minimum_notional),
                        }
                        for key, row in sorted(self.native_contracts.items())
                        if row.active
                    }
                )
                if current_market_sha != market_sha:
                    raise ValueError("PAPER_RESTART_NATIVE_CONTRACT_METADATA_DRIFT")
        else:
            started_at = started_at or now_utc()
            if self.native_contracts:
                # A quiet market is still a permitted identity. Its missing
                # quote blocks only the later market-order estimate.
                markets = {
                    key: market for key, market in self.native_contracts.items() if market.active
                }
            else:
                # Legacy v3/test compatibility, not the v4 native startup path.
                with closing(_readonly(self.price_db)) as db:
                    table = (
                        "vike_minute_heads"
                        if self.price_mode == "vike_minute"
                        else "market_quote_heads"
                    )
                    keys = [row[0] for row in db.execute(f"SELECT instrument FROM {table}")]
                    reader = _read_vike_minute if self.price_mode == "vike_minute" else _read_quote
                    quotes = {key: reader(db, key) for key in keys}
                markets = {}
                for key, quote in quotes.items():
                    try:
                        markets[key] = _candidate_market(Instrument.parse(key), self.catalog, quote)
                    except ValueError, KeyError:
                        continue
            if not markets:
                raise ValueError("NO_VERIFIED_DEFAULT_PERP_MARKET_CATALOG")
            permitted = tuple(sorted((Instrument.parse(key) for key in markets)))
            rulebook = Rulebook(
                program=f"{self.portfolio_id}_10000_VIRTUAL_PAPER",
                stage="RESEARCH_PAPER",
                source=risk_source,
                observed_at=started_at,
                version=self.schema,
                timezone="UTC",
                initial_balance=Decimal("10000"),
                profit_target=None,
                daily_loss=Decimal("500"),
                static_loss=(
                    None if paper_risk_profile == "CHALLENGE_TRAILING_8PCT" else Decimal("1000")
                ),
                trailing_loss=(
                    Decimal("800") if paper_risk_profile == "CHALLENGE_TRAILING_8PCT" else None
                ),
                confirmed=True,
                account_terms_confirmed=False,
                permitted=permitted,
                max_gross_leverage=Decimal("2"),
            )
            market_sha = digest(
                {
                    key: {
                        "catalog_sha": row.catalog_sha,
                        "amount_step": str(row.amount_step),
                        "minimum_notional": str(row.minimum_notional),
                    }
                    for key, row in sorted(markets.items())
                }
            )
        self.started_at = started_at
        if portfolio_id in PAPER_PROFILES:
            self.portfolio_seal = _verify_portfolio_selection(
                self.registry_db,
                self.profile,
                as_of=started_at,
            )
            self.selected_accounts = _sealed_p1_accounts(
                self.registry_db,
                as_of=started_at,
                aliases=self.profile.registry_aliases,
            )
            if study_accounts is not None and dict(study_accounts) != self.selected_accounts:
                raise ValueError("V4_CAMPAIGN_LEGACY_IDENTITY_DRIFT")
        else:
            assert study_seal is not None and study_accounts is not None
            self.portfolio_seal = dict(study_seal)
            self.selected_accounts = dict(study_accounts)
        self.policy = {
            **_policy(self.profile, price_mode=self.price_mode),
            "selected_account_hashes": self.selected_accounts,
        }
        if paper_risk_profile != "LEGACY_STATIC_10PCT":
            self.policy["paper_challenge_risk_profile"] = paper_risk_profile
            self.policy["trailing_cap_assumption"] = "UNCAPPED"
            self.policy["account_terms_confirmed"] = False
        if source_mark_age_seconds is not None:
            self.policy.update(
                source_price_policy=SOURCE_NATIVE_MARK_POLICY,
                source_mark_age_seconds=source_mark_age_seconds,
                source_mark_fallback="NONE",
            )
        if portfolio_id not in PAPER_PROFILES:
            self.policy.update(
                {
                    "v4_paper_study": self.portfolio_seal,
                    "approval_reference": "docs/V4-SIXTEEN-PAPER-20261109.md",
                    "scientific_qualification": "NOT_ESTABLISHED",
                    "exclusion_warnings_not_revoked": True,
                }
            )
        if self.portfolio_id != "P1":
            self.policy.update(
                {
                    "registry_portfolio": self.portfolio_seal,
                    "paper_sizing_evidence_class": self.profile.sizing_evidence,
                }
            )
        self.policy_sha = digest(self.policy)
        if saved.exists() and manifest.get("pm02_sha") != self.policy_sha:
            raise ValueError("PAPER_RESTART_CANONICAL_ACCOUNT_POLICY_DRIFT")
        self.run = ShadowRun(
            base,
            run_id=run_id,
            rulebook=rulebook,
            started_at=started_at,
            mode="RESEARCH_SYNTHETIC",
            pm01_sha=self.profile.reference_sha,
            pm02_sha=self.policy_sha,
            market_manifest_sha=market_sha,
        )
        if not self.run.account.pm04_state:
            self.run.record(
                _event(
                    self.run,
                    "PM04_CONFIG",
                    "configure",
                    started_at,
                    started_at,
                    {"policy": self.policy},
                )
            )
        state = self.run.account.pm04_state.get("paper_execution", {})
        self.last_seen = {
            alias: state.get("last_source_seq", {}).get(alias, 0) for alias in self.members
        }
        self.prestart_seen = {alias: False for alias in self.members}
        # Live service recovery must not ingest past downtime source records
        # as fresh T+300 entries: index only (source_id,seq) head, no full
        # source history JSON extraction or long-held live source read.
        # Historical replay keeps the original as-of-run-start policy. A
        # historical caller may legitimately know a source event at the run
        # start even when the constructor is invoked later in wall-clock time.
        with closing(_readonly(self.source_db)) as db:
            for alias in self.members:
                if self.source_startup_policy == "NO_DOWNTIME_REPLAY":
                    cutoff = _prestart_source_cursor(db, alias, self.last_seen[alias])
                else:
                    row = db.execute(
                        "SELECT MAX(seq) FROM source_receipts WHERE source_id=? "
                        "AND julianday(json_extract(payload, '$.first_known_at')) "
                        "<= julianday(?)",
                        (alias, self.started_at),
                    ).fetchone()
                    cutoff = int(row[0]) if row[0] is not None else 0
                self.prestart_seen[alias] = cutoff > 0 and self.last_seen[alias] == 0
                self.last_seen[alias] = max(self.last_seen[alias], cutoff)

    def _observations(
        self, db: sqlite3.Connection, required: set[str], at: str
    ) -> tuple[list[dict], dict[str, dict], dict[str, NativeMarket]]:
        quotes, markets, obs = {}, {}, []

        def collect(price_connection: sqlite3.Connection) -> None:
            for key in sorted(required):
                quote = (
                    _read_vike_minute(price_connection, key)
                    if self.price_mode == "vike_minute"
                    else _read_quote(price_connection, key)
                )
                if quote is None:
                    raise ValueError("PAPER_QUOTE_MISSING:" + key)
                market = (
                    self.native_contracts[key]
                    if self.native_contracts
                    else _candidate_market(Instrument.parse(key), self.catalog, quote)
                )
                if Instrument.parse(key) not in self.run.account.rulebook.permitted:
                    raise ValueError("PAPER_MARKET_NOT_FROZEN_IN_RUN:" + key)
                obs.append(_market_observation(quote, market, at=at))
                quotes[key] = quote
                markets[key] = market

        if self.price_mode == "vike_minute":
            with closing(_readonly(self.price_db)) as price_connection:
                price_connection.execute("BEGIN")
                try:
                    collect(price_connection)
                finally:
                    price_connection.execute("ROLLBACK")
        else:
            collect(db)
        return obs, quotes, markets

    def _known_instruments(self) -> set[str]:
        state = self.run.account
        result = {inst.key for inst, qty in state.quantities.items() if qty}
        # PM03 valuations include each pod's held positions even when
        # opposing pod legs net to zero in consolidated quantities. Missing
        # market data must defer the T+300 attempt, not crash at account.mark.
        for held_book in state.pm_quantities.values():
            result |= {inst.key for inst, qty in held_book.items() if qty}
        for pod in state.pm04_state["pod_targets"].values():
            result |= {key for key, q in pod.items() if number(q)}
        for pod in state.pm04_state["routed_targets"].values():
            result |= {key for key, q in pod.items() if number(q)}
        return result

    def _process_source(self, db: sqlite3.Connection, alias: str, source: dict, at: str) -> str:
        book = source["book"]
        if clock(source["receipt"]["first_known_at"]) <= clock(self.started_at):
            return "PRE_START_UNMODELED"
        if source["seq"] <= self.last_seen[alias]:
            return "ALREADY_SEEN"
        if book.get("account_id") != self.selected_accounts[alias]:
            return "BLOCKED_SELECTED_ACCOUNT_IDENTITY_MISMATCH"
        receipt = source["receipt"]
        if (
            receipt.get("observation_kind") != "OBSERVED_STATE_CHANGE"
            or receipt.get("position_transition_eligible") is not True
            or not isinstance(receipt.get("stream_epoch"), str)
            or not receipt["stream_epoch"]
            or receipt.get("signal_eligible") is not False
        ):
            return "BLOCKED_SOURCE_NOT_PROSPECTIVE_POSITION_TRANSITION"
        if self.native_contracts and not verify_official_position_transition(
            db,
            alias=alias,
            receipt_id=source["receipt_id"],
            receipt_sha=source["sha"],
            receipt=receipt,
        ):
            return "BLOCKED_OFFICIAL_POSITION_STREAM_PROOF"
        scope = assess_selected_parent_perp_scope(
            book,
            decision_at=at,
            max_age_seconds=MAX_SOURCE_AGE,
        )
        if scope["status"] != "SELECTED_SCOPE_OBSERVED_RESEARCH_ONLY":
            return "BLOCKED_SOURCE_SCOPE:" + ",".join(scope["reasons"])
        for key in book["positions"]:
            if Instrument.parse(key) not in self.run.account.rulebook.permitted:
                return "BLOCKED_MARKET:PAPER_MARKET_NOT_FROZEN_IN_RUN:" + key
        payload = {
            "pod": alias,
            "source_seq": source["seq"],
            "source_sha": source["sha"],
            "positions": book["positions"],
            "first_known_at": book["first_known_at"],
            "source_book_sha": book["snapshot_sha"],
            "sizing_policy": "FIXED_K_NATIVE_QUANTITY",
            "policy_version": self.policy["version"],
            "frozen_k": self.policy["fixed_k_by_pod"][alias],
            "release_sha256": self.policy_sha,
        }
        self.run.record(
            _event(
                self.run,
                "PM04_PAPER_SOURCE",
                f"src_{alias}_{source['seq']}",
                at,
                book["source_event_at"],
                payload,
                first_known_at=book["first_known_at"],
            )
        )
        self.last_seen[alias] = source["seq"]
        return "RECORDED_PAPER_SOURCE"

    def _execute_exits(self, db: sqlite3.Connection, at: str) -> dict[str, str]:
        state = self.run.account.pm04_state.get("paper_execution", {})
        outcome: dict[str, str] = {}
        for pod, pending in sorted(state.get("exits", {}).items()):
            if pending["status"] != "PENDING_EXIT":
                continue
            if clock(at) > clock(pending["deadline_at"]):
                self.run.record(
                    _event(
                        self.run,
                        "PM04_PAPER_EXIT_UNRESOLVED",
                        "exit_unresolved_" + pending["exit_id"],
                        at,
                        pending["source_event_at"],
                        {"pod": pod, "reason": "NO_EXECUTABLE_QUOTE_WITHIN_EXIT_GRACE"},
                        first_known_at=pending["first_known_at"],
                    )
                )
                outcome[pod] = "UNRESOLVED_EXPOSURE"
                continue
            if self.run.account.breached:
                self.run.record(
                    _event(
                        self.run,
                        "PM04_PAPER_EXIT_UNRESOLVED",
                        "exit_unresolved_" + pending["exit_id"],
                        at,
                        pending["source_event_at"],
                        {"pod": pod, "reason": "CONTRACTUAL_BREACH_NO_SIMULATED_EXIT"},
                        first_known_at=pending["first_known_at"],
                    )
                )
                outcome[pod] = "UNRESOLVED_EXPOSURE"
                continue
            required = set(pending["positions"]) | self._known_instruments()
            try:
                _, quotes, markets = self._observations(db, required, at)
                amounts = {key: row["mid_quote"] for key, row in quotes.items()}
                sized = target_from_fixed_k(
                    source_quantities=pending["positions"],
                    k=Decimal(self.profile.k[pod]),
                    source_marks=amounts,
                    follower_marks=amounts,
                    follower_equity_usd=self.run.account.equity,
                    max_gross_notional_usd=Decimal(self.policy["max_gross_notional"]),
                    max_market_notional_usd=Decimal("5000"),
                    pod_loss_budget_usd=Decimal(self.profile.risk[pod]),
                )
                target = {}
                for key, raw in sized["target_quantities"].items():
                    market = markets[key]
                    value = number(raw)
                    steps = (abs(value) / market.amount_step).to_integral_value(rounding=ROUND_DOWN)
                    target[key] = str(steps * market.amount_step * (1 if value >= 0 else -1))
            except (ValueError, KeyError) as exc:
                outcome[pod] = "WAIT_EXIT_MARKET:" + str(exc)
                continue
            payload = {
                "pod": pod,
                "exit_id": pending["exit_id"],
                "source_seq": pending["source_seq"],
                "targets": target,
                "quotes": quotes,
                "quote_shas": {key: digest(quote) for key, quote in quotes.items()},
                "markets": {
                    key: {
                        "amount_step": str(m.amount_step),
                        "minimum_notional": str(m.minimum_notional),
                    }
                    for key, m in markets.items()
                },
                "policy_version": self.policy["version"],
                "source_nav_required": False,
            }
            self.run.record(
                _event(
                    self.run,
                    "PM04_PAPER_EXIT",
                    "exit_" + pending["exit_id"],
                    at,
                    pending["source_event_at"],
                    payload,
                    first_known_at=pending["first_known_at"],
                )
            )
            outcome[pod] = self.run.account.pm04_state["paper_execution"]["exits"][pod]["status"]
        return outcome

    def _cancel_disconnected_entries(
        self,
        db: sqlite3.Connection,
        at: str,
    ) -> dict[str, str]:
        """Fence old-epoch pending new risk BEFORE consuming recovery events."""
        if not self.native_contracts:
            return {}
        state = self.run.account.pm04_state.get("paper_execution", {})
        canceled: dict[str, str] = {}
        for pod, intent_id in sorted(state.get("active", {}).items()):
            intent = state["history"][intent_id]
            if intent["status"] != "PENDING_5M":
                continue
            source = _read_source(db, pod, intent["source_seq"])
            if source is not None and verify_official_position_transition(
                db,
                alias=pod,
                receipt_id=source["receipt_id"],
                receipt_sha=source["sha"],
                receipt=source["receipt"],
            ):
                continue
            self.run.record(
                _event(
                    self.run,
                    "PM04_PAPER_SOURCE_GAP",
                    "gap_" + intent_id,
                    at,
                    intent["first_known_at"],
                    {"pod": pod, "intent_id": intent_id},
                    first_known_at=intent["first_known_at"],
                )
            )
            canceled[pod] = "CANCELED_SOURCE_GAP"
        return canceled

    def _execute_pending(self, db: sqlite3.Connection, at: str) -> dict[str, str]:
        from .pm_paper_contracts import PaperOpportunity

        state = self.run.account.pm04_state.get("paper_execution", {})
        outcome: dict[str, str] = {}
        for pod, intent_id in sorted(state.get("active", {}).items()):
            intent = state["history"][intent_id]
            eligibility = PaperOpportunity.model_validate(intent).eligibility(at)
            if eligibility in ("TERMINAL", "WAIT"):
                continue
            if self.native_contracts:
                # A disconnect/reconnect invalidates a queued opportunity.
                # Never use an earlier epoch's desired state after a gap.
                source = _read_source(db, pod, intent["source_seq"])
                if source is None or not verify_official_position_transition(
                    db,
                    alias=pod,
                    receipt_id=source["receipt_id"],
                    receipt_sha=source["sha"],
                    receipt=source["receipt"],
                    require_current_positions=True,
                ):
                    self.run.record(
                        _event(
                            self.run,
                            "PM04_PAPER_SOURCE_GAP",
                            "gap_" + intent_id,
                            at,
                            intent["first_known_at"],
                            {"pod": pod, "intent_id": intent_id},
                            first_known_at=intent["first_known_at"],
                        )
                    )
                    outcome[pod] = "CANCELED_SOURCE_GAP"
                    continue
            if eligibility == "EXPIRED":
                self.run.record(
                    _event(
                        self.run,
                        "PM04_PAPER_EXPIRE",
                        "expire_" + intent_id,
                        at,
                        intent["first_known_at"],
                        {
                            "intent_id": intent_id,
                            "reason": "MARKET_OR_TARGET_UNAVAILABLE_WITHIN_GRACE",
                        },
                        first_known_at=intent["first_known_at"],
                    )
                )
                outcome[pod] = "EXPIRED_NO_TRADE"
                continue
            required = set(intent["positions"]) | self._known_instruments()
            try:
                source_fence = _read_source(db, pod, intent["source_seq"])
                if source_fence is None or source_fence["sha"] != intent["source_sha"]:
                    raise ValueError("PAPER_EFFECT_SOURCE_FENCE_MISMATCH")
                latest_fence = _read_source(db, pod)
                if latest_fence is None or latest_fence["seq"] != intent["source_seq"]:
                    raise ValueError("PAPER_EFFECT_SOURCE_HEAD_ADVANCED")
                _, quotes, markets = self._observations(db, required, at)
                amounts = {key: quote["mid_quote"] for key, quote in quotes.items()}
                if self.source_mark_age_seconds is None:
                    # Legacy paper run semantics, preserved only for old
                    # policy versions; never infer this is source pricing.
                    native_marks = amounts
                    native_price_proof = None
                else:
                    latest = _read_source(db, pod)
                    if latest is None or latest["book"]["positions"] != intent["positions"]:
                        raise ValueError("PAPER_SOURCE_MARK_BOOK_CHANGED_OR_MISSING")
                    if not verify_official_position_transition(
                        db,
                        alias=pod,
                        receipt_id=latest["receipt_id"],
                        receipt_sha=latest["sha"],
                        receipt=latest["receipt"],
                        require_current_positions=True,
                    ):
                        # A self-consistent source_book SHA is not official
                        # stream provenance, even in a research-only run.
                        raise ValueError("PAPER_NATIVE_PRICE_SOURCE_PROOF_INVALID")
                    native_marks = verified_source_native_marks(
                        latest["book"],
                        instruments=set(intent["positions"]),
                        decision_at=at,
                        max_age_seconds=self.source_mark_age_seconds,
                    )
                    native_price_proof = {
                        "source_seq": latest["seq"],
                        "source_sha": latest["sha"],
                        "book_sha": latest["book"]["snapshot_sha"],
                        "marks": native_marks,
                        "mark_evidence": {
                            key: latest["book"]["source_mark_evidence"][key]
                            for key in sorted(native_marks)
                        },
                        "decision_cutoff": at,
                        "policy": SOURCE_NATIVE_MARK_POLICY,
                    }
                sized = target_from_fixed_k(
                    source_quantities=intent["positions"],
                    k=Decimal(intent.get("frozen_k", self.profile.k[pod])),
                    source_marks=native_marks,
                    follower_marks=amounts,
                    follower_equity_usd=self.run.account.equity,
                    max_gross_notional_usd=Decimal(self.policy["max_gross_notional"]),
                    max_market_notional_usd=Decimal("5000"),
                    pod_loss_budget_usd=Decimal(self.profile.risk[pod]),
                )
                quantized = {}
                for key, raw in sized["target_quantities"].items():
                    market = markets[key]
                    value = number(raw)
                    steps = (abs(value) / market.amount_step).to_integral_value(rounding=ROUND_DOWN)
                    value = steps * market.amount_step * (1 if value >= 0 else -1)
                    if value and abs(value) * number(amounts[key]) < market.minimum_notional:
                        value = Decimal("0")
                    quantized[key] = str(value)
                if not quantized:
                    raise ValueError("EMPTY_EXECUTION_SCOPE")
            except (ValueError, KeyError) as exc:
                outcome[pod] = "WAIT_MARKET_OR_TARGET:" + str(exc)
                continue
            payload = {
                "intent_id": intent_id,
                "effect_identity": digest(
                    [
                        self.run_id,
                        pod,
                        intent_id,
                        intent["source_sha"],
                        intent.get("frozen_k"),
                        intent.get("release_sha256"),
                        self.policy_sha,
                    ]
                ),
                "decision_source_chain_sha": source_fence["chain_sha"],
                "decision_source_first_known_at": intent["first_known_at"],
                "decision_cutoff": at,
                "source_seq": intent["source_seq"],
                "source_sha": intent["source_sha"],
                "targets": quantized,
                "quotes": quotes,
                "quote_shas": {key: digest(quote) for key, quote in quotes.items()},
                "markets": {
                    key: {
                        "amount_step": str(m.amount_step),
                        "minimum_notional": str(m.minimum_notional),
                    }
                    for key, m in markets.items()
                },
                "policy_version": self.policy["version"],
                "sizing_policy": "FIXED_K_NATIVE_QUANTITY",
                "source_nav_required": False,
            }
            if intent.get("frozen_k") is not None:
                payload["frozen_k"] = intent["frozen_k"]
                payload["release_sha256"] = intent["release_sha256"]
            if native_price_proof is not None:
                payload["native_source_price_proof"] = native_price_proof
                payload["source_mark_policy"] = SOURCE_NATIVE_MARK_POLICY
            if self.native_contracts:
                # Final fresh-source fence after slow PM03/04 calculations.
                # The source and paper journals remain separate SQLite DBs;
                # this cannot provide a cross-database atomic commit.
                with closing(_readonly(self.source_db)) as final_db:
                    current_source = _read_source(final_db, pod, intent["source_seq"])
                    still_valid = (
                        current_source is not None
                        and verify_official_position_transition(
                            final_db,
                            alias=pod,
                            receipt_id=current_source["receipt_id"],
                            receipt_sha=current_source["sha"],
                            receipt=current_source["receipt"],
                            require_current_positions=True,
                        )
                    )
                if not still_valid:
                    self.run.record(
                        _event(
                            self.run,
                            "PM04_PAPER_SOURCE_GAP",
                            "gap_" + intent_id,
                            at,
                            intent["first_known_at"],
                            {"pod": pod, "intent_id": intent_id},
                            first_known_at=intent["first_known_at"],
                        )
                    )
                    outcome[pod] = "CANCELED_SOURCE_GAP"
                    continue
            self.run.record(
                _event(
                    self.run,
                    "PM04_PAPER_EXECUTE",
                    "attempt_" + intent_id,
                    at,
                    intent["first_known_at"],
                    payload,
                    first_known_at=intent["first_known_at"],
                )
            )
            outcome[pod] = self.run.account.pm04_state["paper_execution"]["history"][intent_id][
                "status"
            ]
        return outcome

    def _reconcile_flat_targets(self, at: str) -> None:
        """Migrate proven flat legacy targets through a new durable local event."""
        from .pm_forward_single_shot import follower_exit_decision

        for pod, target in sorted(self.run.account.pm04_state["routed_targets"].items()):
            if not any(number(qty) for qty in target.values()):
                continue
            if not follower_exit_decision(self.run.account, pod, at).clear_obsolete_target:
                continue
            self.run.record(
                _event(
                    self.run,
                    "PM04_PAPER_RECONCILE_FLAT",
                    "flat_" + digest([self.run_id, pod, target, self.run.last_event_id]),
                    at,
                    at,
                    {"pod": pod},
                )
            )

    def step(self, at: str | None = None) -> dict:
        at = at or now_utc()
        clock(at)
        prior_positions = {key.key: qty for key, qty in self.run.account.quantities.items() if qty}
        results: dict[str, str] = {}
        with closing(_readonly(self.source_db)) as db:
            # Avoid pinning the source WAL while PM03/04 appends to its own
            # financial ledger. Every SELECT completes its own short read;
            # terminal attempts separately revalidate against a fresh view.
            try:
                source_gap_results = self._cancel_disconnected_entries(db, at)
                for alias in self.members:
                    rows = db.execute(
                        "SELECT seq FROM source_receipts WHERE source_id=? AND seq>? "
                        "ORDER BY seq ASC",
                        (alias, self.last_seen[alias]),
                    ).fetchall()
                    if not rows:
                        results[alias] = (
                            "PRE_START_UNMODELED"
                            if self.prestart_seen[alias]
                            else "ALREADY_SEEN"
                            if self.last_seen[alias]
                            else "SOURCE_MISSING"
                        )
                        continue
                    for (seq,) in rows:
                        source = _read_source(db, alias, seq)
                        if source is None:
                            raise ValueError("PAPER_SOURCE_SEQUENCE_DISAPPEARED")
                        results[alias] = self._process_source(db, alias, source, at)
                        if results[alias] == "RECORDED_PAPER_SOURCE":
                            self.prestart_seen[alias] = False
                exit_results = self._execute_exits(db, at)
                self._reconcile_flat_targets(at)
                execution_results = self._execute_pending(db, at)
                required = self._known_instruments()
                if not required:
                    tick_status = "NO_ACTIVE_TARGETS"
                else:
                    try:
                        obs, quotes, _ = self._observations(db, required, at)
                        inp = {
                            "state_known": True,
                            "prices": {row["instrument"]: row["mark"] for row in obs},
                            "l2_quote_shas": {key: digest(quote) for key, quote in quotes.items()},
                        }
                        self.run.record(
                            _event(
                                self.run,
                                "MARK",
                                "mark_" + digest([at, inp]),
                                at,
                                at,
                                inp,
                            )
                        )
                        tick_status = "PAPER_MARK_COMMITTED"
                        # Market-driven pod HALTs require prompt exits even
                        # without a new leader/source position receipt.
                        risk_state = self.run.account.pm04_state
                        for pod, stats in sorted(risk_state["pod_stats"].items()):
                            held = self.run.account.pm_quantities.get(pod, {})
                            pending = (
                                risk_state.get("paper_execution", {}).get("exits", {}).get(pod)
                            )
                            if (
                                stats["state"] not in ("SUSPENDED", "REDUCED")
                                or not any(held.values())
                                or (
                                    pending is not None
                                    and pending.get("reason") == "POD_RISK_LATCHED"
                                )
                            ):
                                continue
                            trigger_id = digest([self.run_id, pod, at, "POD_RISK_EXIT"])
                            self.run.record(
                                _event(
                                    self.run,
                                    "PM04_PAPER_RISK_TRIGGER",
                                    "risk_" + trigger_id,
                                    at,
                                    at,
                                    {"pod": pod, "quote_sha": digest(quotes)},
                                )
                            )
                        exit_results.update(self._execute_exits(db, at))
                    except ValueError as exc:
                        tick_status = "BLOCKED_PAPER_MARK:" + str(exc)
            finally:
                if db.in_transaction:
                    db.execute("ROLLBACK")
        acct = self.run.account
        current_positions = {key.key: qty for key, qty in acct.quantities.items() if qty}
        position_deltas = {
            key: str(
                current_positions.get(key, Decimal("0")) - prior_positions.get(key, Decimal("0"))
            )
            for key in sorted(set(current_positions) | set(prior_positions))
            if current_positions.get(key, Decimal("0")) != prior_positions.get(key, Decimal("0"))
        }
        pod_pnl = acct.pm_equity_pnl()
        return {
            "schema": self.schema,
            "run_id": self.run_id,
            "portfolio_id": self.portfolio_id,
            "portfolio_seal": self.portfolio_seal,
            "portfolio_members": list(self.profile.full_aliases),
            "sizing_evidence_class": self.profile.sizing_evidence,
            "as_of": at,
            "source_results": results,
            "execution_results": execution_results,
            "exit_results": exit_results,
            "source_gap_results": source_gap_results,
            "pending_exits": acct.pm04_state.get("paper_execution", {}).get("exits", {}),
            "unresolved_exposures": acct.pm04_state.get("paper_execution", {}).get(
                "unresolved_exposures", {}
            ),
            "execution_policy_version": (
                ESTIMATED_POLICY_VERSION if self.price_mode == "vike_minute" else POLICY_VERSION
            ),
            "execution_intents": {
                pod: dict(acct.pm04_state["paper_execution"]["history"][intent_id])
                for pod, intent_id in sorted(
                    acct.pm04_state.get("paper_execution", {}).get("active", {}).items()
                )
            },
            "execution_outcomes": acct.pm04_state.get("paper_execution", {}).get("outcomes", {}),
            "tick": tick_status,
            "equity": str(acct.equity),
            "cash": str(acct.cash),
            "net_pnl": str(acct.equity - acct.rulebook.initial_balance),
            "return_pct": str(
                Decimal("100") * (acct.equity / acct.rulebook.initial_balance - Decimal("1"))
            ),
            "drawdown_usd": str(acct.equity - acct.high_water),
            "realized_pnl": str(acct.realized_pnl),
            "unrealized_pnl": str(acct.unrealized_pnl),
            "costs": str(acct.costs),
            "funding": "UNAVAILABLE_NOT_POSTED",
            "quantity_count": sum(bool(q) for q in acct.quantities.values()),
            "positions": {k.key: str(q) for k, q in acct.quantities.items() if q},
            "net_position_changes_since_step": position_deltas,
            "pod_pnl": {key: str(value) for key, value in pod_pnl.items()},
            "pod_fees": {key: str(value) for key, value in acct.pm_costs.items()},
            "pod_positions": {
                pod: {key.key: str(qty) for key, qty in positions.items() if qty}
                for pod, positions in acct.pm_quantities.items()
            },
            "pod_risk": acct.pm04_state.get("pod_stats", {}),
            "risk": acct.risk.value,
            "last_event_id": self.run.last_event_id,
            "ledger_head_sha": (
                self.run.ledger.read()[-1]["sha"] if self.run.last_event_id else None
            ),
            "modeled_execution_only": True,
            "source_quote_latency_unmeasured": True,
            "real_broker_fills": 0,
            "order_route": "NONE",
            "trading_authorized": False,
        }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-db", required=True, type=Path)
    parser.add_argument("--registry-db", type=Path, default=DEFAULT_REGISTRY)
    parser.add_argument("--state-root", required=True, type=Path)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--portfolio", choices=tuple(PAPER_PROFILES), default="P1")
    parser.add_argument("--price-mode", choices=("l2", "vike_minute"), default="l2")
    parser.add_argument(
        "--price-db", type=Path, help="Isolated Vike price journal; required for vike_minute"
    )
    parser.add_argument("--markets-json", type=Path, help="Legacy v3 CCXT market metadata JSON")
    parser.add_argument(
        "--propr-catalog",
        type=Path,
        help="V4 pinned Propr native display catalog; price-independent",
    )
    parser.add_argument(
        "--paper-min-notional",
        type=str,
        default="10",
        help="Explicit v4 virtual-paper minimum-notional assumption, USD",
    )
    parser.add_argument("--watch", action="store_true")
    parser.add_argument("--poll-seconds", type=float, default=2.0)
    args = parser.parse_args()
    if not 0.1 <= args.poll_seconds <= 300:
        raise ValueError("PAPER_POLL_INTERVAL_INVALID")
    if args.price_mode == "vike_minute" and args.propr_catalog is not None:
        if args.markets_json is not None:
            raise ValueError("VIKE_NATIVE_CATALOG_MUST_NOT_REQUIRE_CCXT")
        native_catalog = load_propr_catalog(args.propr_catalog)
        contracts = official_paper_contracts(
            native_catalog.native_symbols,
            observed_at=now_utc(),
            minimum_notional_usd=Decimal(args.paper_min_notional),
        )
        if not contracts:
            raise ValueError("VIKE_NATIVE_CATALOG_NO_VERIFIED_ACTIVE_CONTRACTS")
        catalog = {}
    else:
        if args.price_mode == "vike_minute":
            raise ValueError("VIKE_V4_REQUIRES_PINNED_NATIVE_PROPR_CATALOG")
        contracts = None
        catalog = (
            json.loads(args.markets_json.read_text()) if args.markets_json else load_ccxt_catalog()
        )
    with _exclusive_runner(args.state_root, args.run_id):
        consumer = ObservedP1Paper(
            source_db=args.source_db,
            registry_db=args.registry_db,
            state_root=args.state_root,
            run_id=args.run_id,
            catalog=catalog,
            portfolio_id=args.portfolio,
            price_mode=args.price_mode,
            price_db=args.price_db,
            native_contracts=contracts,
        )
        while True:
            print(json.dumps(consumer.step(), sort_keys=True), flush=True)
            if not args.watch:
                break
            # Wake at the exact earliest due/deadline, otherwise check fresh
            # source/market receipts at <=2-second cadence. A 30-second
            # historical polling interval must never delay execution.
            execution = consumer.run.account.pm04_state.get("paper_execution", {})
            deadlines = [
                clock(stamp)
                for intent in execution.get("history", {}).values()
                if intent["status"] == "PENDING_5M"
                for stamp in (intent["due_at"], intent["deadline_at"])
                if clock(stamp) > clock(now_utc())
            ]
            deadlines += [
                clock(exit_row["deadline_at"])
                for exit_row in execution.get("exits", {}).values()
                if exit_row["status"] == "PENDING_EXIT"
                and clock(exit_row["deadline_at"]) > clock(now_utc())
            ]
            to_due = min(
                ((dt - clock(now_utc())).total_seconds() for dt in deadlines),
                default=2.0,
            )
            time.sleep(max(0.05, min(2.0, args.poll_seconds, to_due)))


if __name__ == "__main__":
    main()
