"""Stage-1 universe inventory for Phase 7 (no alpha, PnL, or account inference)."""
from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

START_MS = 1785888000000
END_MS = 1793664000000
CUTOFF = datetime(2026, 11, 4, tzinfo=timezone.utc)
BASE = Path("/home/quant/dev/copytrade-pm")
DIRECTORIES = (
    "wallet_fills_90d",
    "broader_active_inventory_fills_90d",
    "nansen_smart_money_fills_90d",
)


def summarize(label: str, address: str, rows: list[tuple[int, str, str, float]], source: str, vendor_equity: str | float | None, *, opening_positions: bool) -> dict:
    within = [(ms, coin, side, gross) for ms, coin, side, gross in rows if START_MS <= ms < END_MS]
    if not within:
        return {"alias": label, "address": address, "source": source, "fills": 0, "observation_days": 0,
                "opening_positions": opening_positions, "vendor_equity_untimestamped": vendor_equity}
    days = {datetime.fromtimestamp(ms / 1000, tz=timezone.utc).date().isoformat() for ms, _, _, _ in within}
    coins = Counter(coin for _, coin, _, _ in within)
    gross = Counter()
    main = 0
    for _, coin, _, notional in within:
        gross[coin] += max(0.0, notional)
        if ":" not in coin and not coin.startswith("@"):
            main += 1
    end_ms = max(ms for ms, _, _, _ in within)
    top_coin, top_gross = gross.most_common(1)[0]
    gross_total = sum(gross.values())
    return {
        "alias": label,
        "address": address,
        "source": source,
        "fills": len(within),
        "observation_days": len(days),
        "first_fill_utc": datetime.fromtimestamp(min(ms for ms, _, _, _ in within) / 1000, tz=timezone.utc).isoformat(),
        "last_fill_utc": datetime.fromtimestamp(end_ms / 1000, tz=timezone.utc).isoformat(),
        "last_fill_age_days_at_cutoff": round((CUTOFF.timestamp() * 1000 - end_ms) / 86_400_000, 1),
        "main_perp_fill_fraction": round(main / len(within), 4),
        "distinct_instruments": len(coins),
        "top_coin": top_coin,
        "top_coin_gross_fill_share": round(top_gross / gross_total, 4) if gross_total else None,
        "gross_turnover_by_coin_fraction": {coin: round(n / gross_total, 6) for coin, n in gross.items()} if gross_total else {},
        "fills_per_observation_day": round(len(within) / len(days), 2),
        "opening_positions": opening_positions,
        "vendor_equity_untimestamped": vendor_equity,
    }


def load_json_sources(root: Path) -> tuple[dict[str, dict], dict]:
    result = {}
    source_hashes = {}
    for directory in DIRECTORIES:
        for p in sorted((root / directory).glob("*.json")):
            blob = p.read_bytes()
            payload = json.loads(blob)
            addr = payload.get("address", "").lower()
            if not addr.startswith("0x") or len(addr) != 42:
                continue
            source_hashes[str(p.relative_to(root))] = hashlib.sha256(blob).hexdigest()
            fills = payload.get("fills", [])
            rows = []
            has_position = False
            for f in fills:
                try:
                    time = int(f["time"])
                    coin = str(f["coin"])
                    side = str(f["side"])
                    gross = abs(float(f["px"]) * float(f["sz"]))
                    if "startPosition" in f:
                        has_position = True
                    rows.append((time, coin, side, gross))
                except (ValueError, KeyError, TypeError):
                    continue
            label = payload.get("label") or p.stem.split("_0x")[0]
            entry = summarize(label, addr, rows, directory, payload.get("equity"), opening_positions=has_position)
            if addr in result:
                raise ValueError(f"duplicate raw wallet {addr}")
            result[addr] = entry
    return result, source_hashes


