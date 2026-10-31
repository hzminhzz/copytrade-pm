"""Independent 2026 Jul-Sep HyperX wallet fill economics; no follower alpha claim.

Cashflow is VENDOR-REPORTED CLOSED PNL MINUS REPORTED FILL FEES,
not wallet equity or net after funding/unrealized PnL. 92 calendar days,
start-inclusive/end-exclusive; never splice an October position anchor
into a July hypothetical follower backtest.
"""

from __future__ import annotations

import argparse
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
import gzip
from hashlib import sha256
import json
import os
from pathlib import Path
from urllib.parse import quote

from .pm_fill_replay import CUT, W019_LIT_GENERATION, _coins, _source_fills
from .pm_hyperx_overlay_audit import _read_pages, _source_tuple, examine
from .pm_propr_scope import classify_coin, SCOPE_STRICT, SCOPE_TENTATIVE
from .pm_sources import CohortEntry, load_cohort


START = datetime(2026, 7, 1, tzinfo=UTC)
END = datetime(2026, 10, 1, tzinfo=UTC)  # Exclusive: 92 calendar days.
ZERO = Decimal("0")
SOURCE_PREFIX = Path("slow_pod_data_v1/hyperx_fills_cache_v1/pages")
SCHEMA = "pm36_independent_2026q3_vendor_fill_audit_v1"


@dataclass(frozen=True)
class EconomicFill:
    timestamp: datetime
    trade_id: int
    coin: str
    before: Decimal
    after: Decimal
    delta: Decimal
    price: Decimal
    closed_pnl: Decimal
    fee: Decimal
    fee_token: str
    direction: str

    @property
    def turnover(self) -> Decimal:
        return abs(self.delta * self.price)

    @property
    def net_reported(self) -> Decimal:
        return self.closed_pnl - self.fee


def _record(record: dict, alias: str, coin: str, address: str) -> EconomicFill:
    try:
        time, tid, label, before, after, delta, price = _source_tuple(record, alias, coin, address)
    except ValueError:
        # Legacy PM-01 accepts zero-price opaque #ID settlement records.
        # These can report vendor close PnL but are not tradable prices.
        if not coin.startswith("#") or Decimal(str(record.get("px"))) != ZERO:
            raise
        if record.get("user", "").lower() != address or record.get("coin") != coin:
            raise ValueError("OPAQUE_SETTLEMENT_WALLET_MISMATCH")
        tid = record.get("tid")
        milliseconds = record.get("time")
        if type(tid) is not int or type(milliseconds) is not int:
            raise ValueError("INVALID_OPAQUE_SETTLEMENT_ID")
        price = ZERO
        before = Decimal(str(record["start_position"]))
        size = Decimal(str(record["sz"]))
        if not before.is_finite() or not size.is_finite() or size <= ZERO:
            raise ValueError("INVALID_OPAQUE_SETTLEMENT_POSITION")
        if record.get("side") not in ("A", "B"):
            raise ValueError("INVALID_OPAQUE_SETTLEMENT_SIDE")
        delta = size if record["side"] == "B" else -size
        after = before + delta
        time = datetime.fromtimestamp(milliseconds / 1000, UTC)
        label = coin
    if "closed_pnl" not in record or "fee" not in record:
        raise ValueError("INCOMPLETE_VENDOR_PNL_FEE_EVIDENCE")
    pnl, fee = Decimal(str(record["closed_pnl"])), Decimal(str(record["fee"]))
    if not pnl.is_finite() or not fee.is_finite():
        raise ValueError("NONFINITE_VENDOR_ECONOMICS")
    token = record.get("fee_token")
    if token != "USDC":
        raise ValueError("UNSUPPORTED_VENDOR_FEE_CURRENCY")
    return EconomicFill(
        time,
        tid,
        label,
        before,
        after,
        delta,
        price,
        pnl,
        fee,
        token,
        str(record.get("dir", "UNKNOWN")),
    )


