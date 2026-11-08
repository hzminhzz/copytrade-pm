"""Consolidate retrospective T+5 wallet screens without inventing missing returns.

Produces one row per current, non-excluded SQLite wallet. Every row remains
scientifically unqualified, because source completeness / true first-known
follower receipt / actual broker fills are absent.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from hashlib import sha256
from pathlib import Path
import json
import sqlite3

import polars as pl

ROOT = Path("/home/quant/.local/share/copytrade/reports/fastpass-july-nov-recovery-20261108")
DB = "file:/home/quant/.local/share/copytrade/registry/wallet_registry.sqlite?mode=ro"
SOURCES = {
    "native": ROOT / "t5-native-candidates-r3.json",
    "native_all": ROOT / "t5-native-all-r3.json",
    "vike_inferred": ROOT / "t5-vike-inferred-r3.json",
}


def _read() -> tuple[dict, dict]:
    receipts = {}
    inputs = {}
    for name, path in SOURCES.items():
        raw = path.read_bytes()
        doc = json.loads(raw)
        if doc.get("scientifically_qualified") is not False or doc.get("actual_follower_fills") is not False:
            raise ValueError("UNEXPECTED_AUTHORITY_CLAIM")
        if doc.get("clock_quality") != "HISTORICAL_EXCHANGE_ORACLE_NOT_FIRST_KNOWN":
            raise ValueError("UNKNOWN_CLOCK_BASIS")
        receipts[name] = doc
        inputs[name] = sha256(raw).hexdigest()
    return receipts, inputs


def _current_registry() -> list[dict]:
    db = sqlite3.connect(DB, uri=True)
    rows = db.execute("select wallet_id,lower(address) from wallets").fetchall()
    excluded = {id for (id,) in db.execute("select distinct wallet_id from exclusions")}
    pref = {"sqlite_primary":0, "research_v2":1, "ml4t_strict":2, "frozen_pm01":3}
    aliases = defaultdict(list)
    for wid, alias, namespace in db.execute(
        "select wallet_id,alias,namespace from wallet_aliases"
    ):
        aliases[wid].append((pref.get(namespace,9),alias))
    source_rows = []
    for wid,address in rows:
        if wid in excluded:
            continue
        choices=sorted(aliases.get(wid,[]))
        src_name = choices[0][1] if choices else f"REG{wid}"
        source_rows.append({"registry_id":wid,"wallet_alias":src_name})
    return source_rows


def _scenario(receipt:dict, wallet:str, m:int):
    matches=[x for x in receipt["results"] if x.get("wallet")==wallet and x.get("cost_multiplier")==m]
    if len(matches)>1:
        raise ValueError("DUPLICATE_WALLET_SCENARIO")
    return matches[0] if matches else None


def _score_record(wallet: str, receipts:dict):
    # Prefer exact observed native startPosition for IDs with such source.
    # Later Vike fill-inferred anchors remain a lower-authority alternative.
    modes = (
        ("native", receipts["native_all"]),
        ("native", receipts["native"]),
        ("vike_inferred", receipts["vike_inferred"]),
    )
    a = next((r for name,doc in modes for r in [_scenario(doc,wallet,1)]
              if name=="native" and r and r.get("net_usd_screen_only") is not None), None)
    if a is None:
        a = _scenario(receipts["vike_inferred"],wallet,1)
        if a is not None and a.get("status") == "NO_COMPLETE_OBSERVED_POSITION_SOURCE":
            a=None
        if a:
            base="vike_inferred"
        else:
            a=_scenario(receipts["native_all"],wallet,1)
            base="native"
    else:
        base="native"
    if a is None:
        return {"source_mode":None,"status":"NO_IMMUTABLE_LOCAL_INPUT","sim_net_1x":None}
    chosen = receipts["vike_inferred"] if base=="vike_inferred" else receipts["native"]
    rows = {m:_scenario(chosen,wallet,m) for m in (1,2,3)}
    if base=="native":
        # The comprehensive cohort has only 1x; the focused 1x/2x/3x is used
        # only when its named 1x matches exactly (same source/cost run).
        all_row=_scenario(receipts["native_all"],wallet,1)
        focus_row=_scenario(receipts["native"],wallet,1)
        if all_row is not None and focus_row is not None:
            if all_row.get("net_usd_screen_only") != focus_row.get("net_usd_screen_only"):
                raise ValueError("NATIVE_REPLAY_1X_REPRO_MISMATCH:"+wallet)
        if focus_row is None:
            rows[1]=all_row
    vals={}
    for m in (1,2,3):
        v=rows.get(m)
        complete=bool(v and v.get("selected_episode_replay_completed"))
        # Pod-loss stop is valid risk outcome when flattened, but not alpha.
        vals[f"sim_net_{m}x"]=float(v["net_usd_screen_only"]) if complete and v.get("net_usd_screen_only") is not None else None
    primary = rows.get(1) or a
    eligible=all(vals.get(f"sim_net_{m}x") is not None for m in (1,2,3))
    risk_stopped=any((rows.get(m) or {}).get("status")=="STOPPED_BY_POD_RISK" or (rows.get(m) or {}).get("contract_breached") for m in (1,2,3))
    robust_net=min(vals.values()) if eligible and not risk_stopped else None
    coverage=primary.get("native_selected_fill_fraction")
    qualifying=(
        eligible and robust_net is not None and robust_net>0
        and coverage is not None and coverage>=0.80
        and primary.get("orders",0)>=20
        and all((rows.get(m) or {}).get("status","").startswith(("COMPLETED_NATIVE","COMPLETED_VIKE"))
                for m in (1,2,3))
        and all(not (rows.get(m) or {}).get("unverified_execution",True) for m in (1,2,3))
        and bool(primary.get("last_local_source_fill_at"))
        and primary["last_local_source_fill_at"]>="2026-11-06"
    )
    # Even "qualifying" would only mean the numerical subset screen, NOT an
    # actual complete first-known follower account / scientific qualification.
    return {
        "source_mode":base,
        "status":primary["status"],
        "partial_net_at_block_usd":float(primary["partial_net_at_block_usd"])
             if primary.get("partial_net_at_block_usd") is not None else None,
        **vals,
        "worst_cost_net":robust_net,
        "risk_stopped_any_scenario":bool(risk_stopped),
        "numerical_subset_screen_pass":bool(qualifying),
        "observed_source_selected_fraction":coverage,
        "order_count_1x":primary.get("orders"),
        "single_shot_capacity_rejected_1x":primary.get("single_shot_capacity_rejected"),
        "forced_exit_over_capacity_1x":primary.get("forced_exit_over_research_capacity"),
        "zero_volume_forced_exit_1x":primary.get("unverified_zero_volume_exit"),
        "gross_cap_rejected_1x":primary.get("gross_cap_rejected"),
        "pod_stop_1x":primary.get("pod_stops"),
        "max_drawdown_usd_1x":float(primary["max_drawdown_usd"]) if primary.get("max_drawdown_usd") is not None else None,
        "last_source_fill":primary.get("last_local_source_fill_at"),
        "last_replay_at":primary.get("last_replay_at"),
        "market_missing_detail":primary.get("market_missing_detail"),
        "k_30d_pretest":primary.get("k"),
    }


def main() -> None:
    receipts, hashes = _read()
    registry = _current_registry()
    all_rows = []
    for item in registry:
        record = _score_record(item["wallet_alias"],receipts)
        all_rows.append({**item,**record,"scientifically_qualified":False,
                         "actual_follower_fills":False,"trading_authorized":False})
    if not all_rows:
        raise ValueError("EMPTY_REGISTRY")
    df = pl.DataFrame(all_rows, infer_schema_length=None).with_columns(
        pl.col("sim_net_1x").rank("ordinal", descending=True).alias("conditional_rank_1x"),
        pl.col("worst_cost_net").rank("ordinal", descending=True).alias("conditional_rank_worst_cost"),
    )
    df = df.sort(["conditional_rank_worst_cost","conditional_rank_1x"],nulls_last=True)
    summary={
        "schema":"copytrade_t5_historical_rankings_v1",
        "registry_count_non_excluded":len(registry),
        "source_receipt_sha256":hashes,
        "source_clock_basis":"HISTORICAL_EXCHANGE_ORACLE",
        "ranking_basis":"PM03_T5_SINGLE_SHOT_BURST_COST_SCENARIOS",
        "realized_follower_pnl_available":False,
        "scientifically_qualified":False,
        "trading_authorized":False,
        "model_numeric_profit_target_reached_count":sum(1 for doc in receipts.values() for x in doc["results"] if x.get("pass_time_oracle") is not None),
        "status_counts":dict(Counter(x["status"] for x in all_rows)),
        "scenario_complete_count":int(df["worst_cost_net"].is_not_null().sum()),
        "numerically_passed_subset_screen_count":int(df["numerical_subset_screen_pass"].sum()),
        "screens_not_qualification":"Source flat-to-flat selection is hindsight and may omit open losing episodes; missing market paths null.",
    }
    target=ROOT / "t5-rankings-20261108-v3"
    target.mkdir(mode=0o700,exist_ok=False)
    (target/"wallet_rankings.csv").write_bytes(df.write_csv().encode())
    (target/"receipt.json").write_bytes((json.dumps(summary,sort_keys=True,indent=2)+"\n").encode())
    # Use restrictive mode even under permissive caller umask.
    (target/"wallet_rankings.csv").chmod(0o600)
    (target/"receipt.json").chmod(0o600)
    print("SUMMARY",json.dumps(summary,sort_keys=True))
    print("TOP_CONDITIONAL")
    for r in df.filter(pl.col("worst_cost_net").is_not_null()).head(20).iter_rows(named=True):
        print(json.dumps({k:r.get(k) for k in (
            "wallet_alias","status","sim_net_1x","sim_net_2x","sim_net_3x",
            "worst_cost_net","observed_source_selected_fraction",
            "order_count_1x","single_shot_capacity_rejected_1x","forced_exit_over_capacity_1x",
            "numerical_subset_screen_pass","last_source_fill"
        )},sort_keys=True))
    print("PRIVATE_ARTIFACT",str(target))


if __name__=="__main__":
    main()
