"""Read-only public Hyperliquid source -> native PM03/PM04 forward PAPER experiment.

This deliberately has no broker dependency or order API. It consumes only
locally first-known receipts that arrive AFTER run creation, and records
modeled, top-of-book, risk-limited virtual fills in an isolated ShadowRun.
It is NOT the protected Guardian, real demo execution, or paper qualification.
"""

from __future__ import annotations

import argparse
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
from .pm_fixed_k_source_scope import assess_selected_parent_perp_scope
from .pm_exposure_sizing import target_from_fixed_k
from .pm_forward_ccxt_market import NativeMarket, parse_ccxt_market
from .pm_forward_journal import PaperJournal
from .pm_forward_portfolios import P1
from .pm_forward_single_shot import POLICY_VERSION

P1_K = {"S035": "0.0282", "S051": "0.0430", "S053": "0.0296"}
P1_REGISTRY_ALIASES = {"S035": "S035-ENA", "S051": "S051-BTC", "S053": "S053-HYPE"}
DEFAULT_REGISTRY = Path("/home/quant/.local/share/copytrade/registry/wallet_registry.sqlite")
SCHEMA = "observed_fixed_k_p1_single_shot_v3"
CAPACITY_BASIS = "DISPLAYED_L2_TOP_LEVEL"
MAX_SOURCE_AGE = 180
MAX_QUOTE_AGE = 30


def now_utc() -> str:
    return datetime.now(UTC).isoformat(timespec="microseconds")


def _readonly(path: Path) -> sqlite3.Connection:
    if path.is_symlink() or not path.is_file():
        raise ValueError("SOURCE_TAPE_MUST_EXIST_AND_NOT_BE_SYMLINK")
    conn = sqlite3.connect("file:" + str(path.resolve()) + "?mode=ro", uri=True, timeout=2)
    conn.execute("PRAGMA query_only=ON")
    return conn


def _sealed_p1_accounts(registry_db: Path, *, as_of: str) -> dict[str, str]:
    """Pin canonical source-account identity once; never read a public name as ownership."""
    selected: dict[str, str] = {}
    with closing(_readonly(registry_db)) as db:
        db.execute("BEGIN")
        try:
            for alias, full in P1_REGISTRY_ALIASES.items():
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
        or any(c not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-"
               for c in run_id)
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
    query = ("SELECT seq,receipt_id,payload,receipt_sha,prior_sha,chain_sha "
             "FROM source_receipts WHERE source_id=?")
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
        receipt.get("schema") != "paper_first_known_source_v1"
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
    predecessor = conn.execute(
        "SELECT chain_sha FROM source_receipts WHERE source_id=? AND seq=?",
        (alias, seq - 1),
    ).fetchone() if seq > 1 else ("0" * 64,)
    if predecessor is None or prior != predecessor[0]:
        raise ValueError("OBSERVED_SOURCE_RECEIPT_PREDECESSOR_MISMATCH")
    return {"seq": seq, "sha": sha, "receipt": receipt, "book": book}


