"""Causal, signed leader-book change detector for private REST generations.

No equities, sizing, broker clients, orders, or credentials. REST snapshots only
prove that signed positions differed *between two observed books*; they never
prove native source fill timestamps or economically executable follower alpha.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
from hashlib import sha256
import argparse
import json
from pathlib import Path
import re
from typing import Any

from .pm_combo2 import BATCH_SECONDS
from .pm_combo2_capture import _private_file
from .pm_combo2_rest_capture import MANAGERS, _canonical
from .pm_e4_prospective import _dex_universe

SCHEMA = "combo2_signed_rest_position_delta_v1"
SYMBOL = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,79}\Z")
MAX_SWEEP_SECONDS = 240
MAX_OBSERVATION_GAP_SECONDS = 900


def _clock(value: str) -> datetime:
    if not isinstance(value, str):
        raise ValueError("REST_OBSERVATION_TIMESTAMP_MISSING")
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if result.tzinfo is None:
        raise ValueError("REST_OBSERVATION_TIMEZONE_MISSING")
    return result.astimezone(UTC)


def _decimal(value: Any) -> Decimal:
    if isinstance(value, bool) or not isinstance(value, (int, float, str, Decimal)):
        raise ValueError("INVALID_SIGNED_SOURCE_QUANTITY")
    try:
        x = Decimal(str(value))
    except InvalidOperation as exc:
        raise ValueError("INVALID_SIGNED_SOURCE_QUANTITY") from exc
    if not x.is_finite() or abs(x) > Decimal("1e18"):
        raise ValueError("INVALID_SIGNED_SOURCE_QUANTITY")
    return x


def _generation(path: Path) -> dict:
    if not path.is_dir() or path.is_symlink() or path.stat().st_mode & 0o077:
        raise ValueError("UNSAFE_OR_MISSING_PRIVATE_GENERATION")
    raw_report = _private_file(path / "report.json")
    report = json.loads(raw_report)
    if (
        report.get("schema") != "combo2_rest_account_capture_v1"
        or report.get("route") != "HYPERLIQUID_READ_ONLY_POST_INFO"
        or report.get("all_subjects_captured") is not True
        or report.get("all_accounts_coherent_at_one_instant") is not False
        or report.get("follower_source_equity_verified") is not False
        or report.get("network_order_mutations") != 0
        or report.get("errors")
        or report.get("account_count") != 10
        or report.get("paper_fills_created") != 0
    ):
        raise ValueError("INCOMPLETE_OR_UNTRUSTED_REST_SWEEP")
    start = _clock(report["started_at"])
    end = _clock(report["finished_at"])
    if not 0 <= (end - start).total_seconds() <= MAX_SWEEP_SECONDS:
        raise ValueError("REST_SWEEP_NONCAUSAL_OR_TOO_SLOW")
    raw_catalog = _private_file(path / "raw" / "perpDexs.json")
    catalog_meta = json.loads(_private_file(path / "metadata" / "perpDexs.json"))
    if (
        catalog_meta.get("kind") != "perpDexs"
        or catalog_meta.get("sha256") != sha256(raw_catalog).hexdigest()
        or catalog_meta.get("scope_hash") is not None
    ):
        raise ValueError("REST_DEX_CATALOG_RAW_HASH_MISMATCH")
    catalog = json.loads(raw_catalog)
    dexs = _dex_universe(catalog)
    if (
        report.get("dex_catalog_sha256") != sha256(_canonical(catalog)).hexdigest()
        or report.get("dex_count") != len(dexs)
        or not 1 <= len(dexs) <= 20
    ):
        raise ValueError("REST_DEX_CATALOG_REPORT_MISMATCH")
    managers = report.get("managers", {})
    subjects = report.get("subjects", {})
    if set(managers) != set(MANAGERS) or not isinstance(subjects, dict):
        raise ValueError("REST_LEADER_CENSUS_MISSING")
    expected = []
    for manager in MANAGERS:
        count = managers[manager].get("subaccount_count")
        if not isinstance(count, int) or isinstance(count, bool) or not 0 <= count <= 8:
            raise ValueError("REST_SUBACCOUNT_CENSUS_UNATTESTED")
        expected.append(manager)
        expected.extend(f"{manager}-sub{i:02d}" for i in range(count))
    if len(expected) != 10 or set(subjects) != set(expected):
        raise ValueError("REST_SUBACCOUNT_SCOPE_NOT_COMPLETE")
    books: dict[str, dict[str, Decimal]] = {manager: {} for manager in MANAGERS}
    for alias in expected:
        manager = alias.split("-sub")[0]
        row = subjects[alias]
        identity = row.get("sha256")
        if (
            not isinstance(identity, str)
            or re.fullmatch(r"[a-f0-9]{64}", identity) is None
            or row.get("observed_dexs") != len(dexs)
            or row.get("spot_observed") is not True
            or row.get("account_mode")
            not in {"unifiedAccount", "portfolioMargin", "disabled", "default", "dexAbstraction"}
            or row.get("errors")
        ):
            raise ValueError("REST_SUBJECT_ACCOUNT_UNVERIFIED")
        for dex in sorted(dexs):
            tag = f"{alias}-dex-{dex}"
            frame = _private_file(path / "raw" / (tag + ".json"))
            meta = json.loads(_private_file(path / "metadata" / (tag + ".json")))
            at = _clock(meta.get("locally_received_at"))
            if (
                meta.get("kind") != "clearinghouseState"
                or meta.get("sha256") != sha256(frame).hexdigest()
                or meta.get("scope_hash") != identity
                or not start <= at <= end
            ):
                raise ValueError("REST_ACCOUNT_FRAME_PROVENANCE_INVALID")
            payload = json.loads(frame)
            if (
                not isinstance(payload, dict)
                or not isinstance(payload.get("marginSummary"), dict)
                or not isinstance(payload.get("assetPositions"), list)
            ):
                raise ValueError("REST_ACCOUNT_FRAME_MALFORMED")
            unique = set()
            for item in payload["assetPositions"]:
                position = item.get("position") if isinstance(item, dict) else None
                if not isinstance(position, dict):
                    raise ValueError("REST_SIGNED_POSITION_MALFORMED")
                coin = position.get("coin")
                if not isinstance(coin, str) or not SYMBOL.fullmatch(coin):
                    raise ValueError("REST_POSITION_SYMBOL_INVALID")
                if coin in unique:
                    raise ValueError("REST_DUPLICATE_POSITION_SYMBOL")
                unique.add(coin)
                qty = _decimal(position.get("szi"))
                symbol = f"hyperliquid/mainnet:perp:{dex}/{coin}"
                books[manager][symbol] = books[manager].get(symbol, Decimal(0)) + qty
    scopes = {
        alias: (
            subjects[alias]["sha256"],
            subjects[alias]["account_mode"],
        )
        for alias in expected
    }
    return {
        "start": start,
        "end": end,
        "scopes": scopes,
        "dexs": dexs,
        "books": books,
        "report_sha256": sha256(raw_report).hexdigest(),
    }


def _kind(before: Decimal, after: Decimal) -> str:
    if after == 0:
        return "CLOSE"
    if before == 0:
        return "OPEN_LONG" if after > 0 else "OPEN_SHORT"
    if before * after < 0:
        return "REVERSE_LONG" if after > 0 else "REVERSE_SHORT"
    if abs(after) > abs(before):
        return "INCREASE_LONG" if after > 0 else "INCREASE_SHORT"
    return "REDUCE_LONG" if after > 0 else "REDUCE_SHORT"


def compare_generations(
    earlier: Path, later: Path, *, max_gap_seconds: int = MAX_OBSERVATION_GAP_SECONDS
) -> dict:
    """Compare aggregate manager positions across two complete REST sweeps.

    Timestamp the *fully observed* second sweep, not a retrospective source
    fill or earlier partial account observation. Private addresses never leave
    the generation store. No execution order can be produced by this module.
    """
    if not 60 <= max_gap_seconds <= MAX_OBSERVATION_GAP_SECONDS:
        raise ValueError("INVALID_REST_OBSERVATION_GAP_POLICY")
    if earlier.resolve() == later.resolve():
        raise ValueError("SAME_SOURCE_GENERATION")
    old = _generation(earlier)
    new = _generation(later)
    gap = (new["start"] - old["end"]).total_seconds()
    if not 0 <= gap <= max_gap_seconds:
        raise ValueError("REST_OBSERVATION_GAP_OR_REORDERING")
    if old["scopes"] != new["scopes"] or old["dexs"] != new["dexs"]:
        raise ValueError("REST_SUBACCOUNT_OR_DEX_SCOPE_DRIFT")
    events = []
    for manager in MANAGERS:
        old_book, new_book = old["books"][manager], new["books"][manager]
        for symbol in sorted(old_book.keys() | new_book.keys()):
            before = old_book.get(symbol, Decimal(0))
            after = new_book.get(symbol, Decimal(0))
            if before == after:
                continue
            action = _kind(before, after)
            fingerprint = {
                "schema": SCHEMA,
                "old_report_sha256": old["report_sha256"],
                "new_report_sha256": new["report_sha256"],
                "manager": manager,
                "instrument": symbol,
                "before": str(before),
                "after": str(after),
            }
            events.append(
                {
                    "schema": SCHEMA,
                    "signal_id": sha256(_canonical(fingerprint)).hexdigest(),
                    "manager": manager,
                    "instrument": symbol,
                    "signed_quantity_before": str(before),
                    "signed_quantity_after": str(after),
                    "signed_delta": str(after - before),
                    "change_kind": action,
                    "source_event_at": None,
                    "first_known_at": new["end"].isoformat(),
                    "due_at": (new["end"] + timedelta(seconds=BATCH_SECONDS)).isoformat(),
                    "old_report_sha256": old["report_sha256"],
                    "new_report_sha256": new["report_sha256"],
                    "subaccounts_included": True,
                    "source_equity_verified": False,
                    "execution_authorized": False,
                    "provenance": "REST_TWO_COMPLETE_NONATOMIC_BOOKS_NOT_SOURCE_FILL",
                }
            )
    return {
        "schema": "combo2_signed_rest_delta_batch_v1",
        "first_known_at": new["end"].isoformat(),
        "source_books_complete": True,
        "source_equity_verified": False,
        "execution_authorized": False,
        "signals": events,
        "source_pair_sha256": sha256(
            _canonical([old["report_sha256"], new["report_sha256"]])
        ).hexdigest(),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--earlier", type=Path, required=True)
    parser.add_argument("--later", type=Path, required=True)
    options = parser.parse_args()
    print(json.dumps(compare_generations(options.earlier, options.later), sort_keys=True))


if __name__ == "__main__":
    main()
