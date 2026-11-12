"""Bounded wallet-scoped Reservoir research backfill, with two frozen cohorts.

With --cohort sealed_six, fill the missing July1..Oct11 selected 14-wallet
dates, preserving the separately verified Oct12..Nov11 data.
With --cohort monitored_plus_six, fetch July1..Nov11 for the immutable union
of the 264 configured/subscribed wallets and 14 six-portfolio wallets (269
unique in the monitored snapshot). These are distinct evidence generations;
never reuse or silently overwrite the narrower Parquet.
Only hyperliquid + xyz, one request per DEX/day, no live ingest or trading.

Run under RESERVOIR_AWS_PROFILE=mgmt while default AWS login is expired.
The configured profile determines who pays S3 requester-pays charges.
"""

from __future__ import annotations

import argparse
from copy import deepcopy
from datetime import UTC, date, datetime, timedelta
import json
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.catalog_reservoir_six_portfolios import (  # noqa: E402
    PRIVATE_RESEARCH_ROOT,
    historical_windows,
    window_sources as sealed_window_sources,
)
from scripts.pilot_reservoir_wallet_scoped import (  # noqa: E402
    ALLOWED_DEXES,
    AWS_PROFILE,
    CORE,
    SNAP_FIELDS,
    column_budget,
    exclusive_bytes,
    fetch,
    jdump,
    preflight,
    private_lock,
    registry_scope,
    remote_connection,
    verify_artifact,
    report,
    scope_from_registry,
    source_keys,
    verify_manifest,
)

MAX_PER_BATCH_MB = 2000
MAX_TOTAL_MB = 50_000
ALLOWED_COHORTS = ("sealed_six", "monitored_plus_six")


def windows(cohort: str) -> tuple[tuple[str, date, date], ...]:
    if cohort == "sealed_six":
        return historical_windows()
    if cohort != "monitored_plus_six":
        raise ValueError("UNAPPROVED_COHORT")
    begin, end = date(2026, 7, 1), date(2026, 11, 11)
    result: list[tuple[str, date, date]] = []
    while begin <= end:
        last = min(begin + timedelta(days=6), end)
        result.append((f"{begin:%Y%m%d}-{last:%Y%m%d}", begin, last))
        begin = last + timedelta(days=1)
    return tuple(result)


def window_for(first_day: str, cohort: str = "sealed_six") -> tuple[str, date, date]:
    for token, start, end in windows(cohort):
        if first_day == str(start):
            return token, start, end
    raise ValueError("START_NOT_APPROVED_SEVEN_DAY_WINDOW")


def root_for(token: str, dex: str, cohort: str = "sealed_six") -> Path:
    if dex not in ALLOWED_DEXES:
        raise ValueError("THIRD_DEX_NOT_ALLOWED")
    if cohort == "sealed_six":
        prefix = "reservoir-six"
    elif cohort == "monitored_plus_six":
        prefix = "reservoir-monitored-plus-six"
    else:
        raise ValueError("UNAPPROVED_COHORT")
    return PRIVATE_RESEARCH_ROOT / f"{prefix}-{dex}-{token}"


