"""Audit staged Vike MCP tail-fill and closed-trade pages, without source mutation.

Source timestamps are retrospective and are not first-local-known follower receipts.
"""
from __future__ import annotations
from collections import defaultdict, Counter
from datetime import UTC, datetime
from hashlib import sha256
import json
from pathlib import Path
import re
import sqlite3
import statistics


ROOT=Path(".workspace")
DB="file:/home/quant/.local/share/copytrade/registry/wallet_registry.sqlite?mode=ro"
SUM=Path("/tmp/vike7d_432.json")
FILL_RE=re.compile(r"vike-recovery-20261108-(.+?)(?:-p(\d+)-c(\d+))?\.json$")
TRADE_RE=re.compile(r"vike-trades-20261108-(.+?)-p(\d+)-c(\d+)\.json$")

def dt(s):
    return datetime.fromisoformat(s.replace("Z","+00:00")).astimezone(UTC)

def read():
    fills=defaultdict(dict)
    trades=defaultdict(dict)
    state=defaultdict(lambda:{"fill_parts":defaultdict(set),"fill_cursor":{},"fills_window":None,
       "trade_parts":defaultdict(set),"trade_cursor":{},"trades_window":None,"file_shas":[],"conflicts":0})
    for p in sorted(ROOT.glob("vike-recovery-20261108-*.json")):
        m=FILL_RE.fullmatch(p.name)
        if not m:
            continue
        alias,page,chunk=m.groups()
        page=int(page or 1)
        chunk=int(chunk or 1)
        obj=json.loads(p.read_text())
        items=(obj.get("data") or {}).get("items",[]) if "data" in obj else obj.get("items",[])
        cursor=(obj.get("data") or {}).get("nextCursor") if "data" in obj else obj.get("nextCursor")
        s=state[alias]
        s["fill_parts"][page].add(chunk)
        s["fill_cursor"][page]=cursor
        s["fills_window"]=(obj["requested_start"],obj["requested_end"])
        s["file_shas"].append((p.name,sha256(p.read_bytes()).hexdigest()))
        for e in items:
            try:
                t=dt(e["ts"])
                assert dt(obj["requested_start"])<=t<dt(obj["requested_end"])
                assert float(e["size_token"])>0 and float(e["price"])>0
                assert e["side"] in {"buy","sell"}
                key=(str(e["symbol"]),str(e["trade_id"]))
            except (KeyError,ValueError,AssertionError):
                s["conflicts"]+=1
                continue
            before=fills[alias].get(key)
            if before is not None and before !=e:
                s["conflicts"]+=1
            else:
                fills[alias][key]=e
    for p in sorted(ROOT.glob("vike-trades-20261108-*.json")):
        m=TRADE_RE.fullmatch(p.name)
        if not m:
            continue
        alias,page,chunk=m.groups()
        page=int(page)
        chunk=int(chunk)
        obj=json.loads(p.read_text())
        s=state[alias]
        s["trade_parts"][page].add(chunk)
        s["trade_cursor"][page]=obj.get("nextCursor")
        s["trades_window"]=(obj["requested_start"],obj["requested_end"])
        s["file_shas"].append((p.name,sha256(p.read_bytes()).hexdigest()))
        for t in obj.get("trades",[]):
            try:
                assert dt(obj["requested_start"])<=dt(t["close_ts"])<dt(obj["requested_end"])
                key=(t["symbol"],t["direction"],t["open_ts"],t["close_ts"])
            except (KeyError,ValueError,AssertionError):
                s["conflicts"]+=1
                continue
            before=trades[alias].get(key)
            if before is not None and before!=t:
                s["conflicts"]+=1
            else:
                trades[alias][key]=t
    return fills,trades,state

