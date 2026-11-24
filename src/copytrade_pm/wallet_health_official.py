"""Read-only, rate-budgeted official HL wallet-health capture.

Capture original HTTPS provider replies and normalise the financial facts an
official reply can actually support — main-perp equity, funding payments and
non-funding ledger updates. Do not infer first-known historical positions,
whole-wallet NAV, follower PnL, or PM03 financial effects.

Slice 3 cutover (C3): wallet enumeration is the roster, not
``wallet_registry.sqlite``.

* Candidates are the union of active ``SeatLease.wallet``, unsettled
  ``draining`` wallets (Q16/Q21 keep observing residuals) and scored candidates,
  plus an optional union with wallets the ``FactStore`` already holds.
* Normalised ``equity`` / ``funding`` / ``ledger`` rows go to the
  :class:`~copytrade_pm.facts.store.FactStore` through
  :class:`~copytrade_pm.facts.ingest.FactIngestor`, with ``first_known_at_ms``
  set to the reply's own receive clock.
* The immutable raw private archive is optional, and ``--publish-dir`` is
  optional: when supplied it receives an aggregate-only summary that carries no
  address and no USD amount.

The roster is opened read-only; this module never writes roster state, never
signs anything, and never claims trading authorization.
"""

from __future__ import annotations

import argparse
from collections import Counter, deque
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
import fcntl
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import sys
import time
from typing import Any, Callable, Sequence
from urllib.error import HTTPError, URLError

from copytrade_kernel import KnownAtTs

from .facts.ingest import FactIngestor
from .facts.schemas import KNOWN_AT_BASIS_FETCH_CLOCK
from .facts.store import FactStore
from .pm_acquisition_contracts import verify_raw
from .pm_e4_prospective import INFO_ENDPOINT, guarded_info
from .pm_health_arguments import DEFAULT_WEIGHT_PER_MIN, HISTORY_DAYS, MAX_WALLETS
from .pm_health_arguments import add_arguments as add_arguments
from .pm_hyperx_account_triage import write_immutable_private
from .roster import RosterStore

SOURCE = "OFFICIAL_HYPERLIQUID_INFO"
CAPTURE_SCHEMA = "wallet_health_capture_v2"
RECEIPT_SCHEMA = "wallet_health_official_receipt_v2"
SUMMARY_SCHEMA = "wallet_health_capture_summary_v2"
SUMMARY_NAME = "capture-summary.json"
PUBLISHED_NAME = "wallet-health-capture.json"

#: Fact provenance: a captured official reply ranks below imported archives.
FACT_SOURCE_ID = "official_hyperliquid_info"
FACT_SOURCE_RANK = 10
FACT_KINDS = ("equity", "funding", "ledger")
ACCOUNT_SCOPE = "HL_MAIN_PERP_ONLY"

ADDRESS = re.compile(r"0x[0-9a-fA-F]{40}\Z")
MAX_DEEP = 64
MAX_ATTEMPTS = 2000
WEIGHTS = {
    "clearinghouseState": 2,
    "userAbstraction": 20,
    # Reserve extra units for variable-length historical response pages.
    "userNonFundingLedgerUpdates": 50,
    "userFunding": 50,
    "userFillsByTime": 50,
}
MAX_LEDGER_PAGE = 500
MAX_FILL_PAGE = 2000


def _now() -> datetime:
    return datetime.now(UTC)


def _number(raw: object) -> Decimal | None:
    if not isinstance(raw, str) or not raw:
        return None
    try:
        value = Decimal(raw)
    except InvalidOperation:
        return None
    return value if value.is_finite() else None


def _book_equity(body: object, mode: object, received_at: datetime) -> Decimal | None:
    # Per-DEX values do NOT represent total account equity under unified or
    # portfolio margin. Do not sum main/HIP-3 values or assume subaccount cash.
    if mode not in {"default", "disabled"} or not isinstance(body, dict):
        return None
    summary = body.get("marginSummary")
    if (
        not isinstance(summary, dict)
        or not isinstance(body.get("assetPositions"), list)
        or type(body.get("time")) is not int
        or not int((received_at - timedelta(minutes=15)).timestamp() * 1000)
        <= body["time"]
        <= int(received_at.timestamp() * 1000) + 1000
    ):
        return None
    equity = _number(summary.get("accountValue"))
    return equity if equity is not None and equity >= 0 else None


