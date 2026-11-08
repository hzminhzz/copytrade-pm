"""Infer event-time quantities from FULL Vike fills bounded by closed trade cycles.

No future "max_size_token" is used. Since Vike does not supply native
startPosition, flat anchors are retrospectively inferred from completed trade
intervals and verified zero net signed fills. NOT native book evidence.
"""

from __future__ import annotations

from collections import Counter,defaultdict
from datetime import UTC,datetime
from hashlib import sha256
import json
from decimal import Decimal as D
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parent))
from research_vike_recovery_audit_20261108 import read  # noqa: E402
from research_t5_native_source_20261108 import native_inst  # noqa: E402

START=datetime(2026,7,1,tzinfo=UTC)
END=datetime(2026,11,7,tzinfo=UTC)


def parse(value:str)->datetime:
    when=datetime.fromisoformat(value.replace("Z","+00:00"))
    if when.tzinfo is None:
        raise ValueError("NAIVE_CLOCK")
    return when.astimezone(UTC)


def infer_with_trade_anchors(fills:list[dict], trades:list[dict]) -> tuple[list[dict],dict]:
    by_symbol=defaultdict(list)
    for f in fills:
        by_symbol[f["symbol"]].append(f)
    trade_by_symbol=defaultdict(list)
    for t in trades:
        if not (t.get("is_complete") and t.get("close_observed")):
            continue
        try:
            a,b=parse(t["open_ts"]),parse(t["close_ts"])
        except (KeyError,ValueError,TypeError):
            continue
        if START<=a<b<END and t.get("direction") in {"long","short"}:
            trade_by_symbol[t["symbol"]].append((a,b,t))
    valid=[]
    counts=Counter()
    for coin,obs in by_symbol.items():
        obs.sort(key=lambda f:(f["ts"],str(f["trade_id"])))
        pairs=sorted(trade_by_symbol.get(coin,[]),key=lambda x:(x[0],x[1]))
        try:
            inst=native_inst(coin)
        except ValueError:
            counts["unsupported_native_instrument"]+=len(obs)
            continue
        past_end=START
        for a,b,t in pairs:
            counts["evaluated_closed_trade_cycles"]+=1
            if a<=past_end:
                counts["overlap_with_prior_episode"]+=1
                past_end=max(past_end,b)
                continue
            # Independent cycle must not overlap any other episode for same coin.
            if any(a<o_b and o_a<b for o_a,o_b,_ in pairs if (o_a,o_b)!=(a,b)):
                counts["overlap_with_another_episode"]+=1
                past_end=max(past_end,b)
                continue
            ts_a=t["open_ts"]
            ts_b=t["close_ts"]
            # All observed fills within these bounds; exact opening/closing fill
            # is a required prerequisite for claiming an observed flat cycle.
            fragment=[f for f in obs if ts_a<=f["ts"]<=ts_b]
            if len(fragment)<2 or fragment[0]["ts"]!=ts_a or fragment[-1]["ts"]!=ts_b:
                counts["missing_exact_boundary_fills"]+=1
                past_end=b
                continue
            q=D("0")
            sample=[]
            wrong=False
            sign=1 if t["direction"]=="long" else -1
            for f in fragment:
                if f.get("side") not in {"buy","sell"}:
                    wrong=True
                    break
                try:
                    qty=D(str(f["size_token"]))
                    px=D(str(f["price"]))
                    if qty<=0 or px<=0 or not qty.is_finite() or not px.is_finite():
                        wrong=True
                        break
                except (ValueError,TypeError):
                    wrong=True
                    break
                q+=qty if f["side"]=="buy" else -qty
                if q*sign < -D("0.00000001"):
                    wrong=True
                    break
                sample.append({
                    "at":parse(f["ts"]),"symbol":coin,"inst":inst,
                    "source_qty_after":q,"source_after_notional":q*px,
                    "source_px":px,"event_id":str(f["trade_id"]),
                })
            if wrong:
                counts["invalid_path_or_direction"]+=1
            elif abs(q)>D("0.00000001"):
                counts["not_flat_on_closed_boundary"]+=1
            else:
                counts["valid_inferred_flat_to_flat_cycles"]+=1
                counts["valid_inferred_source_fills"]+=len(sample)
                valid.extend(sample)
            past_end=b
    valid.sort(key=lambda e:(e["at"],e["symbol"],e["event_id"]))
    counts["total_source_fills"]=len(fills)
    counts["selected_native_rows"]=len(valid)
    counts["total_closed_trade_rows"]=len(trades)
    counts["latest_fill_ms"]=int(max(parse(f["ts"]) for f in fills).timestamp()*1000) if fills else 0
    return valid,dict(counts)


def load_vike_inferred() -> tuple[dict[str,list[dict]],dict]:
    full, trades, metadata=read()
    output={}
    diagnostics={}
    for raw_name in ("REG179_FULL","REG267_FULL","REG238_FULL"):
        st=metadata[raw_name]
        if not st["fill_parts"]:
            continue
        n=max(st["fill_parts"])
        if sorted(st["fill_parts"])!=list(range(1,n+1)):
            continue
        if any(sorted(v)!=list(range(1,max(v)+1)) for v in st["fill_parts"].values()):
            continue
        has_final_cursor = st["fill_cursor"].get(n) is not None
        if has_final_cursor and raw_name!="REG238_FULL":
            continue
        alias=raw_name.replace("_FULL","")
        fill_rows=list(full[raw_name].values())
        if has_final_cursor:
            # A tail-only 238 window is NOT a complete July-to-Nov stream.
            # Its saved pages cover a continuous descending recent window.
            # Begin one calendar day *after* the oldest reached page to avoid
            # a partial first day and distinguish it from full-window wallets.
            anchor=datetime(2026,9,22,tzinfo=UTC)
            if not fill_rows or min(parse(x["ts"]) for x in fill_rows)>anchor:
                continue
            fill_rows=[x for x in fill_rows if parse(x["ts"])>=anchor]
        trade_rows=list(trades[alias].values())
        events,metrics=infer_with_trade_anchors(fill_rows,trade_rows)
        metrics["source_last_ms"]=metrics["latest_fill_ms"]
        metrics["vike_source_wallet_sha_collection"]=sha256(
            json.dumps(sorted(st["file_shas"]),sort_keys=True,separators=(",",":")).encode()
        ).hexdigest()
        metrics["pagination_complete_to_july1"]=not has_final_cursor
        metrics["window_start"]=("2026-09-22T00:00:00+00:00" if has_final_cursor else "2026-07-01T00:00:00+00:00")
        metrics["data_source_class"]=("VIKE_BOUNDED_TAIL_INFERRED_FLAT_ANCHOR_NOT_FULL_STUDY" if has_final_cursor else "VIKE_RETROSPECTIVE_INFERRED_FLAT_ANCHOR")
        output[alias]=events
        diagnostics[alias]=metrics
    return output,diagnostics


if __name__=="__main__":
    a,b=load_vike_inferred()
    for alias in sorted(a):
        print(alias,len(a[alias]),b[alias])
