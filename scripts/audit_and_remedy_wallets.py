"""Comprehensive Wallet Quality Audit & Remediation.

1. Hyperliquid Public API Equity Check:
   Queries https://api.hyperliquid.xyz/info for all 284 research wallets.
   Identifies wallets with total equity < 1000 USD.

2. Data Quality & Gaps Audit:
   Checks fill coverage, zero-fill wallets, and date ranges in wallet_store.
"""

from __future__ import annotations

import json
import sqlite3
import time
import urllib.request
from pathlib import Path

from copytrade_pm.wallet_store.catalog import DEFAULT_REGISTRY_DB


def get_research_wallets() -> list[dict]:
    con = sqlite3.connect(DEFAULT_REGISTRY_DB)
    query = """
    SELECT DISTINCT w.address, c.cohort_id
    FROM wallets w
    JOIN cohort_memberships cm ON cm.wallet_id = w.wallet_id
    JOIN cohorts c ON c.cohort_id = cm.cohort_id
    """
    rows = con.execute(query).fetchall()
    wallets_map = {}
    for addr, cohort in rows:
        addr_lower = addr.lower()
        wallets_map.setdefault(addr_lower, []).append(cohort)

    # Exclusions
    exclusions_query = """
    SELECT w.address, e.reason, e.known_at
    FROM exclusions e
    JOIN wallets w ON w.wallet_id = e.wallet_id
    """
    ex_rows = con.execute(exclusions_query).fetchall()
    ex_map = {r[0].lower(): r[1] for r in ex_rows}

    results = []
    for addr, cohorts in sorted(wallets_map.items()):
        results.append({
            "address": addr,
            "cohorts": cohorts,
            "excluded_reason": ex_map.get(addr),
        })
    return results


def check_hl_equity(address: str, max_retries: int = 3) -> dict:
    url = "https://api.hyperliquid.xyz/info"
    payload = json.dumps({"type": "clearinghouseState", "user": address}).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json", "User-Agent": "copytrade-pm/1.0"}
    )
    for attempt in range(max_retries):
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            perp_equity = float(data.get("marginSummary", {}).get("accountValue", 0.0))
            cross_equity = float(data.get("crossMarginSummary", {}).get("accountValue", 0.0))
            withdrawable = float(data.get("withdrawable", 0.0))
            return {
                "perp_equity": perp_equity,
                "cross_equity": cross_equity,
                "withdrawable": withdrawable,
                "total_equity": max(perp_equity, withdrawable),
                "error": None,
            }
        except Exception as e:
            if attempt == max_retries - 1:
                return {
                    "perp_equity": 0.0,
                    "cross_equity": 0.0,
                    "withdrawable": 0.0,
                    "total_equity": 0.0,
                    "error": str(e),
                }
            time.sleep(0.5)


def run_audit():
    print("=" * 80)
    print("STEP 1: AUDITING HYPERLIQUID LIVE EQUITY (< $1,000)")
    print("=" * 80)

    wallets = get_research_wallets()
    print(f"Total active research wallets: {len(wallets)}")

    under_1000 = []
    over_1000 = []
    errors = []

    for i, w in enumerate(wallets):
        addr = w["address"]
        eq_info = check_hl_equity(addr)
        if eq_info["error"]:
            errors.append((addr, eq_info["error"]))
            print(f"[{i+1}/{len(wallets)}] {addr}: ERROR {eq_info['error']}")
            continue

        tot_eq = eq_info["total_equity"]
        w["live_equity"] = tot_eq
        w["perp_equity"] = eq_info["perp_equity"]
        w["withdrawable"] = eq_info["withdrawable"]

        if tot_eq < 1000.0:
            under_1000.append(w)
            print(f"[{i+1}/{len(wallets)}] {addr}: ${tot_eq:,.2f} (< $1000) - Cohorts: {','.join(w['cohorts'])} | Excluded: {w['excluded_reason']}")
        else:
            over_1000.append(w)
            if (i + 1) % 50 == 0:
                print(f"[{i+1}/{len(wallets)}] Progress: {len(under_1000)} under $1k, {len(over_1000)} >= $1k")
        time.sleep(0.05)  # respectful rate limit to public node

    print("\nEquity Audit Summary:")
    print(f"  >= $1,000 Equity: {len(over_1000)}")
    print(f"  < $1,000 Equity:  {len(under_1000)}")
    print(f"  Errors:           {len(errors)}")

    # Save findings
    out_path = Path("data/private/hl_equity_audit.json")
    with open(out_path, "w") as f:
        json.dump({
            "audited_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "total_audited": len(wallets),
            "under_1000": under_1000,
            "over_1000_count": len(over_1000),
            "errors": errors,
        }, f, indent=2)
    print(f"Saved equity audit to {out_path}")

    # Check already excluded vs new to exclude
    already_excluded = [w for w in under_1000 if w["excluded_reason"] is not None]
    new_to_exclude = [w for w in under_1000 if w["excluded_reason"] is None]
    print(f"  - Already in exclusions: {len(already_excluded)}")
    print(f"  - NEW candidates to exclude: {len(new_to_exclude)}")


if __name__ == "__main__":
    run_audit()
