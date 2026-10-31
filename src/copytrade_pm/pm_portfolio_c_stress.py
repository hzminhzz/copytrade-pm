"""Portfolio C stress diagnostics from the exact immutable PM-03/PM-04 ledger.

No additional execution simulator: reapply sealed PM events and evaluate
signed account/virtual-pod positions already reconciled by PM-03. Stress PnL
is hypothetical and is never posted to account economics or called a fill.
"""

from __future__ import annotations

import argparse
from decimal import Decimal as D
from hashlib import sha256
import json
from pathlib import Path

from .pm03_account import Account, digest
from .pm03_memory import Event
from .pm03_run import ShadowRun
from .pm_portfolio_c_driver import (
    PODS,
    RESULT_SCHEMA,
    SOURCE_FILLS_SHA,
    START,
    _private_json,
    _rulebook,
    pm_to_native,
    shock,
)

ZERO = D("0")
ONE = D("1")


def _profile(account: Account, at: str, *, kind: str) -> dict | None:
    if kind not in ("PM04_SIGNAL", "PM04_TICK"):
        return None
    marks = account.marks
    quantities = {k: q for k, q in account.quantities.items() if q}
    if not quantities:
        return None
    if set(quantities) - set(marks):
        raise ValueError("STRESS_UNKNOWN_ACTIVE_MARK")
    pod_books = {
        pod: {k: q for k, q in account.pm_quantities.get(pod, {}).items() if q} for pod in PODS
    }
    gross = sum((abs(q * marks[k]) for k, q in quantities.items()), ZERO)
    floor, floors = account.floor()
    if floor is None or "daily" not in floors:
        raise ValueError("NO_CONTRACTUAL_STRESS_FLOOR")
    # S1: independent adverse direction for the frozen commodity/index pair.
    s1 = ZERO
    s1_exposure = ZERO
    included = []
    for k, qty in quantities.items():
        native = pm_to_native(k.key)
        coin = native.split(":")[-1]
        if native in (
            "hyperliquid:mainnet:perp:xyz:CL",
            "hyperliquid:mainnet:perp:xyz:XYZ100",
        ):
            notional = abs(qty * marks[k])
            s1 += notional * shock("xyz:" + coin)
            s1_exposure += notional
            included.append("xyz:" + coin)
    # S2: common 10% crash/rally, with pod-by-pod signed return.
    crash = {
        p: sum((q * marks[k] * D("-0.10") for k, q in book.items()), ZERO)
        for p, book in pod_books.items()
    }
    rally = {
        p: sum((q * marks[k] * D("0.10") for k, q in book.items()), ZERO)
        for p, book in pod_books.items()
    }
    crash_loss = max(ZERO, -sum(crash.values(), ZERO))
    rally_loss = max(ZERO, -sum(rally.values(), ZERO))
    side, pnl, common_loss = (
        ("ALL_MARKETS_DOWN_10PCT", crash, crash_loss)
        if crash_loss >= rally_loss
        else ("ALL_MARKETS_UP_10PCT", rally, rally_loss)
    )
    simult = sum(pnl[p] < ZERO for p in PODS)
    active_pods = sum(bool(book) for book in pod_books.values())
    daily_headroom = account.equity - floors["daily"]
    # S3: no exit liquidity; existing inventory remains on the PM-03 book.
    # Apply 2x each instrument's fixed conservative adverse shock. Do not
    # assert that a stop or a subsequent exit would actually have filled.
    interruption_loss = ZERO
    for k, qty in quantities.items():
        native = pm_to_native(k.key)
        parts = native.split(":")
        coin = parts[-1] if parts[3] == "default" else parts[3] + ":" + parts[4]
        interruption_loss += abs(qty * marks[k]) * shock(coin) * D("2")
    return {
        "at": at,
        "active_pods": active_pods,
        "marked_account_gross_usd": str(gross),
        "S1": {
            "joint_CL_XYZ100_adverse_loss_usd": str(s1),
            "combined_CL_XYZ100_gross_usd": str(s1_exposure),
            "active_members": sorted(included),
            "direct_mark_shock_only_not_liquidity": True,
        },
        "S2": {
            "side": side,
            "common_factor_account_loss_usd": str(common_loss),
            "simultaneously_losing_pods": simult,
            "pod_pnl_usd": {p: str(x) for p, x in pnl.items()},
            "market_wide_shock_size": "10%",
        },
        "S3": {
            "loss_if_2x_adverse_and_exit_fully_unavailable_usd": str(interruption_loss),
            "daily_floor_headroom_before_shock_usd": str(daily_headroom),
            "daily_floor_at_risk_if_unavailable": interruption_loss >= daily_headroom,
            "inventory_remaining_usd_if_exit_capacity_zero": str(gross),
            "zero_exit_assumption_not_an_executed_trade": True,
            "broker_stop_guarantees_loss": False,
        },
    }


