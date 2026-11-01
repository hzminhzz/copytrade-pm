"""Bounded prospective, read-only E4 account-evidence acquisition.

HyperX analytics is *supplemental*. Actual currently observed all-DEX
positions come from official Hyperliquid public account streams. Each
response is immutable, timestamped on local receipt and SHA-addressed.
Do not infer a historical first-known time or synthesize a continuous event
census from snapshots. No trading API, wallet private keys or broker use.
"""

from __future__ import annotations

import argparse
import asyncio
from datetime import UTC, datetime, timedelta
from hashlib import sha256
import json
from pathlib import Path
import re
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .pm_hyperx_account_triage import _write_immutable_private
from .pm_hyperx_gap_recovery import _private_dir
from .pm_sources import load_cohort

INFO_URL = "https://api.hyperliquid.xyz/info"
WS_URL = "wss://api.hyperliquid.xyz/ws"
PODS = ("CO-001", "W015", "VS066")
MAX_DURATION = 90
MAX_FRAMES = 250
MAX_BODY = 3_000_000
MAX_INFO_CALLS = 26
MAX_SUBACCOUNTS = 16
SUBSCRIPTIONS = (
    "allDexsClearinghouseState",
    "userEvents",
    "userFills",
    "userFundings",
    "userNonFundingLedgerUpdates",
)
ALIASES = frozenset(PODS)


def _now() -> datetime:
    return datetime.now(UTC)


def _canonical(obj: Any) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), allow_nan=False).encode() + b"\n"


def _safe_dir(out: Path) -> None:
    if not re.fullmatch(r"g[0-9A-Za-z_-]{12,80}", out.name):
        raise ValueError("E4_INVALID_GENERATION_NAME")
    if out.exists():
        raise ValueError("E4_IMMUTABLE_GENERATION_ALREADY_EXISTS")
    _private_dir(out)
    if out.stat().st_mode & 0o077:
        raise ValueError("E4_EVIDENCE_DIRECTORY_NOT_PRIVATE")


def _guarded_info(request: dict) -> tuple[dict | list, bytes, str]:
    body = _canonical(request)
    url = Request(
        INFO_URL,
        data=body,
        headers={
            "Content-Type": "application/json",
            "User-Agent": "OpenAI File Downloader, XaiImageApiFetch/1.0",
        },
    )
    with urlopen(url, timeout=18) as response:
        raw = response.read(MAX_BODY + 1)
    if len(raw) > MAX_BODY:
        raise ValueError("E4_PROVIDER_RESPONSE_TOO_LARGE")
    parsed = json.loads(raw)
    if parsed is not None and not isinstance(parsed, (list, dict)):
        raise ValueError("E4_INVALID_PROVIDER_JSON")
    return parsed, raw, sha256(raw).hexdigest()


