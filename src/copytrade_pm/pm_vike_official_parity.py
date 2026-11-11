"""Independent bounded Hyperliquid REST complete-perp-book audit for Vike observations.

This is a per-DEX REST census, NOT an atomic exchange frame, not a
continuous source feed and never a V4 paper transition.
"""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
import json
import os
import stat
from hashlib import sha256
import re
from time import monotonic
from typing import Callable

from .pm_e4_prospective import _account_state, _dex_universe, _guarded_info
from .pm_vike_stream_canary import allowed_wallet

MAX_DEXS = 32
MAX_WALL_SECONDS = 30.0
MAX_PROVIDER_SKEW_MS = 30_000


def independent_official_census(
    address: str,
    *,
    info: Callable = _guarded_info,
    max_wall_seconds: float = MAX_WALL_SECONDS,
    max_provider_skew_ms: int = MAX_PROVIDER_SKEW_MS,
) -> dict:
    """Fetch every official perpetual DEX, reject a partial or skewed census.

    The all-DEX materialization is intentionally NOT submitted to
    PersistentAccount: independent non-atomic REST calls cannot masquerade as
    an original official allDexsClearinghouseState WebSocket frame.
    """
    wallet = allowed_wallet(address)
    if not 0 < max_wall_seconds <= MAX_WALL_SECONDS:
        raise ValueError("OFFICIAL_RECON_WALL_BUDGET_INVALID")
    if not 0 <= max_provider_skew_ms <= MAX_PROVIDER_SKEW_MS:
        raise ValueError("OFFICIAL_RECON_SKEW_BUDGET_INVALID")
    started = monotonic()
    catalog, raw_catalog, catalog_sha = info({"type": "perpDexs"})
    if not isinstance(raw_catalog, bytes) or sha256(raw_catalog).hexdigest() != catalog_sha:
        raise ValueError("OFFICIAL_RECON_CATALOG_HASH_INVALID")
    dexs = _dex_universe(catalog)
    if len(dexs) > MAX_DEXS:
        raise ValueError("OFFICIAL_RECON_DEX_LIMIT_EXCEEDED")
    states: list[list] = []
    stamps: dict[str, int] = {}
    hashes: dict[str, str] = {}
    for dex in sorted(dexs):
        if monotonic() - started > max_wall_seconds:
            raise ValueError("OFFICIAL_RECON_WALL_BUDGET_EXCEEDED")
        params = {"type": "clearinghouseState", "user": wallet}
        if dex != "default":
            params["dex"] = dex
        body, raw, actual_sha = info(params)
        if not isinstance(raw, bytes) or sha256(raw).hexdigest() != actual_sha:
            raise ValueError("OFFICIAL_RECON_RAW_HASH_INVALID")
        if not isinstance(body, dict):
            raise ValueError("OFFICIAL_RECON_STATE_NOT_OBJECT")
        timestamp = body.get("time")
        if type(timestamp) is not int or timestamp < 1_000_000_000_000:
            raise ValueError("OFFICIAL_RECON_PROVIDER_TIME_INVALID")
        stamps[dex] = timestamp
        hashes[dex] = actual_sha
        states.append(["" if dex == "default" else dex, body])
    completed = datetime.now(UTC).isoformat()
    if monotonic() - started > max_wall_seconds:
        raise ValueError("OFFICIAL_RECON_WALL_BUDGET_EXCEEDED")
    skew = max(stamps.values()) - min(stamps.values())
    if skew > max_provider_skew_ms:
        raise ValueError("OFFICIAL_RECON_NONATOMIC_SKEW_EXCEEDED")
    book = _account_state(
        {"user": wallet, "clearinghouseStates": states},
        wallet,
        expected_dexs=dexs,
    )
    return {
        "schema": "copytrade_independent_official_rest_perp_census_v1",
        "account_sha256": sha256(wallet.encode()).hexdigest(),
        "dex_catalog_sha256": catalog_sha,
        "dex_state_shas": hashes,
        "dex_provider_times_ms": stamps,
        "dex_count": len(dexs),
        "position_count": book["position_count"],
        "positions": book["positions"],
        "provider_time_skew_ms": skew,
        "completed_at": completed,
        "scope_parity": book["dex_catalog_parity_verified"],
        "source_kind": "OFFICIAL_NONATOMIC_REST_CENSUS",
        "continuous_observation_proven": False,
        "new_risk_eligible": False,
        "first_known_transition": None,
        "order_route": "NONE",
    }