def main():
    fills,trades,state=read()
    db=sqlite3.connect(DB,uri=True)
    identities={}
    for a,wa,wid in db.execute("select lower(w.address),wa.alias,w.wallet_id from wallets w join wallet_aliases wa on w.wallet_id=wa.wallet_id"):
        identities[wa]=(wid,a)
    for wid in [179,238,267]:
        identities[f"REG{wid}"]=(wid,db.execute("select lower(address) from wallets where wallet_id=?",(wid,)).fetchone()[0])
    snap=json.loads(SUM.read_text()) if SUM.exists() else {}
    print("RECOVERED",len(fills),"wallets, ",sum(len(v) for v in fills.values()),"unique raw fill ids; ",sum(len(v) for v in trades.values()),"distinct closed trades")
    for alias in sorted(state):
        s=state[alias]
        if s["conflicts"]:
            raise RuntimeError(f"Vike data conflicts for {alias}: {s['conflicts']}")
        for kind in ("fill","trade"):
            chunks=s[f"{kind}_parts"]
            cursor=s[f"{kind}_cursor"]
            if chunks:
                assert list(sorted(chunks))==list(range(1,max(chunks)+1)),(alias,kind,"missing_pages")
                for page,ks in chunks.items():
                    assert sorted(ks)==list(range(1,max(ks)+1)),(alias,kind,"missing_chunks")
            complete=bool(chunks) and cursor[max(chunks)] is None
            if kind=="fill":
                s["fills_complete"]=complete
            else:
                s["trades_complete"]=complete
        wid,address=identities.get(alias,(None,None))
        native=snap.get(address,{}) or {}
        v=sorted(fills.get(alias,{}).values(),key=lambda v:v["ts"])
        t=sorted(trades.get(alias,{}).values(),key=lambda t:t["close_ts"])
        cf=Counter(f["fee_token"] for f in v)
        gross=sum(float(f["closed_pnl"]) for f in v)
        known_usdc=sum(float(f["fee"]) for f in v if f["fee_token"] in {"USDC","USD"})
        nov=[f for f in v if dt(f["ts"])>=datetime(2026,11,1,tzinfo=UTC)]
        nov_gross=sum(float(f["closed_pnl"]) for f in nov)
        durations=[t2["duration_seconds"]/3600 for t2 in t if t2.get("duration_seconds") is not None]
        valid_t=[x for x in t if x.get("is_complete") and x.get("close_observed")]
        t7=[x for x in valid_t if dt(x["close_ts"])>=datetime(2026,11,1,tzinfo=UTC)]
        t7net=sum(float(x["realized_pnl"])-float(x["total_fee"]) for x in t7)
        tnet=sum(float(x["realized_pnl"])-float(x["total_fee"]) for x in valid_t)
        daily=defaultdict(float)
        for x in t7:
            daily[x["close_ts"][:10]]+=float(x["realized_pnl"])-float(x["total_fee"])
        print(json.dumps({"wallet":alias,"registry_wallet_id":wid,
          "vike_fills":len(v),"fills_min":v[0]["ts"] if v else None,"fills_max":v[-1]["ts"] if v else None,
          "fills_window_complete":s.get("fills_complete"),"nov_fills":len(nov),"nov_gross_close":round(nov_gross,2),
          "gross_close_in_recovery_window":round(gross,2),"fee_usdc_only":round(known_usdc,2),
          "fee_units":dict(cf),
          "closed_trades_from_jul1":len(t),"complete_closed_trades":len(valid_t),"trade_history_complete":s.get("trades_complete"),
          "median_hold_h":round(statistics.median(durations),2) if durations else None,
          "trades_le24h_fraction":round(sum(z<=24 for z in durations)/len(durations),3) if durations else None,
          "source_trade_net_including_fees":round(tnet,2) if valid_t else None,
          "nov7d_trades":len(t7),"nov7d_net_closed":round(t7net,2),
          "profitable_close_days":sum(x>0 for x in daily.values()),"losing_close_days":sum(x<0 for x in daily.values()),
          "worst_close_day":round(min(daily.values()),2) if daily else None,
          "vendor7_current_dd":(native.get("metrics") or {}).get("current_drawdown_pct"),
          "vendor7_alltime_dd":(native.get("metrics") or {}).get("max_drawdown_pct"),
          "vendor_account_value":(native.get("equity") or {}).get("account_value"),
          "vendor_open_unreal":(native.get("open_positions") or {}).get("unrealized_pnl")},
          default=str))
    print("CAUSAL_STATUS HISTORICAL_RETROSPECTIVE_ONLY")
if __name__=="__main__":
    main()
