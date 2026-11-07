"""Private research inventory for July-November wallet fills.

Reads the local immutable source generations and SQLite; does not update either.
Retrospective wallet fill clock != follower first-known clock.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import UTC, datetime
from hashlib import sha256
import json
from pathlib import Path
import sqlite3

import polars as pl

ROOT = Path("/home/quant/dev/copytrade-pm/data")
DB = "file:/home/quant/.local/share/copytrade/registry/wallet_registry.sqlite?mode=ro"
VIKE_SUMMARY = Path("/tmp/vike7d_432.json")
START_MS = int(datetime(2026, 7, 1, tzinfo=UTC).timestamp() * 1000)
END_MS = int(datetime(2026, 11, 8, tzinfo=UTC).timestamp() * 1000)
LOCAL_DIRS = (
    "wallet_fills_90d",
    "broader_active_inventory_fills_90d",
    "nansen_smart_money_fills_90d",
    "ml4t_100k_500k_fills_90d",
    "ml4t_jul1_to_now_fills",
    "ml4t_top6_fills_90d",
)

def alias_data(db):
    latest: dict[str,str] = {}
    records = db.execute("""
        SELECT lower(w.address), wa.namespace, wa.alias, wa.known_at
        FROM wallet_aliases wa JOIN wallets w ON w.wallet_id=wa.wallet_id
    """).fetchall()
    pref = {"sqlite_primary": 0, "ml4t_strict":1, "frozen_pm01":2, "research_v2":3}
    opts: dict[str,list[tuple[int,str]]] = defaultdict(list)
    for a,n,s,k in records:
        opts[a].append((pref.get(n,9),s))
    for a,values in opts.items():
        latest[a] = sorted(values)[0][1]
    ids={a:wid for wid,a in db.execute("select wallet_id, lower(address) from wallets")}
    excluded={r[0] for r in db.execute("select lower(w.address) from exclusions x join wallets w on w.wallet_id=x.wallet_id")}
    return latest, ids, excluded

def read_source():
    # One immutable record per native trade ID+account+instrument; no double-count between generations.
    ledger: dict[tuple[str,str,str],dict]={}
    counts=Counter()
    source_shas = []
    source_by_addr=defaultdict(set)
    for dirname in LOCAL_DIRS:
        paths=sorted((ROOT/dirname).glob("*.json"))
        for p in paths:
            try:
                raw = p.read_bytes()
                v=json.loads(raw)
            except (ValueError, OSError, UnicodeError):
                counts["invalid_json"] += 1
                continue
            source_shas.append(sha256(raw).hexdigest())
            a=str(v.get("address","")).lower()
            if not (a.startswith("0x") and len(a)==42 and isinstance(v.get("fills"),list)):
                counts["invalid_wallet_schema"] += 1
                continue
            source_by_addr[a].add(dirname)
            fills=v["fills"]
            counts[dirname+"_wallet_files"]+=1
            counts[dirname+"_fills"]+=len(fills)
            for e in fills:
                try:
                    ms=int(e["time"])
                    if not START_MS <= ms < END_MS:
                        continue
                    coin=str(e["coin"])
                    tid=str(e["tid"])
                    if not coin or coin.startswith("@") or not tid:
                        counts["unsupported_scope"] += 1
                        continue
                    cp=float(e.get("closedPnl", e.get("closed_pnl",0)) or 0)
                    fee=float(e.get("fee",0) or 0)
                    size=float(e.get("sz",0) or 0)
                    px=float(e.get("px",0) or 0)
                    before=e.get("startPosition",e.get("start_position"))
                    if px<=0 or size<=0:
                        counts["invalid_size"]+=1
                        continue
                except (KeyError, ValueError, TypeError):
                    counts["malformed_event"]+=1
                    continue
                key=(a,coin,tid)
                row={"address":a,"ms":ms,"coin":coin,"tid":tid,"closed_pnl":cp,
                     "fee":fee,"fee_token":str(e.get("feeToken",e.get("fee_token",""))),
                     "qty":size,"px":px,"side":str(e.get("side","")),
                     "before":str(before) if before is not None else None}
                old=ledger.get(key)
                if old is None:
                    ledger[key]=row
                elif (old["ms"],old["px"],old["qty"],old["side"]) != (ms,px,size,row["side"]):
                    counts["conflicting_duplicate"]+=1
                else:
                    counts["matching_duplicate"]+=1
    print("LOCAL_SOURCE_SHA_SET", sha256(json.dumps(sorted(source_shas), separators=(",", ":")).encode()).hexdigest(), "files", len(source_shas))
    print("SOURCE_COUNTERS",json.dumps(dict(counts),sort_keys=True))
    print("SOURCE_ADDRESSES",len(source_by_addr),"UNIQUE_NATIVE_FILLS",len(ledger))
    return pl.DataFrame(list(ledger.values())),source_by_addr,counts

def main():
    db=sqlite3.connect(DB,uri=True)
    alias,ids,excluded=alias_data(db)
    frame,sources,counts=read_source()
    q=frame.with_columns(pl.from_epoch(pl.col("ms"),time_unit="ms").dt.replace_time_zone("UTC").alias("utc"))
    period=q.group_by("address").agg(
        pl.len().alias("fills"),
        pl.col("ms").min().alias("earliest_ms"),
        pl.col("ms").max().alias("latest_ms"),
        pl.col("utc").dt.date().n_unique().alias("active_days"),
        pl.col("closed_pnl").sum().alias("closed_pnl_gross_usd"),
        (pl.col("closed_pnl")!=0).sum().alias("pnl_closes"),
        (pl.col("utc")>=datetime(2026,11,1,tzinfo=UTC)).sum().alias("fills_nov"),
        (pl.col("closed_pnl")*(pl.col("utc")>=datetime(2026,11,1,tzinfo=UTC))).sum().alias("gross_closed_nov"),
    )
    historical={r["address"]:r for r in period.iter_rows(named=True)}
    snap=json.loads(VIKE_SUMMARY.read_text()) if VIKE_SUMMARY.exists() else {}
    print("LOCAL_WALLETS",len(historical),"IN_REGISTRY",sum(a in ids for a in historical),
          "OWNER_EXCLUDED",sum(a in excluded for a in historical),
          "JULY_PRESENT",sum((r["earliest_ms"]<=START_MS+31*86400000) for r in historical.values()),
          "NOVEMBER_LOCAL",sum(r["fills_nov"]>0 for r in historical.values()))
    print("PER_GROUP",json.dumps({k:v for k,v in counts.items() if k.endswith("_wallet_files") or k.endswith("_fills")},sort_keys=True))
    # vendor has newer LAST fill than our combined historical local evidence
    missing=[]
    for a,v in historical.items():
        s=snap.get(a) or {}
        life=s.get("lifetime") or {}
        last_s=life.get("last_fill_ts")
        if last_s:
            last_ms=int(datetime.fromisoformat(last_s.replace("Z","+00:00")).timestamp()*1000)
            delta_h=(last_ms-v["latest_ms"])/3_600_000
            if delta_h>2:
                missing.append({"wallet_id":ids.get(a),"alias":alias.get(a),
                                "local_fills":v["fills"],"active_days":v["active_days"],
                                "historical_gross":round(v["closed_pnl_gross_usd"],2),
                                "vendor7_trades":(s.get("metrics") or {}).get("trade_count"),
                                "vendor7_gross":(s.get("metrics") or {}).get("total_realized_pnl"),
                                "last_gap_hours":round(delta_h,1),
                                "current_excluded":a in excluded,
                                "latest_ms":v["latest_ms"],
                                "recent_activity":v["fills_nov"],
                                "address":a})
    missing.sort(key=lambda v: (v["current_excluded"],-(v["vendor7_trades"] or 0),-v["historical_gross"]))
    print("VIKE_KNOWN_MORE_RECENT",len(missing),"TOP_GAPS")
    for v in missing[:22]:
        x={k:v[k] for k in ("wallet_id","alias","local_fills","active_days","historical_gross",
                "vendor7_trades","vendor7_gross","last_gap_hours","current_excluded","recent_activity")}
        print(json.dumps(x))
    print("LEADER_RESEARCH_RANKING")
    top=[]
    for a,v in historical.items():
        if a in excluded or a not in ids:
            continue
        s=snap.get(a) or {}
        m=s.get("metrics") or {}
        # Historical date-range and activity. NOT a portfolio economics score.
        if v["active_days"]<25 or v["pnl_closes"]<10:
            continue
        top.append((v["active_days"],v["closed_pnl_gross_usd"],a,v,s,m))
    top.sort(key=lambda x:(-x[0],-x[1]))
    for days,pnl,a,v,s,m in top[:32]:
        print(json.dumps({"wallet_id":ids[a],"alias":alias.get(a),"days":days,
             "fills":v["fills"],"earliest":datetime.fromtimestamp(v["earliest_ms"]/1000,UTC).date().isoformat(),
             "latest":datetime.fromtimestamp(v["latest_ms"]/1000,UTC).isoformat(),
             "source_gross_closed":round(pnl,2),"nov_fills":v["fills_nov"],
             "vike_7d_trades":m.get("trade_count"),
             "vike_7d_gross":m.get("total_realized_pnl"),
             "vike_7d_avg_hold_h":round(m["avg_duration_seconds"]/3600,2)
                if m.get("avg_duration_seconds") is not None else None}))
    print("STATUS HISTORICAL_SOURCE_ONLY no first-known follower capital or net PNL")
if __name__=="__main__":
    main()
