"""Read-only matched T0+300 / CWSA economics through the existing PM03/PM04 owners.

This module creates no trades, optimizes no k, and cannot promote a policy.
"""

from __future__ import annotations

import argparse
from bisect import bisect_right
from collections import Counter
from contextlib import closing
from copy import deepcopy
from datetime import UTC, datetime
from decimal import Decimal as D
from hashlib import sha256
import json
from pathlib import Path
import random
import re
import sqlite3
import subprocess

from .pm03_account import Account, Instrument, Rulebook, clock, digest, number
from .pm03_memory import Event, Ledger
from .pm03_risk import RiskPolicy
from .pm03_run import ShadowRun
from .pm_forward_journal import PaperJournal
from .production_manifest import canonical, verify

OLD = "FIRST_KNOWN_T0_300_V1"
NEW = "CWSA_UTC_5M_V3"


def millis(at):
    return int(clock(at).timestamp() * 1000)


def _sha(value):
    if not isinstance(value, str) or re.fullmatch(r"[a-f0-9]{64}", value) is None:
        raise ValueError("ECONOMICS_SHA_REQUIRED")
    return value


def _private(path):
    path = Path(path)
    if path.is_symlink() or not path.is_file():
        raise ValueError("ECONOMICS_ORIGINAL_FILE_REQUIRED")
    return path.read_bytes()


def _fills(value):
    if isinstance(value, dict):
        for key, child in value.items():
            if key == "fills" and isinstance(child, list):
                yield from child
            else:
                yield from _fills(child)
    elif isinstance(value, list):
        for child in value:
            yield from _fills(child)


def _trace(manifest, timing):
    rulebook = Rulebook.from_dict(manifest["rulebook"])
    initial = Account.start(rulebook, manifest["started_at"]).snapshot()
    return {
        "timing_policy": timing,
        "manifest": manifest,
        "manifest_sha": digest(manifest),
        "head_sha": "0" * 64,
        "states": [{"at_ms": millis(manifest["started_at"]), "account": initial}],
        "events": [],
        "members": {},
        "source_accounts": {},
        "source_dexes": {},
        "opportunities": {},
        "original_evidence_shas": [],
        "cost_policy_shas": [],
        "executions": [],
        "coverage_events": [],
        "breach_events": [],
        "final_account": initial,
        "source_events": [],
        "execution_evidence": [],
        "native_originals_verified": False,
    }


def _record(trace, event, account, result, head, *, decision, first_known, source_at, fill_at):
    financial = deepcopy({k: v for k, v in account.items() if k != "pm04"})
    trace["states"].append({"at_ms": decision, "account": financial})
    trace["final_account"], trace["head_sha"] = deepcopy(account), head
    kind = event["kind"]
    if trace["states"][-2]["at_ms"] > decision:
        raise ValueError("ECONOMICS_NONCAUSAL_EVENT_ORDER")
    trace["events"].append(
        {
            "kind": kind,
            "decision_ms": decision,
            "first_known_ms": first_known,
            "source_ms": source_at,
            "hypothetical_fill_ms": fill_at,
            "input_sha": digest(event),
        }
    )
    if account.get("breached") and not trace["breach_events"]:
        trace["breach_events"].append({"at_ms": decision, "reason": account.get("halt_reason")})
    for fill in _fills(result):
        price = fill.get("execution_price", fill.get("modeled_price"))
        if "quantity" in fill and price is not None:
            trace["executions"].append(dict(fill, execution_price=price, decision_ms=decision))
    if "GAP" in kind or result.get("status") in {"COVERAGE_GAP", "UNRESOLVED"}:
        trace["coverage_events"].append(
            {"at_ms": decision, "kind": kind, "status": result.get("status")}
        )


