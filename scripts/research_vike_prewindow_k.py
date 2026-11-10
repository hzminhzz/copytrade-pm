"""Vike July exposure summaries -> explicitly retrospective research k; no backdated releases.

This tool reads private, bounded Vike hourly-position aggregates captured through the
Vike plugin. It does not pull current wallet scores, simulate future outcomes, or write
to the SQLite registry, SHADOW consumers, portfolio releases or any service.
"""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import UTC, datetime
from decimal import Decimal, ROUND_DOWN
from hashlib import sha256
import json
import os
from pathlib import Path

from copytrade_pm.pm_offline_repository import native_instrument
from copytrade_pm.pm_v4_fast_screen import (
    RETRO_MODEL,
    RETRO_SCHEMA,
    _v2_source_digest,
    _v2_source_files,
)


def compact(obj: object) -> bytes:
    return (
        json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True) + "\n"
    ).encode()


def checked_publish(root: Path, prefix: str, obj: object) -> tuple[Path, str]:
    payload = compact(obj)
    digest = sha256(payload).hexdigest()
    dst = root / f"{prefix}-{digest[:16]}.json"
    try:
        descriptor = os.open(dst, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
    except FileExistsError:
        if dst.read_bytes() != payload:
            raise ValueError("IMMUTABLE_RESEARCH_RECEIPT_CONFLICT") from None
    return dst, digest


def build(
    *,
    evidence_dir: Path,
    source_root: Path,
    output_root: Path,
    generated_at: str,
    min_days: int = 7,
) -> dict:
    if min_days != RETRO_MODEL["min_observation_days"]:
        raise ValueError("RETRO_RISK_FUNCTION_MUST_STAY_PREDECLARED")
    root = evidence_dir.resolve(strict=True)
    files = sorted(root.glob("vike-prewindow-1011-batch[0-9][0-9].json"))
    if len(files) != 16:
        raise ValueError("INCOMPLETE_VIKE_TRAINING_COHORT_BATCHES")
    source_files = _v2_source_files(source_root)
    original_ids = {}
    markets = set()
    for path in source_files:
        raw = json.loads(path.read_bytes())
        addr = raw["address"].lower()
        identity = sha256(addr.encode()).hexdigest()
        if identity in original_ids:
            raise ValueError("DUPLICATE_SOURCE_WALLET")
        original_ids[identity] = path.stem.split("_0x")[0]
        for fill in raw["fills"]:
            try:
                markets.add(native_instrument(fill.get("coin")))
            except ValueError, TypeError:
                continue

    input_sha = sha256()
    rows = {}
    for path in files:
        blob = path.read_bytes()
        input_sha.update(sha256(blob).digest())
        payload = json.loads(blob)
        if payload.get("schema") != "vike_prewindow_exposure_aggregate_v1":
            raise ValueError("INVALID_VIKE_EVIDENCE_SCHEMA")
        for record in payload["results"]:
            account = record["sha"]
            if account in rows or account not in original_ids:
                raise ValueError("UNRECOGNIZED_OR_DUPLICATE_VIKE_WALLET")
            rows[account] = record
    if set(rows) != set(original_ids):
        raise ValueError("V4_VIKE_TRAINING_UNIVERSE_MISMATCH")

    decision = {}
    reasons = Counter()
    for account, record in sorted(rows.items()):
        if record.get("error"):
            reason = "VENDOR_QUERY_FAILED"
        elif record.get("more") or record.get("cursor"):
            reason = "INCOMPLETE_VIKE_PAGINATION"
        elif record.get("invalid", 0):
            reason = "INVALID_VIKE_SNAPSHOT_ROW"
        elif record.get("days", 0) < min_days or record.get("snapshots", 0) < 24:
            reason = "INSUFFICIENT_PREWINDOW_OBSERVATION"
        elif record.get("max_usd", 0) <= 0:
            reason = "ZERO_OR_UNKNOWN_OBSERVED_EXPOSURE"
        elif (
            record.get("first_ts") is None
            or record.get("last_ts") is None
            or not "2026-07-01T00:00:00" <= record["first_ts"][:19]
            or not record["last_ts"][:19] < "2026-08-05T00:00:00"
        ):
            reason = "PREWINDOW_TIMESTAMP_NOT_VERIFIED"
        else:
            reason = "TRAINING_EVIDENCE_ELIGIBLE"
        reasons[reason] += 1
        if reason != "TRAINING_EVIDENCE_ELIGIBLE":
            continue
        gross = Decimal(str(record["max_usd"]))
        raw_k = min(
            Decimal(RETRO_MODEL["max_k"]),
            Decimal(RETRO_MODEL["risk_budget_usd"])
            / (Decimal(RETRO_MODEL["stress_move_fraction"]) * gross),
        )
        k = raw_k.quantize(Decimal("0.000000000001"), rounding=ROUND_DOWN)
        if k <= 0:
            reasons["K_UNDER_MINIMUM_REPRESENTABLE"] += 1
            reasons[reason] -= 1
            continue
        decision[account] = {
            "k": str(k),
            "max_observed_gross_usd": str(gross),
            "observation_days": int(record["days"]),
            "snapshots": int(record["snapshots"]),
            "first_observed_at": record["first_ts"],
            "last_observed_at": record["last_ts"],
            "evidence_sha256": sha256(compact(record)).hexdigest(),
        }

    # Explicit scenario proxies, not authenticated historic venue precision.
    # Avoid using post-cutoff successful trades to choose k or trading policy.
    # No market is silently defaulted to another DEX.
    market_rules = {
        m: {"step": "0.00001", "minimum_notional": "10", "max_notional": "10000"}
        for m in sorted(markets)
    }
    policy = {
        "schema": "v4_screen_retrospective_k_policy_v1",
        "training_start": "2026-07-01T00:00:00+00:00",
        "training_end": "2026-08-05T00:00:00+00:00",
        "generated_at": generated_at,
        "model": RETRO_MODEL,
        "vike_training_aggregates_sha256": input_sha.hexdigest(),
        "wallets": decision,
        "markets": market_rules,
    }
    output_root.mkdir(mode=0o700, parents=True, exist_ok=True)
    policy_path, policy_sha = checked_publish(output_root, "retro-vike-k-policy", policy)
    manifest = {
        "schema": RETRO_SCHEMA,
        "study_id": "vike-jul2026-to-aug04-94wallet-k-oos-v1",
        "kind": "V4_RETROSPECTIVE_TRAINED_K_SCREEN",
        "clock_basis": "HISTORICAL_ORACLE",
        "start": "2026-08-05T00:00:00+00:00",
        "end": "2026-11-03T00:00:00+00:00",
        "source_collection_sha256": _v2_source_digest(source_root),
        "k_policy_path": policy_path.name,
        "k_policy_sha256": policy_sha,
    }
    manifest_path, manifest_sha = checked_publish(output_root, "retro-vike-screen-job", manifest)
    receipt = {
        "schema": "vike_retro_k_calibration_receipt_v1",
        "classification": "RETROSPECTIVELY_GENERATED_RESEARCH_PARAMETERS_NOT_A_PAST_RELEASE",
        "generated_at": generated_at,
        "source": "Vike historical hl_market.positions wallet scoped, hourly, calendar prewindow",
        "observed_training_hours_start": policy["training_start"],
        "observed_training_hours_end_exclusive": policy["training_end"],
        "calibration_source_sha256": input_sha.hexdigest(),
        "source_wallet_count": len(original_ids),
        "wallets_with_train_k": len(decision),
        "blocked_reasons": dict(sorted(reasons.items())),
        "assumed_historical_lot_step": "0.00001 (proxy, not exchange-verified at historical date)",
        "historical_signed_release": False,
        "genuine_forward_first_known": False,
        "scientifically_qualified": False,
        "order_route": "NONE",
        "policy_filename": policy_path.name,
        "policy_sha256": policy_sha,
        "job_filename": manifest_path.name,
        "job_sha256": manifest_sha,
        "research_only_aliases": [
            {
                "alias": original_ids[key],
                "k": item["k"],
                "observation_days": item["observation_days"],
                "max_observed_gross_usd": item["max_observed_gross_usd"],
            }
            for key, item in decision.items()
        ],
    }
    receipt_path, receipt_sha = checked_publish(
        output_root, "retro-vike-calibration-receipt", receipt
    )
    return {
        "policy": str(policy_path),
        "manifest": str(manifest_path),
        "receipt": str(receipt_path),
        "receipt_sha256": receipt_sha,
        "with_k": len(decision),
        "source_wallets": len(rows),
        "blocked": dict(sorted(reasons.items())),
        "market_rules": len(market_rules),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence-dir", type=Path, required=True)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    args = parser.parse_args()
    result = build(
        evidence_dir=args.evidence_dir,
        source_root=args.source_root,
        output_root=args.output_root,
        generated_at=datetime.now(UTC).isoformat(),
    )
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
