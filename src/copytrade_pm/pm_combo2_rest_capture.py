"""Bounded read-only Hyperliquid account-scope evidence for Combo 2.

This module uses ONLY informational /info calls. It does not subscribe to
WebSockets or have any order/exchange endpoint. It does not compute follower
equity from unrelated account-values: unified/portfolio accounts remain
UNKNOWN until a separately verified valuation contract exists.
"""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
import uuid
from hashlib import sha256
import json
from pathlib import Path
import re
from time import sleep
from typing import Any, Callable
from urllib.request import Request, urlopen

from .pm_e4_prospective import _dex_universe, _subaccount_roster
from .pm_hyperx_account_triage import _write_immutable_private
from .pm_hyperx_gap_recovery import _private_dir
from .pm_sources import _resolved_identity

INFO = "https://api.hyperliquid.xyz/info"
READ_ONLY_TYPES = frozenset(
    {"perpDexs", "subAccounts", "userAbstraction", "spotClearinghouseState", "clearinghouseState"}
)
MANAGERS = ("W028", "CA-008", "W015")
MAX_SUBJECTS = 10
MAX_DEXS = 20
MAX_CALLS = 180
ADDRESS = re.compile(r"0x[a-f0-9]{40}", re.I)


def _canonical(data: Any) -> bytes:
    return (
        json.dumps(data, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n"
    ).encode()


def read_info(query: dict) -> tuple[Any, bytes]:
    """Fixed informational-only POST; there is NO order mutation transport."""
    if not isinstance(query, dict) or query.get("type") not in READ_ONLY_TYPES:
        raise PermissionError("ONLY_HYPERLIQUID_INFO_READS_ALLOWED")
    if query["type"] == "perpDexs":
        if set(query) != {"type"}:
            raise ValueError("INVALID_INFO_CATALOG_QUERY")
    elif (
        set(query) - {"type", "user", "dex"}
        or not isinstance(query.get("user"), str)
        or not ADDRESS.fullmatch(query["user"])
        or (query["type"] != "clearinghouseState" and "dex" in query)
    ):
        raise ValueError("INVALID_INFO_ACCOUNT_QUERY")
    request = Request(
        INFO,
        data=_canonical(query),
        headers={
            "Content-Type": "application/json",
            "User-Agent": "OpenAI File Downloader, XaiImageApiFetch/1.0",
        },
    )
    with urlopen(request, timeout=18) as response:
        raw = response.read(3_000_001)
    if len(raw) > 3_000_000:
        raise ValueError("INFO_RESPONSE_TOO_LARGE")
    return json.loads(raw), raw


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _private_generation(path: Path) -> None:
    if path.exists() or path.is_symlink():
        raise ValueError("IMMUTABLE_CAPTURE_GENERATION_EXISTS")
    _private_dir(path)
    if path.stat().st_mode & 0o077:
        raise ValueError("CAPTURE_DIR_NOT_PRIVATE")


def collect(
    root: Path,
    generation: Path,
    *,
    fetch: Callable[[dict], tuple[Any, bytes]] = read_info,
    sleep_between: float = 0.15,
) -> dict:
    """One 10-account bounded sweep. The sequential REST census is NOT atomic."""
    if not 0 <= sleep_between <= 2:
        raise ValueError("INVALID_REST_PACING")
    identities = _resolved_identity(root)
    if any(alias not in identities for alias in MANAGERS):
        raise ValueError("COMBO2_SOURCE_IDENTITY_UNKNOWN")
    _private_generation(generation)
    report: dict[str, Any] = {
        "schema": "combo2_rest_account_capture_v1",
        "started_at": _now(),
        "route": "HYPERLIQUID_READ_ONLY_POST_INFO",
        "network_order_mutations": 0,
        "all_accounts_coherent_at_one_instant": False,
        "follower_source_equity_verified": False,
        "paper_fills_created": 0,
        "managers": {},
        "subjects": {},
        "errors": [],
        "request_count": 0,
    }

    def record(tag: str, query: dict) -> Any:
        if report["request_count"] >= MAX_CALLS:
            raise ValueError("SOURCE_REST_MAX_CALLS")
        if query["type"] not in READ_ONLY_TYPES:
            raise PermissionError("NETWORK_ORDER_REQUEST_PROHIBITED")
        requested_at = _now()
        report["request_count"] += 1
        data, raw = fetch(query)
        received_at = _now()
        sha = sha256(raw).hexdigest()
        _write_immutable_private(generation / "raw" / f"{tag}.json", raw)
        _write_immutable_private(
            generation / "metadata" / f"{tag}.json",
            _canonical(
                {
                    "kind": query["type"],
                    "requested_at": requested_at,
                    "locally_received_at": received_at,
                    "sha256": sha,
                    "scope_hash": (
                        sha256(query["user"].lower().encode()).hexdigest()
                        if "user" in query
                        else None
                    ),
                }
            ),
        )
        if sleep_between:
            sleep(sleep_between)
        return data

    catalog = record("perpDexs", {"type": "perpDexs"})
    dexs = sorted(_dex_universe(catalog))
    if not 1 <= len(dexs) <= MAX_DEXS:
        raise ValueError("EXCESSIVE_OFFICIAL_DEX_CENSUS")
    report["dex_count"] = len(dexs)
    report["dex_catalog_sha256"] = sha256(_canonical(catalog)).hexdigest()
    subjects: dict[str, str] = {}
    for alias in MANAGERS:
        master = identities[alias]
        roster = record(f"{alias}-subaccounts", {"type": "subAccounts", "user": master})
        children = _subaccount_roster(roster, master)
        report["managers"][alias] = {
            "subaccount_count": len(children),
            "parent_subject_sha256": sha256(master.encode()).hexdigest(),
        }
        subjects[alias] = master
        for index, child in enumerate(children):
            subjects[f"{alias}-sub{index:02d}"] = child
    if len(subjects) > MAX_SUBJECTS or len(set(a.lower() for a in subjects.values())) != len(
        subjects
    ):
        report["errors"].append("SOURCE_SCOPE_EXCEEDS_SHARED_10_ACCOUNT_LIMIT")
        report["finished_at"] = _now()
        _write_immutable_private(generation / "report.json", _canonical(report))
        return report
    report["account_count"] = len(subjects)
    for alias, address in subjects.items():
        digest = sha256(address.lower().encode()).hexdigest()
        row: dict[str, Any] = {
            "sha256": digest,
            "observed_dexs": 0,
            "account_mode": "UNKNOWN",
            "spot_observed": False,
            "position_rows": 0,
            "errors": [],
        }
        report["subjects"][alias] = row
        for label, query in (
            ("abstraction", {"type": "userAbstraction", "user": address}),
            ("spot", {"type": "spotClearinghouseState", "user": address}),
        ):
            try:
                data = record(f"{alias}-{label}", query)
                if label == "abstraction":
                    if data not in (
                        "disabled",
                        "default",
                        "unifiedAccount",
                        "portfolioMargin",
                        "dexAbstraction",
                    ):
                        raise ValueError("UNRECOGNIZED_ABSTRACTION")
                    row["account_mode"] = data
                else:
                    if not isinstance(data, dict) or not isinstance(data.get("balances"), list):
                        raise ValueError("INVALID_SPOT_SCOPE")
                    row["spot_observed"] = True
                    row["spot_token_count"] = len(data["balances"])
            except Exception as exc:
                row["errors"].append(f"{label}_{type(exc).__name__}")
        for dex in dexs:
            try:
                payload = {"type": "clearinghouseState", "user": address}
                if dex != "default":
                    payload["dex"] = dex
                data = record(f"{alias}-dex-{dex}", payload)
                if (
                    not isinstance(data, dict)
                    or not isinstance(data.get("marginSummary"), dict)
                    or not isinstance(data.get("assetPositions"), list)
                ):
                    raise ValueError("INCOMPLETE_DEX_STATE")
                row["observed_dexs"] += 1
                row["position_rows"] += len(data["assetPositions"])
            except Exception as exc:
                row["errors"].append(f"DEX_{dex}_{type(exc).__name__}")
        if row["errors"]:
            report["errors"].append(alias + ":INCOMPLETE_REST_CENSUS")
    report["all_subjects_captured"] = (
        len(subjects) == 10
        and not report["errors"]
        and all(
            v["observed_dexs"] == len(dexs)
            and v["spot_observed"]
            and v["account_mode"] != "UNKNOWN"
            for v in report["subjects"].values()
        )
    )
    report["finished_at"] = _now()
    _write_immutable_private(generation / "report.json", _canonical(report))
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--research-root", type=Path, required=True)
    path = parser.add_mutually_exclusive_group(required=True)
    path.add_argument("--generation", type=Path)
    path.add_argument("--store", type=Path)
    args = parser.parse_args()
    generation = args.generation
    if args.store is not None:
        generation = args.store / (
            "gC2" + datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ") + "-" + uuid.uuid4().hex[:8]
        )
    result = collect(args.research_root, generation)
    print(
        json.dumps(
            {
                key: result[key]
                for key in (
                    "schema",
                    "account_count",
                    "dex_count",
                    "all_subjects_captured",
                    "follower_source_equity_verified",
                    "request_count",
                    "errors",
                    "network_order_mutations",
                    "finished_at",
                )
                if key in result
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