def _parse_ledger_delta(delta: object) -> tuple[str, dict[str, Any]] | None:
    if not isinstance(delta, dict):
        return None
    kind = delta.get("type")
    if isinstance(kind, str) and kind:
        return kind, delta
    if len(delta) == 1:
        item_kind, detail = next(iter(delta.items()))
        if isinstance(item_kind, str) and item_kind and isinstance(detail, dict):
            return item_kind, detail
    return None


def _ledger_audit(rows: object, *, since: int, until: int) -> dict:
    """Only classify identifiable external cash flows; all other deltas abstain."""
    if not isinstance(rows, list) or len(rows) > MAX_LEDGER_PAGE:
        raise ValueError("INVALID_HL_LEDGER_PAGE")
    kinds: Counter[str] = Counter()
    external = {"deposit": Decimal("0"), "withdraw": Decimal("0")}
    ambiguity: set[str] = set()
    for row in rows:
        if not isinstance(row, dict) or type(row.get("time")) is not int:
            raise ValueError("INVALID_HL_LEDGER_ROW")
        if not since <= row["time"] <= until:
            raise ValueError("FUTURE_OR_OUT_OF_WINDOW_LEDGER")
        parsed = _parse_ledger_delta(row.get("delta"))
        if parsed is None:
            ambiguity.add("UNRECOGNIZED_LEDGER_DELTA")
            continue
        kind, detail = parsed
        kinds[kind] += 1
        if kind in external:
            amount = _number(detail.get("usdc"))
            if amount is None or amount < 0:
                ambiguity.add("UNVERIFIED_" + kind.upper() + "_AMOUNT")
            else:
                external[kind] += amount
        elif kind not in {
            "internalTransfer",
            "spotTransfer",
            "subAccountTransfer",
            "accountClassTransfer",
            "send",
            "vaultDeposit",
            "vaultWithdraw",
            "vaultCreate",
            "vaultDistribution",
            "vaultLeaderCommission",
            "borrowLend",
            "cStakingTransfer",
            "rewardsClaim",
        }:
            ambiguity.add("UNRECOGNIZED_LEDGER_DELTA")
    if len(rows) == MAX_LEDGER_PAGE:
        ambiguity.add("LEDGER_PAGE_LIMIT_CENSORED")
    return {
        "event_types": dict(sorted(kinds.items())),
        "external_deposit_usd_observed": str(external["deposit"]) if not ambiguity else None,
        "external_withdraw_usd_observed": str(external["withdraw"]) if not ambiguity else None,
        "complete_for_declared_90d_window": not ambiguity,
        "reasons": sorted(ambiguity),
        "not_full_account_capital_reconciliation": True,
    }


class WeightBudget:
    def __init__(self, max_per_min: int = DEFAULT_WEIGHT_PER_MIN):
        if not 50 <= max_per_min <= 600:
            raise ValueError("UNSAFE_SHARED_IP_WEIGHT_BUDGET")
        self.limit = max_per_min
        self.charges: deque[tuple[float, int]] = deque()
        self.calls = 0
        self.total_reserved = 0

    def acquire(self, kind: str) -> None:
        weight = WEIGHTS[kind]
        while True:
            now = time.monotonic()
            while self.charges and self.charges[0][0] <= now - 60.0:
                self.charges.popleft()
            if self.calls >= MAX_ATTEMPTS:
                raise ValueError("HL_HEALTH_HTTP_ATTEMPT_LIMIT")
            if sum(v for _, v in self.charges) + weight <= self.limit:
                self.charges.append((now, weight))
                self.calls += 1
                self.total_reserved += weight
                return
            time.sleep(max(0.05, 60.0 - (now - self.charges[0][0])))


