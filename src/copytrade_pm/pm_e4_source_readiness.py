"""Audit read-only capture bytes, identity, clocks and coverage independently.

Integrity is distinct from continuity, capital reconciliation and qualification.
A currently open or interrupted generation is never treated as completed evidence.
"""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
from hashlib import sha256
import json
from pathlib import Path
import re

from .pm_e4_prospective import SUBSCRIPTIONS, account_state, dex_universe, subaccount_roster
from .pm_portfolio_e0 import PORTFOLIOS

PORTFOLIO_PODS = PORTFOLIOS


def _time(value: object) -> datetime:
    if not isinstance(value, str):
        raise ValueError("INVALID_TIME")
    stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if stamp.tzinfo is None or stamp.utcoffset() is None:
        raise ValueError("NAIVE_TIME")
    return stamp.astimezone(UTC)


def _read(path: Path, errors: list[str]) -> bytes:
    if path.is_symlink() or not path.is_file():
        raise ValueError("UNSAFE_OR_MISSING_FILE")
    if path.stat().st_mode & 0o077:
        errors.append("NON_PRIVATE_FILE:" + path.name)
    return path.read_bytes()


def _object(raw: bytes) -> dict:
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise ValueError("NON_OBJECT")
    return value


def _generation(directory: Path, portfolio: str) -> dict:
    errors: list[str] = []
    result = {
        "generation": directory.name,
        "verified_frame_count": 0,
        "errors": errors,
        "status": "BLOCKED",
    }
    for path in (directory, directory / "frames", directory / "metadata", directory / "discovery"):
        if path.is_symlink():
            errors.append("SYMLINK_DIRECTORY")
            return result
        if path.exists() and path.stat().st_mode & 0o077:
            errors.append("NON_PRIVATE_DIRECTORY:" + path.name)
    try:
        raw_report = _read(directory / "session-report.json", errors)
        report = _object(raw_report)
        result["session_report_sha256"] = sha256(raw_report).hexdigest()
    except OSError, ValueError:
        errors.append("MISSING_OR_INVALID_REPORT")
        return result
    started = finished = None
    try:
        started, finished = _time(report["started_at"]), _time(report["finished_at"])
        if finished < started:
            raise ValueError("REVERSED_SESSION")
        result.update(started_at=started.isoformat(), finished_at=finished.isoformat())
    except ValueError, KeyError, TypeError:
        errors.append("INVALID_SESSION_TIMESTAMPS")
    if report.get("schema") != "e4_live_readonly_stream_session_v2":
        errors.append("LEGACY_OR_UNKNOWN_CAPTURE_CONTRACT")
    if report.get("errors") != []:
        errors.append("SOURCE_SESSION_ERRORS")
    if report.get("disconnect_reason") != "BOUNDED_SESSION_ROTATION":
        errors.append("INCOMPLETE_SESSION")
    if report.get("trading_authorized") is not False:
        errors.append("INVALID_READ_ONLY_CONTRACT")
    subjects = report.get("subjects")
    if not isinstance(subjects, dict) or any(
        not isinstance(k, str) or not isinstance(v, str) or not re.fullmatch("[0-9a-f]{64}", v)
        for k, v in subjects.items()
    ):
        subjects = {}
        errors.append("INVALID_ACCOUNT_IDENTITIES")
    if len(set(subjects.values())) != len(subjects):
        errors.append("DUPLICATE_ACCOUNT_IDENTITIES")
    by_hash = {v: k for k, v in subjects.items()}
    dexs = None
    try:
        catalog = _read(directory / "discovery" / "dex_catalog.json", errors)
        if sha256(catalog).hexdigest() != report["dex_catalog_sha256"]:
            raise ValueError("DEX_HASH_MISMATCH")
        dexs = dex_universe(json.loads(catalog))
        discovery_clock = report["discovery_receipts"]["dex_catalog.json"]
        if (
            discovery_clock["sha256"] != report["dex_catalog_sha256"]
            or started is None
            or finished is None
            or not started
            <= _time(discovery_clock["requested_at"])
            <= _time(discovery_clock["received_at"])
            <= finished
        ):
            raise ValueError("DEX_DISCOVERY_CLOCK_OR_HASH_MISMATCH")
    except OSError, ValueError, KeyError, TypeError:
        errors.append("INVALID_DEX_DISCOVERY")
    snapshots, addresses, acknowledgments = {}, {}, set()
    source_clock_unknown = 0
    last_receipt = None
    seen_filenames: set[str] = set()
    for meta_file in sorted((directory / "metadata").glob("*.json")):
        try:
            meta = _object(_read(meta_file, errors))
            filename = meta["filename"]
            if (
                not isinstance(filename, str)
                or Path(filename).name != filename
                or filename in seen_filenames
            ):
                raise ValueError("UNSAFE_OR_DUPLICATE_FILENAME")
            seen_filenames.add(filename)
            raw = _read(directory / "frames" / filename, errors)
            if sha256(raw).hexdigest() != meta["source_raw_sha256"]:
                raise ValueError("RAW_HASH_MISMATCH")
            at = _time(meta["locally_received_at"])
            frame = _object(raw)
            channel = frame.get("channel")
            if channel != meta["channel"]:
                raise ValueError("CHANNEL_MISMATCH")
            result["verified_frame_count"] += 1
            # Count verified bytes independently from causal or coverage acceptance.
            if started is None or finished is None or not started <= at <= finished:
                errors.append("RECEIPT_OUTSIDE_SESSION")
            if last_receipt is not None and at < last_receipt:
                errors.append("NON_MONOTONIC_RECEIPT_CLOCK")
            last_receipt = at
            data = frame.get("data")
            if channel == "subscriptionResponse" and isinstance(data, dict):
                subscription = data.get("subscription", {})
                identity = sha256(str(subscription.get("user", "")).lower().encode()).hexdigest()
                acknowledgments.add((by_hash.get(identity), subscription.get("type")))
            if channel != "allDexsClearinghouseState":
                continue
            if not isinstance(data, dict):
                raise ValueError("INVALID_ACCOUNT_FRAME")
            address = str(data.get("user", "")).lower()
            subject = by_hash.get(sha256(address.encode()).hexdigest())
            if subject is None or subject != meta.get("subject"):
                raise ValueError("ACCOUNT_IDENTITY_MISMATCH")
            parsed = account_state(data, address, dexs)
            if dexs is None:
                raise ValueError("UNVERIFIED_DEX_SCOPE")
            addresses[subject] = address
            for state in parsed["per_dex"]:
                clock = state["state_at"]
                if not isinstance(clock, (int, float)) or isinstance(clock, bool) or clock <= 0:
                    source_clock_unknown += 1
                elif datetime.fromtimestamp(clock / 1000, UTC) > at:
                    errors.append("SOURCE_CLOCK_AFTER_RECEIPT")
                elif (at - datetime.fromtimestamp(clock / 1000, UTC)).total_seconds() > 300:
                    errors.append("STALE_SOURCE_STATE_AT_RECEIPT")
            snapshots[subject] = {
                "locally_received_at": at.isoformat(),
                "nonzero_positions": parsed["position_count"],
                "perp_dexs_seen": parsed["observed_dex_count"],
                "official_dex_catalog_parity": True,
                "last_frame_sha256": meta["source_raw_sha256"],
            }
        except OSError, ValueError, KeyError, TypeError, ArithmeticError, OverflowError:
            errors.append("INVALID_FRAME:" + meta_file.name)
    checked = result["verified_frame_count"]
    if checked == 0:
        errors.append("NO_VERIFIED_FRAMES")
    if type(report.get("frames_stored")) is not int or checked != report["frames_stored"]:
        errors.append("FRAME_COUNT_MISMATCH")
    if len(list((directory / "frames").glob("*.json"))) != checked:
        errors.append("RAW_FRAME_COUNT_MISMATCH")
    expected = set(PORTFOLIOS[portfolio])
    counts = report.get("subaccount_counts", {})
    receipts = report.get("discovery_receipts", {})
    if not isinstance(counts, dict) or not isinstance(receipts, dict):
        counts, receipts = {}, {}
        errors.append("INVALID_DISCOVERY_METADATA")
    for alias in PORTFOLIOS[portfolio]:
        try:
            filename = alias + "-subaccounts.json"
            raw = _read(directory / "discovery" / filename, errors)
            metadata = receipts[filename]
            parent = metadata.get("request", {}).get("user") or addresses.get(alias)
            if (
                not isinstance(parent, str)
                or sha256(parent.lower().encode()).hexdigest() != subjects[alias]
            ):
                raise ValueError("CENSUS_REQUEST_IDENTITY_MISMATCH")
            if sha256(raw).hexdigest() != metadata["sha256"]:
                raise ValueError("CENSUS_HASH_MISMATCH")
            if (
                started is None
                or finished is None
                or not (
                    started
                    <= _time(metadata["requested_at"])
                    <= _time(metadata["received_at"])
                    <= finished
                )
            ):
                raise ValueError("CENSUS_CLOCK_MISMATCH")
            members = subaccount_roster(json.loads(raw), parent)
            if type(counts.get(alias)) is not int or counts[alias] != len(members):
                raise ValueError("CENSUS_COUNT_MISMATCH")
            for index, address in enumerate(members):
                code = f"{alias}-sub{index:02d}"
                expected.add(code)
                if sha256(address.lower().encode()).hexdigest() != subjects.get(code):
                    raise ValueError("SUBACCOUNT_IDENTITY_MISMATCH")
        except OSError, ValueError, KeyError, TypeError:
            errors.append("UNVERIFIED_SUBACCOUNT_CENSUS:" + alias)
    scope = report.get("observed_scope_subjects", sorted(subjects))
    if (
        not isinstance(scope, list)
        or any(not isinstance(x, str) for x in scope)
        or len(scope) != len(set(scope))
        or not 0 < len(scope) <= 10
    ):
        scope = []
        errors.append("INVALID_OR_OVER_LIMIT_OBSERVATION_SCOPE")
    if (
        set(subjects) != expected
        or not set(scope).issubset(expected)
        or set(snapshots) != set(scope)
    ):
        errors.append("MISSING_OR_EXTRA_ACCOUNT_SNAPSHOTS")
    if report.get("snapshots") != snapshots:
        errors.append("SNAPSHOT_CLAIMS_NOT_BOUND_TO_RAW_FRAMES")
    if acknowledgments != {(alias, kind) for alias in scope for kind in SUBSCRIPTIONS}:
        errors.append("INCOMPLETE_SUBSCRIPTION_ACKNOWLEDGMENTS")
    result["observed_accounts"] = len(snapshots)
    result["observed_subjects"] = sorted(snapshots)
    result["discovered_subjects"] = sorted(subjects)
    result["unobserved_subjects"] = sorted(expected - set(snapshots))
    result["complete_account_scope_observed"] = set(snapshots) == expected
    result["source_state_clocks_unknown"] = source_clock_unknown
    result["errors"] = sorted(set(errors))
    result["status"] = "OBSERVED_BOUNDED_ONLY" if not errors else "BLOCKED"
    return result