def budget_summary(max_total_mb: int = MAX_TOTAL_MB, cohort: str = "sealed_six") -> dict:
    projected = 0
    present = []
    absent = []
    billing = set()
    verified_artifacts = 0
    verified_fill_rows = 0
    verified_position_rows = 0
    for token, first, last in windows(cohort):
        for dex in sorted(ALLOWED_DEXES):
            path = root_for(token, dex, cohort) / "preflight.json"
            if not path.exists():
                absent.append({"dex": dex, "first": str(first)})
                continue
            _, frozen = verify_manifest(path.parent)
            if frozen["days"] != [
                str(first + timedelta(days=i)) for i in range((last - first).days + 1)
            ]:
                raise ValueError("PREFLIGHT_WINDOW_DRIFT")
            billing.add(frozen["aws_billing_profile"])
            projected += frozen["total_projected_compressed_bytes"]
            for day in frozen["days"]:
                for kind in ("fills", "position_snapshot"):
                    item = next(
                        x
                        for x in frozen["objects"]
                        if x["type"] == kind and f"date={day}/" in x["key"]
                    )
                    proven = verify_artifact(
                        path.parent / kind / f"day={day}",
                        item["etag"],
                        frozen["scope"]["wallet_set_sha256"],
                    )
                    if proven is None:
                        continue
                    verified_artifacts += 1
                    if kind == "fills":
                        verified_fill_rows += proven["rows"]
                    else:
                        verified_position_rows += proven["rows"]
            present.append(
                {
                    "dex": dex,
                    "first": str(first),
                    "projected_MB": round(frozen["total_projected_compressed_bytes"] / 1e6, 3),
                }
            )
    if projected > max_total_mb * 1_000_000:
        raise ValueError("TOTAL_PROJECTED_SOURCE_BUDGET_EXCEEDED")
    return {
        "schema": "reservoir_six_from_july_budget_v2",
        "cohort": cohort,
        "billing_profiles": sorted(billing),
        "weeks": len(windows(cohort)),
        "preflight_done": len(present),
        "preflight_missing": len(absent),
        "immutable_artifacts_verified": verified_artifacts,
        "verified_fill_rows_staged": verified_fill_rows,
        "verified_position_rows_staged": verified_position_rows,
        "missing_windows": absent,
        "planned_new_days": sum((e - s).days + 1 for _, s, e in windows(cohort)),
        "projected_MB": round(projected / 1e6, 3),
        "max_total_MB": max_total_mb,
    }


def cached_metadata_preflight(
    start: date, end: date, folder: Path, dex: str, max_projected_bytes: int
) -> dict:
    """Reuse immutable source-object metadata, NOT earlier filtered wallet data.

    Footer column chunks and S3 object versions do not depend on the wallet
    filter. Rebinding a new 269-wallet scope avoids re-reading old footers;
    every S3 ETag/size is independently checked before data retrieval.
    """
    if dex not in ALLOWED_DEXES:
        raise ValueError("THIRD_DEX_NOT_ALLOWED")
    wallets, scope = scope_from_registry("monitored_plus_six")
    selected_wallets, selected_scope = registry_scope()
    if len(wallets) != 269 or len(selected_wallets) != 14:
        raise ValueError("MONITORED_SCOPE_INTEGRITY")
    prior_roots = sealed_window_sources()
    objects = []
    projected = 0
    reused_count = 0
    conn = None
    try:
        for step in range((end - start).days + 1):
            day = str(start + timedelta(days=step))
            cached = {}
            root = prior_roots.get((dex, day))
            if root is not None and (root / "preflight.json").is_file():
                older = json.loads((root / "preflight.json").read_text())
                if (
                    older["scope"]["wallet_set_sha256"] != selected_scope["wallet_set_sha256"]
                    or older["scope"]["portfolio_versions"] != selected_scope["portfolio_versions"]
                    or older.get("dex", "hyperliquid") != dex
                    or day not in older["days"]
                ):
                    raise ValueError("CACHED_SOURCE_SCOPE_DRIFT")
                for record in older["objects"]:
                    if f"date={day}/" in record["key"]:
                        cached[record["type"]] = deepcopy(record)
            fill_key = f"by_dex/{dex}/fills/perp/all/date={day}/fills.parquet"
            snapshot_prefix = f"by_dex/{dex}/snapshots/perp/date={day}/"
            fill = cached.get("fills")
            snap = cached.get("position_snapshot")
            if fill is None or fill["key"] != fill_key:
                fill = None
            if snap is None or not snap["key"].startswith(snapshot_prefix):
                snap = None
            if fill is None or snap is None:
                if conn is None:
                    conn = remote_connection()
                new_fill, new_snap = source_keys(day, dex=dex, snapshot_scope="dex")
                if fill is None:
                    new_fill["type"] = "fills"
                    new_fill["column_budget"] = column_budget(conn, new_fill["key"], CORE)
                    fill = new_fill
                if snap is None:
                    new_snap["type"] = "position_snapshot"
                    new_snap["column_budget"] = column_budget(conn, new_snap["key"], SNAP_FIELDS)
                    snap = new_snap
            for kind, entry, fields in (
                ("fills", fill, CORE),
                ("position_snapshot", snap, SNAP_FIELDS),
            ):
                if entry["type"] != kind:
                    raise ValueError("CACHED_OBJECT_TYPE_MISMATCH")
                if entry["column_budget"]["selected_columns"] != list(fields):
                    raise ValueError("CACHED_SCHEMA_PROJECTION_MISMATCH")
                if not entry.get("etag") or entry["bytes"] <= 0:
                    raise ValueError("CACHED_OBJECT_VERSION_MISSING")
                if kind in cached and entry == cached[kind]:
                    reused_count += 1
                projected += entry["column_budget"]["projected_compressed_bytes"]
                objects.append(entry)
        if projected > max_projected_bytes:
            raise ValueError("COST_CAP_ESTIMATE_EXCEEDED")
        days = [str(start + timedelta(days=i)) for i in range((end - start).days + 1)]
        manifest = {
            "schema": "reservoir_pilot_preflight_v1",
            "aws_billing_profile": AWS_PROFILE,
            "dex": dex,
            "snapshot_scope": "dex",
            "created_utc": datetime.now(UTC).isoformat(),
            "days": days,
            "scope": scope,
            "objects": objects,
            "total_projected_compressed_bytes": projected,
            "max_projected_compressed_bytes": max_projected_bytes,
            "metadata_objects_reused_from_sealed": reused_count,
            "source_first_known": False,
            "status": "PREFLIGHT_ONLY",
        }
        digest = exclusive_bytes(folder / "preflight.json", (jdump(manifest) + "\n").encode())
        return {
            "status": "PREFLIGHT_PROVISIONAL",
            "days": len(days),
            "wallet_count": len(wallets),
            "object_count": len(objects),
            "metadata_objects_reused": reused_count,
            "total_projected_compressed_MB": round(projected / 1e6, 3),
            "preflight_sha256": digest,
        }
    finally:
        if conn is not None:
            conn.close()