def read_checkpoint(path: Path, run_id: str) -> dict:
    path = Path(path)
    if path.is_symlink() or not path.is_file():
        raise ValueError("ECONOMICS_CHECKPOINT_JOURNAL_MISSING")
    with closing(sqlite3.connect(f"file:{path.resolve()}?mode=ro", uri=True)) as db:
        db.execute("PRAGMA query_only=ON")
        db.execute("BEGIN")
        row = db.execute("SELECT manifest FROM runs WHERE run_id=?", (run_id,)).fetchone()
        if row is None:
            raise ValueError("ECONOMICS_CHECKPOINT_RUN_MISSING")
        trace = _trace(json.loads(row[0]), NEW)
        outcomes = {}
        originals, policies = set(), set()

        def observe(event, account, result, head):
            decision = millis(event["event_at"])
            source_at = decision
            if event["kind"] == "CWSA_PAPER_REVIEW":
                mandate, outcome = event["mandate"], event["outcome"]
                source = mandate["source_id"]
                old = trace["members"].setdefault(source, mandate["k"])
                if number(old) != number(mandate["k"]):
                    raise ValueError("ECONOMICS_K_NOT_FROZEN")
                trace["source_accounts"][source] = mandate["source_account_sha"]
                if outcome["sample"] is not None:
                    trace["source_dexes"][source] = outcome["sample"]["scope"]["dexes"]
                source_at = outcome["published_ms"]
                outcomes[
                    digest([mandate["mandate_id"], mandate["generation"], outcome["outcome_id"]])
                ] = result["status"]
                originals.update(event.get("originals", {}))
                policies.add(digest(event["policy"]["costs"]))
                trace["execution_evidence"].append(
                    {
                        "kind": event["kind"],
                        "outcome_kind": outcome["kind"],
                        "checkpoint_ms": outcome["checkpoint_ms"],
                        "published_ms": outcome["published_ms"],
                        "decision_ms": decision,
                        "source_sample": outcome["sample"],
                        "policy": event["policy"],
                        "requested_targets": result.get("requested_targets"),
                        "status": result["status"],
                        "markets": event.get("markets"),
                        "quotes": event.get("quotes"),
                    }
                )
            _record(
                trace,
                event,
                account,
                result,
                head,
                decision=decision,
                first_known=source_at,
                source_at=source_at,
                fill_at=decision,
            )

        PaperJournal._verify(db, run_id, on_event=observe)
        if not outcomes:
            raise ValueError("ECONOMICS_CHECKPOINT_POLICY_EVENTS_MISSING")
        trace["opportunities"] = dict(sorted(Counter(outcomes.values()).items()))
        trace["original_evidence_shas"] = sorted(originals)
        trace["cost_policy_shas"] = sorted(policies)
        trace["native_originals_verified"] = bool(originals)
        return trace


