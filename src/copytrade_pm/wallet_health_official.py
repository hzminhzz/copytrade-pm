"""Read-only, rate-budgeted official HL wallet-health capture (Track B).

Capture original HTTPS provider replies; do not infer first-known historical
positions, whole-wallet NAV, follower PnL, or PM03 financial effects.
"""

from __future__ import annotations

import argparse
from collections import Counter, deque
from contextlib import closing
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
import fcntl
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import time
from typing import Callable
from urllib.error import HTTPError, URLError

from . import wallet_registry as registry
from .pm_acquisition_contracts import verify_raw
from .pm_e4_prospective import _guarded_info
from .pm_hyperx_account_triage import _write_immutable_private
from .wallet_health import FinancialEvidence, assess, canonical, save_immutable

SOURCE = "OFFICIAL_HYPERLIQUID_INFO"
INFO_ENDPOINT = "https://api.hyperliquid.xyz/info"
ADDRESS = re.compile(r"0x[0-9a-fA-F]{40}\Z")
MAX_WALLETS = 512
MAX_DEEP = 64
MAX_ATTEMPTS = 2000
# Substantially below the venue's 1,200-weight/minute shared-IP ceiling.
DEFAULT_WEIGHT_PER_MIN = 240
WEIGHTS = {
    "clearinghouseState": 2,
    "userAbstraction": 20,
    # Reserve extra units for variable-length historical response pages.
    "userNonFundingLedgerUpdates": 50,
    "userFunding": 50,
    "userFillsByTime": 50,
}
HISTORY_DAYS = 90


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


def _ledger_audit(rows: object, *, since: int, until: int) -> dict:
    """Only classify identifiable external cash flows; all other deltas abstain."""
    if not isinstance(rows, list) or len(rows) > 500:
        raise ValueError("INVALID_HL_LEDGER_PAGE")
    kinds: Counter[str] = Counter()
    external = {"deposit": Decimal("0"), "withdraw": Decimal("0")}
    ambiguity: set[str] = set()
    for row in rows:
        if not isinstance(row, dict) or type(row.get("time")) is not int:
            raise ValueError("INVALID_HL_LEDGER_ROW")
        if not since <= row["time"] <= until:
            raise ValueError("FUTURE_OR_OUT_OF_WINDOW_LEDGER")
        delta = row.get("delta")
        if not isinstance(delta, dict) or len(delta) != 1:
            ambiguity.add("UNRECOGNIZED_LEDGER_DELTA")
            continue
        kind, detail = next(iter(delta.items()))
        if not isinstance(kind, str):
            raise ValueError("INVALID_HL_LEDGER_TYPE")
        kinds[kind] += 1
        if kind in external:
            if not isinstance(detail, dict):
                ambiguity.add("UNPARSEABLE_" + kind.upper())
                continue
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
            "rewardsClaim",
        }:
            ambiguity.add("UNRECOGNIZED_LEDGER_DELTA")
    if len(rows) == 500:
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


def _roster(db: Path, as_of: datetime) -> tuple[list[tuple[int, str]], int, str]:
    # Identity and addresses must be from the same SQLite MVCC snapshot.
    cutoff = as_of.isoformat()
    with closing(registry.connect(db, False)) as con:
        con.execute("BEGIN")
        matches = con.execute(
            """SELECT DISTINCT w.wallet_id,w.venue,w.network,w.address
               FROM wallets w JOIN cohort_memberships m ON m.wallet_id=w.wallet_id
               WHERE m.known_at<=?
                 AND NOT EXISTS (
                   SELECT 1 FROM exclusions x
                   WHERE x.wallet_id=w.wallet_id AND x.known_at<=?)
               ORDER BY w.wallet_id""",
            (cutoff, cutoff),
        ).fetchall()
    ids = [int(row[0]) for row in matches]
    inventory_sha = sha256(json.dumps([cutoff, ids], separators=(",", ":")).encode()).hexdigest()
    admitted = []
    for wid, venue, network, address in matches:
        if str(venue).upper() not in {"HL", "HYPERLIQUID"}:
            continue
        if str(network).lower() not in {"mainnet", "hyperliquid", "hl"}:
            continue
        if isinstance(address, str) and ADDRESS.fullmatch(address):
            admitted.append((wid, address.lower()))
    # A single public selected account must not consume multiple quota slots.
    if len({address for _, address in admitted}) != len(admitted):
        raise ValueError("REGISTRY_DUPLICATE_HL_ACCOUNT_IDENTITY")
    return admitted, len(ids), inventory_sha


