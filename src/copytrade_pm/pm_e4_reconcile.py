"""Cross-source E4 read-only account reconciliation: HyperX vs official Hyperliquid.

Provenance is byte-level and point-in-time; neither asynchronous comparison
nor retrospective margin history is a verified funding/collateral ledger.
A master wallet with subaccounts is *not* silently reduced to the master.
"""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
from decimal import Decimal as D
from hashlib import sha256
import json
from pathlib import Path

from .pm_e4_prospective import (
    PODS,
    account_state,
    canonical,
    dex_universe,
    subaccount_roster,
    safe_dir,
)
from .pm_hyperx_account_triage import verify_response, write_immutable_private
from .pm_sources import load_cohort

KIND_FILES = ("wallet_analysis", "trader_funding", "trader_margin")
MAX_EQUITY_SNAPSHOT_LAG_SECONDS = 300
MAX_EQUITY_RELATIVE_DIFFERENCE = D("0.01")


def _read_raw(path: Path) -> tuple[object, str]:
    if not path.is_file():
        raise ValueError("E4_MISSING_IMMUTABLE_SOURCE")
    raw = path.read_bytes()
    return json.loads(raw), sha256(raw).hexdigest()


def _account_replay(
    generation: Path,
    subject: str,
    address: str,
    dex_catalog: set[str],
) -> dict:
    snapshots = sorted((generation / "account_states").glob(subject + "-[0-9][0-9][0-9][0-9].json"))
    if not snapshots:
        raise ValueError("E4_MISSING_LIVE_ALL_DEX_ACCOUNT")
    last_at = None
    last_state = None
    for path in snapshots:
        snap, _ = _read_raw(path)
        if not isinstance(snap, dict) or snap.get("wallet") != subject:
            raise ValueError("E4_WRONG_SNAPSHOT_IDENTITY")
        frame_sha = snap["source_raw_sha256"]
        frame_id = path.stem.rsplit("-", 1)[-1]
        frame_path = next((generation / "ws_frames").glob(frame_id + "-*.json"), None)
        if frame_path is None:
            raise ValueError("E4_MISSING_SOURCE_FRAME")
        frame, digest = _read_raw(frame_path)
        if digest != frame_sha or not isinstance(frame, dict):
            raise ValueError("E4_SOURCE_FRAME_SHA_MISMATCH")
        metadata, _ = _read_raw(generation / "ws_metadata" / (frame_id + ".json"))
        if (
            metadata["raw_sha256"] != digest
            or metadata["alias"] != subject
            or metadata["channel"] != "allDexsClearinghouseState"
            or metadata["first_locally_received_at"] != snap["first_locally_received_at"]
        ):
            raise ValueError("E4_LOCAL_RECEIPT_REWRITE")
        observed_at = datetime.fromisoformat(snap["first_locally_received_at"])
        if observed_at.tzinfo is None:
            raise ValueError("E4_NAIVE_LOCAL_RECEIPT")
        if last_at is not None and observed_at <= last_at:
            raise ValueError("E4_NONMONOTONIC_LOCAL_RECEIPT")
        state = account_state(frame["data"], address, dex_catalog)
        if state != snap["state"]:
            raise ValueError("E4_NORMALIZATION_DIVERGENCE")
        last_at, last_state = observed_at, state
    assert last_state is not None and last_at is not None
    equity = sum((D(row["account_value_usd"]) for row in last_state["per_dex"]), D(0))
    gross = sum((abs(D(row["total_notional_usd"])) for row in last_state["per_dex"]), D(0))
    margin = sum((D(row["margin_used_usd"]) for row in last_state["per_dex"]), D(0))
    return {
        "account": subject,
        "identity_sha256": sha256(address.lower().encode()).hexdigest(),
        "source": "OFFICIAL_HYPERLIQUID_WS_ALL_DEXS",
        "last_locally_received_at": last_at.isoformat(),
        "snapshot_count": len(snapshots),
        "all_dex_catalog_parity": last_state["dex_catalog_parity_verified"],
        "dex_count": last_state["observed_dex_count"],
        "position_count": last_state["position_count"],
        "perp_account_value_sum_usd": str(equity),
        "perp_gross_proxy_usd": str(gross),
        "perp_margin_used_usd": str(margin),
        "subaccount_portfolio_included": False,
        "spot_collateral_included": False,
    }


def _portfolio_latest(payload: object) -> tuple[datetime, D]:
    if not isinstance(payload, list):
        raise ValueError("E4_INVALID_OFFICIAL_PORTFOLIO")
    rows = {row[0]: row[1] for row in payload if isinstance(row, list) and len(row) == 2}
    periods = rows.get("perpDay")
    if not isinstance(periods, dict):
        raise ValueError("E4_NO_OFFICIAL_PERP_ACCOUNT_VALUE_HISTORY")
    times = periods.get("accountValueHistory", [])
    if not isinstance(times, list) or not times:
        raise ValueError("E4_NO_PERP_EQUITY_HISTORY")
    t, value = times[-1]
    if not isinstance(t, int):
        raise ValueError("E4_INVALID_PORTFOLIO_CLOCK")
    return datetime.fromtimestamp(t / 1000, UTC), D(str(value))