def read_legacy(path: Path) -> dict:
    path = Path(path)
    manifest = json.loads(_private(path / "manifest.json"))
    trace = _trace(manifest, OLD)
    rulebook = Rulebook.from_dict(manifest["rulebook"])
    policy = RiskPolicy(**{k: number(v) for k, v in manifest["risk_policy"].items()})
    account = Account.start(rulebook, manifest["started_at"])
    policies, lineage = set(), set()
    saw_source = False
    for row in Ledger.read_path(path / "events.jsonl"):
        event = Event(**row["event"])
        result = ShadowRun.replay_record(account, event, manifest, policy)
        snapshot = account.snapshot()
        post_sha = digest({"account": snapshot, "result": result})
        if event.payload.get("post_state_sha") != post_sha or event.payload.get("tool_trace") != {
            "action": "pm03.shadow." + event.kind.lower(),
            "status": "OK",
            "executed_at": event.decision_at,
            "input_sha": event.source_sha,
            "output_sha": post_sha,
            "rulebook_sha": account.rulebook.sha,
        }:
            raise ValueError("ECONOMICS_LEGACY_REPLAY_DIVERGENCE")
        raw = event.payload["input"]
        if event.kind == "PM04_CONFIG":
            p = raw["policy"]
            if p["batch_seconds"] != 300 or not p.get("fixed_k_by_pod"):
                raise ValueError("ECONOMICS_LEGACY_POLICY_NOT_FIXED_K_T0_300")
            if trace["members"] and trace["members"] != p["fixed_k_by_pod"]:
                raise ValueError("ECONOMICS_K_NOT_FROZEN")
            trace["members"] = dict(p["fixed_k_by_pod"])
            policies.add(digest(p))
        if event.kind == "PM04_PAPER_SOURCE":
            saw_source = True
            trace["source_events"].append(dict(raw, decision_ms=millis(event.decision_at)))
        if event.kind == "STAGE":
            raise ValueError("ECONOMICS_STAGE_CHANGE_REQUIRES_SEPARATE_WINDOW")
        if raw.get("quotes") or raw.get("markets"):
            trace["execution_evidence"].append(
                {
                    "kind": event.kind,
                    "decision_ms": millis(event.decision_at),
                    "input": raw,
                    "result": result,
                }
            )
        if (
            event.kind == "PM04_PAPER_EXECUTE"
            and millis(event.decision_at) < millis(event.first_known_at) + 300000
        ):
            raise ValueError("ECONOMICS_LEGACY_EARLY_ENTRY")
        if "costs" in raw:
            policies.add(digest(raw["costs"]))
        lineage.add(event.source_sha)
        _record(
            trace,
            event.to_dict(),
            snapshot,
            result,
            row["sha"],
            decision=millis(event.decision_at),
            first_known=millis(event.first_known_at),
            source_at=millis(event.source_event_at),
            fill_at=millis(event.hypothetical_fill_at),
        )
    if not saw_source:
        raise ValueError("ECONOMICS_LEGACY_POLICY_EVENTS_MISSING")
    execution = account.pm04_state.get("paper_execution", {})
    trace["opportunities"] = dict(
        sorted(Counter(r["status"] for r in execution.get("history", {}).values()).items())
    )
    trace["cost_policy_shas"] = sorted(policies)
    # Self-hashed event lineage does not authenticate original native response bytes.
    trace["lineage_shas"] = sorted(lineage)
    return trace


def _attest_legacy(trace, pin):
    """Reuse the original receipt verifier and pin its full source prefix."""
    from .pm_forward_observed_paper import _read_source
    from .pm_forward_stream_journal import verify_official_position_transition

    if not pin.get("source_journal") or not pin.get("source_prefixes"):
        raise ValueError("LEGACY_SOURCE_SCOPE_NOT_REATTESTED")
    path = Path(pin["source_journal"])
    if path.is_symlink() or not path.is_file():
        raise ValueError("LEGACY_SOURCE_JOURNAL_MISSING")
    verified, native = {}, True
    with closing(sqlite3.connect(f"file:{path.resolve()}?mode=ro", uri=True)) as db:
        db.execute("PRAGMA query_only=ON")
        db.execute("BEGIN")
        for source, prefix in pin["source_prefixes"].items():
            count = prefix["sequence"]
            if type(count) is not int or count < 1:
                raise ValueError("ECONOMICS_SOURCE_PREFIX")
            for sequence in range(1, count + 1):
                row = _read_source(db, source, sequence)
                if row is None:
                    raise ValueError("ECONOMICS_SOURCE_PREFIX_MISSING")
                verified[source, sequence] = row
            if row["chain_sha"] != _sha(prefix["head_sha"]):
                raise ValueError("ECONOMICS_SOURCE_PREFIX_PIN")
        for event in trace["source_events"]:
            source = event["pod"]
            row = verified.get((source, event["source_seq"]))
            if (
                row is None
                or row["sha"] != event["source_sha"]
                or row["book"]["snapshot_sha"] != event["source_book_sha"]
            ):
                raise ValueError("ECONOMICS_SOURCE_CAUSAL_LINK")
            book = row["book"]
            if (
                millis(book["first_known_at"]) > event["decision_ms"]
                or book["positions"] != event["positions"]
            ):
                raise ValueError("ECONOMICS_SOURCE_CAUSAL_LINK")
            account = book["account_id"]
            dexes = sorted(d.removeprefix("mainnet:perp:") for d in book["dex_census"])
            if (
                trace["source_accounts"].setdefault(source, account) != account
                or trace["source_dexes"].setdefault(source, dexes) != dexes
            ):
                raise ValueError("ECONOMICS_NATIVE_SCOPE_CHANGED")
            if verify_official_position_transition(
                db,
                alias=source,
                receipt_id=row["receipt_id"],
                receipt_sha=row["sha"],
                receipt=row["receipt"],
            ):
                trace["original_evidence_shas"].append(book["provider_raw_sha"])
            else:
                native = False
    trace["native_originals_verified"] = native and bool(trace["source_events"])
    trace["source_prefixes"] = pin["source_prefixes"]