def _original_records(root: Path, entry: CohortEntry, coin: str) -> list[EconomicFill]:
    if entry.alias == "W019" and coin == "LIT":
        folder = root / W019_LIT_GENERATION
    else:
        folder = root / SOURCE_PREFIX / entry.alias / quote(coin, safe="")
    results: list[EconomicFill] = []
    seen: set[int] = set()
    for n in range(1, 151):
        archive = folder / f"page-{n:05d}.json.gz"
        meta_file = folder / f"page-{n:05d}.meta.json"
        if not archive.exists() and not meta_file.exists():
            if n == 1:
                raise ValueError("MISSING_FIRST_ORIGINAL_FILL_PAGE")
            break
        if not archive.is_file() or not meta_file.is_file():
            raise ValueError("PARTIAL_IMMUTABLE_ORIGINAL_PAGE")
        raw = gzip.decompress(archive.read_bytes())
        meta = json.loads(meta_file.read_bytes())
        if (
            sha256(raw).hexdigest() != meta.get("sha256")
            or meta.get("alias", meta.get("wallet_alias")) != entry.alias
            or meta.get("coin") != coin
            or meta.get("page") != n
        ):
            raise ValueError("ORIGINAL_FILL_PAGE_PROVENANCE_DRIFT")
        doc = json.loads(raw)
        if doc.get("page") != n or doc.get("page_size") != 2000:
            raise ValueError("ORIGINAL_VENDOR_PAGINATION_DRIFT")
        for record in doc.get("fills", []):
            parsed = _record(record, entry.alias, coin, entry.address)
            if parsed.trade_id in seen:
                raise ValueError("DUPLICATE_VENDOR_TID")
            seen.add(parsed.trade_id)
            if parsed.timestamp <= CUT:
                results.append(parsed)
        if doc.get("has_more") is False:
            break
    return results


def _same_normalized(e: EconomicFill, original: tuple) -> bool:
    return (
        e.timestamp == original[0]
        and e.trade_id == original[1]
        and e.coin == original[2]
        and (e.before, e.after, e.delta, e.price) == original[3:]
    )


def _extra_records(
    entry: CohortEntry,
    generations: tuple[Path, ...],
    verified_extra: set[tuple[str, int]],
) -> dict[tuple[str, int], EconomicFill]:
    extra: dict[tuple[str, int], EconomicFill] = {}
    for generation in generations:
        alias_dir = generation / entry.alias
        if not alias_dir.is_dir():
            continue
        for coin_dir in sorted(alias_dir.iterdir()):
            if not coin_dir.is_dir():
                continue
            from urllib.parse import unquote

            coin = unquote(coin_dir.name)
            for doc in _read_pages(coin_dir, entry.alias, coin):
                for record in doc.get("fills", []):
                    parsed = _record(record, entry.alias, coin, entry.address)
                    key = (coin, parsed.trade_id)
                    if key not in verified_extra:
                        continue
                    if key in extra:
                        raise ValueError("REPEATED_VERIFIED_OVERLAY_ECONOMIC_FILL")
                    extra[key] = parsed
    if set(extra) != verified_extra:
        raise ValueError("MISSING_ECONOMICS_FOR_VERIFIED_OVERLAY")
    return extra