# ---------------------------------------------------------------------------
# Candidates: roster first, optional FactStore union
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class CandidateWallet:
    """One wallet to observe, with the reasons it was selected."""

    wallet: str
    reasons: tuple[str, ...]

    @property
    def data(self) -> dict[str, Any]:
        return {"wallet": self.wallet, "reasons": list(self.reasons)}


@dataclass(frozen=True, slots=True)
class RosterSelection:
    """Read-only roster view plus the identity digest it was read at."""

    candidates: tuple[CandidateWallet, ...]
    accounts: tuple[str, ...]
    active: int
    draining: int
    scored: int
    inventory_sha256: str

    @property
    def by_reason(self) -> dict[str, int]:
        return {
            "active": self.active,
            "draining": self.draining,
            "scored": self.scored,
        }


def roster_candidates(
    roster_db: Path,
    *,
    as_of_ms: int,
    include_scored: bool = True,
) -> RosterSelection:
    """Active + draining + scored roster wallets at one known-at clock.

    The roster is opened read-only; a missing file, a schema mismatch or an
    address that is not a Hyperliquid account identity all fail closed.
    """
    as_of = KnownAtTs(int(as_of_ms))
    reasons: dict[str, set[str]] = {}
    with RosterStore(roster_db) as roster:
        accounts = roster.accounts()
        counts = {"active": 0, "draining": 0, "scored": 0}
        for account_id in accounts:
            book = roster.book_at(account_id, as_of=as_of)
            for wallet in book.wallets:
                if "active" not in reasons.setdefault(wallet, set()):
                    counts["active"] += 1
                reasons[wallet].add("active")
            for wallet in book.draining_wallets:
                if "draining" not in reasons.setdefault(wallet, set()):
                    counts["draining"] += 1
                reasons[wallet].add("draining")
        if include_scored:
            for wallet in roster.latest_scorecard(as_of=as_of):
                if "scored" not in reasons.setdefault(wallet, set()):
                    counts["scored"] += 1
                reasons[wallet].add("scored")
        inventory_sha = roster.inventory_sha()
    return RosterSelection(
        candidates=tuple(
            CandidateWallet(wallet=wallet, reasons=tuple(sorted(reasons[wallet])))
            for wallet in sorted(reasons)
        ),
        accounts=tuple(accounts),
        active=counts["active"],
        draining=counts["draining"],
        scored=counts["scored"],
        inventory_sha256=inventory_sha,
    )


def merge_candidates(
    selection: Sequence[CandidateWallet],
    extra: Sequence[str] = (),
    *,
    reason: str = "facts",
) -> tuple[CandidateWallet, ...]:
    """Union roster candidates with extra wallets, keeping every reason."""
    reasons: dict[str, set[str]] = {item.wallet: set(item.reasons) for item in selection}
    for wallet in extra:
        reasons.setdefault(wallet, set()).add(reason)
    merged = []
    for wallet in sorted(reasons):
        if not ADDRESS.fullmatch(wallet):
            # Never echo the value: it may be a private identity token.
            raise ValueError("CANDIDATE_INVALID_HL_ACCOUNT_IDENTITY")
        merged.append(CandidateWallet(wallet=wallet, reasons=tuple(sorted(reasons[wallet]))))
    # A single public selected account must not consume multiple quota slots.
    if len({item.wallet for item in merged}) != len(merged):
        raise ValueError("CANDIDATE_DUPLICATE_HL_ACCOUNT_IDENTITY")
    return tuple(merged)


def facts_union(facts_root: Path, *, since: datetime, until: datetime) -> tuple[str, ...]:
    """Wallets the FactStore already tracks inside ``[since, until]``."""
    store = FactStore(facts_root)
    try:
        return store.distinct_wallets(
            ("fills", "positions", "equity"),
            start_day=since.date().isoformat(),
            end_day=until.date().isoformat(),
        )
    finally:
        store.close()


# ---------------------------------------------------------------------------
# Normalisation: provider reply -> canonical fact rows
# ---------------------------------------------------------------------------


def _event_ms(value: int) -> datetime:
    return datetime.fromtimestamp(value / 1000, UTC)


