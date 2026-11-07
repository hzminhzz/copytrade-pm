"""Rank current-registry candidates with long local fills and seven-day Vike checks.

This is historical source selection, NOT an executable follower PM account simulation.
"""
from __future__ import annotations
from datetime import UTC,datetime
import json
import sqlite3
import polars as pl

from research_fastpass_history_20261108 import read_source,alias_data,DB
from research_vike_recovery_audit_20261108 import read as read_vike

def main():
  db=sqlite3.connect(DB,uri=True)
  alias,ids,excluded=alias_data(db)
  src,_,_=read_source()
  base=src.with_columns(pl.from_epoch("ms",time_unit="ms").dt.replace_time_zone("UTC").alias("when"))
  base=base.group_by("address").agg(
    pl.len().alias("n_fills"),pl.col("ms").min().alias("first_ms"),pl.col("ms").max().alias("last_ms"),
    pl.col("when").dt.date().n_unique().alias("days"),pl.col("closed_pnl").sum().alias("gross"),
    (pl.col("closed_pnl")!=0).sum().alias("close_fills"),
    (pl.col("closed_pnl").filter(pl.col("when")<datetime(2026,10,1,tzinfo=UTC)).sum()).alias("q3gross"),
    (pl.col("closed_pnl").filter(pl.col("when")>=datetime(2026,10,1,tzinfo=UTC)).sum()).alias("q4gross"),
    pl.col("closed_pnl").filter(pl.col("when")>=datetime(2026,11,1,tzinfo=UTC)).sum().alias("novpartial"),
  )
  hist={x["address"]:x for x in base.iter_rows(named=True)}
  summary=json.load(open("/tmp/vike7d_432.json"))
  vike_fills,vike_trades,vike_state=read_vike()
  special={}
  for a in ("REG179","REG267","REG238"):
    if not vike_state[a].get("file_shas"):
      continue
    wid=int(a[3:])
    address=db.execute("select lower(address) from wallets where wallet_id=?",(wid,)).fetchone()[0]
    trades=[x for x in vike_trades[a].values() if x.get("is_complete") and x.get("close_observed")]
    if trades:
      special[address]={"days":len(set(x["close_ts"][:10] for x in trades)),
       "n_fills":len(vike_fills[a]),"first_ms":int(datetime.fromisoformat(min(x["close_ts"] for x in trades)).timestamp()*1000),
       "last_ms":int(datetime.fromisoformat(max(x["close_ts"] for x in trades)).timestamp()*1000),
       "gross":sum(float(x["realized_pnl"])-float(x["total_fee"]) for x in trades),
       "q3gross":sum(float(x["realized_pnl"])-float(x["total_fee"]) for x in trades if x["close_ts"]<"2026-10-01"),
       "q4gross":sum(float(x["realized_pnl"])-float(x["total_fee"]) for x in trades if x["close_ts"]>="2026-10-01"),
       "novpartial":sum(float(x["realized_pnl"])-float(x["total_fee"]) for x in trades if x["close_ts"]>="2026-11-01"),
       "median_h":float(__import__("statistics").median(x["duration_seconds"]/3600 for x in trades)),
       "close_fills":len(trades),"special_vike_trades":True,
       }
  all_src={**hist,**special}
  tiers={"strict":[],"balanced":[],"relaxed":[]}
  candidates=[]
  for a,m in all_src.items():
    if a in excluded or a not in ids:
      continue
    s=summary.get(a) or {}
    met=s.get("metrics") or {}
    if not met:
      continue
    equity=float((s.get("equity") or {}).get("account_value") or 0)
    trades7=float(met.get("trade_count") or 0)
    pnl7=float(met.get("total_realized_pnl") or 0)
    dd=met.get("max_drawdown_pct")
    cdd=met.get("current_drawdown_pct")
    if dd is None or cdd is None:
      continue
    dd=float(dd)
    cdd=float(cdd)
    hold_h=float(met.get("avg_duration_seconds") or 0)/3600
    open_unreal=float((s.get("open_positions") or {}).get("unrealized_pnl") or 0)
    if equity<1000 or m["days"]<25 or m["gross"]<=0 or trades7<3 or pnl7<=0 or hold_h<=0:
      continue
    if m["first_ms"]>int(datetime(2026,9,1,tzinfo=UTC).timestamp()*1000):
      continue
    if float(m["q3gross"])<=0 or float(m["q4gross"])<=0:
      continue
    metrics={"wallet_id":ids[a],"alias":alias.get(a) or f"REG{ids[a]}", "days":m["days"],
      "historical_source_net_if_vike_else_gross":round(m["gross"],2),
      "source_q3":round(float(m["q3gross"]),2),"source_q4":round(float(m["q4gross"]),2),
      "trades7":int(trades7),"pnl7":round(pnl7,2),"hold7h":round(hold_h,2),
      "vendorDD":round(dd,2),"vendorCurrentDD":round(cdd,2),"eq":round(equity,2),
      "unreal_pct_equity":round(100*open_unreal/equity,2),"long_trade_median_h":round(m.get("median_h",0),2) if m.get("median_h") else None,
      "source_kind":"VIKE_COMPLETE_CLOSED_TRADE" if m.get("special_vike_trades") else "LOCAL_PARTIAL_FILLS",
      "first_ms":m["first_ms"]}
    if hold_h<=24 and dd<=20 and cdd<=12 and open_unreal/equity>=-.08 and trades7>=5:
      tiers["strict"].append(metrics)
    if hold_h<=36 and dd<=35 and cdd<=20 and open_unreal/equity>=-.15 and trades7>=5:
      tiers["balanced"].append(metrics)
    if hold_h<=72 and dd<=55 and cdd<=30 and open_unreal/equity>=-.25 and trades7>=3:
      tiers["relaxed"].append(metrics)
    candidates.append(metrics)
  print("TIERS", {k:len(v) for k,v in tiers.items()})
  for k in ("strict","balanced","relaxed"):
    print("TIER",k)
    for row in sorted(tiers[k],key=lambda x:(-x["trades7"],-x["pnl7"]))[:32]:
      print(json.dumps(row,sort_keys=True))
  print("TOP_POSITIVE_HISTORY",len(candidates))
  for row in sorted(candidates,key=lambda x:(-x["trades7"],-x["pnl7"]))[:25]:
    print(json.dumps(row,sort_keys=True))
if __name__=="__main__":
  main()