def _save_reply(
    generation: Path,
    wallet_id: int,
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
    name = f"w{wallet_id:06d}/{kind}.json"
    _write_immutable_private(generation / "raw" / name, raw)
    record = {
        "schema": "wallet_health_official_receipt_v1",
        "source": SOURCE,
        "endpoint": INFO_ENDPOINT,
        "wallet_id": wallet_id,
        "account_scope": "HL_MAIN_PERP_ONLY",
        "request_sha256": sha256(canonical(request)).hexdigest(),
        "raw_sha256": supplied_sha,
        "requested_at": requested_at.isoformat(),
        "received_at": received_at.isoformat(),
        "historical_first_known": False,
        "source_continuity_verified": False,
        "trading_authorized": False,
    }
    _write_immutable_private(generation / "receipts" / name, canonical(record))
    # Verify the bytes independently after writing, not just a self-asserted SHA.
    if sha256((generation / "raw" / name).read_bytes()).hexdigest() != record["raw_sha256"]:
        raise ValueError("DURABLE_HL_SOURCE_RECEIPT_MISMATCH")
    return record


def capture(
    db: Path,
    generation: Path,
    *,
    max_wallets: int = MAX_WALLETS,
    deep_wallets: int = 0,
    weight_per_min: int = DEFAULT_WEIGHT_PER_MIN,
    info: Callable = _guarded_info,
    clock: Callable[[], datetime] = _now,
    out_report: Path | None = None,
    publish_dir: Path | None = None,
) -> dict:
    if not 1 <= max_wallets <= MAX_WALLETS or not 0 <= deep_wallets <= MAX_DEEP:
        raise ValueError("INVALID_HEALTH_CAPTURE_BOUNDS")
    start = clock()
    if start.utcoffset() != timedelta(0):
        raise ValueError("UTC_CAPTURE_CLOCK_REQUIRED")
    roster, registered, roster_sha = _roster(db, start)
    generation = Path(generation)
    if not re.fullmatch(r"g[A-Za-z0-9_-]{12,80}", generation.name):
        raise ValueError("INVALID_HEALTH_GENERATION_NAME")
    if generation.exists():
        raise ValueError("IMMUTABLE_HEALTH_GENERATION_ALREADY_EXISTS")
    generation.mkdir(mode=0o700, parents=True)
    if generation.is_symlink() or generation.stat().st_mode & 0o077:
        raise ValueError("PRIVATE_HEALTH_GENERATION_REQUIRED")
    budget = WeightBudget(weight_per_min)
    errors: Counter[str] = Counter()
    financial: dict[int, FinancialEvidence] = {}
    verified_raw = 0
    ledger_audits = []
    activity_verified = 0
    queried = 0

    def fetch(wallet_id: int, address: str, kind: str, extra: dict | None = None):
        nonlocal verified_raw
        request = {"type": kind, "user": address, **(extra or {})}
        for attempt in range(3):
            budget.acquire(kind)
            requested = clock()
            try:
                payload, raw, signed = info(request)
                received = clock()
                receipt = _save_reply(
                    generation, wallet_id, kind, request, payload, raw, signed, requested, received
                )
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

    last_ms = int(start.timestamp() * 1000)
    since = last_ms - HISTORY_DAYS * 86400 * 1000
    for wallet_id, address in roster[:max_wallets]:
        queried += 1
        state = fetch(wallet_id, address, "clearinghouseState")
        mode = fetch(wallet_id, address, "userAbstraction")
        if state is None or mode is None:
            continue
        state_body, state_meta, at = state
        mode_body = mode[0]
        equity = _book_equity(state_body, mode_body, at)
        last_trade = None
        activity_complete = False
        if queried <= deep_wallets:
            extra = {"startTime": since, "endTime": last_ms}
            for kind in ("userNonFundingLedgerUpdates", "userFunding", "userFillsByTime"):
                reply = fetch(wallet_id, address, kind, extra)
                if reply is None:
                    continue
                payload = reply[0]
                if kind == "userNonFundingLedgerUpdates":
                    try:
                        ledger = _ledger_audit(payload, since=since, until=last_ms)
                    except ValueError, TypeError:
                        errors["LEDGER_INCOMPLETE_OR_INVALID"] += 1
                    else:
                        ledger_audits.append({"wallet_id": wallet_id, **ledger})
                elif kind == "userFillsByTime":
                    if (
                        isinstance(payload, list)
                        and len(payload) <= 2000
                        and all(
                            isinstance(row, dict)
                            and type(row.get("time")) is int
                            and since <= row["time"] <= last_ms
                            for row in payload
                        )
                        and (len(payload) < 2000 or bool(payload))
                    ):
                        if payload:
                            last_trade = datetime.fromtimestamp(
                                max(row["time"] for row in payload) / 1000, UTC
                            )
                        # A saturated 2,000-fill page proves recent activity
                        # but not inactivity when its newest event is old.
                        activity_complete = len(payload) < 2000 or (
                            last_trade is not None and last_trade >= at - timedelta(days=30)
                        )
                        activity_verified += int(activity_complete)
        financial[wallet_id] = FinancialEvidence(
            account_scope="HL_MAIN_PERP_ONLY",
            observed_at=at,
            known_at=at,
            source_sha256=state_meta["raw_sha256"],
            closing_equity=equity,
            capital_verified=equity is not None,
            source_continuity_verified=False,
            last_trade_at=last_trade,
            activity_complete=activity_complete,
            liquidation_verified=None,
            complete_flows=False,
            complete_pnl=False,
        )
    finished = clock()
    if finished.utcoffset() != timedelta(0) or finished < start:
        raise ValueError("INVALID_CAPTURE_FINISH_CLOCK")
    report = assess(db, as_of=finished, financial=financial, provider_budget=MAX_WALLETS)
    path = save_immutable(report, out_report or (generation / "reports"))
    if publish_dir is not None:
        from .wallet_health_projection import project, publish

        publish(publish_dir, project(report, published_at=finished))
    summary = {
        "schema": "wallet_health_official_capture_v1",
        "source": SOURCE,
        "started_at": start.isoformat(),
        "completed_at": finished.isoformat(),
        "requested_registry_identity_sha256": roster_sha,
        "actual_registry_identity_sha256": report.registry_asof_identity_sha256,
        "registry_wallets_asof": registered,
        "candidate_hl_accounts": len(roster),
        "requested_accounts": queried,
        "raw_receipts_verified": verified_raw,
        "verified_main_perp_capital": sum(f.capital_verified for f in financial.values()),
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
        "ledger_diagnostics": ledger_audits,
        "wallet_health_report_sha256": path.stem.split("-")[-1],
        "read_only_source_and_registry": True,
        "trading_authorized": False,
    }
    _write_immutable_private(generation / "capture-manifest.json", canonical(summary))
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Official HL read-only wallet health capture")
    parser.add_argument("--db", type=Path, default=registry.DB)
    parser.add_argument("--generation", required=True, type=Path)
    parser.add_argument("--max-wallets", type=int, default=MAX_WALLETS)
    parser.add_argument("--deep-wallets", type=int, default=0)
    parser.add_argument("--weight-per-minute", type=int, default=DEFAULT_WEIGHT_PER_MIN)
    parser.add_argument("--publish-dir", type=Path)
    args = parser.parse_args(argv)
    # Only one official capture against the source IP and roster at a time.
    lock = args.generation.parent / "wallet-health-capture.lock"
    lock.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if lock.parent.stat().st_mode & 0o077:
        raise ValueError("PRIVATE_CAPTURE_ROOT_REQUIRED")
    fd = os.open(lock, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise ValueError("HEALTH_CAPTURE_ALREADY_RUNNING") from exc
        result = capture(
            args.db,
            args.generation,
            max_wallets=args.max_wallets,
            deep_wallets=args.deep_wallets,
            weight_per_min=args.weight_per_minute,
            publish_dir=args.publish_dir,
        )
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)
    # Never print raw addresses or USD amounts from private source receipts.
    print(
        json.dumps({k: v for k, v in result.items() if k != "ledger_diagnostics"}, sort_keys=True)
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