def equity_row(
    wallet: str,
    state: object,
    mode: object,
    *,
    received_at: datetime,
    first_known_at_ms: int,
) -> dict[str, Any] | None:
    """One main-perp equity observation, or ``None`` when the reply abstains."""
    equity = _book_equity(state, mode, received_at)
    if equity is None or not isinstance(state, dict):
        return None
    summary = state.get("marginSummary")
    if not isinstance(summary, dict):  # pragma: no cover - _book_equity proved it
        return None
    return {
        "wallet": wallet,
        "account_scope": ACCOUNT_SCOPE,
        "abstraction_mode": str(mode),
        "equity_usd": equity,
        "withdrawable_usd": _number(state.get("withdrawable")),
        "margin_used_usd": _number(summary.get("totalMarginUsed")),
        "observed_at": _event_ms(int(state["time"])),
        "event_ts_ms": int(state["time"]),
        "first_known_at_ms": int(first_known_at_ms),
        "known_at_basis": KNOWN_AT_BASIS_FETCH_CLOCK,
        "arrival_seq": 0,
        "source_id": FACT_SOURCE_ID,
        "source_rank": FACT_SOURCE_RANK,
        "batch_sha16": "",
    }


def funding_rows(
    wallet: str,
    payload: object,
    *,
    since: int,
    until: int,
    first_known_at_ms: int,
) -> list[dict[str, Any]]:
    """Funding payments from ``userFunding``; a malformed page fails closed."""
    if not isinstance(payload, list):
        raise ValueError("INVALID_HL_FUNDING_PAGE")
    rows: list[dict[str, Any]] = []
    for row in payload:
        if not isinstance(row, dict) or type(row.get("time")) is not int:
            raise ValueError("INVALID_HL_FUNDING_ROW")
        if not since <= row["time"] <= until:
            raise ValueError("FUTURE_OR_OUT_OF_WINDOW_FUNDING")
        delta = row.get("delta")
        if not isinstance(delta, dict) or delta.get("type") != "funding":
            continue
        coin = delta.get("coin")
        payment = _number(delta.get("usdc"))
        digest = row.get("hash")
        if not isinstance(coin, str) or not coin:
            raise ValueError("INVALID_HL_FUNDING_COIN")
        if payment is None:
            raise ValueError("INVALID_HL_FUNDING_AMOUNT")
        if not isinstance(digest, str) or not digest:
            raise ValueError("INVALID_HL_FUNDING_HASH")
        rows.append(
            {
                "wallet": wallet,
                "coin": coin,
                "payment_usd": payment,
                "funding_rate": _number(delta.get("fundingRate")),
                "size": _number(delta.get("szi")),
                "hash": digest,
                "event_ts": _event_ms(int(row["time"])),
                "event_ts_ms": int(row["time"]),
                "first_known_at_ms": int(first_known_at_ms),
                "known_at_basis": KNOWN_AT_BASIS_FETCH_CLOCK,
                "arrival_seq": 0,
                "source_id": FACT_SOURCE_ID,
                "source_rank": FACT_SOURCE_RANK,
                "batch_sha16": "",
            }
        )
    return rows


def ledger_rows(
    wallet: str,
    payload: object,
    *,
    since: int,
    until: int,
    first_known_at_ms: int,
) -> list[dict[str, Any]]:
    """Non-funding ledger updates, one row per provider delta."""
    if not isinstance(payload, list):
        raise ValueError("INVALID_HL_LEDGER_PAGE")
    if len(payload) > MAX_LEDGER_PAGE:
        raise ValueError("INVALID_HL_LEDGER_PAGE")
    rows: list[dict[str, Any]] = []
    for row in payload:
        if not isinstance(row, dict) or type(row.get("time")) is not int:
            raise ValueError("INVALID_HL_LEDGER_ROW")
        if not since <= row["time"] <= until:
            raise ValueError("FUTURE_OR_OUT_OF_WINDOW_LEDGER")
        digest = row.get("hash")
        if not isinstance(digest, str) or not digest:
            raise ValueError("INVALID_HL_LEDGER_HASH")
        parsed = _parse_ledger_delta(row.get("delta"))
        if parsed is None:
            raise ValueError("INVALID_HL_LEDGER_DELTA")
        kind, detail = parsed
        amount = next(
            (
                val
                for key in ("usdc", "usdcValue", "netWithdrawnUsd", "amount")
                if (val := _number(detail.get(key))) is not None
            ),
            None,
        )
        raw_token = detail.get("token")
        token = (
            raw_token
            if isinstance(raw_token, str) and raw_token
            else ("USDC" if amount is not None else None)
        )
        rows.append(
            {
                "wallet": wallet,
                "kind": kind,
                "amount_usd": amount,
                "token": token,
                "hash": digest,
                "event_ts": _event_ms(int(row["time"])),
                "event_ts_ms": int(row["time"]),
                "first_known_at_ms": int(first_known_at_ms),
                "known_at_basis": KNOWN_AT_BASIS_FETCH_CLOCK,
                "arrival_seq": 0,
                "source_id": FACT_SOURCE_ID,
                "source_rank": FACT_SOURCE_RANK,
                "batch_sha16": "",
            }
        )
    return rows