def _dex_universe(body: object) -> set[str]:
    """Official perpDexs: null is default, entries name HIP-3 dexs."""
    if not isinstance(body, list) or not body or body[0] is not None:
        raise ValueError("E4_INVALID_DEX_CATALOG")
    names = {"default"}
    for item in body[1:]:
        if not isinstance(item, dict):
            raise ValueError("E4_INVALID_DEX_CATALOG")
        name = item.get("name")
        if not isinstance(name, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", name):
            raise ValueError("E4_INVALID_DEX_NAME")
        if name in names:
            raise ValueError("E4_DUPLICATE_DEX")
        names.add(name)
    return names


def _subaccount_roster(payload: object, parent: str) -> list[str]:
    if payload is None:
        return []
    if not isinstance(payload, list) or len(payload) > MAX_SUBACCOUNTS:
        raise ValueError("E4_INVALID_SUBACCOUNT_CENSUS")
    members = []
    for row in payload:
        if not isinstance(row, dict):
            raise ValueError("E4_INVALID_SUBACCOUNT_CENSUS")
        address = row.get("subAccountUser")
        owner = row.get("master")
        if (
            not isinstance(address, str)
            or re.fullmatch(r"0x[a-fA-F0-9]{40}", address) is None
            or str(owner).lower() != parent.lower()
        ):
            raise ValueError("E4_SUBACCOUNT_PARENT_MISMATCH")
        members.append(address)
    if len({a.lower() for a in members}) != len(members) or parent.lower() in {
        a.lower() for a in members
    }:
        raise ValueError("E4_DUPLICATE_OR_SELF_SUBACCOUNT")
    return members


def _account_state(
    body: dict, expected_address: str, expected_dexs: set[str] | None = None
) -> dict:
    """Strictly parse the official all-DEX wallet state without flattening DEXs."""
    if str(body.get("user", "")).lower() != expected_address.lower():
        raise ValueError("E4_ALL_DEXS_WRONG_WALLET")
    records = body.get("clearinghouseStates")
    if not isinstance(records, list) or not records:
        raise ValueError("E4_MISSING_ALL_DEXS_CENSUS")
    positions = {}
    seen_positions: set[str] = set()
    risk_metadata = {}
    per_dex = []
    counts = 0
    observed_dexs: set[str] = set()
    for pair in records:
        if not isinstance(pair, list) or len(pair) != 2:
            raise ValueError("E4_INVALID_ALL_DEXS_ENTRY")
        dex, state = pair
        if not isinstance(dex, str) or not isinstance(state, dict):
            raise ValueError("E4_UNKNOWN_DEX_OR_STATE")
        dex_name = dex or "default"
        if "/" in dex_name or ":" in dex_name or dex_name in observed_dexs:
            raise ValueError("E4_INVALID_OR_DUPLICATE_DEX_NAME")
        observed_dexs.add(dex_name)
        if "marginSummary" not in state or not isinstance(state.get("assetPositions"), list):
            raise ValueError("E4_MISSING_MARGIN_OR_POSITIONS")
        margin = state["marginSummary"]
        if not isinstance(margin, dict):
            raise ValueError("E4_UNKNOWN_MARGIN")
        for key in ("accountValue", "totalNtlPos", "totalMarginUsed"):
            if key not in margin:
                raise ValueError("E4_MISSING_MARGIN_FIELD")
            from decimal import Decimal

            n = Decimal(str(margin[key]))
            if not n.is_finite():
                raise ValueError("E4_INVALID_MARGIN_NUMBER")
        n_positions = 0
        for row in state["assetPositions"]:
            if not isinstance(row, dict) or not isinstance(row.get("position"), dict):
                raise ValueError("E4_INVALID_POSITION_ROW")
            p = row["position"]
            coin = p.get("coin")
            if not isinstance(coin, str) or not coin:
                raise ValueError("E4_MISSING_POSITION_COIN")
            # A prefixed HIP-3 coin has to correspond to its returned DEX.
            if ":" in coin and (dex_name == "default" or coin.split(":", 1)[0] != dex_name):
                raise ValueError("E4_DEX_COIN_MISMATCH")
            clean = coin.split(":", 1)[-1]
            if not clean or ":" in clean or "/" in clean or clean.strip() != clean:
                raise ValueError("E4_UNKNOWN_INSTRUMENT_FORMAT")
            key = f"hyperliquid/mainnet:perp:{dex_name}/{clean}"
            from decimal import Decimal

            qty = Decimal(str(p["szi"]))
            if not qty.is_finite() or key in seen_positions:
                raise ValueError("E4_INVALID_OR_DUPLICATE_POSITION")
            seen_positions.add(key)
            # Preserve native risk fields without inferring leverage or a wallet denominator.
            risk_metadata[key] = {name: p[name] for name in ("leverage", "marginUsed") if name in p}
            if qty:
                positions[key] = str(qty)
                n_positions += 1
        counts += n_positions
        per_dex.append(
            {
                "dex": dex_name,
                "position_count": n_positions,
                "account_value_usd": str(margin["accountValue"]),
                "total_notional_usd": str(margin["totalNtlPos"]),
                "margin_used_usd": str(margin["totalMarginUsed"]),
                "state_at": state.get("time"),
            }
        )
    if expected_dexs is not None and observed_dexs != expected_dexs:
        raise ValueError("E4_ALL_DEXS_NOT_EQUAL_OFFICIAL_CATALOG")
    return {
        "dex_catalog_parity_verified": expected_dexs is not None,
        "position_count": counts,
        "observed_dex_count": len(records),
        "positions": positions,
        "native_position_risk_metadata": risk_metadata,
        "per_dex": per_dex,
        "complete_scope_claim": "EXCHANGE_WS_ALL_DEXS_USER_SCOPE_AT_RECEIPT_ONLY",
        "full_wallet_equity_reconciled": False,
        "source_equity_asof_2026q3": False,
        "continuous_position_event_feed_proven": False,
    }


def _info_queries(address: str, since: int) -> list[tuple[str, dict]]:
    return [
        ("portfolio", {"type": "portfolio", "user": address}),
        ("spot_state", {"type": "spotClearinghouseState", "user": address}),
        ("funding_recent", {"type": "userFunding", "user": address, "startTime": since}),
        (
            "ledger_recent",
            {"type": "userNonFundingLedgerUpdates", "user": address, "startTime": since},
        ),
    ]


async def collect(
    research_root: Path,
    generation: Path,
    *,
    duration: int = 35,
    max_frames: int = 180,
    include_info: bool = True,
) -> dict:
    """One bounded observation window; no infinite process or automatic retries."""
    if not (1 <= duration <= MAX_DURATION and 1 <= max_frames <= MAX_FRAMES):
        raise ValueError("E4_UNBOUNDED_PROSPECTIVE_CAPTURE")
    entries, fingerprint = load_cohort(research_root)
    roster = {p.alias: p for p in entries if p.alias in ALIASES}
    if set(roster) != ALIASES:
        raise ValueError("E4_FROZEN_WALLET_ROSTER_MISMATCH")
    _safe_dir(generation)
    started = _now()
    summary: dict[str, Any] = {
        "schema": "e4_prospective_account_capture_v1",
        "classification": "READ_ONLY_LOCAL_RECEIPTS_NOT_FULL_HISTORIC_E4",
        "started_at": started.isoformat(),
        "cohort_source_sha": fingerprint,
        "wallets": {
            p: {
                "identity_sha256": roster[p].address_sha256,
                "ws_all_dex_snapshot_count": 0,
                "events_seen": 0,
                "native_position_count_latest": None,
                "status": "NO_CURRENT_ACCOUNT_SNAPSHOT",
            }
            for p in PODS
        },
        "read_only": True,
        "broker_orders_enabled": False,
        "historical_q3_qualified": False,
        "ws_frames_saved": 0,
        "info_calls": 0,
        "websocket": "NOT_STARTED",
        "errors": [],
    }
    by_addr = {v.address.lower(): k for k, v in roster.items()}
    subjects = {k: v.address for k, v in roster.items()}
    expected_dexs: set[str] | None = None
    try:
        data, raw, dex_sha = await asyncio.to_thread(_guarded_info, {"type": "perpDexs"})
        summary["info_calls"] += 1
        _write_immutable_private(generation / "catalog" / "perpDexs.json", raw)
        expected_dexs = _dex_universe(data)
        summary["perp_dex_catalog_sha256"] = dex_sha
        summary["expected_perp_dexs"] = len(expected_dexs)
    except (ValueError, HTTPError, URLError, TimeoutError) as exc:
        summary["errors"].append("PERP_DEX_CATALOG_" + type(exc).__name__)
    for alias in PODS:
        summary["wallets"][alias]["subaccounts"] = {}
        summary["wallets"][alias]["subaccounts_census_verified"] = False
        summary["info_calls"] += 1
        requested = _now()
        try:
            data, raw, record_sha = await asyncio.to_thread(
                _guarded_info, {"type": "subAccounts", "user": roster[alias].address}
            )
            received = _now()
            addresses = _subaccount_roster(data, roster[alias].address)
            _write_immutable_private(generation / "info_raw" / alias / "subaccounts.json", raw)
            _write_immutable_private(
                generation / "info_metadata" / alias / "subaccounts.json",
                _canonical(
                    {
                        "requested_at": requested.isoformat(),
                        "received_at": received.isoformat(),
                        "sha256": record_sha,
                        "observed_subaccount_count": len(addresses),
                        "response_was_null": data is None,
                    }
                ),
            )
            summary["wallets"][alias]["subaccounts_census_verified"] = True
            summary["wallets"][alias]["observed_subaccount_count"] = len(addresses)
            for index, address in enumerate(addresses):
                key = f"{alias}-sub{index:02d}"
                if address.lower() in by_addr:
                    raise ValueError("E4_DUPLICATE_WALLET_AND_SUBACCOUNT")
                by_addr[address.lower()] = key
                subjects[key] = address
                summary["wallets"][alias]["subaccounts"][key] = {
                    "identity_sha256": sha256(address.lower().encode()).hexdigest(),
                    "status": "NO_SUBACCOUNT_SNAPSHOT",
                    "ws_all_dex_snapshot_count": 0,
                    "native_position_count_latest": None,
                }
        except (ValueError, HTTPError, URLError, TimeoutError) as exc:
            summary["errors"].append(alias + ":SUBACCOUNT_DISCOVERY_" + type(exc).__name__)
    try:
        if len(subjects) > 10:
            raise ValueError("E4_PROVIDER_USER_LIMIT_REQUIRES_BOUNDED_ROTATION")
        import websockets

        async with websockets.connect(
            WS_URL,
            open_timeout=16,
            close_timeout=6,
            ping_interval=15,
            ping_timeout=12,
            max_size=MAX_BODY,
        ) as ws:
            summary["websocket"] = "CONNECTED"
            for subject, address in subjects.items():
                kinds = SUBSCRIPTIONS if subject in PODS else ("allDexsClearinghouseState",)
                for kind in kinds:
                    await ws.send(
                        json.dumps(
                            {"method": "subscribe", "subscription": {"type": kind, "user": address}}
                        )
                    )
            deadline = asyncio.get_running_loop().time() + duration
            while summary["ws_frames_saved"] < max_frames:
                remaining = deadline - asyncio.get_running_loop().time()
                if remaining <= 0:
                    break
                try:
                    raw = await asyncio.wait_for(ws.recv(), timeout=remaining)
                except asyncio.TimeoutError:
                    break
                received = _now()
                if not isinstance(raw, str) or len(raw.encode()) > MAX_BODY:
                    summary["errors"].append("NON_TEXT_OR_OVERSIZED_WS_FRAME")
                    break
                payload = json.loads(raw)
                if not isinstance(payload, dict):
                    summary["errors"].append("MALFORMED_WS_PAYLOAD")
                    break
                channel = payload.get("channel")
                data = payload.get("data")
                owner = None
                if isinstance(data, dict):
                    owner = by_addr.get(str(data.get("user", "")).lower())
                serial = summary["ws_frames_saved"]
                wire = raw.encode()
                name = (
                    generation / "ws_frames" / f"{serial:04d}-{sha256(wire).hexdigest()[:20]}.json"
                )
                sha = _write_immutable_private(name, wire)
                summary["ws_frames_saved"] += 1
                _write_immutable_private(
                    generation / "ws_metadata" / f"{serial:04d}.json",
                    _canonical(
                        {
                            "channel": channel,
                            "alias": owner,
                            "first_locally_received_at": received.isoformat(),
                            "raw_sha256": sha,
                            "snapshot": data.get("isSnapshot") if isinstance(data, dict) else None,
                            "raw_file": str(name.relative_to(generation)),
                        }
                    ),
                )
                if owner and isinstance(data, dict):
                    parent = owner if owner in PODS else owner.split("-sub", 1)[0]
                    if owner in PODS:
                        summary["wallets"][owner]["events_seen"] += 1
                    if channel == "allDexsClearinghouseState":
                        try:
                            canonical = _account_state(data, subjects[owner], expected_dexs)
                        except (KeyError, ValueError, TypeError) as exc:
                            summary["errors"].append(
                                f"{owner}:E4_ALL_DEXS_VALIDATION:{type(exc).__name__}"
                            )
                        else:
                            current = (
                                summary["wallets"][owner]
                                if owner in PODS
                                else summary["wallets"][parent]["subaccounts"][owner]
                            )
                            current["ws_all_dex_snapshot_count"] += 1
                            current["native_position_count_latest"] = canonical["position_count"]
                            current["observed_dex_count"] = canonical["observed_dex_count"]
                            current["status"] = (
                                "OFFICIAL_ALL_DEXS_ACCOUNT_OBSERVED_ASOF_RECEIPT"
                                if canonical["dex_catalog_parity_verified"]
                                else "PARTIAL_ACCOUNT_OBSERVED_DEX_CATALOG_UNKNOWN"
                            )
                            _write_immutable_private(
                                generation / "account_states" / f"{owner}-{serial:04d}.json",
                                _canonical(
                                    {
                                        "wallet": owner,
                                        "identity_sha256": sha256(
                                            subjects[owner].lower().encode()
                                        ).hexdigest(),
                                        "first_locally_received_at": received.isoformat(),
                                        "source_raw_sha256": sha,
                                        "state": canonical,
                                    }
                                ),
                            )
                if channel == "error":
                    summary["errors"].append("SOURCE_WS_SUBSCRIPTION_REJECTION")
    except Exception as exc:
        # Never expose raw HTTP/WS exception messages containing addresses.
        summary["websocket"] = "FAILED_OR_INTERRUPTED"
        summary["errors"].append("E4_WS_" + type(exc).__name__)

    if include_info:
        since = int((started - timedelta(days=7)).timestamp() * 1000)
        for alias in PODS:
            for tag, req in _info_queries(roster[alias].address, since):
                if summary["info_calls"] >= MAX_INFO_CALLS:
                    raise ValueError("E4_INFO_BUDGET_EXCEEDED")
                requested = _now()
                summary["info_calls"] += 1
                try:
                    parsed, raw, sha = await asyncio.to_thread(_guarded_info, req)
                    received = _now()
                    raw_path = generation / "info_raw" / alias / f"{tag}.json"
                    _write_immutable_private(raw_path, raw)
                    meta = {
                        "requested_at": requested.isoformat(),
                        "received_at": received.isoformat(),
                        "sha256": sha,
                        "raw_path": str(raw_path.relative_to(generation)),
                        "response_shape": type(parsed).__name__,
                        "response_rows": len(parsed) if isinstance(parsed, list) else None,
                    }
                    _write_immutable_private(
                        generation / "info_metadata" / alias / f"{tag}.json",
                        _canonical(meta),
                    )
                    summary["wallets"][alias].setdefault("info", {})[tag] = {
                        "sha256": sha,
                        "captured": True,
                        "rows": meta["response_rows"],
                        "known_at": received.isoformat(),
                    }
                except (ValueError, TypeError, HTTPError, URLError, TimeoutError) as exc:
                    summary["wallets"][alias].setdefault("info", {})[tag] = {
                        "captured": False,
                        "error_class": type(exc).__name__,
                    }
                    summary["errors"].append(f"{alias}:INFO_{tag}:{type(exc).__name__}")
                await asyncio.sleep(0.2)
    summary["finished_at"] = _now().isoformat()
    _write_immutable_private(generation / "capture-report.json", _canonical(summary))
    return summary


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--research-root", type=Path, required=True)
    p.add_argument("--generation", type=Path, required=True)
    p.add_argument("--duration", type=int, default=35)
    p.add_argument("--max-frames", type=int, default=180)
    p.add_argument("--no-info", action="store_true")
    args = p.parse_args()
    from .pm_source_rotation import DEFAULT_LOCK, observer_lock

    with observer_lock(DEFAULT_LOCK):
        summary = asyncio.run(
            collect(
                args.research_root,
                args.generation,
                duration=args.duration,
                max_frames=args.max_frames,
                include_info=not args.no_info,
            )
        )
    print(
        json.dumps(
            {
                "generation": str(args.generation),
                "report_sha256": sha256(
                    (args.generation / "capture-report.json").read_bytes()
                ).hexdigest(),
                "websocket": summary["websocket"],
                "wallets": {
                    p: {k: v for k, v in summary["wallets"][p].items() if k != "identity_sha256"}
                    for p in PODS
                },
                "ws_frames_saved": summary["ws_frames_saved"],
                "info_calls": summary["info_calls"],
                "errors": summary["errors"],
                "historical_q3_qualified": False,
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
