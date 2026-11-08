"""Exact native startPosition -> signed after position historical source compiler.

Only observed complete zero-to-zero episodes. Never read future trade max_size,
wallet current equity or vendor realized PnL to build follower exposure.
"""

from __future__ import annotations

from collections import Counter,defaultdict
from datetime import UTC,datetime,timedelta
from decimal import Decimal as D
from pathlib import Path
import itertools
import math
import sqlite3
import sys

sys.path.insert(0,str(Path(__file__).resolve().parent))
from research_fastpass_history_20261108 import read_source  # noqa: E402
from copytrade_pm.pm_offline_repository import native_instrument  # noqa: E402
from copytrade_pm.pm03_account import Instrument  # noqa: E402
from copytrade_pm.pm_offline_manifest import ManifestInvalid  # noqa: E402

DB="file:/home/quant/.local/share/copytrade/registry/wallet_registry.sqlite?mode=ro"
START=datetime(2026,7,1,tzinfo=UTC)
END=datetime(2026,11,7,tzinfo=UTC)

def native_inst(coin: str) -> Instrument:
    native = native_instrument(coin)
    p=native.split(":")
    if len(p)!=5:
        raise ValueError("NON_NATIVE_PERP")
    return Instrument("hyperliquid",":".join(p[1:4]),p[4])

def native_events_from_coin(rows:list[dict]) -> tuple[list[dict],dict]:
    """Certified *subset* only: starts at observed flat and ends at observed flat.

    Reject mismatched, cross-through and ambiguous paths; no inferred opening
    inventory, no self-healed unknown segments. Returns exact position after
    each original fill of fully observed flat-to-flat episode.
    """
    if not rows:
        return [],{}
    coins={x["coin"] for x in rows}
    if len(coins)!=1:
        raise ValueError("MIXED_INSTRUMENT_CHAIN")
    symbol=next(iter(coins))
    try:
        inst=native_inst(symbol)
    except (ValueError,ManifestInvalid):
        return [],{"unsupported_market_coin_fills":len(rows)}
    rows=sorted(rows,key=lambda x:(x["ms"],str(x["tid"])))
    out=[]
    active=[]
    previous=None
    counts=Counter()
    for row in rows:
        if row["before"] is None:
            counts["unknown_position_before"]+=1
            active=[]
            previous=None
            continue
        try:
            before=D(row["before"])
            qty=D(str(row["qty"]))
            px=D(str(row["px"]))
            after=before+qty*(1 if row["side"]=="B" else -1)
            if not (before.is_finite() and qty.is_finite() and px.is_finite() and qty>0 and px>0):
                raise ValueError("NONFINITE_FILL")
        except (ValueError,ArithmeticError,TypeError):
            counts["malformed_native_fill"]+=1
            active=[]
            previous=None
            continue
        if previous is not None and abs(before-previous)>D("0.00000001")*max(D("1"),abs(previous)):
            counts["unlinked_position_chain"]+=1
            if active:
                counts["discarded_interrupted_episode"]+=1
            active=[]
        previous=after
        if before*after<0:
            counts["crossed_through_zero"]+=1
            if active:
                counts["discarded_crossed_episode"]+=1
            active=[]
            continue
        observed={
            "at":datetime.fromtimestamp(row["ms"]/1000,tz=UTC),
            "symbol":symbol,
            "inst":inst,
            "source_after_notional":after*px,
            "source_qty_after":after,
            "source_px":px,
            "event_id":str(row["tid"]),
        }
        if not active:
            if before==0 and after!=0:
                active=[observed]
            else:
                counts["left_censored_fill"]+=1
            continue
        active.append(observed)
        if after==0:
            if active[0]["at"]>=START and active[-1]["at"]<END:
                out.extend(active)
                counts["complete_flat_to_flat_episodes"]+=1
                counts["complete_native_fills"]+=len(active)
            else:
                counts["episode_outside_window"]+=1
            active=[]
    if active:
        counts["right_censored_episode"]+=1
        counts["right_censored_native_fills"]+=len(active)
    return out,dict(counts)

