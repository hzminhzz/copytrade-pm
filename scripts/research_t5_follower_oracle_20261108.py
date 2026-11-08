"""Read-only T+5m fixed-k historical-oracle follower screen using native PM03.

The Vike closed-trade feed supplies max trade size, not a versioned native
position book. Its leader notional is a PROXY and is never a certified source
target. Source event clocks are hindsight oracle inputs, not first-known tape.
No account/broker network or production writes. Model OHLCV opens, not L2.
"""

from __future__ import annotations

import argparse
from collections import Counter, OrderedDict, defaultdict
from datetime import UTC, datetime, timedelta
from decimal import Decimal as D
from hashlib import sha256
from pathlib import Path
import json
import math
import sys

from copytrade_pm.pm03_account import Account, Instrument, Rulebook
from copytrade_pm.pm03_execution import CostModel, MarketObservation
from copytrade_pm.pm_offline_market import _verified_day
from copytrade_pm.pm_offline_repository import native_instrument
from copytrade_pm.pm_offline_manifest import ManifestBlocked, ManifestInvalid

sys.path.insert(0, str(Path(__file__).resolve().parent))
from research_vike_recovery_audit_20261108 import read as read_vike  # noqa: E402
from research_t5_native_source_20261108 import (  # noqa: E402
    load_wallet_native,training_k_native,build_events_native,
)
from research_t5_vike_inferred_source_20261108 import load_vike_inferred  # noqa: E402

MARKET_ROOT = Path("/home/quant/dev/quant/ml4t-data/.data/store")
END = datetime(2026, 11, 7, tzinfo=UTC)
START = datetime(2026, 7, 1, tzinfo=UTC)
NOV = datetime(2026, 11, 1, tzinfo=UTC)
MODEL = "PM03_T5_FOLLOWER_HISTORICAL_ORACLE_SCREEN_ONLY"
PRICE_KIND = "SHA_VERIFIED_HL_1M_NEXT_OPEN_NOT_BID_ASK"
SCENARIO = {
    "capital": "10000", "pod_stop": "200", "daily_loss": "450",
    "trailing_loss": "1000", "profit_target": "1500",
    "max_pod_gross": "3000", "max_market_gross": "3000",
    "calibration_notional_per_source_trade": "1000", "max_k": "1",
    "fee_bps_per_side": "5", "spread_full_bps": "3",
    "slippage_bps_per_side": "5",
    "impact_bps_at_100pct_volume": "20",
    "max_participation_prior_complete_minute": "0.05",
    "forced_single_shot_exit_over_capacity": "model_with_impact_unverified_executability",
    "funding_debit_bps_each_8h": "1",
}

def d(x: object) -> D:
    return D(str(x))

