"""Gemini-style wallet screening and five-minute PM03 three-pod exploratory replay.

This is a distinct versioned, retrospective FIXED-SCALE study, not the
source-equity-normalized PM01/E0 sizing contract. No market/broker mutations.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import UTC, datetime, timedelta
from decimal import Decimal as D
from hashlib import sha256
from itertools import combinations
import json
from math import log1p, sqrt
import os
from pathlib import Path
import tempfile
from statistics import median

from .pm_historical_combos import Episode, QUANTITY_GRID, _minute_at_or_after, _native_pm, _run_combo
from .pm_hl94_audit import COHORT, normalized_fill, fill_key
from .pm_propr_scope import SCOPE_STRICT, classify_coin
from .pm_shadow import VerifiedHyperliquidMinuteSource
from .pm_sparse_equity_portfolio import BoundedCarryMinuteMarket

START = datetime(2026, 8, 1, tzinfo=UTC)
SPLIT = datetime(2026, 9, 30, tzinfo=UTC)
END = datetime(2026, 10, 30, tzinfo=UTC)
SCHEMA = "hl94_gemini_fixed_scale_discovery_v1"
REPLAY_SCHEMA = "hl94_gemini_pm03_five_minute_replay_v1"
RISK_CAPS = (D("6000"), D("18000"), D("9000"))
PROPR_SNAPSHOT = "PROPR_PUBLIC_ASSET_UNIVERSE_20261030.json"


def _files(root: Path):
    return [(name, file) for name in COHORT for file in sorted((root / name).glob("*.json"))]


def _label(payload: dict, path: Path, address: str):
    alias = payload.get("label") or payload.get("alias_label")
    if isinstance(alias, str) and (alias.startswith(("S0", "C0", "N0", "CA-", "CO-"))):
        return alias
    if path.name.startswith(("S0", "C0", "N0", "CA-", "CO-")):
        return path.stem.split("_0x")[0]
    return "NANSEN-" + sha256(address.encode()).hexdigest()[:9]


def load_wallets(root: Path):
    """Read original files, retaining provider timestamp ordering within a millisecond."""
    wallets = {}
    seen = {}
    files = _files(root)
    source_hashes = {}
    for cohort, path in files:
        data = path.read_bytes()
        payload = json.loads(data)
        address = str(payload["address"]).lower()
        source_hashes[cohort + "/" + path.name] = sha256(data).hexdigest()
        info = wallets.setdefault(address, {"alias": _label(payload, path, address),
                                             "address": address, "records": [], "invalid": 0,
                                             "duplicates": 0, "conflicts": 0})
        for raw in payload["fills"]:
            try:
                row = normalized_fill(raw)
            except ValueError:
                info["invalid"] += 1
                continue
            key = fill_key(address, row)
            if key in seen:
                if seen[key] != row:
                    info["conflicts"] += 1
                else:
                    info["duplicates"] += 1
                continue
            seen[key] = row
            at = datetime.fromtimestamp(row["timestamp_ms"]/1000, UTC)
            info["records"].append((at, row, raw))
    for wallet in wallets.values():
        wallet["records"].sort(key=lambda row: row[0])  # stable: never sort tied timestamps by TID
    return wallets, source_hashes


def source_chains(wallet: dict, *, native_coins: set[str]) -> tuple[list[Episode], dict]:
    grouped = defaultdict(list)
    for at, row, _raw in wallet["records"]:
        if row["coin"] in native_coins and at < END:
            grouped[row["coin"]].append((at, int(row["tid"]), row["coin"], D(row["start_position"]),
                                         D(row["end_position"]), D(row["signed_delta"]), D(row["price"])))
    episodes = []
    counts = Counter()
    for coin, rows in grouped.items():
        active = []
        prior = None
        for entry in rows:
            time, _, _, before, after, _, _ = entry
            if prior is not None and before != prior:
                counts["discontinuities"] += 1
                if active:
                    counts["discarded_interrupted_segments"] += 1
                active = []
            prior = after
            if not active:
                if before == 0 and after != 0:
                    active = [entry]
                elif before != 0:
                    counts["unanchored_rows"] += 1
                continue
            elif before == 0:
                # Either a repeated start anchor or a preceding lost flat.
                counts["discontinuities"] += 1
                active = [entry] if after else []
                continue
            active.append(entry)
            if after == 0:
                episodes.append(Episode(wallet["alias"], coin, tuple(active)))
                counts["complete_episodes"] += 1
                active = []
        if active:
            episodes.append(Episode(wallet["alias"], coin, tuple(active)))
            counts["censored_open_episodes"] += 1
    episodes.sort(key=lambda ep: (ep.start, ep.coin))
    counts["source_event_rows_in_anchored_segments"] = sum(len(ep.events) for ep in episodes)
    return episodes, dict(counts)


def _native_coin_set(snapshot: dict, market_root: Path) -> set[str]:
    accepted = set()
    for coin in snapshot["market_symbols"]["crypto"]:
        if classify_coin(coin, snapshot) != SCOPE_STRICT:
            continue
        try:
            family = VerifiedHyperliquidMinuteSource._family(
                f"hyperliquid:mainnet:perp:default:{coin}"
            )
        except Exception:
            continue
        # Require actual native market inputs, not a different venue's OHLCV.
        if (market_root / family / "year=2026/month=08/day=01/data.parquet").is_file():
            accepted.add(coin)
    return accepted


def _pct(values: list[float], pct: float) -> float:
    if not values:
        return 0.
    values = sorted(values)
    return values[min(len(values)-1, round((len(values)-1)*pct))]


def _source_stat(wallet: dict, episodes: list[Episode], eligible_coins: set[str]):
    train = [(at, row, raw) for at, row, raw in wallet["records"] if START <= at < SPLIT]
    recent = [(at, row, raw) for at, row, raw in wallet["records"] if START <= at < END]
    days = {}
    total_notional = D(0)
    eligible_notional = D(0)
    maker = 0
    taker = 0
    missing_close_pnl = 0
    for at, row, raw in train:
        value = D(row["size"]) * D(row["price"])
        total_notional += value
        if row["coin"] in eligible_coins:
            eligible_notional += value
        if raw.get("crossed") is True:
            taker += 1
        elif raw.get("crossed") is False:
            maker += 1
        if row["closed_pnl"] is None and ("Close" in str(raw.get("dir", ""))):
            missing_close_pnl += 1
        day = at.date().isoformat()
        days[day] = days.get(day, D(0)) + (D(row["closed_pnl"]) if row["closed_pnl"] else D(0)) - D(str(raw.get("fee") or 0))
    losses = [float(x) for x in days.values() if x < 0]
    worst_day = min(losses) if losses else 0.0
    realized_net = float(sum(days.values(), D(0)))
    holds = sorted((ep.end-ep.start).total_seconds()/3600 for ep in episodes if ep.end < SPLIT and ep.end > ep.start and ep.events[-1][4] == 0)
    gross_trace = {}
    last_prices = {}
    gross_samples = []
    anchored_rows = sorted((event for ep in episodes for event in ep.events), key=lambda r: r[0])
    for at, _tid, coin, _before, after, _, px in anchored_rows:
        if at >= SPLIT:
            break
        last_prices[coin] = px
        gross_trace[coin] = after
        if at >= START:
            gross_samples.append(float(sum((abs(q*last_prices[k]) for k, q in gross_trace.items()), D(0))))
    p95_gross = _pct(gross_samples, .95)
    # A single training-frozen k-factor preserves every observed source quantity.
    # $2k historical observed-position P95 reference and $200 historical
    # realized worst-day loss are independent conservative upper bounds.
    k_gross = 2000/max(p95_gross, 1.)
    k_day = 200/abs(worst_day) if worst_day < 0 else 1.
    k = min(1., k_gross, k_day)
    coverage = float(eligible_notional/total_notional) if total_notional else 0.
    maker_fraction = maker/max(maker+taker, 1)
    fills_per_day = len(train)/60
    source_span_days = ((train[-1][0]-train[0][0]).total_seconds()/86400) if len(train)>1 else 0.
    anchored_train = sum(START <= e[0] < SPLIT for e in anchored_rows)
    native_train = sum(r['coin'] in eligible_coins for _,r,_ in train)
    anchored_ratio = anchored_train/max(native_train, 1)
    n_episodes = sum(ep.start >= START and ep.start < SPLIT for ep in episodes)
    median_hold = median(holds) if holds else None
    # Discovery-only heuristic; score is NOT an alpha estimator.
    score = (2*log1p(max(realized_net, 0)/1000) + 0.5*log1p(max(n_episodes, 0))
             + min(median_hold or 0, 48)/24 + 2*coverage
             - max(0, fills_per_day-120)/30 - 2*maker_fraction
             - min(5., 20*abs(worst_day)/max(realized_net,1000.))
             - (1 if len(recent)<100 else 0))
    exclusion = []
    if len(train) < 30:
        exclusion.append("TOO_FEW_DISCOVERY_FILLS")
    if source_span_days < 40:
        exclusion.append("SHORT_TRUNCATED_DISCOVERY_SPAN")
    if anchored_ratio < .85:
        exclusion.append("INSUFFICIENT_ANCHORED_SOURCE_BOOK_COVERAGE")
    if coverage < .65:
        exclusion.append("LOW_SUPPORTED_PROPR_NOTIONAL")
    if n_episodes < 1:
        exclusion.append("NO_SOURCE_ANCHORED_POSITION")
    if maker_fraction > .85 and fills_per_day > 50:
        exclusion.append("MAKER_DEPENDENT_CHURN")
    if fills_per_day > 180:
        exclusion.append("EXCESSIVE_CHURN")
    if missing_close_pnl > max(20, len(train)*.05):
        exclusion.append("MISSING_REALIZED_CLOSE_PNL")
    if p95_gross <= 0:
        exclusion.append("SOURCE_GROSS_UNOBSERVED")
    if realized_net <= 0:
        exclusion.append("NEGATIVE_DISCOVERY_SOURCE_REALIZED_NET")
    # Prior Gemini report explicitly identified these as suspected martingale /
    # severe tail risk. Label this as an external, holdout-contaminating prior,
    # never represent it as an independently reproduced discovery-window fact.
    gemini_prior_risk = {"S054-BTC", "S065-BTC", "S049-LINK", "S059-HYPE"}
    if wallet["alias"] in gemini_prior_risk:
        exclusion.append("GEMINI_REPORTED_TAIL_RISK_PRIOR_NOT_INDEPENDENTLY_CONFIRMED")
    if wallet["alias"] == "N051-HYPE":
        exclusion.append("GEMINI_REPORTED_C017_CLONE_PRIOR")
    return {"wallet": wallet["alias"], "fills_60d": len(train), "fills_90d": len(recent),
            "source_realized_pnl_60d": round(realized_net,2),
            "source_worst_realized_day_usd": round(worst_day,2),
            "median_completed_hold_hours": round(median_hold, 2) if median_hold is not None else None,
            "maker_fraction": round(maker_fraction,4), "fills_per_calendar_day": round(fills_per_day,2),
            "discovery_observation_span_days": round(source_span_days,2),
            "source_anchored_fill_coverage_fraction": round(anchored_ratio,4),
            "strict_native_propr_notional_fraction": round(coverage,4),
            "supported_coin_count": len({r["coin"] for _, r, _ in train if r["coin"] in eligible_coins}),
            "anchored_episode_count_discovery": n_episodes,
            "anchored_events": sum(len(ep.events) for ep in episodes),
            "source_position_p95_observed_fill_mark_usd": round(p95_gross,2),
            "frozen_k": format(D(str(k)).quantize(D("0.0000000001")),"f"),
            "scale_is_source_trade_ratio_not_historical_wallet_equity": True,
            "score": round(score,4), "excluded": exclusion}


def _corr(a: dict[str, float], b: dict[str, float]) -> float:
    dates = [(START+timedelta(days=i)).date().isoformat() for i in range(60)]
    x = [a.get(d, 0.) for d in dates]
    y = [b.get(d, 0.) for d in dates]
    mx, my = sum(x)/len(x), sum(y)/len(y)
    dx = sum((v-mx)**2 for v in x)
    dy = sum((v-my)**2 for v in y)
    return sum((u-mx)*(v-my) for u, v in zip(x,y))/sqrt(dx*dy) if dx>0 and dy>0 else 0.


def _source_daily(wallet: dict):
    days = defaultdict(float)
    for at, r, raw in wallet["records"]:
        if START <= at < SPLIT:
            days[at.date().isoformat()] += float(r["closed_pnl"] or 0) - float(raw.get("fee") or 0)
    return days


def screen(root: Path, market_root: Path, scope_path: Path) -> dict:
    wallets, hashes = load_wallets(root)
    scope_raw = scope_path.read_bytes()
    scope = json.loads(scope_raw)
    if scope.get("schema") != "propr_public_universe_browser_snapshot_v1":
        raise ValueError("UNVERIFIED_PROPR_SNAPSHOT")
    coins = _native_coin_set(scope, market_root)
    stats, episodes_by_alias, source_rows = [], {}, {}
    for wallet in wallets.values():
        eps, audit = source_chains(wallet, native_coins=coins)
        entry = _source_stat(wallet, eps, coins)
        entry["chain_audit"] = audit
        entry["invalid_records"] = wallet["invalid"]
        entry["duplicate_records"] = wallet["duplicates"]
        entry["conflicting_records"] = wallet["conflicts"]
        stats.append(entry)
        episodes_by_alias[wallet["alias"]] = eps
        source_rows[wallet["alias"]] = wallet
    stats.sort(key=lambda r: (-r["score"], r["wallet"]))
    eligible = [r for r in stats if not r["excluded"]]
    shortlist = eligible[:20]
    daily = {a: _source_daily(w) for a,w in source_rows.items()}
    by_alias = {r["wallet"]: r for r in stats}
    candidates = []
    for trio in combinations(sorted(r["wallet"] for r in shortlist),3):
        if "C017-HYPE" in trio and "N051-HYPE" in trio:
            continue
        pair_corr = [_corr(daily[a], daily[b]) for a,b in combinations(trio,2)]
        same_coins = [set(ep.coin for ep in episodes_by_alias[w] if ep.start < SPLIT) for w in trio]
        overlap = len(set.intersection(*same_coins)) if all(same_coins) else 0
        rank = sum(by_alias[w]["score"] for w in trio) - 2*sum(max(c,0) for c in pair_corr) - overlap*.4
        candidates.append({"wallets":list(trio),"discovery_screen_score":round(rank,4),
                           "pairwise_source_realized_pnl_correlation":[round(c,3) for c in pair_corr],
                           "common_three_way_instruments":overlap})
    candidates.sort(key=lambda x:(-x["discovery_screen_score"],x["wallets"]))
    # Pre-register three Gemini-motivated portfolio ideas at discovery only.
    # These are not chosen based on the validation PnL.
    explicit = [("S048-BTC","S060-HYPE","S053-HYPE"),
                ("S048-BTC","S035-ENA","C017-HYPE"),
                ("S048-BTC","S060-HYPE","C017-HYPE")]
    frozen = list(candidates[:5])
    known = {tuple(x["wallets"]) for x in frozen}
    for group in explicit:
        trio = tuple(sorted(group))
        if set(trio).issubset({r["wallet"] for r in shortlist}) and trio not in known:
            item = next((c for c in candidates if tuple(c["wallets"]) == trio), None)
            if item is not None:
                frozen.append(item)
                known.add(trio)
    return {"schema":SCHEMA,"status":"FROZEN_DISCOVERY_ONLY","source_start":START.isoformat(),
            "discovery_end":SPLIT.isoformat(),"validation_end":END.isoformat(),
            "source_file_sha256":hashes,"propr_scope_sha256":sha256(scope_raw).hexdigest(),
            "supported_native_propr_crypto":sorted(coins),"raw_wallet_count":len(wallets),
            "audit":stats,"shortlist":[r["wallet"] for r in shortlist],
            "top_10_candidate_triples":candidates[:10],"frozen_validation_triples":frozen,
            "all_discovery_triples_screened":len(candidates),
            "gemini_prior_report_makes_validation_not_untouched":True,
            "historical_equity_recovery_required":False,
            "science":"RETROSPECTIVE_FIXED_K_SOURCE_TRADE_RATIO_PROXY_NOT_SOURCE_NAV",
            "live_orders_permitted":False}


def source_actions(episodes: dict[str,list[Episode]], trio: tuple[str,...],
                   scales: dict[str,D], *, start: datetime, end: datetime,
                   delay: timedelta):
    if delay < timedelta(0):
        raise ValueError("NEGATIVE_FOLLOWER_DELAY")
    out = defaultdict(dict)
    for w in trio:
        rows = sorted((row for ep in episodes[w] for row in ep.events), key=lambda r:r[0])
        positions = {}
        remaining = []
        for row in rows:
            if row[0] < start:
                if row[4]:
                    positions[row[2]] = row[4]
                else:
                    positions.pop(row[2],None)
            elif row[0] < end:
                remaining.append(row)
        if positions:
            at = _minute_at_or_after(start + delay)
            if at < end:
                out[at][w] = {_native_pm(k):(v*scales[w]).quantize(QUANTITY_GRID)
                              for k,v in positions.items()}
        index = 0
        while index < len(remaining):
            due = _minute_at_or_after(remaining[index][0]+delay)
            while index < len(remaining) and (
                remaining[index][0] < due or (delay == timedelta(0) and remaining[index][0] == due)
            ):
                row = remaining[index]
                if row[4]:
                    positions[row[2]] = row[4]
                else:
                    positions.pop(row[2],None)
                index += 1
            if start <= due < end:
                out[due][w] = {_native_pm(k):(v*scales[w]).quantize(QUANTITY_GRID)
                               for k,v in positions.items()}
    return sorted(out.items())


def replay(report: dict, root: Path, market_root: Path, scope_path: Path, *,
           offset: int, count: int, delay_minutes: int, costs: D, capacity: bool,
           risk_scale: D = D(1), stale_minutes: int = 15,
           pod_loss_limit: D | None = D(200), selection: str = "frozen",
           screening_sha256: str | None = None) -> dict:
    cohort, hashes = load_wallets(root)
    if hashes != report["source_file_sha256"] or sha256(scope_path.read_bytes()).hexdigest() != report["propr_scope_sha256"]:
        raise ValueError("FROZEN_SOURCE_IDENTITY_DRIFT")
    allowed_coins = set(report["supported_native_propr_crypto"])
    by_alias = {w["alias"]: w for w in cohort.values()}
    if selection not in ("frozen", "top10"):
        raise ValueError("INVALID_SELECTION_SET")
    pool = report["frozen_validation_triples"] if selection == "frozen" else report["top_10_candidate_triples"]
    frozen = pool[offset:offset+count]
    aliases = {w for x in frozen for w in x["wallets"]}
    episodes = {w:source_chains(by_alias[w],native_coins=allowed_coins)[0] for w in aliases}
    if risk_scale <= 0 or risk_scale > 1:
        raise ValueError("INVALID_SCENARIO_RISK_SCALE")
    sizes = {r["wallet"]:D(r["frozen_k"])*risk_scale for r in report["audit"] if r["wallet"] in aliases}
    market = VerifiedHyperliquidMinuteSource(market_root)
    results = []
    for candidate in frozen:
        trio = tuple(candidate["wallets"])
        for phase, start,end in (("DISCOVERY",START,SPLIT),("VALIDATION",SPLIT,END)):
            actions = source_actions(episodes, trio, sizes, start=start,end=end,delay=timedelta(minutes=delay_minutes))
            proxy = BoundedCarryMinuteMarket(market_root,max_minutes=stale_minutes,native_source=market)
            result = _run_combo(phase+"_"+"_".join(trio),trio,episodes,sizes,proxy,
                                actions_override=actions,risk_limits=RISK_CAPS,
                                cost_multiplier=costs,measure_tracking=True,
                                capacity_enforced=capacity,start_at=start,end_at=end,holdout_at=None,
                                pod_loss_limit=pod_loss_limit)
            result.update({"phase":phase,"candidate_score":candidate["discovery_screen_score"],
                           "fixed_source_trade_ratios":{w:str(sizes[w]) for w in trio},
                           "minute_delay":delay_minutes,"cost_multiplier":str(costs),
                           "risk_scale":str(risk_scale),"max_mark_only_staleness_minutes":stale_minutes,
                           "pod_hard_stop_usd":str(pod_loss_limit) if pod_loss_limit is not None else None,
                           "capacity_enforced":capacity,
                           "source_basis":"OBSERVED_ANCHORED_PARTIAL_SOURCE_BOOK",
                           "historical_source_equity_used":False,
                           "sizing_proxy":"FROZEN_DISCOVERY_K_TIMES_SOURCE_POSITION_QUANTITY",
                           "stale_mark_proxy_count":proxy.diagnostics["stale_open_price_proxy_bars"],
                           "follower_execution_verified":False})
            results.append(result)
    return {"schema":REPLAY_SCHEMA,"status":"EXECUTED_FIXED_K_PM03_PARTIAL_REPLAY",
            "screening_source_sha256":screening_sha256,
            "selection_set":selection,"selected_range":[offset,offset+len(frozen)],"delay_minutes":delay_minutes,
            "cost_multiplier":str(costs),"capacity_enforced":capacity,
            "risk_scale":str(risk_scale),"max_mark_only_staleness_minutes":stale_minutes,
            "pod_hard_stop_usd":str(pod_loss_limit) if pod_loss_limit is not None else None,
            "results":results,"source_market_day_sha256":dict(sorted(market.source_days.items())),
            "no_live_orders":True,"scientifically_qualified":False}


def write_evidence(out: Path, payload: dict) -> tuple[Path, str]:
    """94-wallet private evidence: immutable, SHA-addressed, mode 0600."""
    out.mkdir(parents=True, exist_ok=True, mode=0o700)
    if out.stat().st_mode & 0o077:
        raise ValueError("EVIDENCE_DIRECTORY_NOT_PRIVATE")
    raw = (json.dumps(payload, sort_keys=True, indent=2, ensure_ascii=False) + "\n").encode()
    digest = sha256(raw).hexdigest()
    labels = {
        SCHEMA: "hl94-screen",
        REPLAY_SCHEMA: "hl94-pm03",
        "hl94_three_pod_descriptive_portfolio_comparison_v1": "hl94-summary",
    }
    label = labels.get(payload["schema"])
    if label is None:
        raise ValueError("UNRECOGNIZED_HL94_EVIDENCE_SCHEMA")
    target = out / f"{label}-{digest[:20]}.json"
    if target.exists():
        if sha256(target.read_bytes()).hexdigest() != digest:
            raise ValueError("SHA_EVIDENCE_COLLISION")
        return target, digest
    fd, temp = tempfile.mkstemp(prefix=".pending-hl94-", dir=out)
    try:
        with os.fdopen(fd, "wb") as stream:
            os.fchmod(stream.fileno(), 0o600)
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, target)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)
    return target, digest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase",choices=("screen","replay"),required=True)
    parser.add_argument("--data-root",type=Path,required=True)
    parser.add_argument("--market-root",type=Path,required=True)
    parser.add_argument("--propr-snapshot",type=Path,required=True)
    parser.add_argument("--out",type=Path,required=True)
    parser.add_argument("--screening-report",type=Path)
    parser.add_argument("--offset",type=int,default=0)
    parser.add_argument("--count",type=int,default=5)
    parser.add_argument("--delay",type=int,choices=(0,5,15),default=5)
    parser.add_argument("--costs",type=int,choices=(1,2,3),default=1)
    parser.add_argument("--capacity",action="store_true")
    parser.add_argument("--risk-scale",choices=("1","0.5","0.25"),default="1")
    parser.add_argument("--stale-mark-minutes",type=int,default=15)
    parser.add_argument("--pod-loss-usd",type=int,choices=(0,200),default=200)
    parser.add_argument("--selection",choices=("frozen","top10"),default="frozen")
    args=parser.parse_args()
    if args.phase=="screen":
        result=screen(args.data_root,args.market_root,args.propr_snapshot)
    else:
        if args.screening_report is None or args.offset<0 or args.count<1:
            raise ValueError("SCREENING_REPORT_AND_VALID_REPLAY_RANGE_REQUIRED")
        screening_bytes = args.screening_report.read_bytes()
        result=replay(json.loads(screening_bytes),args.data_root,args.market_root,
                      args.propr_snapshot,offset=args.offset,count=args.count,
                      delay_minutes=args.delay,costs=D(args.costs),capacity=args.capacity,
                      risk_scale=D(args.risk_scale),stale_minutes=args.stale_mark_minutes,
                      pod_loss_limit=D(args.pod_loss_usd) if args.pod_loss_usd else None,
                      selection=args.selection,screening_sha256=sha256(screening_bytes).hexdigest())
    path,digest=write_evidence(args.out,result)
    print(json.dumps({"report":str(path),"sha256":digest,"schema":result["schema"],
                      "shortlist":result.get("shortlist"),
                      "top_triples":result.get("top_10_candidate_triples"),
                      "results":[{"wallets":r["wallets"],"phase":r["phase"],
                                  "pnl":r.get("pnl_usd"),"status":r["status"],
                                  "stop":r.get("stop_reason"),"observed_through":r.get("observed_through")}
                                 for r in result.get("results",[])]},sort_keys=True))


if __name__=="__main__":
    main()