def wallet_fills(
    root: Path,
    entry: CohortEntry,
    *,
    generations: tuple[Path, ...] = (),
    verified_additions: list[tuple] | None = None,
) -> tuple[list[EconomicFill], list[str]]:
    """All original + audited overlay records; reconcile exact 7-field fill tuples."""
    coins = _coins(root, entry.alias)
    normalized, issues = _source_fills(
        root,
        entry.alias,
        entry.address,
        coins,
        additional_events=verified_additions or [],
    )
    fatal = [r for r in issues if not r.endswith(":POSITION_DISCONTINUITY")]
    if fatal:
        raise ValueError("UNVERIFIED_OR_INCOMPLETE_VENDOR_FILL_SOURCE")
    canonical = {(x[2], x[1]): x for x in normalized}
    if len(canonical) != len(normalized):
        raise ValueError("DUPLICATE_NORMALIZED_SOURCE_TID")
    recorded = {}
    for coin in coins:
        for record in _original_records(root, entry, coin):
            key = (coin, record.trade_id)
            if (
                key in recorded
                or key not in canonical
                or not _same_normalized(record, canonical[key])
            ):
                raise ValueError("ORIGINAL_ECONOMIC_FILL_REPLAY_MISMATCH")
            recorded[key] = record
    extra_identifiers = {(x[2], x[1]) for x in verified_additions or []}
    if verified_additions and len(extra_identifiers) != len(verified_additions):
        raise ValueError("DUPLICATE_VERIFIED_OVERLAY_SOURCE")
    if extra_identifiers:
        extra = _extra_records(entry, generations, extra_identifiers)
        for key, record in extra.items():
            if (
                key in recorded
                or key not in canonical
                or not _same_normalized(record, canonical[key])
            ):
                raise ValueError("OVERLAY_ECONOMIC_FILL_REPLAY_MISMATCH")
            recorded[key] = record
    if set(recorded) != set(canonical):
        raise ValueError("MISSING_VERIFIED_FILL_ECONOMICS")
    # Preserve source continuity order for same-millisecond fills: TID order
    # can contradict the position-before/after link established by PM-01.
    return [recorded[(x[2], x[1])] for x in normalized], issues


def describe_wallet(
    alias: str,
    fills: list[EconomicFill],
    issues: list[str],
    display_snapshot: dict | None = None,
) -> dict:
    """Vendor-reported *realized* source trading ledger, no equity or ROI."""
    selected = [f for f in fills if START <= f.timestamp < END]
    monthly = {}
    per_day: dict[str, Decimal] = defaultdict(lambda: ZERO)
    for f in selected:
        per_day[f.timestamp.date().isoformat()] += f.net_reported
    for month in ("2026-07", "2026-08", "2026-09"):
        sub = [f for f in selected if f.timestamp.strftime("%Y-%m") == month]
        monthly[month] = {
            "fills": len(sub),
            "gross_closed_pnl_usdc": str(sum((f.closed_pnl for f in sub), ZERO)),
            "reported_fees_usdc": str(sum((f.fee for f in sub), ZERO)),
            "realized_after_reported_fees_usdc": str(sum((f.net_reported for f in sub), ZERO)),
            "days_with_fills": len({f.timestamp.date() for f in sub}),
        }
    realized_gross = sum((f.closed_pnl for f in selected), ZERO)
    fees = sum((f.fee for f in selected), ZERO)
    turnover = sum((f.turnover for f in selected), ZERO)
    # Cumulative realized cashflow only; never call this an equity drawdown.
    running = ZERO
    high = ZERO
    cashflow_peak_to_trough = ZERO
    for event in selected:
        running += event.net_reported
        high = max(high, running)
        cashflow_peak_to_trough = max(cashflow_peak_to_trough, high - running)
    net = realized_gross - fees
    unresolved = sum(1 for error in issues if error.endswith(":POSITION_DISCONTINUITY"))
    # Ex-post Propr display overlap is NOT proof of historical tradability,
    # nor does dropping unsupported legs preserve a hedged source portfolio.
    scope = None
    if display_snapshot is not None:
        by_class: dict[str, dict[str, Decimal | int]] = defaultdict(
            lambda: {"fills": 0, "closed_pnl": ZERO, "fee": ZERO}
        )
        classifications = {}
        for event in selected:
            if event.coin not in classifications:
                classifications[event.coin] = classify_coin(event.coin, display_snapshot)
            cls = classifications[event.coin]
            by_class[cls]["fills"] += 1
            by_class[cls]["closed_pnl"] += event.closed_pnl
            by_class[cls]["fee"] += event.fee
        scope = {
            cls: {
                "fills": values["fills"],
                "reported_realized_net_usdc": str(values["closed_pnl"] - values["fee"]),
            }
            for cls, values in sorted(by_class.items())
        }
    # Daily evidence includes the reported fee on OPEN fills, and recognizes
    # closed PNL when reported. It is not continuously marked equity.
    return {
        "wallet": alias,
        "window": {"start_inclusive": START.isoformat(), "end_exclusive": END.isoformat()},
        "window_calendar_days": 92,
        "fills": len(selected),
        "days_with_fills": len(per_day),
        "first_fill": selected[0].timestamp.isoformat() if selected else None,
        "last_fill": selected[-1].timestamp.isoformat() if selected else None,
        "instruments_with_fills": len({f.coin for f in selected}),
        "gross_closed_pnl_usdc": str(realized_gross),
        "reported_fees_usdc": str(fees),
        "realized_after_reported_fees_usdc": str(net),
        "turnover_notional_usdc_proxy": str(turnover),
        "realized_net_to_turnover_bps_not_roi": (
            str(net / turnover * Decimal("10000")) if turnover else None
        ),
        "realized_cashflow_max_peak_to_trough_usdc_not_equity_drawdown": str(
            cashflow_peak_to_trough
        ),
        "best_realized_fill_day_usdc": str(max(per_day.values())) if per_day else None,
        "worst_realized_fill_day_usdc": str(min(per_day.values())) if per_day else None,
        "monthly": monthly,
        "daily_realized_net_usdc_on_days_with_fills": dict(
            sorted((k, str(v)) for k, v in per_day.items())
        ),
        "post_anchor_position_chain_gaps_all_history": unresolved,
        "reported_settlement_fills_in_window": sum(f.direction == "Settlement" for f in selected),
        "expost_propr_display_classification_not_historical_tradability": scope,
        "source_account_equity": None,
        "source_unrealized_pnl": None,
        "source_funding_pnl": None,
        "source_total_return": None,
        "follower_realized_net_pnl": None,
        "prop_firm_pass_probability": None,
        "classification": "VENDOR_REPORTED_REALIZED_ONLY_NOT_EXECUTABLE_FOLLOWER",
    }