def run_one(
    mode: str,
    start: str,
    dex: str,
    max_batch_mb: int,
    cohort: str = "sealed_six",
) -> dict:
    token, first, last = window_for(start, cohort)
    target = root_for(token, dex, cohort)
    with private_lock(target):
        if mode == "preflight":
            path = target / "preflight.json"
            if path.exists():
                _, pre = verify_manifest(target)
                if pre.get("dex") != dex or pre.get("snapshot_scope") != "dex":
                    raise ValueError("PREEXISTING_BATCH_MISMATCH")
                if pre["days"][0] != start or pre["days"][-1] != str(last):
                    raise ValueError("PREEXISTING_BATCH_DATES_DRIFT")
                result = {
                    "status": "PREFLIGHT_REUSED_VERIFIED",
                    "projected_MB": round(pre["total_projected_compressed_bytes"] / 1e6, 3),
                }
            elif cohort == "monitored_plus_six":
                result = cached_metadata_preflight(
                    first, last, target, dex, max_batch_mb * 1_000_000
                )
            else:
                result = preflight(
                    first,
                    last,
                    target,
                    max_batch_mb * 1_000_000,
                    dex=dex,
                    snapshot_scope="dex",
                    cohort=cohort,
                )
        elif mode == "fetch":
            _, pre = verify_manifest(target)
            if pre.get("dex") != dex or pre.get("snapshot_scope") != "dex":
                raise ValueError("UNAPPROVED_ACQUISITION_SCOPE")
            result = fetch(target)
        elif mode == "report":
            result = report(target)
            # No private addresses in the output.
            result = {
                "source_rows": result["summary"].get("source_rows", 0),
                "source_only_ids": result["summary"].get("source_only_ids", 0),
                "local_matches": result["summary"].get("matched_ids", 0),
                "anchor": result["explicit_anchor_parity"],
                "status": "HISTORICAL_SOURCE_REPORT",
            }
        else:
            raise ValueError("INVALID_MODE")
    return {"window": token, "dex": dex, "cohort": cohort, "billing_profile": AWS_PROFILE, **result}