# ---------------------------------------------------------------------------
# Capture
# ---------------------------------------------------------------------------


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def _save_reply(
    generation: Path,
    index: int,
    wallet: str,
    kind: str,
    request: dict,
    payload: object,
    raw: bytes,
    supplied_sha: str,
    requested_at: datetime,
    received_at: datetime,
) -> dict:
    verify_raw(payload, raw, supplied_sha)
    if received_at < requested_at:
        raise ValueError("PROVIDER_CLOCK_ORDER_INVALID")
    name = f"w{index:06d}/{kind}.json"
    write_immutable_private(generation / "raw" / name, raw)
    record = {
        "schema": RECEIPT_SCHEMA,
        "source": SOURCE,
        "endpoint": INFO_ENDPOINT,
        "wallet_ref": sha256(wallet.encode()).hexdigest()[:16],
        "account_scope": ACCOUNT_SCOPE,
        "request_sha256": sha256(_canonical(request)).hexdigest(),
        "raw_sha256": supplied_sha,
        "requested_at": requested_at.isoformat(),
        "received_at": received_at.isoformat(),
        "historical_first_known": False,
        "source_continuity_verified": False,
        "trading_authorized": False,
    }
    write_immutable_private(generation / "receipts" / name, _canonical(record))
    # Verify the bytes independently after writing, not just a self-asserted SHA.
    if sha256((generation / "raw" / name).read_bytes()).hexdigest() != record["raw_sha256"]:
        raise ValueError("DURABLE_HL_SOURCE_RECEIPT_MISMATCH")
    return record