def _margin_latest(payload: object) -> tuple[datetime, D] | None:
    if not isinstance(payload, dict):
        raise ValueError("E4_INVALID_HYPERX_MARGIN_DATA")
    points = payload.get("points", [])
    if not isinstance(points, list) or not points:
        return None
    point = points[-1]
    if not isinstance(point, dict):
        raise ValueError("E4_INVALID_HYPERX_MARGIN_DATA")
    time = datetime.fromisoformat(point["snapshot_time"].replace("Z", "+00:00"))
    if time.tzinfo is None:
        raise ValueError("E4_NAIVE_HYPERX_MARGIN_TIME")
    return time.astimezone(UTC), D(str(point["account_value"]))


def _triangulation(snapshot: dict, equity_time: datetime, equity: D) -> dict:
    observed = datetime.fromisoformat(snapshot["last_locally_received_at"])
    difference = D(snapshot["perp_account_value_sum_usd"]) - equity
    relative = abs(difference) / max(D(1), abs(equity))
    lag = abs((observed - equity_time).total_seconds())
    return {
        "official_portfolio_last_observation_at": equity_time.isoformat(),
        "official_portfolio_perp_value_usd": str(equity),
        "official_streamed_perp_sum_usd": snapshot["perp_account_value_sum_usd"],
        "difference_usd": str(difference),
        "relative_difference": str(relative),
        "asof_gap_seconds": lag,
        "asynchronous_margin_parity_within_1pct_and_300s": (
            relative <= MAX_EQUITY_RELATIVE_DIFFERENCE and lag <= MAX_EQUITY_SNAPSHOT_LAG_SECONDS
        ),
        "independently_reconciled_account_equity": False,
    }