def archive_independent_census(
    address: str,
    *,
    root: Path,
    info: Callable = _guarded_info,
) -> dict:
    """Persist original official response bytes and a manifest-last proof.

    Unfinished directories have no manifest and are never admitted. This
    archive is a read-only research receipt, not a financial source journal.
    """
    if root.is_symlink() or any(parent.is_symlink() for parent in root.parents):
        raise ValueError("OFFICIAL_RECON_ARCHIVE_SYMLINK_INVALID")
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    if stat.S_IMODE(root.stat().st_mode) != 0o700:
        raise PermissionError("OFFICIAL_RECON_ARCHIVE_NOT_PRIVATE")
    collected: list[tuple[str, bytes, str]] = []

    def captured(request: dict):
        value, raw, sha = info(request)
        label = (
            request.get("dex", "default") if request["type"] == "clearinghouseState" else "catalog"
        )
        collected.append((label, raw, sha))
        return value, raw, sha

    report = independent_official_census(address, info=captured)
    if len(collected) != report["dex_count"] + 1:
        raise ValueError("OFFICIAL_RECON_ARCHIVE_RESPONSE_COUNT_INVALID")
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    directory = root / ("census-" + report["account_sha256"][:16] + "-" + stamp)
    directory.mkdir(mode=0o700, exist_ok=False)
    root_fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(root_fd)
    finally:
        os.close(root_fd)
    files = []
    for label, raw, digest in collected:
        if not isinstance(raw, bytes) or sha256(raw).hexdigest() != digest:
            raise ValueError("OFFICIAL_RECON_ARCHIVE_ORIGINAL_DRIFT")
        file_name = "raw-" + label + ".json"
        if (
            not label
            or not label.isascii()
            or not all(char.isalnum() or char in "-_" for char in label)
        ):
            raise ValueError("OFFICIAL_RECON_ARCHIVE_LABEL_INVALID")
        with os.fdopen(
            os.open(directory / file_name, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600),
            "wb",
        ) as handle:
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())
        files.append({"name": file_name, "sha256": digest, "size_bytes": len(raw)})
    manifest = {
        "schema": "copytrade_independent_official_rest_archive_v1",
        "census": report,
        "original_files": files,
        "continuous_coverage_verified": False,
        "v4_paper_source_eligible": False,
        "order_route": "NONE",
    }
    serialized = (json.dumps(manifest, sort_keys=True, separators=(",", ":")) + "\n").encode()
    with os.fdopen(
        os.open(directory / "manifest.json", os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600),
        "wb",
    ) as handle:
        handle.write(serialized)
        handle.flush()
        os.fsync(handle.fileno())
    directory_fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)
    return {
        "archive": str(directory),
        "manifest_sha256": sha256(serialized).hexdigest(),
        "account_sha256": report["account_sha256"],
        "dex_count": report["dex_count"],
        "position_count": report["position_count"],
        "provider_time_skew_ms": report["provider_time_skew_ms"],
        "continuous_coverage_verified": False,
        "v4_paper_source_eligible": False,
    }


def audit_selected_campaign(
    *,
    registry_db: Path,
    manifest: Path,
    manifest_sha256: str,
    root: Path,
    at: str,
    workers: int = 3,
    info: Callable = _guarded_info,
) -> dict:
    """Archive a simultaneous bounded 14-parent cohort audit, NOT continuity.

    The lower-level per-account census validates the full official DEX scope.
    Failures are explicit and do not admit any subset to new risk.
    """
    from .pm_v4_sixteen_scenarios import load_campaign

    if not 1 <= workers <= 3:
        raise ValueError("OFFICIAL_RECON_WORKER_BUDGET_INVALID")
    campaign = load_campaign(
        manifest=manifest,
        registry_db=registry_db,
        at=at,
        expected_sha256=manifest_sha256,
    )
    if len(campaign.parents) != 14:
        raise ValueError("OFFICIAL_RECON_CAMPAIGN_NOT_14")
    results = {}
    with ThreadPoolExecutor(max_workers=workers) as pool:
        tasks = {
            pool.submit(archive_independent_census, address, root=root, info=info): alias
            for alias, address in campaign.parents.items()
        }
        for task in as_completed(tasks):
            alias = tasks[task]
            try:
                receipt = task.result()
                results[alias] = {"status": "OFFICIAL_REST_CENSUS_VERIFIED", **receipt}
            except Exception as exc:
                results[alias] = {
                    "status": "BLOCKED_OFFICIAL_REST_CENSUS",
                    "reason_class": type(exc).__name__,
                    "first_known_transition": None,
                    "v4_paper_source_eligible": False,
                }
    ready = sum(row["status"] == "OFFICIAL_REST_CENSUS_VERIFIED" for row in results.values())
    return {
        "schema": "copytrade_vike_official_campaign_snapshot_audit_v1",
        "selected_parent_count": len(campaign.parents),
        "independent_census_verified": ready,
        "continuous_coverage_verified": 0,
        "paper_new_risk_eligible": 0,
        "accounts": dict(sorted(results.items())),
        "status": "REST_CENSUS_14_OF_14_NOT_CONTINUITY"
        if ready == 14
        else "BLOCKED_PARTIAL_REST_CENSUS",
        "order_route": "NONE",
    }