def read_csv_cohort(file: Path, source: str) -> dict[str, dict]:
    by_addr = defaultdict(list)
    labels, equity = {}, {}
    opener = gzip.open if file.suffix == ".gz" else open
    with opener(file, mode="rt", newline="") as handle:
        for row in csv.DictReader(handle):
            address = row.get("address", "").lower()
            if not address.startswith("0x") or len(address) != 42:
                continue
            try:
                dt = datetime.fromisoformat(row["datetime_utc"].replace("Z", "+00:00")).replace(tzinfo=timezone.utc)
                px = float(row["price"])
                size = float(row["size"])
            except (ValueError, TypeError, KeyError):
                continue
            by_addr[address].append((int(dt.timestamp() * 1000), row["coin"], row["side"], abs(px * size)))
            labels[address] = row["alias"]
            equity[address] = row.get("equity_usd")
    return {
        address: summarize(labels[address], address, rows, source, equity[address], opening_positions=False)
        for address, rows in by_addr.items()
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--source-root", type=Path, default=BASE)
    ap.add_argument("--output", type=Path)
    args = ap.parse_args()
    root = args.source_root
    items, hashes = load_json_sources(root / "data")
    source_counts = {"raw_json": len(items)}
    for filename, source in (
        ("HL108_ALL_90D_FILLS_CONSOLIDATED_20261103.csv.gz", "phase4_hl108_csv"),
        ("PHASE5_NEW50_ALL_FILLS_CONSOLIDATED_20261104.csv.gz", "phase5_new50_csv"),
    ):
        cohort = read_csv_cohort(root / "docs" / filename, source)
        source_counts[source] = len(cohort)
        hashes[f"docs/{filename}"] = hashlib.sha256((root / "docs" / filename).read_bytes()).hexdigest()
        for address, entry in cohort.items():
            if address not in items:  # canonical address, never count duplicated alias twice
                items[address] = entry
            elif source == "phase4_hl108_csv" and entry["alias"] != "Unlabeled":
                # Registered roster name takes precedence over raw file display label.
                items[address]["alias"] = entry["alias"]
    exclusions = {}
    denylist = root / "data/private/exclusions/PROPFIRM_DENYLIST_47_20261104.csv"
    with denylist.open(newline="") as handle:
        for row in csv.DictReader(handle):
            exclusions[row["address"].lower()] = row
    hashes[str(denylist.relative_to(root))] = hashlib.sha256(denylist.read_bytes()).hexdigest()
    counts = Counter()
    for entry in items.values():
        reject = exclusions.get(entry["address"])
        reasons = []
        if reject:
            reasons.append("OWNER_REJECTION" if reject["research_excluded"] == "true" else "PROP_FIRM_DENYLIST")
        if entry["observation_days"] < 40:
            reasons.append("LT_40_OBSERVATION_DAYS")
        if entry["fills"] <= 0:
            reasons.append("NO_90D_FILLS")
        if entry.get("last_fill_age_days_at_cutoff", 1000) > 14:
            reasons.append("STALE_GT_14D")
        if entry.get("main_perp_fill_fraction", 0) < 0.8:
            reasons.append("NON_MAIN_PERP_SCOPE")
        if entry.get("fills_per_observation_day", 0) > 100:
            reasons.append("HIGH_CHURN_100_PLUS_FILLS_PER_ACTIVE_DAY")
        entry["screen_reasons"] = reasons
        entry["recommendation"] = "REJECT" if reject or "NO_90D_FILLS" in reasons else ("WATCH" if reasons else "CANDIDATE_UNVERIFIED")
        entry["equity_freshness"] = "UNKNOWN_STATIC_VENDOR_ONLY"
        entry["native_coverage"] = "NOT_CHECKED_AT_STAGE1"
        entry["whole_account_position_coverage"] = "UNKNOWN"
        counts[entry["recommendation"]] += 1
    output = {
        "schema": "phase7_universe_readonly_v1",
        "time_utc": CUTOFF.isoformat(),
        "n_canonical_wallets": len(items),
        "source_wallets": source_counts,
        "source_sha256": hashes,
        "counts": dict(counts),
        "wallets": sorted(items.values(), key=lambda x: (x["recommendation"], x["alias"], x["address"])),
        "financially_qualified": False,
    }
    text = json.dumps(output, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        if args.output.exists():
            raise FileExistsError("immutable artifact already exists")
        args.output.write_text(text)
    print(json.dumps({"source_wallets": source_counts, "canonical_wallets": len(items),
                      "counts": dict(counts), "artifact_sha256": hashlib.sha256(text.encode()).hexdigest()}, sort_keys=True))


if __name__ == "__main__":
    main()