def load_wallet_native() -> tuple[dict[str,list[dict]],dict]:
    df,src,counts=read_source()
    db=sqlite3.connect(DB,uri=True)
    ids={addr:wid for wid,addr in db.execute("select wallet_id,lower(address) from wallets")}
    exclusions={addr for (addr,) in db.execute(
        "select lower(w.address) from exclusions x join wallets w on w.wallet_id=x.wallet_id")}
    aliases={}
    prefs={"sqlite_primary":0,"research_v2":1,"ml4t_strict":2,"frozen_pm01":3}
    for addr,n,alias in db.execute(
        "select lower(w.address),a.namespace,a.alias from wallet_aliases a join wallets w on a.wallet_id=w.wallet_id"):
        key=(prefs.get(n,9),alias)
        if addr not in aliases or key<aliases[addr]:
            aliases[addr]=key
    walletrows={}
    diagnostics={}
    for group in df.sort(["address","coin","ms","tid"]).partition_by("address",maintain_order=True):
        address=group["address"][0]
        if address not in ids or address in exclusions:
            continue
        ident=aliases[address][1] if address in aliases else f"REG{ids[address]}"
        out=[]
        skipped=Counter()
        for coin, coins in itertools.groupby(group.iter_rows(named=True),key=lambda x:x["coin"]):
            rows=list(coins)
            clean,metrics=native_events_from_coin(rows)
            out.extend(clean)
            skipped.update(metrics)
        out.sort(key=lambda x:(x["at"],x["symbol"],x["event_id"]))
        walletrows[ident]=out
        skipped["total_source_fills"]=group.height
        skipped["selected_native_rows"]=len(out)
        skipped["source_active_days"]=group["ms"].n_unique()
        skipped["source_last_ms"]=int(group["ms"].max())
        skipped["source_first_ms"]=int(group["ms"].min())
        diagnostics[ident]=dict(skipped)
    return walletrows,diagnostics


def training_k_native(events: list[dict]) -> tuple[D,datetime,int,D]:
    if not events:
        return D("0"),END,0,D("0")
    origin=min(e["at"] for e in events).replace(hour=0,minute=0,second=0,microsecond=0)
    cut=origin+timedelta(days=30)
    train=[e for e in events if e["at"]<cut]
    if len(train)<20:
        return D("0"),cut,len(train),D("0")
    state=defaultdict(lambda:D("0"))
    grosses=[]
    for e in train:
        state[e["symbol"]]=e["source_after_notional"]
        gross=sum(abs(x) for x in state.values())
        if gross>0:
            grosses.append(float(gross))
    if not grosses:
        return D("0"),cut,len(train),D("0")
    grosses.sort()
    p90=D(str(grosses[min(len(grosses)-1,math.ceil(len(grosses)*0.90)-1)]))
    return min(D("1"),D("2000")/p90),cut,len(train),p90


def build_events_native(
    events: list[dict], test_start: datetime, delay_minutes: int,
) -> tuple[dict[datetime, dict[str, D]], dict]:
    """Wait from the FIRST observed change, collapse the full wallet burst.

    A new burst cannot start until the earlier five-minute decision. All
    changes already observed strictly BEFORE the decision minute are applied
    to the same snapshot. Never split a single burst into several orders.
    """
    if delay_minutes not in {0, 5, 10}:
        raise ValueError("UNSUPPORTED_DELAY_MINUTES")
    known_book: dict[str, D] = {}
    eligible: list[tuple[datetime, str, str, D]] = []
    stats = Counter()
    for event in sorted(events, key=lambda e: (e["at"], e["symbol"], e["event_id"])):
        when = event["at"]
        symbol = event["symbol"]
        notional = event["source_after_notional"]
        if when < test_start:
            known_book[symbol] = notional
        elif when < END:
            eligible.append((when, symbol, event["event_id"], notional))
            stats["selected_source_fills"] += 1
    # Research-start book: only previously observed source positions. This
    # initial catch-up is a separate simulated signal at the frozen cutoff.
    for symbol, notional in known_book.items():
        if notional:
            eligible.append((test_start, symbol, "initial_book", notional))
            stats["initial_source_positions"] += 1

    eligible.sort(key=lambda e: (e[0], e[1], e[2]))
    def due_after(t: datetime) -> datetime:
        ms = int(t.timestamp() * 1000) + delay_minutes * 60_000
        return datetime.fromtimestamp(((ms // 60_000) + 1) * 60, tz=UTC)

    batches: dict[datetime, dict[str, D]] = {}
    pending: dict[str, D] = {}
    due: datetime | None = None
    for when, symbol, _event_id, notional in eligible:
        # A source event at the exact decision time is NOT known at its open.
        if due is not None and when >= due:
            if due < END:
                batches[due] = dict(sorted(pending.items()))
            else:
                stats["right_censored_due"] += len(pending)
            pending = {}
            due = None
        if due is None:
            due = due_after(when)
        pending[symbol] = notional
    if due is not None:
        if due < END:
            batches[due] = dict(sorted(pending.items()))
        else:
            stats["right_censored_due"] += len(pending)
    stats["batches"] = len(batches)
    stats["coalesced_source_events"] = max(0, len(eligible) - len(batches))
    return dict(sorted(batches.items())), dict(stats)
