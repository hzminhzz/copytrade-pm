"""Bounded native read-only capacity capture. Never installs a source or policy."""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from hashlib import sha256
import json
from math import ceil
from pathlib import Path
import subprocess
from threading import Lock
from time import monotonic, sleep
from urllib.error import HTTPError

from .pm03_account import digest
from .pm_checkpoint_source import (
    GRID_MS,
    CheckpointSample,
    CheckpointScope,
    collect_checkpoint,
    utc_milliseconds,
)
from .pm_e4_prospective import dex_universe, guarded_info
from .pm_forward_release_candidate import sync_directory, write_once
from .pm_source_campaign_roster import load_campaign
from .pm_wire_evidence import publish_wire, read_wire

RATE_SOURCE = (
    "https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api/rate-limits-and-user-limits"
)


def distribution(values):
    values = sorted(values)
    if not values:
        return None
    return {
        "count": len(values),
        "min": values[0],
        "max": values[-1],
        "p50": values[max(0, ceil(len(values) * 0.5) - 1)],
        "p95": values[max(0, ceil(len(values) * 0.95) - 1)],
    }


def summarize(
    samples, *, expected_accounts, revision, requests, roster_sha, rate_weight_per_second, mode
):
    complete = [
        sample
        for sample in samples
        if sample.catalog is not None
        and tuple(r.dex for r in sample.receipts) == sample.scope.dexes
        and all(r.state_ms is not None and r.position_count is not None for r in sample.receipts)
        and all(reason == "CHECKPOINT_UNQUALIFIED_LIMITS" for reason in sample.reasons)
    ]
    # Fixture-qualified candidates also contribute descriptive measurements.
    complete += [
        sample for sample in samples if sample.kind == "COMPLETE" and sample not in complete
    ]
    ages, skews, acquisition = [], [], []
    for sample in samples:
        stamps = [r.state_ms for r in sample.receipts if r.state_ms is not None]
        acquisition.append(sample.validated_ms - sample.started_ms)
        if stamps:
            ages.append(sample.validated_ms - min(stamps))
            skews.append(max(stamps) - min(stamps))
    observed = {
        "request_latency_ms": distribution(
            [r["received_ms"] - r["requested_ms"] for r in requests]
        ),
        "acquisition_ms": distribution(acquisition),
        "provider_age_at_validation_ms": distribution(ages),
        "per_dex_skew_ms": distribution(skews),
    }
    dimensions = {
        "freshness": {
            "observed": observed["provider_age_at_validation_ms"],
            "qualified": False,
            "blocker": "No native timestamp guarantee or prospective tail validation",
        },
        "skew": {
            "observed": observed["per_dex_skew_ms"],
            "qualified": False,
            "blocker": "Short sample does not establish cross-DEX tail bound",
        },
        "grace": {
            "observed": observed["acquisition_ms"],
            "qualified": False,
            "blocker": "Capacity run is not an aligned prospective deadline cohort",
        },
        "throughput": {
            "observed_weight": sum(r["weight"] for r in requests),
            "qualified": False,
            "blocker": "Other shared-IP traffic and long-run tails are not observed",
        },
        "source_gap": {"qualified": False, "blocker": "No multi-day continuity evidence"},
    }
    return {
        "schema": "cwsa_native_capacity_v1",
        "revision": revision,
        "mode": mode,
        "roster_sha": roster_sha,
        "expected_accounts": expected_accounts,
        "sample_count": len(samples),
        "complete_scope_count": len(complete),
        "request_count": len(requests),
        "observed": observed,
        "dimensions": dimensions,
        "rate_weight_per_second": rate_weight_per_second,
        "documented_ip_weight_per_minute": 1200,
        "rate_documentation": RATE_SOURCE,
        "shared_ip_headroom": "UNKNOWN",
        "errors": {
            code: sum(r["error"] == code for r in requests)
            for code in sorted({r["error"] for r in requests if r["error"]})
        },
        "disposition": "UNKNOWN" if complete else "NO_GO",
        "order_route": "NONE",
        "trading_authorized": False,
    }


class CaptureTransport:
    """Explicit experiment pacing, not a freshness SLA or replacement scheduler."""

    def __init__(self, weight_per_second):
        if not 0 < weight_per_second <= 8:
            raise ValueError("CAPACITY_PACING_OUTSIDE_EXPERIMENT_BUDGET")
        self.rate = weight_per_second
        self.lock = Lock()
        self.next = monotonic()
        self.requests = []

    def __call__(self, request):
        weight = 2 if request["type"] == "clearinghouseState" else 20
        with self.lock:
            due = self.next
            self.next = max(monotonic(), due) + weight / self.rate
        sleep(max(0, due - monotonic()))
        started = utc_milliseconds()
        error = None
        try:
            return guarded_info(request)
        except Exception as exc:
            error = f"HTTP_{exc.code}" if isinstance(exc, HTTPError) else type(exc).__name__
            raise
        finally:
            with self.lock:
                self.requests.append(
                    {
                        "kind": request["type"],
                        "weight": weight,
                        "requested_ms": started,
                        "received_ms": utc_milliseconds(),
                        "error": error,
                    }
                )