def check_single_vike_event_against_official(
    event: dict,
    census: dict,
    *,
    max_delay_ms: int = 120_000,
) -> dict:
    """A single event can be *consistent*, never establish whole-book history.

    Concurrent intervening trades make mismatch an unresolved source
    discrepancy, not evidence of vendor fraud or proof of an exit.
    """
    from .pm_vike_position_observations import validate

    account_sha = census.get("account_sha256")
    wallet = (event.get("subject") or {}).get("wallet")
    wallet = allowed_wallet(wallet)
    eid, _, _, symbol, after = validate(event, (wallet,))
    if sha256(wallet.encode()).hexdigest() != account_sha:
        raise ValueError("OFFICIAL_RECON_EVENT_ACCOUNT_MISMATCH")
    if not isinstance(max_delay_ms, int) or not 0 <= max_delay_ms <= 120_000:
        raise ValueError("OFFICIAL_RECON_EVENT_DELAY_BUDGET_INVALID")
    data = event["data"]
    dex = data["dex"]
    if dex == "HL":
        key = "hyperliquid/mainnet:perp:default/" + symbol
        dex_id = "default"
    else:
        if not re.fullmatch(r"[A-Za-z0-9_-]+", dex):
            raise ValueError("OFFICIAL_RECON_EVENT_DEX_INVALID")
        key = "hyperliquid/mainnet:perp:" + dex + "/" + symbol.split(":", 1)[1]
        dex_id = dex
    event_ts = int(datetime.fromisoformat(event["ts"].replace("Z", "+00:00")).timestamp() * 1000)
    provider_time = census["dex_provider_times_ms"].get(dex_id)
    if provider_time is None or not isinstance(provider_time, int):
        raise ValueError("OFFICIAL_RECON_EVENT_DEX_NOT_IN_CENSUS")
    difference = provider_time - event_ts
    if difference < 0 or difference > max_delay_ms:
        status = "INDETERMINATE_TEMPORAL_SCOPE"
    elif str(census["positions"].get(key, "0")) == str(after):
        status = "CONSISTENT_SINGLE_EVENT_NOT_COMPLETE_PROOF"
    else:
        from decimal import Decimal

        status = (
            "CONSISTENT_SINGLE_EVENT_NOT_COMPLETE_PROOF"
            if Decimal(str(census["positions"].get(key, "0"))) == Decimal(after)
            else "DIVERGENT_REQUIRES_CAUSAL_FILL_RECONCILIATION"
        )
    return {
        "event_id_sha256": sha256(eid.encode()).hexdigest(),
        "market": key,
        "status": status,
        "provider_delta_ms": difference,
        "whole_book_complete_history_proven": False,
        "paper_eligible": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registry-db", type=Path, required=True)
    parser.add_argument("--campaign-manifest", type=Path, required=True)
    parser.add_argument("--campaign-sha256", required=True)
    parser.add_argument("--archive-root", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=3)
    args = parser.parse_args()
    os.umask(0o077)
    report = audit_selected_campaign(
        registry_db=args.registry_db,
        manifest=args.campaign_manifest,
        manifest_sha256=args.campaign_sha256,
        root=args.archive_root,
        at=datetime.now(UTC).isoformat(),
        workers=args.workers,
    )
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    report_path = args.archive_root / ("campaign-" + stamp + ".json")
    encoded = (json.dumps(report, sort_keys=True, indent=2) + "\n").encode()
    with os.fdopen(
        os.open(report_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600),
        "wb",
    ) as handle:
        handle.write(encoded)
        handle.flush()
        os.fsync(handle.fileno())
    print(
        json.dumps(
            {
                "status": report["status"],
                "independent_census_verified": report["independent_census_verified"],
                "continuous_coverage_verified": 0,
                "paper_new_risk_eligible": 0,
                "report_path": str(report_path),
                "report_sha256": sha256(encoded).hexdigest(),
            },
            sort_keys=True,
        )
    )
    return 0 if report["independent_census_verified"] == 14 else 2


if __name__ == "__main__":
    raise SystemExit(main())
