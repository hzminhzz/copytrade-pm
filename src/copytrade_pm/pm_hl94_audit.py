"""Read-only audit of the separate 94-file historical wallet cohort.

Never reinterpret the top-level equity snapshot as historical account NAV.
No live network, market orders, or mutation of source data.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from decimal import Decimal, InvalidOperation
from hashlib import sha256
import json
from pathlib import Path

COHORT = ("wallet_fills_90d", "nansen_smart_money_fills_90d", "broader_active_inventory_fills_90d")
SCHEMA = "copytrade_hl94_raw_fill_audit_v1"


def normalized_fill(row: dict) -> dict:
    """Preserve fill identity, source position and native coin; do not infer history."""
    before = row.get("startPosition", row.get("start_position"))
    pnl = row.get("closedPnl", row.get("closed_pnl"))
    required = ("coin", "px", "sz", "side", "time", "tid")
    if not isinstance(row, dict) or any(k not in row for k in required) or before is None:
        raise ValueError("FILL_REQUIRED_FIELD_MISSING")
    try:
        start = Decimal(str(before))
        size = Decimal(str(row["sz"]))
        price = Decimal(str(row["px"]))
        closed_pnl = Decimal(str(pnl)) if pnl is not None else None
        stamp = int(row["time"])
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError("FILL_NUMERIC_INVALID") from exc
    if not all(x.is_finite() for x in (start, size, price)) or size <= 0 or price <= 0:
        raise ValueError("FILL_NONPOSITIVE_OR_NONFINITE")
    if row["side"] not in ("A", "B"):
        raise ValueError("FILL_SIDE_INVALID")
    if stamp < 1_500_000_000_000 or stamp > 2_000_000_000_000:
        raise ValueError("FILL_TIME_INVALID")
    tid = str(row["tid"])
    if not tid.isdigit() or int(tid) <= 0:
        raise ValueError("FILL_TID_INVALID")
    signed_delta = size if row["side"] == "B" else -size
    return {"coin": str(row["coin"]), "timestamp_ms": stamp, "tid": tid,
            "side": row["side"], "size": str(size), "price": str(price),
            "start_position": str(start), "end_position": str(start + signed_delta),
            "signed_delta": str(signed_delta), "closed_pnl": str(closed_pnl) if closed_pnl is not None else None,
            "tx_hash": row.get("hash"), "order_id": row.get("oid")}


def fill_key(wallet: str, row: dict) -> tuple:
    # The exchange trade id (tid) distinguishes legitimate partial executions.
    return (wallet, row["coin"], row["tid"])


def audit(root: Path) -> dict:
    files = [(cohort, file) for cohort in COHORT for file in sorted((root / cohort).glob("*.json"))]
    if not files:
        raise ValueError("COHORT_FILES_MISSING")
    wallets: dict[str, dict] = {}
    keys: dict[tuple, dict] = {}
    conflicts: list[dict] = []
    counters = Counter()
    for cohort, path in files:
        blob = path.read_bytes()
        digest = sha256(blob).hexdigest()
        payload = json.loads(blob)
        address = str(payload.get("address", "")).lower()
        if not (len(address) == 42 and address.startswith("0x") and all(c in "0123456789abcdef" for c in address[2:])):
            raise ValueError(f"WALLET_ADDRESS_INVALID:{path.name}")
        fills = payload.get("fills")
        if not isinstance(fills, list):
            raise ValueError(f"FILL_ARRAY_MISSING:{path.name}")
        wallet = wallets.setdefault(address, {"address": address, "labels": [], "datasets": [],
            "files": [], "raw_fills": 0, "unique_fills": 0, "instruments": set(),
            "first_ms": None, "last_ms": None, "invalid_rows": Counter(),
            "gross_turnover_usd": Decimal(0), "closed_pnl_usd": Decimal(0),
            "position_discontinuities": 0, "completed_episodes": 0, "holding_hours": [],
            "snapshot_equity_usd": [], "duplicate_rows": 0})
        wallet["labels"].append(str(payload.get("label") or payload.get("alias_label") or path.stem.split("_0x")[0]))
        wallet["datasets"].append(cohort)
        wallet["files"].append({"basename": path.name, "sha256": digest, "rows": len(fills)})
        snapshot = payload.get("equity")
        if snapshot is not None:
            wallet["snapshot_equity_usd"].append(str(snapshot))
        wallet["raw_fills"] += len(fills)
        counters["raw_fills"] += len(fills)
        for n, raw in enumerate(fills):
            try:
                row = normalized_fill(raw)
            except ValueError as exc:
                wallet["invalid_rows"][str(exc)] += 1
                counters["invalid_rows"] += 1
                continue
            key = fill_key(address, row)
            if key in keys:
                if keys[key] != row:
                    conflicts.append({"address": address, "tid": row["tid"], "coin": row["coin"],
                                      "file": path.name, "row": n})
                    counters["conflicting_duplicates"] += 1
                else:
                    wallet["duplicate_rows"] += 1
                    counters["exact_duplicates"] += 1
                continue
            keys[key] = row
            wallet["unique_fills"] += 1
            wallet["instruments"].add(row["coin"])
            t = row["timestamp_ms"]
            wallet["first_ms"] = t if wallet["first_ms"] is None else min(t, wallet["first_ms"])
            wallet["last_ms"] = t if wallet["last_ms"] is None else max(t, wallet["last_ms"])
            wallet["gross_turnover_usd"] += Decimal(row["size"]) * Decimal(row["price"])
            if row["closed_pnl"] is not None:
                wallet["closed_pnl_usd"] += Decimal(row["closed_pnl"])
    grouped = defaultdict(list)
    for (address, coin, _), row in keys.items():
        grouped[(address, coin)].append(row)
    for (address, coin), rows in grouped.items():
        wallet = wallets[address]
        prev = None
        opened = None
        for row in sorted(rows, key=lambda r: (r["timestamp_ms"], int(r["tid"]))):
            before = Decimal(row["start_position"])
            after = Decimal(row["end_position"])
            if prev is not None and before != prev:
                wallet["position_discontinuities"] += 1
                opened = None
            if before == 0 and after != 0:
                opened = row["timestamp_ms"]
            if after == 0 and opened is not None:
                wallet["completed_episodes"] += 1
                wallet["holding_hours"].append((row["timestamp_ms"] - opened) / 3600000)
                opened = None
            prev = after
    output = []
    for address, w in sorted(wallets.items()):
        holds = sorted(w.pop("holding_hours"))
        w["median_holding_hours"] = (holds[len(holds)//2] if len(holds)%2 else
                                    (holds[len(holds)//2-1]+holds[len(holds)//2])/2) if holds else None
        w["instruments"] = sorted(w["instruments"])
        w["invalid_rows"] = dict(w["invalid_rows"])
        w["gross_turnover_usd"] = str(w["gross_turnover_usd"])
        w["closed_pnl_usd"] = str(w["closed_pnl_usd"])
        w["holding_duration_scope"] = "ONLY_OBSERVED_CONTINUOUS_ZERO_TO_ZERO_CHAINS_NOT_WHOLE_WALLET"
        w["evidence_status"] = "RAW_FILLS_ONLY_NO_HISTORICAL_EQUITY"
        w["portfolio_eligible"] = False
        w["exclusion_reason"] = "HISTORICAL_EQUITY_AND_FULL_BOOK_NOT_YET_VERIFIED"
        output.append(w)
    report = {"schema": SCHEMA, "file_count": len(files), "unique_wallet_count": len(wallets),
              "dataset_file_counts": {name: sum(c == name for c, _ in files) for name in COHORT},
              "counts": {**dict(counters), "unique_fills": len(keys)},
              "conflict_examples": conflicts[:20], "wallets": output,
              "snapshot_equity_policy": "DESCRIPTIVE_ONLY_NOT_HISTORICAL_EQUITY",
              "source_data_mutated": False}
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    report = audit(args.data_root)
    body = (json.dumps(report, sort_keys=True, indent=2) + "\n").encode()
    digest = sha256(body).hexdigest()
    args.out.mkdir(parents=True, exist_ok=True)
    dest = args.out / f"hl94-audit-{digest[:20]}.json"
    with dest.open("xb") as out:
        out.write(body)
    print(json.dumps({"report": str(dest), "sha256": digest,
                      "counts": report["counts"], "file_count": report["file_count"],
                      "unique_wallet_count": report["unique_wallet_count"]}, sort_keys=True))


if __name__ == "__main__":
    main()