def _read_quote(conn: sqlite3.Connection, inst: str) -> dict | None:
    row = conn.execute(
        "SELECT seq,quote_id,payload,payload_sha,prior_sha,chain_sha,event_at,known_at "
        "FROM market_quote_receipts WHERE instrument=? ORDER BY seq DESC LIMIT 1", (inst,)
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
    predecessor = conn.execute(
        "SELECT chain_sha FROM market_quote_receipts WHERE instrument=? AND seq=?",
        (inst, seq - 1),
    ).fetchone() if seq > 1 else ("0" * 64,)
    if predecessor is None or prior != predecessor[0]:
        raise ValueError("OBSERVED_MARKET_QUOTE_PREDECESSOR_MISMATCH")
    return quote


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
        if inst.market != "mainnet:perp:default":
            # HIP-3 is not independently session-attested by this observer.
            raise ValueError("HIP3_SESSION_NOT_ATTESTED_FOR_PAPER")
        try:
            resolved = parse_ccxt_market(
                raw, first_known_at=quote["market_known_at"], expected=inst,
            )
        except (ValueError, KeyError, TypeError):
            continue
        if resolved.catalog_sha != quote.get("catalog_sha") or not resolved.session_eligible:
            raise ValueError("QUOTE_CATALOG_DRIFT_OR_SESSION_NOT_ELIGIBLE")
        return resolved
    raise ValueError("VERIFIED_NATIVE_MARKET_CATALOG_MISSING")


def _policy() -> dict:
    return {
        "schema": "pm04_research_policy_v1",
        "version": POLICY_VERSION,
        "approval_reference": "docs/decisions/2026-11-03-gemini-phase3-adoption-180d.md",
        "pods": {
            alias: {
                "budget_ref": "p1_observed_paper_" + alias,
                "daily_loss": "150", "max_drawdown": "200", "stress_loss": "200",
            }
            for alias in P1.members
        },
        "fixed_k_by_pod": P1_K,
        "follower_allocations": {alias: "3000" for alias in P1.members},
        "nominal_portfolio_risk": "600",
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
        "fee_bps": "5", "full_spread_bps": "0",
        "slippage_bps": "2", "impact_bps_at_full_participation": "0",
        "max_participation": "0.1", "max_age_seconds": MAX_QUOTE_AGE,
        "latency_seconds": 0,
    }


def _market_observation(quote: dict, market: NativeMarket, *, at: str) -> dict:
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
    run: ShadowRun, kind: str, event_id: str, at: str, source_at: str,
    payload: dict, *, first_known_at: str | None = None,
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
            "evidence_class": "PUBLIC_FIRST_KNOWN_MODELED_L2_ONLY",
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
    ) -> None:
        self.source_db = Path(source_db)
        self.registry_db = Path(registry_db)
        self.catalog = dict(catalog)
        base = Path(state_root)
        if base.is_symlink() or (base.exists() and base.stat().st_mode & 0o077):
            raise ValueError("PAPER_ROOT_MUST_BE_PRIVATE")
        base.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.run_id = run_id
        saved = base / run_id / "manifest.json"
        if saved.exists():
            manifest = json.loads(saved.read_text())
            if (
                manifest.get("pm01_sha") != P1.sha
                or not isinstance(manifest.get("pm02_sha"), str)
                or manifest.get("mode") != "RESEARCH_SYNTHETIC"
            ):
                raise ValueError("PAPER_RESTART_MANIFEST_POLICY_DRIFT")
            started_at = manifest["started_at"]
            rulebook = Rulebook.from_dict(manifest["rulebook"])
            market_sha = manifest["market_manifest_sha"]
        else:
            started_at = started_at or now_utc()
            with closing(_readonly(self.source_db)) as db:
                keys = [row[0] for row in db.execute("SELECT instrument FROM market_quote_heads")]
                quotes = {key: _read_quote(db, key) for key in keys}
            markets: dict[str, NativeMarket] = {}
            for key, quote in quotes.items():
                try:
                    markets[key] = _candidate_market(Instrument.parse(key), self.catalog, quote)
                except (ValueError, KeyError):
                    continue
            if not markets:
                raise ValueError("NO_VERIFIED_DEFAULT_PERP_MARKET_CATALOG")
            permitted = tuple(sorted((Instrument.parse(key) for key in markets)))
            rulebook = Rulebook(
                program="P1_10000_VIRTUAL_PAPER",
                stage="RESEARCH_PAPER",
                source="P1_20261103_RISK_REFERENCE_NOT_PROP_CONTRACT",
                observed_at=started_at, version=SCHEMA, timezone="UTC",
                initial_balance=Decimal("10000"),
                profit_target=None, daily_loss=Decimal("500"),
                static_loss=Decimal("1000"), trailing_loss=None,
                confirmed=True, account_terms_confirmed=False,
                permitted=permitted, max_gross_leverage=Decimal("2"),
            )
            market_sha = digest({
                key: {"catalog_sha": row.catalog_sha, "amount_step": str(row.amount_step),
                      "minimum_notional": str(row.minimum_notional)}
                for key, row in sorted(markets.items())
            })
        self.started_at = started_at
        self.selected_accounts = _sealed_p1_accounts(self.registry_db, as_of=started_at)
        self.policy = {**_policy(), "selected_account_hashes": self.selected_accounts}
        self.policy_sha = digest(self.policy)
        if saved.exists() and manifest.get("pm02_sha") != self.policy_sha:
            raise ValueError("PAPER_RESTART_CANONICAL_ACCOUNT_POLICY_DRIFT")
        self.run = ShadowRun(
            base, run_id=run_id, rulebook=rulebook, started_at=started_at,
            mode="RESEARCH_SYNTHETIC", pm01_sha=P1.sha, pm02_sha=self.policy_sha,
            market_manifest_sha=market_sha,
        )
        if not self.run.account.pm04_state:
            self.run.record(_event(
                self.run, "PM04_CONFIG", "configure", started_at, started_at,
                {"policy": self.policy},
            ))
        state = self.run.account.pm04_state.get("paper_execution", {})
        self.last_seen = {
            alias: state.get("last_source_seq", {}).get(alias, 0)
            for alias in P1.members
        }
        self.prestart_seen = {alias: False for alias in P1.members}
        # This read-only cursor is derived from the immutable run start and
        # the source's first-known sequence. Never replay old signals into
        # a fresh campaign or rescan its historical 1000+ receipts every 2s.
        with closing(_readonly(self.source_db)) as db:
            for alias in P1.members:
                row = db.execute(
                    "SELECT MAX(seq) FROM source_receipts WHERE source_id=? "
                    "AND julianday(json_extract(payload, '$.first_known_at')) "
                    "<= julianday(?)", (alias, self.started_at),
                ).fetchone()
                cutoff = int(row[0]) if row[0] is not None else 0
                self.prestart_seen[alias] = cutoff > 0 and self.last_seen[alias] == 0
                self.last_seen[alias] = max(self.last_seen[alias], cutoff)

    def _observations(self, db: sqlite3.Connection, required: set[str], at: str) -> tuple[list[dict], dict[str, dict], dict[str, NativeMarket]]:
        quotes, markets, obs = {}, {}, []
        for key in sorted(required):
            quote = _read_quote(db, key)
            if quote is None:
                raise ValueError("PAPER_QUOTE_MISSING:" + key)
            market = _candidate_market(Instrument.parse(key), self.catalog, quote)
            if Instrument.parse(key) not in self.run.account.rulebook.permitted:
                raise ValueError("PAPER_MARKET_NOT_FROZEN_IN_RUN:" + key)
            obs.append(_market_observation(quote, market, at=at))
            quotes[key] = quote
            markets[key] = market
        return obs, quotes, markets

    def _known_instruments(self) -> set[str]:
        state = self.run.account
        result = {inst.key for inst, qty in state.quantities.items() if qty}
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
        scope = assess_selected_parent_perp_scope(
            book, decision_at=at, max_age_seconds=MAX_SOURCE_AGE,
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
            "policy_version": POLICY_VERSION,
        }
        self.run.record(_event(
            self.run, "PM04_PAPER_SOURCE", f"src_{alias}_{source['seq']}", at,
            book["source_event_at"], payload, first_known_at=book["first_known_at"],
        ))
        self.last_seen[alias] = source["seq"]
        return "RECORDED_PAPER_SOURCE"

    def _execute_exits(self, db: sqlite3.Connection, at: str) -> dict[str, str]:
        state = self.run.account.pm04_state.get("paper_execution", {})
        outcome: dict[str, str] = {}
        for pod, pending in sorted(state.get("exits", {}).items()):
            if pending["status"] != "PENDING_EXIT":
                continue
            if clock(at) > clock(pending["deadline_at"]):
                self.run.record(_event(
                    self.run, "PM04_PAPER_EXIT_UNRESOLVED", "exit_unresolved_" + pending["exit_id"],
                    at, pending["source_event_at"],
                    {"pod": pod, "reason": "NO_EXECUTABLE_QUOTE_WITHIN_EXIT_GRACE"},
                    first_known_at=pending["first_known_at"],
                ))
                outcome[pod] = "UNRESOLVED_EXPOSURE"
                continue
            if self.run.account.breached:
                self.run.record(_event(
                    self.run, "PM04_PAPER_EXIT_UNRESOLVED",
                    "exit_unresolved_" + pending["exit_id"],
                    at, pending["source_event_at"],
                    {"pod": pod, "reason": "CONTRACTUAL_BREACH_NO_SIMULATED_EXIT"},
                    first_known_at=pending["first_known_at"],
                ))
                outcome[pod] = "UNRESOLVED_EXPOSURE"
                continue
            required = set(pending["positions"]) | self._known_instruments()
            try:
                _, quotes, markets = self._observations(db, required, at)
                amounts = {key: row["mid_quote"] for key, row in quotes.items()}
                sized = target_from_fixed_k(
                    source_quantities=pending["positions"],
                    k=Decimal(P1_K[pod]),
                    source_marks=amounts,
                    follower_marks=amounts,
                    follower_equity_usd=self.run.account.equity,
                    max_gross_notional_usd=Decimal(self.policy["max_gross_notional"]),
                    max_market_notional_usd=Decimal("5000"),
                    pod_loss_budget_usd=Decimal("200"),
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
                "pod": pod, "exit_id": pending["exit_id"],
                "source_seq": pending["source_seq"], "targets": target,
                "quotes": quotes,
                "quote_shas": {key: digest(quote) for key, quote in quotes.items()},
                "markets": {key: {"amount_step": str(m.amount_step),
                                  "minimum_notional": str(m.minimum_notional)}
                            for key, m in markets.items()},
                "policy_version": POLICY_VERSION, "source_nav_required": False,
            }
            self.run.record(_event(
                self.run, "PM04_PAPER_EXIT", "exit_" + pending["exit_id"],
                at, pending["source_event_at"], payload,
                first_known_at=pending["first_known_at"],
            ))
            outcome[pod] = self.run.account.pm04_state["paper_execution"]["exits"][pod]["status"]
        return outcome

    def _execute_pending(self, db: sqlite3.Connection, at: str) -> dict[str, str]:
        state = self.run.account.pm04_state.get("paper_execution", {})
        outcome: dict[str, str] = {}
        for pod, intent_id in sorted(state.get("active", {}).items()):
            intent = state["history"][intent_id]
            if intent["status"] != "PENDING_5M" or clock(at) < clock(intent["due_at"]):
                continue
            if clock(at) > clock(intent["deadline_at"]):
                self.run.record(_event(
                    self.run, "PM04_PAPER_EXPIRE", "expire_" + intent_id,
                    at, intent["first_known_at"],
                    {"intent_id": intent_id, "reason": "MARKET_OR_TARGET_UNAVAILABLE_WITHIN_GRACE"},
                    first_known_at=intent["first_known_at"],
                ))
                outcome[pod] = "EXPIRED_NO_TRADE"
                continue
            required = set(intent["positions"]) | self._known_instruments()
            try:
                _, quotes, markets = self._observations(db, required, at)
                amounts = {key: quote["mid_quote"] for key, quote in quotes.items()}
                sized = target_from_fixed_k(
                    source_quantities=intent["positions"],
                    k=Decimal(P1_K[pod]),
                    source_marks=amounts,
                    follower_marks=amounts,
                    follower_equity_usd=self.run.account.equity,
                    max_gross_notional_usd=Decimal(self.policy["max_gross_notional"]),
                    max_market_notional_usd=Decimal("5000"),
                    pod_loss_budget_usd=Decimal("200"),
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
                "source_seq": intent["source_seq"],
                "source_sha": intent["source_sha"],
                "targets": quantized,
                "quotes": quotes,
                "quote_shas": {key: digest(quote) for key, quote in quotes.items()},
                "markets": {
                    key: {"amount_step": str(m.amount_step),
                          "minimum_notional": str(m.minimum_notional)}
                    for key, m in markets.items()
                },
                "policy_version": POLICY_VERSION,
                "sizing_policy": "FIXED_K_NATIVE_QUANTITY",
                "source_nav_required": False,
            }
            self.run.record(_event(
                self.run, "PM04_PAPER_EXECUTE", "attempt_" + intent_id,
                at, intent["first_known_at"], payload,
                first_known_at=intent["first_known_at"],
            ))
            outcome[pod] = self.run.account.pm04_state["paper_execution"]["history"][intent_id]["status"]
        return outcome

    def step(self, at: str | None = None) -> dict:
        at = at or now_utc()
        clock(at)
        prior_positions = {
            key.key: qty for key, qty in self.run.account.quantities.items() if qty
        }
        results: dict[str, str] = {}
        with closing(_readonly(self.source_db)) as db:
            db.execute("BEGIN")
            try:
                for alias in P1.members:
                    rows = db.execute(
                        "SELECT seq FROM source_receipts WHERE source_id=? AND seq>? "
                        "ORDER BY seq ASC", (alias, self.last_seen[alias]),
                    ).fetchall()
                    if not rows:
                        results[alias] = (
                            "PRE_START_UNMODELED" if self.prestart_seen[alias]
                            else "ALREADY_SEEN" if self.last_seen[alias] else "SOURCE_MISSING"
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
                        self.run.record(_event(
                            self.run, "MARK", "mark_" + digest([at, inp]), at, at, inp,
                        ))
                        tick_status = "PAPER_MARK_COMMITTED"
                        # Market-driven pod HALTs require prompt exits even
                        # without a new leader/source position receipt.
                        risk_state = self.run.account.pm04_state
                        for pod, stats in sorted(risk_state["pod_stats"].items()):
                            held = self.run.account.pm_quantities.get(pod, {})
                            pending = risk_state.get("paper_execution", {}).get(
                                "exits", {}
                            ).get(pod)
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
                            self.run.record(_event(
                                self.run, "PM04_PAPER_RISK_TRIGGER",
                                "risk_" + trigger_id, at, at,
                                {"pod": pod, "quote_sha": digest(quotes)},
                            ))
                        exit_results.update(self._execute_exits(db, at))
                    except ValueError as exc:
                        tick_status = "BLOCKED_PAPER_MARK:" + str(exc)
            finally:
                db.execute("ROLLBACK")
        acct = self.run.account
        current_positions = {key.key: qty for key, qty in acct.quantities.items() if qty}
        position_deltas = {
            key: str(current_positions.get(key, Decimal("0")) - prior_positions.get(key, Decimal("0")))
            for key in sorted(set(current_positions) | set(prior_positions))
            if current_positions.get(key, Decimal("0")) != prior_positions.get(key, Decimal("0"))
        }
        pod_pnl = acct.pm_equity_pnl()
        return {
            "schema": SCHEMA,
            "run_id": self.run_id,
            "as_of": at,
            "source_results": results,
            "execution_results": execution_results,
            "exit_results": exit_results,
            "pending_exits": acct.pm04_state.get("paper_execution", {}).get("exits", {}),
            "unresolved_exposures": acct.pm04_state.get(
                "paper_execution", {}
            ).get("unresolved_exposures", {}),
            "execution_policy_version": POLICY_VERSION,
            "execution_intents": {
                pod: dict(acct.pm04_state["paper_execution"]["history"][intent_id])
                for pod, intent_id in sorted(
                    acct.pm04_state.get("paper_execution", {}).get("active", {}).items()
                )
            },
            "execution_outcomes": acct.pm04_state.get(
                "paper_execution", {}
            ).get("outcomes", {}),
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
    parser.add_argument("--markets-json", type=Path, help="Optional CCXT raw load_markets JSON; otherwise public REST metadata once")
    parser.add_argument("--watch", action="store_true")
    parser.add_argument("--poll-seconds", type=float, default=2.0)
    args = parser.parse_args()
    if not 0.1 <= args.poll_seconds <= 300:
        raise ValueError("PAPER_POLL_INTERVAL_INVALID")
    catalog = json.loads(args.markets_json.read_text()) if args.markets_json else load_ccxt_catalog()
    with _exclusive_runner(args.state_root, args.run_id):
        consumer = ObservedP1Paper(
            source_db=args.source_db,
            registry_db=args.registry_db,
            state_root=args.state_root,
            run_id=args.run_id,
            catalog=catalog,
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