def audit(store: Path, portfolio: str, *, as_of: datetime | None = None) -> dict:
    if portfolio not in PORTFOLIOS:
        raise ValueError("UNKNOWN_PORTFOLIO")
    at = as_of or datetime.now(UTC)
    if at.tzinfo is None:
        raise ValueError("NAIVE_AUDIT_TIME")
    results = [_generation(p, portfolio) for p in sorted(store.glob("gE4*")) if p.is_dir()]
    gaps = []
    previous = None
    for row in results:
        if "finished_at" not in row:
            continue
        start, finish = _time(row["started_at"]), _time(row["finished_at"])
        if previous is not None and start != previous:
            gaps.append(
                {
                    "from": previous.isoformat(),
                    "to": start.isoformat(),
                    "seconds": (start - previous).total_seconds(),
                    "kind": "GAP" if start > previous else "OVERLAP_REQUIRES_DEDUPLICATION",
                }
            )
        previous = finish
    complete = [row for row in results if "finished_at" in row]
    latest = max(complete, key=lambda row: _time(row["finished_at"])) if complete else None
    age = (at - _time(latest["finished_at"])).total_seconds() if latest else None
    recent_subjects = set().union(
        *(
            set(row["observed_subjects"])
            for row in complete
            if not row["errors"] and 0 <= (at - _time(row["finished_at"])).total_seconds() <= 1200
        )
    )
    expected_subjects = set(latest.get("discovered_subjects", [])) if latest else set()
    private = store.exists() and not store.is_symlink() and not (store.stat().st_mode & 0o077)
    return {
        "schema": "e4_independent_source_integrity_v2",
        "portfolio": portfolio,
        "audited_at": at.isoformat(),
        "store_private": private,
        "prospective_generations": results,
        "observed_session_gaps": gaps,
        "all_generations_integrity_pass": private
        and bool(results)
        and all(not r["errors"] for r in results),
        "latest_complete_generation_integrity_pass": private
        and latest is not None
        and not latest["errors"],
        "latest_complete_generation": latest["generation"] if latest else None,
        "latest_complete_age_seconds": age,
        "recent_completed_capture": age is not None and 0 <= age <= 1200,
        "recent_discovered_accounts_observed": bool(expected_subjects)
        and expected_subjects <= recent_subjects,
        "recent_accounts_observed": len(recent_subjects),
        "continuous_account_book_qualified": False,
        "equity_collateral_funding_transfers_reconciled": False,
        "historical_q3_first_known_reconstructed": False,
        "scientifically_qualified": False,
        "trading_authorized": False,
    }


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--store", type=Path, required=True)
    p.add_argument("--portfolio", choices=tuple(PORTFOLIOS), required=True)
    args = p.parse_args()
    print(json.dumps(audit(args.store, args.portfolio), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