def resume_monitored(max_batch_mb: int, max_total_mb: int, max_fetch_batches: int) -> dict:
    """Converge cost-pinned 269-wallet data on one explicit user invocation.

    Preflight every object and enforce whole-history budget BEFORE S3 fill
    acquisition. Network failures leave immutable prior artifacts intact.
    This is synchronous; it does not start an unattended service.
    """
    cohort = "monitored_plus_six"
    for _token, first, _last in windows(cohort):
        for dex in sorted(ALLOWED_DEXES):
            run_one("preflight", str(first), dex, max_batch_mb, cohort)
    budget = budget_summary(max_total_mb, cohort)
    if budget["preflight_missing"] != 0:
        raise ValueError("SOURCE_OBJECT_PREFLIGHT_INCOMPLETE")
    # Cap each operation to bound a single SSH tool invocation; explicit 0
    # permits a full foreground run when the operator chooses it.
    completed = 0
    pending = 0
    for token, first, _last in windows(cohort):
        for dex in sorted(ALLOWED_DEXES):
            root = root_for(token, dex, cohort)
            _wallets, frozen = verify_manifest(root)
            missing = any(
                verify_artifact(
                    root / kind / f"day={day}",
                    next(
                        o["etag"]
                        for o in frozen["objects"]
                        if o["type"] == kind and f"date={day}/" in o["key"]
                    ),
                    frozen["scope"]["wallet_set_sha256"],
                )
                is None
                for day in frozen["days"]
                for kind in ("fills", "position_snapshot")
            )
            if not missing:
                continue
            pending += 1
            if max_fetch_batches and completed >= max_fetch_batches:
                continue
            run_one("fetch", str(first), dex, max_batch_mb, cohort)
            completed += 1
    after = budget_summary(max_total_mb, cohort)
    required_artifacts = (
        len(ALLOWED_DEXES) * 2 * sum((end - start).days + 1 for _, start, end in windows(cohort))
    )
    result = {
        "status": (
            "SOURCE_STAGED_ALL"
            if after["immutable_artifacts_verified"] == required_artifacts
            else "SOURCE_STAGED_PARTIAL"
        ),
        "requested_cohort": cohort,
        "wallet_count": 269,
        "new_batch_fetches": completed,
        "batches_with_missing_artifacts_before": pending,
        "verified_artifacts": after["immutable_artifacts_verified"],
        "required_artifacts": required_artifacts,
        "verified_fill_rows": after["verified_fill_rows_staged"],
        "projected_MB": budget["projected_MB"],
    }
    if result["status"] == "SOURCE_STAGED_ALL":
        from scripts.catalog_reservoir_six_portfolios import (  # noqa: PLC0415
            MONITORED_CATALOG_ROOT,
            build_index,
            write_catalog,
        )

        catalog = build_index(cohort)
        result["catalog_sha256"] = write_catalog(MONITORED_CATALOG_ROOT, catalog)
        result["status"] = "FULL_269_WALLET_SOURCE_CATALOG_VERIFIED"
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("preflight", "fetch", "report", "budget", "resume"))
    parser.add_argument("--start", default=None)
    parser.add_argument("--cohort", choices=ALLOWED_COHORTS, default="sealed_six")
    parser.add_argument("--dex", choices=sorted(ALLOWED_DEXES), default=None)
    parser.add_argument("--max-batch-mb", type=int, default=MAX_PER_BATCH_MB)
    parser.add_argument("--max-total-mb", type=int, default=MAX_TOTAL_MB)
    parser.add_argument("--max-fetch-batches", type=int, default=4)
    args = parser.parse_args()
    if args.max_batch_mb < 1 or args.max_batch_mb > 2500:
        raise ValueError("MAX_BATCH_BUDGET_OUT_OF_BOUNDS")
    if args.max_total_mb < 1 or args.max_total_mb > 50_000:
        raise ValueError("MAX_TOTAL_BUDGET_OUT_OF_BOUNDS")
    if not (0 <= args.max_fetch_batches <= 40):
        raise ValueError("MAX_FETCH_BATCHES_OUT_OF_BOUNDS")
    os.umask(0o077)
    if args.mode == "budget":
        outcome = budget_summary(args.max_total_mb, args.cohort)
    elif args.mode == "resume":
        if args.cohort != "monitored_plus_six":
            raise ValueError("RESUME_REQUIRES_MONITORED_COHORT")
        outcome = resume_monitored(args.max_batch_mb, args.max_total_mb, args.max_fetch_batches)
    else:
        if not args.start or not args.dex:
            raise ValueError("DEX_AND_APPROVED_START_REQUIRED")
        outcome = run_one(args.mode, args.start, args.dex, args.max_batch_mb, args.cohort)
    print(jdump(outcome))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        # AWS diagnostics, source credentials and addresses remain private.
        print(jdump({"status": "BLOCKED", "error_type": type(exc).__name__}), file=sys.stderr)
        raise SystemExit(2) from None