def stress_scenario(
    manifest: dict,
    input_sha: str,
    result_path: Path,
) -> dict:
    blob = result_path.read_bytes()
    file_sha = sha256(blob).hexdigest()
    if result_path.name != f"result-{file_sha[:20]}.json":
        raise ValueError("UNVERIFIED_SHA_ADDRESS")
    report = json.loads(blob)
    if (
        report.get("schema") != RESULT_SCHEMA
        or report.get("input_sha256") != input_sha
        or report.get("source_classification") != "HISTORICAL_ORACLE_NOT_FIRST_KNOWN"
        or report.get("ledger_replay_verified") is not True
    ):
        raise ValueError("UNVERIFIED_REPLAY_PROVENANCE")
    root = result_path.parent
    run = ShadowRun(
        root,
        run_id=report["run_id"],
        rulebook=_rulebook(manifest["instruments"]),
        started_at=START.isoformat(),
        mode="RESEARCH_SYNTHETIC",
        pm01_sha=SOURCE_FILLS_SHA,
        pm02_sha=digest({"pm02": "not supplied", "oracle": input_sha}),
        market_manifest_sha=digest(manifest["market_day_shas"]),
    )
    # ShadowRun construction independently replays and verifies the entire
    # immutable ledger; replicate the same events for stress sample selection.
    account = Account.start(run.initial_rulebook, START.isoformat())
    peaks: dict[str, tuple[D, dict]] = {}
    sampled = 0
    combined_pod_exposure_samples = 0
    at_risk_samples = 0
    cl_active_samples = 0
    xyz100_active_samples = 0
    simultaneous_cl_xyz100_samples = 0
    for row in run.ledger.read():
        ev = Event(**row["event"])
        run._apply(account, ev)
        sample = _profile(account, ev.decision_at, kind=ev.kind)
        if sample is None:
            continue
        sampled += 1
        if sample["active_pods"] >= 2:
            combined_pod_exposure_samples += 1
        if sample["S3"]["daily_floor_at_risk_if_unavailable"]:
            at_risk_samples += 1
        members = set(sample["S1"]["active_members"])
        cl_active_samples += "xyz:CL" in members
        xyz100_active_samples += "xyz:XYZ100" in members
        simultaneous_cl_xyz100_samples += {"xyz:CL", "xyz:XYZ100"} <= members
        keys = {
            "S1": D(sample["S1"]["joint_CL_XYZ100_adverse_loss_usd"]),
            "S2": D(sample["S2"]["common_factor_account_loss_usd"]),
            "S3": D(sample["S3"]["loss_if_2x_adverse_and_exit_fully_unavailable_usd"])
            / max(D("1"), D(sample["S3"]["daily_floor_headroom_before_shock_usd"])),
        }
        for key, score in keys.items():
            if key not in peaks or score > peaks[key][0]:
                peaks[key] = (score, sample)
    if digest(account.snapshot()) != report["account_snapshot_sha256"]:
        raise ValueError("STRESS_SOURCE_ACCOUNT_REPLAY_DIVERGED")
    return {
        "schema": "portfolio_c_sealed_ledger_stress_v1",
        "scenario": {
            "method": report["method"],
            "execution": report["execution"],
            "cost_multiplier": report["cost_multiplier"],
        },
        "source_report_sha256": file_sha,
        "input_sha256": input_sha,
        "account_ledger_verified": True,
        "marked_samples_with_exposure": sampled,
        "samples_with_multiple_active_pods": combined_pod_exposure_samples,
        "samples_with_2x_adverse_exceeding_daily_headroom": at_risk_samples,
        "cl_active_samples": cl_active_samples,
        "xyz100_active_samples": xyz100_active_samples,
        "simultaneous_cl_xyz100_active_samples": simultaneous_cl_xyz100_samples,
        "S1_worst_sample": peaks["S1"][1] if "S1" in peaks else None,
        "S2_worst_sample": peaks["S2"][1] if "S2" in peaks else None,
        "S3_worst_sample": peaks["S3"][1] if "S3" in peaks else None,
        "economic_outcome_of_shocks": "HYPOTHETICAL_NOT_BOOKED",
        "qualification": "HISTORICAL_ORACLE_INCOMPLETE_BOOK_NOT_PROPR_EXECUTABLE",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--result", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    blob = args.input.read_bytes()
    input_sha = sha256(blob).hexdigest()
    if args.input.name != f"portfolio-c-input-{input_sha[:20]}.json":
        raise ValueError("INPUT_SHA_MISMATCH")
    manifest = json.loads(blob)
    result = stress_scenario(manifest, input_sha, args.result)
    path, output_sha = _private_json(args.out, "stress", result)
    print(
        json.dumps(
            {
                "result": str(path),
                "sha256": output_sha,
                "sampled": result["marked_samples_with_exposure"],
                "S1": result["S1_worst_sample"],
                "S2": result["S2_worst_sample"],
                "S3": result["S3_worst_sample"],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