def _quantile(values, probability):
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, max(0, int((len(ordered) - 1) * probability)))]


def compare_curves(old, new, *, start_ms, end_ms, step_ms, uncertainty):
    intervals, missing = [], []
    for at in range(start_ms, end_ms, step_ms):
        if any(at not in curve or at + step_ms not in curve for curve in (old, new)):
            missing.append(at)
        else:
            intervals.append((at, old[at + step_ms] - old[at], new[at + step_ms] - new[at]))
    if not intervals:
        return {
            "matched_intervals": 0,
            "missing_intervals": missing,
            "matched_net_pnl": None,
            "full_window_net_pnl": None,
            "uncertainty": {"status": "NO_MATCHED_INTERVALS"},
        }
    totals = [sum((r[i] for r in intervals), D(0)) for i in (1, 2)]
    pnl = {
        "legacy": str(totals[0]),
        "checkpoint": str(totals[1]),
        "difference": str(totals[1] - totals[0]),
    }
    drawdowns, tails = {}, {}
    for index, label in ((1, "legacy"), (2, "checkpoint")):
        peak = level = maximum = D(0)
        prior = None
        for row in intervals:
            if prior is None or row[0] != prior + step_ms:
                peak = level = D(0)
            level += row[index]
            peak = max(peak, level)
            maximum = max(maximum, peak - level)
            prior = row[0]
        drawdowns[label] = str(maximum)
        losses = sorted(r[index] for r in intervals)
        count = max(1, (len(losses) + 19) // 20)
        tails[label] = {
            "worst_interval_pnl": str(losses[0]),
            "empirical_lower_5pct_mean_pnl": str(sum(losses[:count], D(0)) / count),
        }
    size, repetitions = uncertainty["block_intervals"], uncertainty["replicates"]
    confidence = number(uncertainty["confidence"])
    if (
        type(size) is not int
        or size < 1
        or type(repetitions) is not int
        or not 2 <= repetitions <= 100000
        or not D(0) < confidence < D(1)
        or type(uncertainty["seed"]) is not int
    ):
        raise ValueError("ECONOMICS_UNCERTAINTY_SPEC")
    blocks = [
        [r[2] - r[1] for r in intervals[i : i + size]]
        for i in range(len(intervals) - size + 1)
        if all(intervals[i + j][0] == intervals[i][0] + j * step_ms for j in range(size))
    ]
    inference = {"status": "INSUFFICIENT_CONTIGUOUS_BLOCKS"}
    if len(blocks) >= 2 and len(intervals) >= 2 * size:
        rng, estimates = random.Random(uncertainty["seed"]), []
        for _ in range(repetitions):
            sample = []
            while len(sample) < len(intervals):
                sample.extend(rng.choice(blocks))
            estimates.append(sum(sample[: len(intervals)], D(0)))
        alpha = (D(1) - confidence) / 2
        inference = {
            "status": "CONDITIONAL_PAIRED_BLOCK_BOOTSTRAP",
            "lower": str(_quantile(estimates, alpha)),
            "upper": str(_quantile(estimates, 1 - alpha)),
            "confidence": str(confidence),
            "block_intervals": size,
            "replicates": repetitions,
            "seed": uncertainty["seed"],
            "independent_observation_count_is_not_replicates": True,
        }
    return {
        "matched_intervals": len(intervals),
        "missing_intervals": missing,
        "matched_net_pnl": pnl,
        "full_window_net_pnl": pnl if not missing else None,
        "max_contiguous_matched_drawdown": drawdowns,
        "observed_interval_tails": tails,
        "uncertainty": inference,
    }


def _references(rows):
    quotes, evidence = {}, []
    for row in rows:
        raw = _private(row["path"])
        if sha256(raw).hexdigest() != _sha(row["sha256"]):
            raise ValueError("ECONOMICS_REFERENCE_HASH")
        evidence.append({"role": row["role"], "sha256": row["sha256"]})
        if row["role"] != "FOLLOWER_L2_QUOTES":
            continue
        body = json.loads(raw)
        if body.get("schema") != "cwsa_economics_quotes_v1":
            raise ValueError("ECONOMICS_QUOTE_FILE_SCHEMA")
        for quote in body["quotes"]:
            PaperJournal._validate_market_quote(quote)
            if number(quote["best_bid"]) <= 0 or number(quote["best_ask"]) < number(
                quote["best_bid"]
            ):
                raise ValueError("ECONOMICS_EXECUTABLE_SIDES")
            quotes.setdefault(quote["instrument"], []).append(quote)
    for values in quotes.values():
        values.sort(key=lambda q: clock(q["first_known_at"]))
        by_time = {}
        for q in values:
            identity = millis(q["first_known_at"])
            if identity in by_time and digest(by_time[identity]) != digest(q):
                raise ValueError("ECONOMICS_QUOTE_EQUIVOCATION")
            by_time[identity] = q
    return quotes, evidence


def _curve(trace, quotes, window, max_age):
    states = trace["states"]
    times = [s["at_ms"] for s in states]
    result, gaps = {}, []
    for at in range(window["start_ms"], window["end_ms"] + 1, window["step_ms"]):
        index = bisect_right(times, at) - 1
        if index < 0 or at > times[-1]:
            gaps.append({"at_ms": at, "reason": "LEDGER_WINDOW_NOT_COVERED"})
            continue
        account = states[index]["account"]
        prices = {}
        held = {k for k, v in account["quantities"].items() if number(v)}
        held.update(
            k for book in account["pm_quantities"].values() for k, v in book.items() if number(v)
        )
        for instrument in sorted(held):
            candidates = [
                q for q in quotes.get(instrument, []) if millis(q["first_known_at"]) <= at
            ]
            if not candidates or not 0 <= at - millis(candidates[-1]["source_event_at"]) <= max_age:
                gaps.append(
                    {
                        "at_ms": at,
                        "instrument": instrument,
                        "reason": "INDEPENDENT_QUOTE_UNAVAILABLE",
                    }
                )
                break
            prices[Instrument.parse(instrument)] = number(candidates[-1]["mid_quote"])
        else:
            clone = Account.from_snapshot(
                Rulebook.from_dict(trace["manifest"]["rulebook"]), deepcopy(account)
            )
            if prices:
                clone.mark(prices, datetime.fromtimestamp(at / 1000, UTC).isoformat())
            result[at] = clone.equity
    return result, gaps


def _summary(trace, start, end):
    fills = [f for f in trace["executions"] if start <= f["decision_ms"] <= end]
    notional = sum((abs(number(f["quantity"]) * number(f["execution_price"])) for f in fills), D(0))
    return {
        "timing_policy": trace["timing_policy"],
        "manifest_sha": trace["manifest_sha"],
        "head_sha": trace["head_sha"],
        "recorded_mode": trace["manifest"].get("mode", "FORWARD_PAPER_SIMULATED_v1"),
        "frozen_k": trace["members"],
        "opportunity_counts": trace["opportunities"],
        "rulebook": trace["manifest"]["rulebook"],
        "modeled_fill_count": len(fills),
        "modeled_execution_notional": str(notional),
        "cumulative_ledger_costs": trace["final_account"]["costs"],
        "cost_policy_shas": trace["cost_policy_shas"],
        "opportunity_count_scope": "COMPLETE_PINNED_LEDGER",
        "coverage_events": trace["coverage_events"],
        "risk_breach_events": trace["breach_events"],
        "original_evidence_shas": trace["original_evidence_shas"],
        "source_accounts": trace["source_accounts"],
        "source_dexes": trace["source_dexes"],
        "source_prefixes": trace.get("source_prefixes"),
        "native_originals_verified": trace["native_originals_verified"],
        "execution_evidence": trace["execution_evidence"],
        "decision_events": trace["events"],
        "valuation_basis": "COMMON_INDEPENDENT_L2_MID_NET_OF_RECORDED_COSTS",
        "actually_executable_follower_pnl": None,
        "real_broker_fill_count": 0,
    }


def study_design_sha(spec):
    """Predeclared design excludes future data and ledger heads."""
    return digest(
        {
            "research_revision": spec["research_revision"],
            "window": spec["window"],
            "source_roster": spec["source_roster"],
            "portfolios": [
                {"portfolio_id": p["portfolio_id"], "frozen_k": p["frozen_k"]}
                for p in spec["portfolios"]
            ],
            "reference_quote_max_age_ms": spec["reference_quote_max_age_ms"],
            "uncertainty": spec["uncertainty"],
            "extra_cost_bps": spec["extra_cost_bps"],
            "timing_policies": [OLD, NEW],
        }
    )


def _criterion(spec, reviewer, portfolios, references):
    body = verify(spec["criterion"], reviewer, "cwsa-economics-reviewer-v1")
    if (
        body.get("schema") != "cwsa_economic_criterion_v1"
        or body["study_design_sha"] != study_design_sha(spec)
        or type(body["declared_ms"]) is not int
        or not 0 <= body["declared_ms"] < spec["window"]["start_ms"]
    ):
        raise ValueError("ECONOMICS_CRITERION_NOT_PREDECLARED")
    evidence_sha = _sha(body["derivation_evidence_sha"])
    if not any(
        r["role"] == "ECONOMIC_CRITERION_DERIVATION" and r["sha256"] == evidence_sha
        for r in references
    ):
        raise ValueError("ECONOMICS_CRITERION_DERIVATION_MISSING")
    minimum = body["minimum_matched_intervals"]
    delta, maximum = number(body["minimum_delta_pnl"]), number(body["maximum_checkpoint_drawdown"])
    if (
        type(minimum) is not int
        or minimum < 1
        or maximum < 0
        or type(body["require_positive_lower_bound"]) is not bool
    ):
        raise ValueError("ECONOMICS_CRITERION_NUMERIC_RULE")
    verdicts = {}
    for name, result in portfolios.items():
        pnl = result.get("full_window_net_pnl")
        uncertainty = result.get("uncertainty", {})
        if (
            pnl is None
            or result["matched_intervals"] < minimum
            or (
                body["require_positive_lower_bound"]
                and uncertainty.get("status") != "CONDITIONAL_PAIRED_BLOCK_BOOTSTRAP"
            )
        ):
            verdicts[name] = "UNAVAILABLE"
            continue
        passed = (
            number(pnl["difference"]) >= delta
            and number(result["max_contiguous_matched_drawdown"]["checkpoint"]) <= maximum
            and (not body["require_positive_lower_bound"] or number(uncertainty["lower"]) > 0)
        )
        verdicts[name] = (
            "PASS_MODELED_NUMERIC_CRITERION_ONLY" if passed else "FAIL_MODELED_NUMERIC_CRITERION"
        )
    return {
        "status": "SIGNED_PREDECLARED_CRITERION_EVALUATED_NO_PROMOTION",
        "payload": body,
        "sha": digest(body),
        "portfolio_results": verdicts,
        "approval": spec["criterion"],
        "reviewer_public_sha": sha256(reviewer.public_bytes_raw()).hexdigest(),
    }


def evaluate(spec: dict, *, revision: str, reviewer=None) -> dict:
    if (
        spec.get("schema") != "cwsa_matched_economics_spec_v1"
        or spec["research_revision"] != revision
    ):
        raise ValueError("ECONOMICS_SPEC_OR_REVISION")
    if re.fullmatch(r"[a-f0-9]{40}", revision) is None:
        raise ValueError("ECONOMICS_EXACT_REVISION_REQUIRED")
    window = spec["window"]
    start, end, step = (window[k] for k in ("start_ms", "end_ms", "step_ms"))
    if (
        any(type(v) is not int or v < 0 for v in (start, end, step))
        or not step
        or end <= start
        or (end - start) % step
    ):
        raise ValueError("ECONOMICS_WINDOW")
    if (
        type(spec["reference_quote_max_age_ms"]) is not int
        or spec["reference_quote_max_age_ms"] <= 0
    ):
        raise ValueError("ECONOMICS_REFERENCE_CLOCK_POLICY")
    roster = spec["source_roster"]
    sources = {r["source_id"]: r for r in roster}
    if not sources or len(sources) != len(roster):
        raise ValueError("ECONOMICS_SOURCE_ROSTER")
    for row in roster:
        _sha(row["account_sha"])
        if not row["dexes"] or row["dexes"] != sorted(set(row["dexes"])):
            raise ValueError("ECONOMICS_DEX_SCOPE")
    quotes, references = _references(spec["reference_data"])
    blockers = {
        "PROSPECTIVE_MATCHED_EVIDENCE_NOT_INDEPENDENTLY_QUALIFIED",
        "EXECUTABLE_NATIVE_FILL_EVIDENCE_MISSING",
    }
    if not quotes:
        blockers.add("INDEPENDENT_EXECUTABLE_REFERENCE_QUOTES_MISSING")
    portfolios = {}
    for row in spec["portfolios"]:
        identity, frozen = row["portfolio_id"], row["frozen_k"]
        if (
            identity in portfolios
            or not frozen
            or set(frozen) - set(sources)
            or any(number(v) <= 0 for v in frozen.values())
        ):
            raise ValueError("ECONOMICS_FROZEN_PORTFOLIO")
        result = {"matched_net_pnl": None, "status": "NOT_QUALIFIED", "blockers": []}
        portfolios[identity] = result
        if row["legacy"] is None or row["checkpoint"] is None:
            result["blockers"].append("MATCHED_POLICY_LEDGER_MISSING")
            blockers.update(result["blockers"])
            continue
        try:
            old = read_legacy(Path(row["legacy"]["path"]))
            new = read_checkpoint(Path(row["checkpoint"]["path"]), row["checkpoint"]["run_id"])
            for variant, trace in (("legacy", old), ("checkpoint", new)):
                pin = row[variant]
                if trace["head_sha"] != _sha(pin["head_sha"]) or trace["manifest_sha"] != _sha(
                    pin["manifest_sha"]
                ):
                    raise ValueError("ECONOMICS_LEDGER_PIN")
                if {k: number(v) for k, v in trace["members"].items()} != {
                    k: number(v) for k, v in frozen.items()
                }:
                    raise ValueError("ECONOMICS_ROSTER_OR_K_MISMATCH")
            _attest_legacy(old, row["legacy"])
            if any(
                trace["source_accounts"].get(s) != sources[s]["account_sha"]
                or trace["source_dexes"].get(s) != sources[s]["dexes"]
                for trace in (old, new)
                for s in frozen
            ):
                raise ValueError("ECONOMICS_NATIVE_SCOPE_MISMATCH")
            a, agaps = _curve(old, quotes, window, spec["reference_quote_max_age_ms"])
            b, bgaps = _curve(new, quotes, window, spec["reference_quote_max_age_ms"])
            result.update(
                compare_curves(
                    a, b, start_ms=start, end_ms=end, step_ms=step, uncertainty=spec["uncertainty"]
                )
            )
            summaries = {
                "legacy": _summary(old, start, end),
                "checkpoint": _summary(new, start, end),
            }
            result.update(variants=summaries, coverage_gaps={"legacy": agaps, "checkpoint": bgaps})
            if old["manifest"]["rulebook"] != new["manifest"]["rulebook"]:
                result["blockers"].append("DIFFERENT_RULEBOOKS_REQUIRE_CONFOUNDING_REVIEW")
            if agaps or bgaps or result["matched_intervals"] == 0:
                result["blockers"].append("MATCHED_WINDOW_COVERAGE_INCOMPLETE")
            if not old["native_originals_verified"]:
                result["blockers"].append("LEGACY_NATIVE_ORIGINALS_NOT_REATTESTED")
            result["cost_sensitivities"] = []
            for raw_bps in spec["extra_cost_bps"]:
                bps = number(raw_bps)
                if bps < 0:
                    raise ValueError("ECONOMICS_COST_SENSITIVITY")
                result["cost_sensitivities"].append(
                    {
                        "extra_cost_bps": str(bps),
                        "scope": "FIXED_EXECUTION_COST_PERTURBATION_NO_POLICY_RERUN",
                        "net_pnl": {
                            k: str(
                                number(result["full_window_net_pnl"][k])
                                - number(v["modeled_execution_notional"]) * bps / 10000
                            )
                            if result["full_window_net_pnl"] is not None
                            else None
                            for k, v in summaries.items()
                        },
                    }
                )
        except (ValueError, KeyError, OSError, sqlite3.Error) as exc:
            result.clear()
            result.update(
                matched_net_pnl=None,
                full_window_net_pnl=None,
                status="NOT_QUALIFIED",
                blockers=[str(exc)],
            )
        blockers.update(result["blockers"])
    criterion = {"status": "APPROVED_ECONOMIC_CRITERION_MISSING"}
    if spec["criterion"] is not None and reviewer is not None:
        criterion = _criterion(spec, reviewer, portfolios, references)
    else:
        blockers.add("APPROVED_ECONOMIC_CRITERION_MISSING")
    report = {
        "schema": "cwsa_matched_follower_economics_v1",
        "research_revision": revision,
        "input_sha": digest(spec),
        "roster_sha": digest(roster),
        "source_roster": roster,
        "window": window,
        "portfolios": portfolios,
        "reference_evidence": references,
        "criterion": criterion,
        "blockers": sorted(blockers),
        "verdict": "NOT_QUALIFIED",
        "timing_policies": [OLD, NEW],
        "scientifically_qualified": False,
        "trading_authorized": False,
        "selection": "FROZEN_K_AND_ROSTER_NO_OPTIMIZATION",
        "limitations": [
            "Matched NAV is modeled follower equity; it is not executable broker PnL.",
            "Common independent marks do not create fills or repair missing source history.",
            "Block-bootstrap intervals condition on the observed paths; they do not bound regime or model error.",
            "Latency, gap and changed-risk sensitivities require separately replayed policy ledgers.",
        ],
    }
    report["report_sha"] = digest(report)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spec", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--criterion-public-key", type=Path)
    args = parser.parse_args(argv)
    revision = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    if subprocess.check_output(["git", "status", "--porcelain"], text=True).strip():
        raise ValueError("ECONOMICS_REQUIRES_CLEAN_PINNED_REVISION")
    reviewer = None
    if args.criterion_public_key is not None:
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

        reviewer = Ed25519PublicKey.from_public_bytes(_private(args.criterion_public_key))
    report = evaluate(json.loads(_private(args.spec)), revision=revision, reviewer=reviewer)
    from .v4_source_export import _atomic_private_output

    _atomic_private_output(args.output, canonical(report))
    print(
        json.dumps(
            {
                "verdict": report["verdict"],
                "report_sha": report["report_sha"],
                "blockers": report["blockers"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
