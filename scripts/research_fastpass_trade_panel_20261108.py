"""Polars historical source-manager panel and candidate diversification diagnostics.

Source realized after source fees, not follower fixed-k net PnL or account MTM.
"""
from __future__ import annotations
from datetime import datetime,date,timedelta
import json
import polars as pl
from research_vike_recovery_audit_20261108 import read

SCOPE=("REG238","REG267","REG179","M56","M22","M43")

def main():
  fills,trades,state=read()
  rows=[]
  for a in SCOPE:
    for v in trades.get(a,{}).values():
      if not (v.get("is_complete") and v.get("close_observed")):
        continue
      ts=datetime.fromisoformat(v["close_ts"])
      rows.append({"alias":a,"closed":ts,"close_day":ts.date(),
        "symbol":v["symbol"],"direction":v["direction"],
        "hold_h":v["duration_seconds"]/3600,"pnl_net":float(v["realized_pnl"])-float(v["total_fee"]),
        "pnl_gross":float(v["realized_pnl"]),"source_fee":float(v["total_fee"]),
        "n_fills":v["fill_count"],"volume_usd":v["volume_usd"]})
  frame=pl.DataFrame(rows).with_columns(pl.col("closed").dt.truncate("1mo").alias("month"))
  print("TOTAL",frame.height)
  print("MONTHLY")
  for x in frame.group_by("alias","month").agg(pl.len().alias("trades"),pl.col("pnl_net").sum().alias("net"),
         pl.col("hold_h").median().alias("med_h"),(pl.col("pnl_net")>0).sum().alias("winning_trades")).sort(["alias","month"]).iter_rows(named=True):
    print(json.dumps({**x,"net":round(x["net"],2),"med_h":round(x["med_h"],2)},default=str))
  days=frame.group_by("alias","close_day").agg(pl.col("pnl_net").sum().alias("net"),
                                                  pl.len().alias("trades"))
  print("WALLET_SUMMARY")
  for a in SCOPE:
    sub=frame.filter(pl.col("alias")==a)
    d=days.filter(pl.col("alias")==a)
    d7=d.filter(pl.col("close_day")>=date(2026,11,1))
    print(json.dumps({"alias":a,"trade_count":sub.height,"net_source_closed":round(sub["pnl_net"].sum(),2),
      "fee_source":round(sub["source_fee"].sum(),2),"median_hold_h":round(sub["hold_h"].median(),2),
      "profit_days":d.filter(pl.col("net")>0).height,
      "loss_days":d.filter(pl.col("net")<0).height,
      "worst_daily_source_close":round(d["net"].min(),2),
      "recent7_net":round(d7["net"].sum(),2),
      "recent7_wins":d7.filter(pl.col("net")>0).height,
      "recent7_losses":d7.filter(pl.col("net")<0).height,
      "recent7_worst_day":round(d7["net"].min(),2) if d7.height else None,
      "max_trade_loss":round(sub["pnl_net"].min(),2),
      "n_symbols":sub["symbol"].n_unique(),
      "top4_symbols":sub.group_by("symbol").agg(pl.len().alias("n")).sort("n",descending=True).head(4)["symbol"].to_list()},default=str))
  dt=[date(2026,7,1)+timedelta(days=i) for i in range(130)]
  panel=pl.DataFrame({"close_day":dt})
  for a in SCOPE:
    part=days.filter(pl.col("alias")==a).select("close_day",pl.col("net").alias(a))
    panel=panel.join(part,on="close_day",how="left").with_columns(pl.col(a).fill_null(0))
  print("DAILY_SOURCE_CLOSED_PNL_CORRELATIONS")
  for i,a in enumerate(SCOPE):
    for b in SCOPE[i+1:]:
      corr=panel.select(pl.corr(a,b)).item()
      print(a,b,round(corr,3) if corr is not None else None)
  three=["REG238","REG267","REG179"]
  panel=panel.with_columns(sum(pl.col(a) for a in three).alias("joint_source_net"))
  print("TRIO",{
    "sum_net_source_closed":round(panel["joint_source_net"].sum(),2),
    "seven_day_net":round(panel.filter(pl.col("close_day")>=date(2026,11,1))["joint_source_net"].sum(),2),
    "seven_day_daily_source":[{"date":v["close_day"].isoformat(),"pnl_net":round(v["joint_source_net"],2)} for v in panel.filter(pl.col("close_day")>=date(2026,11,1)).iter_rows(named=True)],
    "trading_daily_joint_worst":round(panel["joint_source_net"].min(),2),
    "joint_close_day_green":panel.filter(pl.col("joint_source_net")>0).height,
    "joint_close_day_red":panel.filter(pl.col("joint_source_net")<0).height,
  })
  print("NOT_A_REAL_FOLLOWER_PORTFOLIO no synchronized account MTM, no first known, no funding, no execution cost, no fixed-k")
if __name__=="__main__":
  main()