def capture(*, root, registry_db, manifest, mode, workers, weight_per_second):
    root = Path(root)
    root.mkdir(mode=0o700, parents=True, exist_ok=False)
    if root.is_symlink() or root.stat().st_mode & 0o077:
        raise ValueError("CAPACITY_EVIDENCE_NOT_PRIVATE")
    campaign = load_campaign(
        manifest=manifest, registry_db=registry_db, at=datetime.now(UTC).isoformat()
    )
    revision = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    dirty = subprocess.check_output(["git", "status", "--porcelain"], text=True).strip()
    if dirty:
        raise ValueError("CAPACITY_REQUIRES_EXACT_CLEAN_REVISION")
    transport = CaptureTransport(weight_per_second)
    _body, raw, raw_sha = transport({"type": "perpDexs"})
    if sha256(raw).hexdigest() != raw_sha:
        raise ValueError("CAPACITY_CATALOG_HASH")
    publish_wire(root / "paper-events.sqlite3", raw.decode(), raw_sha)
    dexes = tuple(sorted(dex_universe(json.loads(raw))))
    roster_sha = digest(
        {alias: sha256(address.encode()).hexdigest() for alias, address in campaign.parents.items()}
    )
    started = utc_milliseconds()
    boundary = started // GRID_MS * GRID_MS

    def collect(item):
        alias, address = item
        scope = CheckpointScope(
            source_id=alias,
            account_sha=sha256(address.encode()).hexdigest(),
            generation=digest(["hyperliquid/mainnet:perp", address, dexes]),
            selection_sha=roster_sha,
            dexes=dexes,
        )
        return collect_checkpoint(
            scope,
            address,
            checkpoint_ms=boundary,
            limits=None,
            evidence_root=root,
            info=transport,
        )

    with ThreadPoolExecutor(max_workers=workers) as pool:
        samples = list(pool.map(collect, sorted(campaign.parents.items())))
    report = summarize(
        samples,
        expected_accounts=len(campaign.parents),
        revision=revision,
        requests=transport.requests,
        roster_sha=roster_sha,
        rate_weight_per_second=weight_per_second,
        mode=mode,
    )
    report.update(
        started_ms=started,
        finished_ms=utc_milliseconds(),
        checkpoint_ms=boundary,
        scope_dexes=dexes,
        catalog_sha=raw_sha,
        workers=workers,
        campaign=campaign.public_status(),
    )
    evidence = {
        "schema": "cwsa_capacity_evidence_v1",
        "report": report,
        "samples": [s.model_dump(mode="json") for s in samples],
        "requests": transport.requests,
    }
    body = json.dumps(evidence, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    write_once(root / "capture.json", body)
    receipt = {"capture_sha": sha256(body).hexdigest(), "report": report}
    write_once(root / "receipt.json", json.dumps(receipt, sort_keys=True).encode())
    sync_directory(root)
    return receipt


def verify_capture(root):
    root = Path(root)
    body = (root / "capture.json").read_bytes()
    receipt = json.loads((root / "receipt.json").read_bytes())
    if sha256(body).hexdigest() != receipt["capture_sha"]:
        raise ValueError("CAPACITY_CAPTURE_HASH")
    evidence = json.loads(body)
    samples = [CheckpointSample.model_validate_json(json.dumps(s)) for s in evidence["samples"]]
    for sample in samples:
        for r in ((sample.catalog,) if sample.catalog else ()) + sample.receipts:
            read_wire(root / "paper-events.sqlite3", r.raw_sha)
    report = evidence["report"]
    reproduced = summarize(
        samples,
        expected_accounts=report["expected_accounts"],
        revision=report["revision"],
        requests=evidence["requests"],
        roster_sha=report["roster_sha"],
        rate_weight_per_second=report["rate_weight_per_second"],
        mode=report["mode"],
    )
    if any(report[k] != v for k, v in reproduced.items()) or receipt["report"] != report:
        raise ValueError("CAPACITY_REPORT_NOT_REPRODUCIBLE")
    return receipt


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--registry", type=Path)
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--mode", choices=("burst", "restart", "constrained"), default="burst")
    parser.add_argument("--workers", type=int, choices=(1, 2, 3), default=3)
    parser.add_argument("--weight-per-second", type=float, default=8)
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args(argv)
    if args.verify:
        result = verify_capture(args.root)
    else:
        if args.registry is None or args.manifest is None:
            parser.error("--registry and --manifest are required for capture")
        result = capture(
            root=args.root,
            registry_db=args.registry,
            manifest=args.manifest,
            mode=args.mode,
            workers=args.workers,
            weight_per_second=args.weight_per_second,
        )
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