def strict_minute(time: datetime, delay: int) -> datetime:
    """First open STRICTLY after source event timestamp + wait."""
    ms = int(time.timestamp() * 1000) + delay * 60_000
    return datetime.fromtimestamp(((ms // 60_000) + 1) * 60, tz=UTC)

def instrument(coin: str) -> Instrument:
    canonical = native_instrument(coin)
    parts = canonical.split(":")
    # Native default and HIP-3 namespace: hyperliquid:mainnet:perp:dex:symbol
    if len(parts) != 5:
        raise ValueError("INVALID_NATIVE_INSTRUMENT")
    return Instrument("hyperliquid", ":".join(parts[1:4]), parts[4])

def iso(t: datetime) -> str:
    return t.isoformat()

def parse(t: str) -> datetime:
    x = datetime.fromisoformat(t.replace("Z","+00:00"))
    if x.tzinfo is None:
        raise ValueError("NAIVE_SOURCE_CLOCK")
    return x.astimezone(UTC)

def pod_stop_state(pnl: D, peak_pnl: D, budget: D) -> tuple[D, bool]:
    """A $200 pod loss is a peak-to-trough trigger, not a guaranteed fill loss."""
    if budget<=0:
        raise ValueError("INVALID_POD_STOP_BUDGET")
    peak=max(peak_pnl,pnl)
    return peak,peak-pnl>=budget

class MissingMarket(Exception):
    pass

class NativePrices:
    """Only SHA-qualified 1m market, strict exact minute and completed t-1 volume."""
    def __init__(self, root: Path, max_days: int = 144):
        self.root = root
        self.max_days = max_days
        self.days: OrderedDict[tuple[str,str],tuple[tuple,tuple]] = OrderedDict()
        self.used_shas: dict[str,tuple[str,str]] = {}
        self.reasons: Counter[str] = Counter()

    def _day(self, coin: str, day: datetime):
        key=(coin,day.date().isoformat())
        if key in self.days:
            self.days.move_to_end(key)
            return self.days[key]
        try:
            inst = native_instrument(coin)
            df, data_sha, meta_sha = _verified_day(self.root, inst, day)
        except (ManifestBlocked,ManifestInvalid,ValueError,OSError) as exc:
            self.reasons[type(exc).__name__] += 1
            raise MissingMarket(f"{coin}:{type(exc).__name__}") from exc
        if df.height != 1440:
            self.reasons["PARTIAL_NATIVE_DAY"] += 1
            raise MissingMarket(f"{coin}:PARTIAL_NATIVE_DAY")
        df=df.sort("timestamp")
        day_start = day.replace(hour=0,minute=0,second=0,microsecond=0)
        expected = [day_start + timedelta(minutes=i) for i in range(1440)]
        times=df["timestamp"].to_list()
        if times != expected:
            self.reasons["NATIVE_DAY_MISSING_OR_DUPLICATE_1M"]+=1
            raise MissingMarket(f"{coin}:NATIVE_DAY_MISSING_OR_DUPLICATE_1M")
        opens=tuple(d(x) for x in df["open"].to_list())
        vols=tuple(d(x) for x in df["volume"].to_list())
        self.days[key]=(opens,vols)
        self.used_shas[f"{coin}@{key[1]}"]=(data_sha,meta_sha)
        while len(self.days)>self.max_days:
            self.days.popitem(last=False)
        return opens,vols

    def at(self, coin: str, t: datetime) -> tuple[D,D]:
        if t.second or t.microsecond:
            raise ValueError("NON_MINUTE_MARK")
        cur=self._day(coin,t)
        i=t.hour*60+t.minute
        if i:
            prev=cur[1][i-1]
        else:
            before=self._day(coin,t-timedelta(minutes=1))
            prev=before[1][-1]
        return cur[0][i], prev

    def used_digest(self) -> str:
        return sha256(json.dumps(sorted((k,*v) for k,v in self.used_shas.items()),sort_keys=True).encode()).hexdigest()


def vike_trades() -> tuple[dict[str,list[dict]],dict[str,dict]]:
    _fills,raw,metadata=read_vike()
    out={}
    for wallet, allrows in sorted(raw.items()):
        rows=[]
        state=metadata[wallet]
        final_page=max(state["trade_parts"]) if state["trade_parts"] else None
        complete= final_page is not None and state["trade_cursor"].get(final_page) is None
        if not complete:
            continue
        for trade in allrows.values():
            if not trade.get("is_complete") or not trade.get("close_observed"):
                continue
            try:
                open_at=parse(trade["open_ts"])
                close_at=parse(trade["close_ts"])
                coin=str(trade["symbol"])
                direction=str(trade["direction"])
                qty=d(trade["max_size_token"])
                price=d(trade["entry_price"])
                inst=instrument(coin)
                if not START<=open_at<close_at<END or not qty>0 or not price>0 or direction not in {"long","short"}:
                    continue
            except (TypeError,KeyError,ValueError,ManifestInvalid):
                continue
            rows.append({
                "open":open_at, "close":close_at,"symbol":coin,
                "inst":inst, "sign":1 if direction=="long" else -1,
                "source_size_notional":qty*price,
                "source_size_token":qty,
                "source_entry_px":price
            })
        out[wallet]=sorted(rows,key=lambda x:(x["open"],x["close"],x["symbol"]))
    return out,metadata


def training_k(trades: list[dict]) -> tuple[D,datetime,int,D]:
    """Pretest fixed-k from 30-day P90 simultaneous gross SOURCE proxy.

    This respects portfolio-level source notional, rather than calibrating
    each small source fill to a separate $1,000 target. Nothing after cutoff
    influences k or the initial target.
    """
    if not trades:
        return D("0"),END,0,D("0")
    first=min(x["open"] for x in trades)
    origin=first.replace(hour=0,minute=0,second=0,microsecond=0)
    cut=origin+timedelta(days=30)
    eligible=[x for x in trades if x["open"]>=origin and x["close"]<cut]
    if len(eligible)<8:
        return D("0"),cut,len(eligible),D("0")
    changes=[]
    for row in trades:
        if row["open"]>=cut:
            continue
        signed=row["source_size_notional"]*row["sign"]
        changes.append((row["open"],row["symbol"],signed))
        if row["close"]<cut:
            changes.append((row["close"],row["symbol"],-signed))
    current=defaultdict(lambda:D("0"))
    gross=[]
    for when,coin,value in sorted(changes,key=lambda x:(x[0],x[1],x[2])):
        current[coin]+=value
        total=sum(abs(v) for v in current.values())
        if total>0:
            gross.append(float(total))
    if not gross:
        return D("0"),cut,len(eligible),D("0")
    gross.sort()
    p90=d(gross[min(len(gross)-1,math.ceil(len(gross)*0.90)-1)])
    if p90<=0:
        return D("0"),cut,len(eligible),p90
    k=min(D(SCENARIO["max_k"]),D("2000")/p90)
    return k,cut,len(eligible),p90


def build_events(trades: list[dict], test_start: datetime, delay: int) -> tuple[dict[datetime,dict[str,D]],dict]:
    """Batch all same-minute source changes into a SINGLE new target per instrument.

    Closing a previously opened but unobserved trade is not synthesized. If a
    trade starts before the calibration boundary, exclude that full roundtrip.
    """
    event_parts=defaultdict(list)
    counts=Counter()
    inst_by_coin={}
    for row in trades:
        if not test_start<=row["open"] or row["close"]>=END:
            counts["left_or_right_censored"]+=1
            continue
        coin=row["symbol"]
        inst_by_coin[coin]=row["inst"]
        entry_due=strict_minute(row["open"],delay)
        exit_due=strict_minute(row["close"],delay)
        if entry_due>=exit_due or exit_due>=END:
            counts["very_short_or_right_censored"]+=1
            continue
        signed_notional=row["source_size_notional"]*row["sign"]
        event_parts[entry_due].append((row["open"],coin,signed_notional))
        event_parts[exit_due].append((row["close"],coin,-signed_notional))
        counts["retained_roundtrips"]+=1
    cumulative=defaultdict(lambda:D("0"))
    by_due={}
    for due,changes in sorted(event_parts.items()):
        modified=set()
        for _when,coin,change in sorted(changes,key=lambda z:(z[0],z[1],z[2])):
            cumulative[coin]+=change
            modified.add(coin)
        by_due[due]={coin:cumulative[coin] for coin in sorted(modified)}
    counts["batched_execution_minutes"]=len(by_due)
    return by_due,dict(counts)


def _rulebook(instruments: set[Instrument], start: datetime) -> Rulebook:
    return Rulebook(
        program="EXPLORATORY_10K_FASTPASS",
        stage="evaluation",
        source="HISTORICAL_ORACLE_NONCONTRACTUAL_ASSUMPTION",
        observed_at="2026-11-08T00:00:00+00:00",
        version="research-t5-v1",
        timezone="UTC",
        initial_balance=D(SCENARIO["capital"]),
        profit_target=D(SCENARIO["profit_target"]),
        daily_loss=D(SCENARIO["daily_loss"]),
        static_loss=None,
        trailing_loss=D(SCENARIO["trailing_loss"]),
        confirmed=True, # enables synthetic PM03 research ledger only
        account_terms_confirmed=False,
        permitted=tuple(sorted(instruments)),
    )

def _costs(mult: int) -> CostModel:
    return CostModel(
        fee_bps=D(SCENARIO["fee_bps_per_side"])*mult,
        full_spread_bps=D(SCENARIO["spread_full_bps"])*mult,
        slippage_bps=D(SCENARIO["slippage_bps_per_side"])*mult,
        impact_bps_at_full_participation=D(SCENARIO["impact_bps_at_100pct_volume"])*mult,
        max_participation=D(SCENARIO["max_participation_prior_complete_minute"]),
        max_age_seconds=0,
        latency_seconds=0,
    )

def execute_wallet(
    wallet: str,
    trades: list[dict],
    prices: NativePrices,
    *,
    delay: int=5, cost_mult: int=1,
    stop_budget: D=D("200"),
    native_events: list[dict] | None=None,
    source_diagnostics: dict | None=None,
) -> dict:
    if native_events is not None:
        k,cut,train_n,train_p90=training_k_native(native_events)
        source_class=(source_diagnostics or {}).get("data_source_class", "HYPERX_NATIVE_START_POSITION_COMPLETE_EPISODES_SELECTED_SCOPE")
        summary_events={"retained_roundtrips":(source_diagnostics or {}).get("complete_flat_to_flat_episodes",0)}
    else:
        k,cut,train_n,train_p90=training_k(trades)
        source_class="VIKE_FUTURE_MAX_TRADE_SIZE_LEAKAGE_PRONE_DIAGNOSTIC"
        summary_events={}
    summary={"wallet":wallet,"source_class":source_class,
       "delay_minutes":delay,"cost_multiplier":cost_mult,"first_known_receipts":False,
       "k":str(k),"train_trades":train_n,"train_source_gross_p90":str(train_p90),
       "training_cutoff":iso(cut),"window_end":iso(END),
       "quality":"UNQUALIFIED_HISTORICAL_ORACLE"}
    if source_diagnostics is not None:
        summary["native_source_diagnostics"]=source_diagnostics
        source_total=source_diagnostics.get("total_source_fills",0)
        summary["native_selected_fill_fraction"]=round(source_diagnostics.get("selected_native_rows",0)/source_total,4) if source_total else None
        source_last=source_diagnostics.get("source_last_ms")
        summary["last_local_source_fill_at"]=iso(datetime.fromtimestamp(source_last/1000,tz=UTC)) if source_last else None
    if k<=0 or cut>=END:
        return {**summary,"status":"INSUFFICIENT_PRE_PERIOD_CALIBRATION","net_usd_screen_only":None}
    if native_events is not None:
        actions,counts=build_events_native(native_events,cut,delay)
        insts={r["inst"] for r in native_events}
        act_inst={r["symbol"]:r["inst"] for r in native_events}
    else:
        actions,counts=build_events(trades,cut,delay)
        insts={r["inst"] for r in trades if r["open"]>=cut and r["close"]<END}
        act_inst={r["symbol"]:r["inst"] for r in trades}
    summary["events"]={**summary_events,**counts}
    if not actions or (native_events is None and counts["retained_roundtrips"]<5):
        return {**summary,"status":"TOO_FEW_COMPLETED_FOLLOWABLE_EPISODES","net_usd_screen_only":None}
    book=_rulebook(insts,cut)
    acct=Account.start(book,iso(cut))
    pm=wallet
    active_leader=defaultdict(lambda:D("0"))
    last_target={inst:D("0") for inst in insts}
    minutes=sorted(actions)
    next_i=0
    cursor=minutes[0]
    last=END
    cost=_costs(cost_mult)
    c=Counter()
    curve=[]
    max_dd=D("0")
    peak=D(SCENARIO["capital"])
    worst_day=D("0")
    stop=False
    pod_peak_pnl=D("0")
    reason=None
    market_missing_detail=None
    # Historical oracle position path. A missing active quote invalidates the entire wallet.
    while cursor<last and (next_i<len(minutes) or any(v for v in acct.quantities.values())):
        if not any(v for v in acct.quantities.values()) and next_i<len(minutes) and cursor<minutes[next_i]:
            cursor=minutes[next_i]  # flat gap: no open position, no market mark needed
        pending=actions.get(cursor,{})
        active={inst for inst,qty in acct.quantities.items() if qty}
        needed=active|{act_inst[coin] for coin in pending}
        quote={}
        try:
            for inst in needed:
                px,prev=prices.at(inst.symbol if inst.market=="mainnet:perp:default" else inst.market.split(":")[-1]+":"+inst.symbol,cursor)
                quote[inst]=(px,prev)
        except MissingMarket as exc:
            reason="MISSING_SHA_VERIFIED_MARK_OR_PRIOR_VOLUME"
            market_missing_detail=str(exc)[:120]
            c["unpriceable_minute"]+=1
            c["failure_at_epoch_minute"]=int(cursor.timestamp()/60)
            break
        # Mark even while flat when the clock jumps between source events.
        # PM03 owns daily baseline resets; skipping flat marks would carry
        # the wrong session floor into the next day's first order.
        acct.mark({inst:quote[inst][0] for inst in active},iso(cursor))
        if active:
            c["marked_active_minutes"]+=1
        else:
            c["flat_transition_marks"]+=1
        peak=max(peak,acct.equity)
        max_dd=max(max_dd,peak-acct.equity)
        worst_day=min(worst_day,acct.equity-acct.daily_start_balance)
        if acct.breached:
            reason="SIMULATED_CONTRACT_FLOOR_BREACH"
            break
        if acct.stage_passed:
            reason="SIMULATED_TARGET_REACHED_WITH_OPEN_EXPOSURE" if active else "SIMULATED_TARGET_REACHED"
            break
        # Each eight-hour settlement charges a conservative absolute funding debit proxy.
        if active and cursor.minute==0 and cursor.hour in (0,8,16):
            charge=sum(abs(acct.quantities[i]*quote[i][0]) for i in active)*D(SCENARIO["funding_debit_bps_each_8h"])/D("10000")
            if charge>0:
                acct.post_funding(-charge,{pm:-charge})
                c["funding_debit_bps_events"]+=1
                if acct.breached:
                    reason="SIMULATED_FLOOR_BREACH_AFTER_FUNDING"
                    break
        # Budget is a peak-to-trough POD drawdown, not only net loss
        # since day zero. Record realized PnL peaks when the account is flat.
        pod_pnl=acct.pm_equity_pnl().get(pm,D("0"))
        pod_peak_pnl,pod_budget_hit=pod_stop_state(pod_pnl,pod_peak_pnl,stop_budget)
        if active and pod_budget_hit:
            if not stop:
                c["pod_stop_triggered"]+=1
            stop=True
        if pending and not stop:
            for coin,signed in pending.items():
                active_leader[coin]=signed
                inst=act_inst[coin]
                px=quote[inst][0]
                last_target[inst]=(k*signed)/px
            next_i+=1
        elif pending:
            next_i+=1
        if pending or (stop and active):
            # One decision per instrument at the minute open; stop is latched.
            targets={inst:D("0") if stop else q for inst,q in last_target.items()}
            # Count every intended source target, including absent or vetoed legs;
            # a missing quote cannot make the risk cap appear smaller.
            gross=sum(abs(k*x) for x in active_leader.values()) if not stop else D("0")
            for inst in sorted(needed):
                old=acct.quantities.get(inst,D("0"))
                desired=targets.get(inst,D("0"))
                px,prev=quote[inst]
                if desired==old:
                    continue
                if gross>D(SCENARIO["max_pod_gross"]) or abs(desired*px)>D(SCENARIO["max_market_gross"]):
                    # Fixed-k: veto increases; reductions and closes remain allowed.
                    if old==0 or (old*desired>0 and abs(desired)>abs(old)):
                        c["gross_cap_rejected"]+=1
                        continue
                    if old*desired<0:
                        desired=D("0")
                delta=desired-old
                if delta==0:
                    continue
                model_volume=prev
                if prev<=0:
                    # No preceding traded volume is NOT proof that a market
                    # order could not exit; hypothetical immediate forced
                    # close with cap-stressed impact, fully unverified.
                    if old*delta<0 and abs(desired)<=abs(old):
                        c["unverified_zero_volume_exit"]+=1
                        model_volume=abs(delta)  # stressed 100% impact, NOT a verified fill
                    else:
                        c["entry_veto_zero_prior_volume"]+=1
                        continue
                if model_volume==prev and abs(delta)>D(SCENARIO["max_participation_prior_complete_minute"])*prev:
                    # Single-shot capacity failure vetoes a NEW entry. Do NOT
                    # fake a delayed split fill. Closing risk must not be held
                    # indefinitely just because historical minute volume was
                    # small: mark it as *non-executable unverified* and stress
                    # impact for its full single-shot notional.
                    if old*delta<0 and abs(desired)<=abs(old):
                        c["forced_exit_over_research_capacity"]+=1
                    else:
                        c["single_shot_capacity_rejected"]+=1
                        continue
                obs=MarketObservation(instrument=inst,event_at=iso(cursor),
                       first_known_at=iso(cursor),mark=px,
                       volume_base=model_volume,quality="OHLCV_1M_PROXY",
                       supported=False)
                try:
                    # Reuse native PM03 cost computation, cash, realized/unrealized
                    # equity, contractual floors and PM cash reconciliation.
                    fillpx, fee,_attr=cost.price_and_fee(delta,obs)
                    acct.simulate_fill(inst,delta,fillpx,fee,accepted=True,allocated={pm:delta})
                except ValueError:
                    reason="NATIVE_PM03_FILL_OR_ACCOUNT_FAILURE"
                    c["native_fill_failure"]+=1
                    break
                c["single_market_orders"]+=1
                c["turnover_usd"]+=abs(delta*px)
                c["fee_usd"]+=fee
                c["slippage_spread_impact_usd_proxy"]+=abs(delta*(fillpx-px))
                # Cash in the consolidated PM03 ledger is independent of vendor PnL.
                if acct.breached:
                    reason="SIMULATED_FLOOR_BREACH_ON_FILL"
                    break
            if reason:
                break
            # Native PM03 retains zero audit keys. Clear only after verified
            # fills so the next mark requires precisely active native legs.
            acct.verify()
            for inst,qty in list(acct.quantities.items()):
                if qty==0:
                    del acct.quantities[inst]
            for book_by_pm in acct.pm_quantities.values():
                for inst,qty in list(book_by_pm.items()):
                    if qty==0:
                        del book_by_pm[inst]
            acct.verify()
            pod_peak_pnl=max(pod_peak_pnl,acct.pm_equity_pnl().get(pm,D("0")))
        if pending or active:
            peak=max(peak,acct.equity)
            max_dd=max(max_dd,peak-acct.equity)
            worst_day=min(worst_day,acct.equity-acct.daily_start_balance)
            curve.append((cursor,acct.equity))
        if acct.stage_passed:
            reason="SIMULATED_TARGET_REACHED"
            break
        cursor+=timedelta(minutes=1)
    # No guarantee of a flat close if last source exit or stop cannot execute.
    still_open={inst.key:str(q) for inst,q in acct.quantities.items() if q}
    if not reason and still_open:
        reason="OPEN_FOLLOWER_AT_MARKET_DATA_CUTOFF"
    status=reason or ("STOPPED_BY_POD_RISK" if stop else ("COMPLETED_VIKE_INFERRED_EPISODE_ORACLE" if source_class.startswith("VIKE_") and native_events is not None else "COMPLETED_NATIVE_SELECTED_EPISODE_SCREEN" if native_events is not None else "COMPLETED_VIKE_FUTURE_MAX_SIZE_DIAGNOSTIC"))
    # A truncated mark path is NOT a complete wallet return. Preserve partial
    # cash/equity as diagnostic only, never as rankable follower PnL.
    path_complete=reason is None and not still_open
    partial=str(acct.equity-D(SCENARIO["capital"]))
    return {**summary,
        "status":status,
        "net_usd_screen_only":partial if path_complete else None,
        "partial_net_at_block_usd":partial if not path_complete else None,
        "realized_pnl_pm03":str(acct.realized_pnl),"fees_pm03":str(acct.costs),
        "funding_pm03":str(acct.funding),"max_drawdown_usd":str(max_dd),
        "worst_session_vs_daily_start_usd":str(worst_day),
        "marked_minutes":c["marked_active_minutes"],"orders":c["single_market_orders"],
        "gross_cap_rejected":c["gross_cap_rejected"],
        "single_shot_capacity_rejected":c["single_shot_capacity_rejected"],
        "forced_exit_over_research_capacity":c["forced_exit_over_research_capacity"],
        "unverified_zero_volume_exit":c["unverified_zero_volume_exit"],
        "entry_veto_zero_prior_volume":c["entry_veto_zero_prior_volume"],
        "pod_stops":c["pod_stop_triggered"],
        "pod_high_water_pnl_usd":str(pod_peak_pnl),
        "market_missing_detail":market_missing_detail,
        "used_market_days":len(prices.used_shas),
        "open_follower_positions_count":len(still_open),
        "pass_time_oracle":iso(cursor) if acct.stage_passed else None,
        "contract_breached":acct.breached,
        "equity_at_end":str(acct.equity),
        "fee_total":str(c["fee_usd"]),
        "turnover_usd":str(c["turnover_usd"]),
        "funding_events":c["funding_debit_bps_events"],
        "market_failure_epoch_minute":c.get("failure_at_epoch_minute"),
        "last_replay_at":iso(cursor),
        "selected_episode_replay_completed":path_complete,
        "readiness":"HISTORICAL_HINDSIGHT_SCREEN_NOT_ACTUAL_FILLS",
        "unverified_execution":bool(c["forced_exit_over_research_capacity"] or c["unverified_zero_volume_exit"]),
    }

def software_sha256() -> str:
    """Pin this screen and the native finance/market modules it invoked."""
    names = (
        "scripts/research_t5_follower_oracle_20261108.py",
        "scripts/research_t5_native_source_20261108.py",
        "scripts/research_t5_vike_inferred_source_20261108.py",
        "scripts/research_vike_recovery_audit_20261108.py",
        "scripts/research_fastpass_history_20261108.py",
        "src/copytrade_pm/pm03_account.py",
        "src/copytrade_pm/pm03_execution.py",
        "src/copytrade_pm/pm_offline_market.py",
    )
    base = Path(__file__).resolve().parent.parent
    parts = [(name, sha256((base / name).read_bytes()).hexdigest()) for name in names]
    return sha256(json.dumps(parts, separators=(",", ":")).encode()).hexdigest()


def main() -> None:
    p=argparse.ArgumentParser()
    p.add_argument("--wallets",default="REG238,REG267,REG179,M56,REG292,REG244,REG337,REG124,M22")
    p.add_argument("--source",choices=("vike","native","vike_inferred"),default="native")
    p.add_argument("--delay",type=int,default=5)
    p.add_argument("--cost-multipliers",default="1,2,3")
    p.add_argument("--output",type=Path)
    args=p.parse_args()
    if args.delay not in {0,5,10}:
        raise SystemExit("DELAY_NOT_PREDECLARED")
    multiples=[int(x) for x in args.cost_multipliers.split(",")]
    if not multiples or any(x not in {1,2,3} for x in multiples):
        raise SystemExit("COST_SCENARIO_NOT_PREDECLARED")
    wallets=[x.strip() for x in args.wallets.split(",") if x.strip()]
    input_trades={}
    native={}
    diagnostics={}
    if args.source=="vike":
        input_trades,_metadata=vike_trades()
    elif args.source=="native":
        native,diagnostics=load_wallet_native()
    else:
        native,diagnostics=load_vike_inferred()
    if args.wallets=="all" and args.source!="vike":
        wallets=sorted(native)
    market=NativePrices(MARKET_ROOT)
    rows=[]
    for wallet in wallets:
        for m in multiples:
            if args.source=="vike" and wallet not in input_trades:
                rows.append({"wallet":wallet,"cost_multiplier":m,"status":"NO_COMPLETE_HISTORICAL_VIKE_CLOSED_TRADES","net_usd_screen_only":None})
                continue
            if args.source!="vike" and wallet not in native:
                rows.append({"wallet":wallet,"cost_multiplier":m,"status":"NO_COMPLETE_OBSERVED_POSITION_SOURCE","net_usd_screen_only":None})
                continue
            try:
                row=execute_wallet(wallet,input_trades.get(wallet,[]),market,delay=args.delay,cost_mult=m,
                    native_events=native.get(wallet) if args.source!="vike" else None,
                    source_diagnostics=diagnostics.get(wallet) if args.source!="vike" else None)
            except Exception as exc:
                # Do not substitute a guessed number for a failed simulation.
                row={"wallet":wallet,"cost_multiplier":m,"status":"FATAL_REPLAY_EXCEPTION",
                    "error_type":type(exc).__name__,"error_detail":str(exc)[:240],
                    "net_usd_screen_only":None}
            rows.append(row)
            print(json.dumps({k:row.get(k) for k in ("wallet","cost_multiplier","status",
                 "net_usd_screen_only","max_drawdown_usd","orders","single_shot_capacity_rejected",
                 "gross_cap_rejected","k","train_trades","marked_minutes","used_market_days","error_type","error_detail")},sort_keys=True))
    digest=sha256(json.dumps([(k,v) for k,v in sorted(market.used_shas.items())],default=str).encode()).hexdigest()
    receipt={"schema":"copytrade_t5_vike_proxy_follower_oracle_screen_v1","scenario":SCENARIO,
       "market_quality":PRICE_KIND,"clock_quality":"HISTORICAL_EXCHANGE_ORACLE_NOT_FIRST_KNOWN",
       "position_quality":("HYPERX_NATIVE_OBSERVED_COMPLETE_EPISODES_SELECTED_SCOPE" if args.source=="native" else "VIKE_RETROSPECTIVE_INFERRED_FILL_BOOK_NOT_NATIVE_STARTPOSITION" if args.source=="vike_inferred" else "VIKE_MAX_TRADE_SIZE_FUTURE_LEAKAGE_PROXY"),
       "source_mode":args.source,
       "source_reconstruction_class":("HISTORICAL_FILLS_INFERRED_CLOSED_EPISODE_FLAT_BOUNDS" if args.source=="vike_inferred" else "NATIVE_STARTPOSITION_OBSERVED_EPISODES" if args.source=="native" else "LOOKAHEAD_PRONE_MAXSIZE_NOT_FOR_RANKING"),
       "source_sha256":sha256(Path("/tmp/vike7d_432.json").read_bytes()).hexdigest() if args.source=="vike" else (sha256(json.dumps(sorted((wallet,dct.get("vike_source_wallet_sha_collection")) for wallet,dct in diagnostics.items())).encode()).hexdigest() if args.source=="vike_inferred" else "27fc98ffd8cea118dda1eabe4cb60c16523cf50b74e9941767fab2dae444b6b3"),
       "scientifically_qualified":False,"trading_authorized":False,"actual_follower_fills":False,
       "window":"[2026-07-01T00:00:00Z,2026-11-07T00:00:00Z)",
       "market_day_sha_collection":digest,"market_days_scanned":len(market.used_shas),
       "software_sha256":software_sha256(),
       "results":rows}
    if args.output:
        output=args.output
        if not output.is_absolute():
            raise SystemExit("OUTPUT_MUST_BE_ABSOLUTE_PRIVATE_PATH")
        output.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
        if output.exists():
            raise SystemExit("IMMUTABLE_RESULT_ALREADY_EXISTS")
        import os
        fd=os.open(output,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
        with os.fdopen(fd,"w") as f:
            f.write(json.dumps(receipt,sort_keys=True,indent=2)+"\n")
    print("SUMMARY",json.dumps({"rows":len(rows),"market_days":len(market.used_shas),
        "status":dict(Counter(x["status"] for x in rows)),
        "report_path":str(args.output) if args.output else None}))
if __name__=="__main__":
    main()