def reconcile(
    root: Path,
    hyperx_root: Path,
    official_generation: Path,
) -> dict:
    cohort, fingerprints = load_cohort(root)
    roster = {x.alias: x for x in cohort if x.alias in PODS}
    if set(roster) != set(PODS):
        raise ValueError("E4_FROZEN_COHORT_DRIFT")
    catalog_data, catalog_sha = _read_raw(official_generation / "catalog" / "perpDexs.json")
    dexs = dex_universe(catalog_data)
    capture, capture_sha = _read_raw(official_generation / "capture-report.json")
    if capture.get("cohort_source_sha") != fingerprints:
        raise ValueError("E4_OFFICIAL_CAPTURE_COHORT_DRIFT")
    results = []
    for alias in PODS:
        entry = roster[alias]
        raw_hyperx = {}
        for kind in KIND_FILES:
            names = sorted(hyperx_root.glob("g*/" + alias + "/" + kind + ".json"))
            if len(names) != 1:
                raise ValueError("E4_HYPERX_MISSING_OR_DUPLICATED_CAPTURE")
            body, sha = _read_raw(names[0])
            verify_response(kind, body, entry.address)
            raw_hyperx[kind] = {
                "sha256": sha,
                "type": "RETROSPECTIVE_VENDOR_ANALYTICS",
                "payload": body,
            }
        sub_data, sub_sha = _read_raw(official_generation / "info_raw" / alias / "subaccounts.json")
        subaddresses = subaccount_roster(sub_data, entry.address)
        root_snap = _account_replay(official_generation, alias, entry.address, dexs)
        sub_snaps = []
        for index, address in enumerate(subaddresses):
            sub_snaps.append(
                _account_replay(official_generation, f"{alias}-sub{index:02d}", address, dexs)
            )
        official_portfolio, official_sha = _read_raw(
            official_generation / "info_raw" / alias / "portfolio.json"
        )
        portfolio_at, portfolio_equity = _portfolio_latest(official_portfolio)
        consistency = _triangulation(root_snap, portfolio_at, portfolio_equity)
        hx_margin = _margin_latest(raw_hyperx["trader_margin"]["payload"])
        current_hx_comparison = (
            {
                "hyperx_last_margin_at": hx_margin[0].isoformat(),
                "hyperx_last_margin_value_usd": str(hx_margin[1]),
                "hyperx_minus_official_perp_snapshot_usd": str(
                    hx_margin[1] - D(root_snap["perp_account_value_sum_usd"])
                ),
                "causal_snapshot_same_time": False,
            }
            if hx_margin is not None
            else {"margin_samples_present": False}
        )
        official_funding, official_funding_sha = _read_raw(
            official_generation / "info_raw" / alias / "funding_recent.json"
        )
        official_ledger, official_ledger_sha = _read_raw(
            official_generation / "info_raw" / alias / "ledger_recent.json"
        )
        spot, spot_sha = _read_raw(official_generation / "info_raw" / alias / "spot_state.json")
        if (
            not isinstance(official_funding, list)
            or not isinstance(official_ledger, list)
            or not isinstance(spot, dict)
        ):
            raise ValueError("E4_INVALID_OFFICIAL_ACCOUNT_SIDE_DATA")
        hx_funding = raw_hyperx["trader_funding"]["payload"]
        if not isinstance(hx_funding.get("records"), list):
            raise ValueError("E4_INVALID_HYPERX_FUNDING_DATA")
        if not isinstance(spot.get("balances"), list):
            raise ValueError("E4_INVALID_SPOT_BALANCE_LIST")
        all_members = [root_snap, *sub_snaps]
        current_positions = sum(m["position_count"] for m in all_members)
        # Account-level equity is not automatically additive across master
        # and subaccounts. Keep their scope separate; never invent a unified
        # source equity/collateral denominator from two data providers.
        row = {
            "pod": alias,
            "identity_sha256": entry.address_sha256,
            "hyperx_raw_sha256": {key: raw_hyperx[key]["sha256"] for key in KIND_FILES},
            "official_raw_sha256": {
                "dex_catalog": catalog_sha,
                "subaccounts": sub_sha,
                "portfolio": official_sha,
                "funding_recent": official_funding_sha,
                "ledger_recent": official_ledger_sha,
                "spot_state": spot_sha,
            },
            "main": root_snap,
            "subaccounts": sub_snaps,
            "subaccounts_observed": len(subaddresses),
            "main_and_subaccount_position_count": current_positions,
            "asynchronous_perp_equity_triangulation": consistency,
            "hyperx_retrospective_margin": current_hx_comparison,
            "hyperx_funding_first_page_count": len(hx_funding["records"]),
            "hyperx_funding_more_pages": hx_funding.get("has_more"),
            "official_funding_first_page_count": len(official_funding),
            "official_funding_page_may_be_truncated": len(official_funding) >= 500,
            "official_nonfunding_ledger_recent_first_page": len(official_ledger),
            "spot_balance_instrument_count": len(spot["balances"]),
            "source_identity_both_providers_verified": True,
            "source_has_locally_timestamped_whole_perp_book_now": True,
            "historical_q3_full_account_book_reconstructed": False,
            "continuous_account_events_proven": False,
            "all_subaccount_collateral_funding_reconciled": False,
            "full_wallet_equity_denominator_eligible_for_e4": False,
            "state": "PROSPECTIVE_ACCOUNT_OBSERVED_NOT_CONTINUOUSLY_RECONCILED",
        }
        results.append(row)
    return {
        "schema": "e4_hyperx_official_account_reconciliation_v1",
        "source_cohort_manifests_sha256": fingerprints,
        "official_capture_sha256": capture_sha,
        "official_generation_name": official_generation.name,
        "official_dex_catalog_sha256": catalog_sha,
        "reported_dex_count": len(dexs),
        "wallet_count": len(results),
        "wallets": results,
        "external_trading_api_loaded": False,
        "live_broker_authorized": False,
        "complete_wallet_e4_historical_source_reconstructed": False,
        "official_current_account_receipts_recorded": True,
        "q3_historical_causality": "NOT_RECOVERABLE_FROM_OCTOBER_SNAPSHOTS",
        "e4_source_readiness": "PARTIAL_PROSPECTIVE_OBSERVED_NOT_RECONCILED",
    }


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--research-root", type=Path, required=True)
    p.add_argument("--hyperx-root", type=Path, required=True)
    p.add_argument("--official-generation", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    a = p.parse_args()
    safe_dir(a.out)
    report = reconcile(a.research_root, a.hyperx_root, a.official_generation)
    raw = canonical(report)
    write_immutable_private(a.out / "reconciliation.json", raw)
    print(
        json.dumps(
            {
                "report_sha256": sha256(raw).hexdigest(),
                "path": str(a.out / "reconciliation.json"),
                "wallets": [
                    {
                        "pod": x["pod"],
                        "main_nonzero_positions": x["main"]["position_count"],
                        "subaccounts": x["subaccounts_observed"],
                        "all_subaccount_positions": (
                            x["main_and_subaccount_position_count"] - x["main"]["position_count"]
                        ),
                        "async_equity_diff_usd": x["asynchronous_perp_equity_triangulation"][
                            "difference_usd"
                        ],
                        "async_equity_close": x["asynchronous_perp_equity_triangulation"][
                            "asynchronous_margin_parity_within_1pct_and_300s"
                        ],
                        "funding_page_truncated": x["official_funding_page_may_be_truncated"],
                        "e4_wallet_equity_fully_reconciled": False,
                    }
                    for x in report["wallets"]
                ],
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