def capture_health(
    *,
    roster_db: Path,
    store: FactStore | None = None,
    generation: Path | None = None,
    facts_root: Path | None = None,
    publish_dir: Path | None = None,
    max_wallets: int = MAX_WALLETS,
    deep_wallets: int = 0,
    weight_per_min: int = DEFAULT_WEIGHT_PER_MIN,
    history_days: int = HISTORY_DAYS,
    include_scored: bool = True,
    raw_archive: bool = True,
    dry_run: bool = False,
    budget: WeightBudget | None = None,
    info: Callable = guarded_info,
    clock: Callable[[], datetime] = _now,
) -> dict:
    """Capture official replies, ingest normalised facts, return a summary.

    ``store`` is the only fact sink; ``generation`` is the optional immutable raw
    archive and ``publish_dir`` the optional aggregate-only publication. At least
    one sink must be supplied, and the raw archive requires ``generation``.
    """
    if not 1 <= max_wallets <= MAX_WALLETS or not 0 <= deep_wallets <= MAX_DEEP:
        raise ValueError("INVALID_HEALTH_CAPTURE_BOUNDS")
    if not 1 <= history_days <= 3650:
        raise ValueError("INVALID_HEALTH_HISTORY_WINDOW")
    if store is None and not raw_archive:
        raise ValueError("NO_CAPTURE_SINK")

    started = clock()
    if started.utcoffset() != timedelta(0):
        raise ValueError("UTC_CAPTURE_CLOCK_REQUIRED")
    start_ms = int(started.timestamp() * 1000)

    selection = roster_candidates(roster_db, as_of_ms=start_ms, include_scored=include_scored)
    since = start_ms - history_days * 86_400 * 1000
    extra: tuple[str, ...] = ()
    if facts_root is not None:
        extra = facts_union(
            facts_root,
            since=datetime.fromtimestamp(since / 1000, UTC),
            until=started,
        )
    candidates = merge_candidates(selection.candidates, extra)
    facts_only = len({wallet for wallet in extra} - {item.wallet for item in selection.candidates})

    archive_root: Path | None = None
    if raw_archive:
        if generation is None:
            raise ValueError("RAW_ARCHIVE_GENERATION_REQUIRED")
        archive_root = Path(generation)
        if not re.fullmatch(r"g[A-Za-z0-9_-]{12,80}", archive_root.name):
            raise ValueError("INVALID_HEALTH_GENERATION_NAME")
        if archive_root.exists():
            raise ValueError("IMMUTABLE_HEALTH_GENERATION_ALREADY_EXISTS")
        archive_root.mkdir(mode=0o700, parents=True)
        if archive_root.is_symlink() or archive_root.stat().st_mode & 0o077:
            raise ValueError("PRIVATE_HEALTH_GENERATION_REQUIRED")

    budget = budget if budget is not None else WeightBudget(weight_per_min)
    errors: Counter[str] = Counter()
    equity: list[dict[str, Any]] = []
    funding: list[dict[str, Any]] = []
    ledger: list[dict[str, Any]] = []
    ledger_audits: list[dict] = []
    verified_raw = 0
    equity_abstained = 0
    activity_verified = 0
    queried = 0

    def fetch(index: int, wallet: str, kind: str, extra_args: dict | None = None):
        nonlocal verified_raw
        request = {"type": kind, "user": wallet, **(extra_args or {})}
        for attempt in range(3):
            budget.acquire(kind)
            requested = clock()
            try:
                payload, raw, signed = info(request)
                received = clock()
                receipt: dict | None = None
                if archive_root is not None:
                    receipt = _save_reply(
                        archive_root,
                        index,
                        wallet,
                        kind,
                        request,
                        payload,
                        raw,
                        signed,
                        requested,
                        received,
                    )
                else:
                    verify_raw(payload, raw, signed)
                    if received < requested:
                        raise ValueError("PROVIDER_CLOCK_ORDER_INVALID")
                verified_raw += 1
                return payload, receipt, received
            except (HTTPError, URLError, TimeoutError, OSError) as exc:
                if attempt == 2 or (
                    isinstance(exc, HTTPError) and exc.code not in {429, 500, 502, 503, 504}
                ):
                    errors[kind + "_" + type(exc).__name__] += 1
                    return None
                time.sleep(min(2**attempt, 2))
            except (ValueError, TypeError, json.JSONDecodeError) as exc:
                errors[kind + "_" + type(exc).__name__] += 1
                return None
        return None

    last_ms = start_ms
    window = {"startTime": since, "endTime": last_ms}
    for index, candidate in enumerate(candidates[:max_wallets], start=1):
        queried += 1
        wallet = candidate.wallet
        state = fetch(index, wallet, "clearinghouseState")
        mode = fetch(index, wallet, "userAbstraction")
        if state is None or mode is None:
            continue
        state_body, _state_receipt, at = state
        first_known_ms = int(at.timestamp() * 1000)
        row = equity_row(
            wallet,
            state_body,
            mode[0],
            received_at=at,
            first_known_at_ms=first_known_ms,
        )
        if row is None:
            equity_abstained += 1
        else:
            equity.append(row)

        if queried > deep_wallets:
            continue
        for kind in ("userNonFundingLedgerUpdates", "userFunding", "userFillsByTime"):
            reply = fetch(index, wallet, kind, window)
            if reply is None:
                continue
            payload = reply[0]
            reply_at = reply[2]
            reply_known_ms = int(reply_at.timestamp() * 1000)
            if kind == "userNonFundingLedgerUpdates":
                if archive_root is not None:
                    try:
                        ledger_audits.append(_ledger_audit(payload, since=since, until=last_ms))
                    except ValueError, TypeError:
                        errors["LEDGER_INCOMPLETE_OR_INVALID"] += 1
                ledger.extend(
                    ledger_rows(
                        wallet,
                        payload,
                        since=since,
                        until=last_ms,
                        first_known_at_ms=reply_known_ms,
                    )
                )
            elif kind == "userFunding":
                funding.extend(
                    funding_rows(
                        wallet,
                        payload,
                        since=since,
                        until=last_ms,
                        first_known_at_ms=reply_known_ms,
                    )
                )
            else:
                activity_verified += int(
                    _fills_activity(payload, at=at, since=since, until=last_ms)
                )

    finished = clock()
    if finished.utcoffset() != timedelta(0) or finished < started:
        raise ValueError("INVALID_CAPTURE_FINISH_CLOCK")

    fact_rows = {"equity": len(equity), "funding": len(funding), "ledger": len(ledger)}
    ingested: dict[str, list[dict[str, Any]]] = {kind: [] for kind in FACT_KINDS}
    if store is not None:
        ingestor = FactIngestor(store, dry_run=dry_run)
        label = archive_root.name if archive_root is not None else f"capture-{start_ms}"
        for kind, rows in (("equity", equity), ("funding", funding), ("ledger", ledger)):
            for receipt in ingestor.ingest_rows(
                kind,
                rows,
                source_id=FACT_SOURCE_ID,
                source_rank=FACT_SOURCE_RANK,
                first_known_at_ms=None,
                input_label=label,
            ):
                ingested[kind].append(receipt.as_dict())

    summary = {
        "schema": CAPTURE_SCHEMA,
        "source": SOURCE,
        "started_at": started.isoformat(),
        "completed_at": finished.isoformat(),
        "roster_inventory_sha256": selection.inventory_sha256,
        "roster_accounts": len(selection.accounts),
        "candidates": {
            **selection.by_reason,
            "facts_only": facts_only,
            "total": len(candidates),
        },
        "requested_accounts": queried,
        "raw_receipts_verified": verified_raw,
        "verified_main_perp_equity": len(equity),
        "equity_abstained": equity_abstained,
        "fact_rows_normalized": fact_rows,
        "fact_rows_written": {
            kind: sum(item["rows_new"] for item in ingested[kind]) for kind in FACT_KINDS
        },
        "fact_batches": {
            "created": sum(item["created"] for kind in FACT_KINDS for item in ingested[kind]),
            "unchanged": sum(not item["created"] for kind in FACT_KINDS for item in ingested[kind]),
        },
        "recent_activity_windows_complete": activity_verified,
        "financial_attribution_verified": 0,
        "follower_net_outcomes_verified": 0,
        "false_positive_rate_verified": False,
        "portfolio_contribution_verified": False,
        "trial_oos_qualification": "NOT_QUALIFIED",
        "source_continuity": "SINGLE_SNAPSHOT_ONLY",
        "provider_calls_reserved": budget.calls,
        "provider_weight_reserved": budget.total_reserved,
        "provider_weight_per_minute": budget.limit,
        "provider_errors": dict(sorted(errors.items())),
        "read_only_source_and_roster": True,
        "trading_authorized": False,
    }
    if ledger_audits:
        summary["ledger_summary"] = _ledger_summary(ledger_audits)
    if archive_root is not None:
        write_immutable_private(archive_root / SUMMARY_NAME, _canonical(summary))
    if publish_dir is not None:
        publish_summary(publish_dir, summary)
    return summary