def study(root: Path, generations: tuple[Path, ...] = ()) -> dict:
    entries, manifest_shas = load_cohort(root)
    snapshot_path = root / "PROPR_PUBLIC_ASSET_UNIVERSE_20261030.json"
    display_snapshot = json.loads(snapshot_path.read_bytes()) if snapshot_path.is_file() else None
    if display_snapshot is not None and (
        display_snapshot.get("schema") != "propr_public_universe_browser_snapshot_v1"
        or display_snapshot.get("retrieved_on_utc_date") != "2026-10-30"
        or display_snapshot.get("not_proof_of_historical_availability") is not True
    ):
        raise ValueError("INVALID_POSTPERIOD_PROPR_DISPLAY_SNAPSHOT")
    extras: dict[str, list[tuple]] = {}
    overlay = None
    if generations:
        overlay, extras = examine(root, generations)
        if overlay["wallet_count"] != 36 or not overlay["original_vendor_cache_intact"]:
            raise ValueError("OVERLAY_RECONCILIATION_NOT_VERIFIED")
    wallets = []
    for entry in entries:
        fills, issues = wallet_fills(
            root,
            entry,
            generations=generations,
            verified_additions=extras.get(entry.alias, []),
        )
        wallets.append(describe_wallet(entry.alias, fills, issues, display_snapshot))
    if len(wallets) != 36 or len({r["wallet"] for r in wallets}) != 36:
        raise ValueError("INVALID_SOURCE_COHORT")
    monthly = {
        month: {
            "fills": sum(row["monthly"][month]["fills"] for row in wallets),
            "reported_realized_after_fees_usdc": str(
                sum(
                    (
                        Decimal(row["monthly"][month]["realized_after_reported_fees_usdc"])
                        for row in wallets
                    ),
                    ZERO,
                )
            ),
        }
        for month in ("2026-07", "2026-08", "2026-09")
    }
    return {
        "schema": SCHEMA,
        "source": "HISTORICAL_HYPERX_VERIFIED_RAW_PAGE_VENDOR_REPORTED_FILL_ECONOMICS",
        "study_start_inclusive": START.isoformat(),
        "study_end_exclusive": END.isoformat(),
        "study_calendar_days": (END - START).days,
        "source_cutoff": CUT.isoformat(),
        "wallet_count": len(wallets),
        "source_manifests_sha256": manifest_shas,
        "overlay_generation_shas": overlay["private_generations"] if overlay else [],
        "verified_overlay_new_pre_cutoff_fills": (
            overlay["new_verified_pre_cutoff_fills"] if overlay else 0
        ),
        "quarter_fill_count": sum(row["fills"] for row in wallets),
        "quarter_days_with_any_wallet_fills": len(
            {day for row in wallets for day in row["daily_realized_net_usdc_on_days_with_fills"]}
        ),
        "sum_vendor_reported_realized_after_fees_usdc_not_portfolio_pnl": str(
            sum(
                (Decimal(row["realized_after_reported_fees_usdc"]) for row in wallets),
                ZERO,
            )
        ),
        "monthly": monthly,
        "propr_postperiod_display_snapshot": (
            {
                "observed_at_utc_date": "2026-10-30",
                "sha256": sha256(snapshot_path.read_bytes()).hexdigest(),
                "not_point_in_time_for_2026q3": True,
                "not_broker_market_id_confirmation": True,
                "not_valid_partial_replication_of_missing_hedges": True,
                "strict_native_crypto_class": SCOPE_STRICT,
                "tentative_xyz_class": SCOPE_TENTATIVE,
            }
            if display_snapshot is not None
            else None
        ),
        "wallets": wallets,
        "qualified_follower_wallets": 0,
        "qualified_portfolio_combinations": 0,
        "qualified_challenge_pass_probability": None,
        "source_wallet_equity_or_roi_known": False,
        "realized_cashflow_cannot_establish_drawdown": True,
        "source_funding_unrealized_and_collateral_unknown": True,
        "no_forward_first_known_signal_clock": True,
        "market_execution_delay_not_simulated_in_this_fill_audit": True,
        "live_risk_authorized": False,
    }