def _fills_activity(payload: object, *, at: datetime, since: int, until: int) -> bool:
    """Recent-activity verdict from a ``userFillsByTime`` page, or abstain."""
    if (
        isinstance(payload, list)
        and len(payload) <= MAX_FILL_PAGE
        and all(
            isinstance(row, dict) and type(row.get("time")) is int and since <= row["time"] <= until
            for row in payload
        )
        and (len(payload) < MAX_FILL_PAGE or bool(payload))
    ):
        last_trade = _event_ms(max(row["time"] for row in payload)) if payload else None
        # A saturated 2,000-fill page proves recent activity but not inactivity
        # when its newest event is old.
        return len(payload) < MAX_FILL_PAGE or (
            last_trade is not None and last_trade >= at - timedelta(days=30)
        )
    return False


def _ledger_summary(audits: Sequence[dict]) -> dict[str, Any]:
    """Aggregate ledger diagnostics: counts only, never an amount or identity."""
    reasons: Counter[str] = Counter()
    types: Counter[str] = Counter()
    complete = 0
    for audit in audits:
        for reason in audit.get("reasons", ()):  # type: ignore[union-attr]
            reasons[reason] += 1
        for name in audit.get("event_types", {}):  # type: ignore[union-attr]
            types[name] += 1
        complete += int(bool(audit.get("complete_for_declared_90d_window")))
    return {
        "wallets_audited": len(audits),
        "complete_90d_windows": complete,
        "event_types": dict(sorted(types.items())),
        "abstention_reasons": dict(sorted(reasons.items())),
        "not_full_account_capital_reconciliation": True,
    }


def publish_summary(publish_dir: Path, summary: dict[str, Any]) -> Path:
    """Publish the aggregate-only capture summary; never an address or amount."""
    from .pm_private_io import publish_atomic_public

    raw = _canonical(dict(summary))
    if ADDRESS.search(raw.decode()):
        raise ValueError("CAPTURE_SUMMARY_WOULD_LEAK_WALLET_ADDRESS")
    if len(raw) > 131072:
        raise ValueError("CAPTURE_SUMMARY_TOO_LARGE")
    publish_atomic_public(publish_dir, raw, name=PUBLISHED_NAME)
    path = Path(publish_dir) / PUBLISHED_NAME
    if sha256(path.read_bytes()).digest() != sha256(raw).digest():
        raise ValueError("CAPTURE_SUMMARY_SHA_DRIFT")
    return path


# ---------------------------------------------------------------------------
# Command surface (C4 registers ``copytrade-pm facts capture-health``)
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="copytrade-pm facts capture-health",
        description="Official HL read-only wallet-health capture into the FactStore.",
    )
    return add_arguments(parser)


@contextmanager
def _capture_lock(directory: Path):
    """Only one official capture against the source IP and roster at a time."""
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    if directory.stat().st_mode & 0o077:
        raise ValueError("PRIVATE_CAPTURE_ROOT_REQUIRED")
    path = directory / "wallet-health-capture.lock"
    fd = os.open(path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise ValueError("HEALTH_CAPTURE_ALREADY_RUNNING") from exc
        yield
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)


def run(args: argparse.Namespace) -> int:
    """Handler entry point shared by the standalone parser and the CLI group."""
    raw_archive = not bool(getattr(args, "no_raw_archive", False))
    if raw_archive and getattr(args, "generation", None) is None:
        raise ValueError("RAW_ARCHIVE_GENERATION_REQUIRED")
    store_root = Path(args.store).expanduser()
    lock_dir = Path(args.generation).expanduser().parent if raw_archive else store_root
    store = FactStore(store_root, create=not bool(getattr(args, "dry_run", False)))
    try:
        with _capture_lock(lock_dir):
            result = capture_health(
                roster_db=Path(args.roster_db).expanduser(),
                store=store,
                generation=Path(args.generation).expanduser() if raw_archive else None,
                facts_root=Path(args.facts_root).expanduser()
                if getattr(args, "facts_root", None)
                else None,
                publish_dir=Path(args.publish_dir).expanduser()
                if getattr(args, "publish_dir", None)
                else None,
                max_wallets=int(args.max_wallets),
                deep_wallets=int(args.deep_wallets),
                weight_per_min=int(args.weight_per_minute),
                history_days=int(args.history_days),
                include_scored=not bool(getattr(args, "no_scored_candidates", False)),
                raw_archive=raw_archive,
                dry_run=bool(getattr(args, "dry_run", False)),
            )
    finally:
        store.close()
    # Never print raw addresses or USD amounts from private source receipts.
    print(json.dumps(result, sort_keys=True))
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return run(args)
    except (RuntimeError, ValueError, FileNotFoundError) as exc:
        print(f"capture-health failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