def save_private_artifact(out: Path, result: dict, kind: str) -> tuple[Path, str]:
    """O_EXCL owner-only SHA-addressed Q3 evidence; never overwrite source."""
    if kind not in {"fills", "episodes", "threepod"}:
        raise ValueError("INVALID_RESEARCH_ARTIFACT_KIND")
    out.mkdir(parents=True, exist_ok=True, mode=0o700)
    if out.stat().st_mode & 0o077:
        raise ValueError("INSECURE_RESEARCH_ARTIFACT_DIRECTORY")
    payload = (json.dumps(result, sort_keys=True, indent=2, allow_nan=False) + "\n").encode()
    digest = sha256(payload).hexdigest()
    path = out / f"pm36-2026q3-{kind}-{digest[:20]}.json"
    if path.exists():
        if sha256(path.read_bytes()).hexdigest() != digest or path.stat().st_mode & 0o077:
            raise ValueError("RESEARCH_ARTIFACT_HASH_CONFLICT")
        return path, digest
    fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "wb") as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())
    return path, digest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--research-root", required=True, type=Path)
    parser.add_argument("--hyperx-generations", type=Path, nargs="*", default=[])
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    result = study(args.research_root, tuple(args.hyperx_generations))
    output, digest = save_private_artifact(args.out, result, "fills")
    print(
        json.dumps(
            {
                "wallets": result["wallet_count"],
                "range": [result["study_start_inclusive"], result["study_end_exclusive"]],
                "days": result["study_calendar_days"],
                "fills": result["quarter_fill_count"],
                "sum_source_realized_net_ex_funding_not_portfolio": (
                    result["sum_vendor_reported_realized_after_fees_usdc_not_portfolio_pnl"]
                ),
                "qualified_followers": result["qualified_follower_wallets"],
                "sha256": digest,
                "artifact": str(output),
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
