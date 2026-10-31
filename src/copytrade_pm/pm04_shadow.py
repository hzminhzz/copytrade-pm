"""PM-04 three-pod shadow coordinator on top of PM-03's sole risk/account engine.

Research-only envelope: pod targets are not orders, provider observations are
not broker authentication, and PM-02 budgets never synthesize positions.
The SAME PM-03 event ledger seals coordinator state, accounting, and recovery.
"""

from __future__ import annotations

from decimal import Decimal as D

from .pm03_account import Account, Instrument, RiskState, ZERO, clock, digest, number
from .pm03_attribution import IntendedVirtualBooks, explain_economics
from .pm03_execution import execute_targets
from .pm03_memory import Event
from .pm03_risk import RiskPolicy, classify, loss_under_shock
from .pm03_run import _cost_model, _evidence, _quotes
from .pm04_broker import empty_broker, ingest, pending_quantities, reconcile

POLICY_SCHEMA = "pm04_research_policy_v1"
STATE_SCHEMA = "pm04_shadow_state_v1"
TARGET_SCHEMA = "pm04_pod_target_v1"


def _positive(policy: dict, key: str) -> D:
    x = number(policy[key])
    if x <= ZERO:
        raise ValueError(f"INVALID_PM04_POLICY_{key}")
    return x


def validate_policy(policy: dict) -> None:
    if (
        policy.get("schema") != POLICY_SCHEMA
        or not policy.get("version")
        or not policy.get("approval_reference")
    ):
        raise ValueError("UNAPPROVED_OR_UNVERSIONED_PM04_RESEARCH_POLICY")
    if not isinstance(policy.get("pods"), dict) or not policy["pods"]:
        raise ValueError("PM04_PODS_REQUIRED")
    budget_ids = [x.get("budget_ref") for x in policy["pods"].values()]
    if len(set(budget_ids)) != len(budget_ids):
        raise ValueError("DUPLICATE_POD_BUDGET_REF")
    for pod, limits in policy["pods"].items():
        if not pod or not limits.get("budget_ref"):
            raise ValueError("MISSING_POD_BUDGET_REF")
        for key in ("daily_loss", "max_drawdown", "stress_loss"):
            _positive(limits, key)
    for key in (
        "max_gross_notional",
        "max_instrument_fraction_equity",
        "max_stress_loss",
        "reconcile_tolerance",
    ):
        _positive(policy, key)
    if number(policy["max_instrument_fraction_equity"]) > D("1"):
        raise ValueError("INVALID_CONCENTRATION_FRACTION")
    if number(policy["reserve"]) < ZERO:
        raise ValueError("INVALID_PM04_RESERVE")
    for field in ("max_signal_age_seconds", "broker_max_age_seconds", "batch_seconds"):
        if not isinstance(policy.get(field), int) or policy[field] < 0:
            raise ValueError("INVALID_PM04_TIME_POLICY")
    if policy["execution_policy"] not in ("IMMEDIATE", "BATCHED", "ASYMMETRIC"):
        raise ValueError("UNKNOWN_PM04_EXECUTION_POLICY")
    if policy["execution_policy"] != "IMMEDIATE" and policy["batch_seconds"] != 300:
        raise ValueError("FIVE_MINUTE_BATCH_CONTRACT_REQUIRED")
    if type(policy.get("broker_required")) is not bool:
        raise ValueError("BROKER_EVIDENCE_REQUIREMENT_MUST_BE_EXPLICIT")


def _fund_independent_pod_budgets(account: Account, policy: dict) -> dict:
    """Allocate explicit synthetic loss envelopes inside PM-03 contract headroom.

    Do not assume that individually sized pods are collectively funded.
    Day and lifetime drawdown envelopes refer to different time horizons.
    """
    reserve = number(policy["reserve"])
    daily = account.rulebook.daily_allowance(account.daily_start_balance)
    if daily is None:
        raise ValueError("UNKNOWN_DAILY_CONTRACTUAL_BUDGET")
    long_term_limits = [
        number(value)
        for value in (account.rulebook.static_loss, account.rulebook.trailing_loss)
        if value is not None
    ]
    if not long_term_limits:
        raise ValueError("UNKNOWN_LONG_TERM_CONTRACTUAL_BUDGET")
    daily_available = daily - reserve
    drawdown_available = min(long_term_limits) - reserve
    stress_available = number(policy["max_stress_loss"]) - reserve
    reserved = {
        kind: sum((number(p[kind]) for p in policy["pods"].values()), ZERO)
        for kind in ("daily_loss", "max_drawdown", "stress_loss")
    }
    if reserved["daily_loss"] > daily_available:
        raise ValueError("UNFUNDED_POD_DAILY_LOSS_ALLOWANCES")
    if reserved["max_drawdown"] > drawdown_available:
        raise ValueError("UNFUNDED_POD_DRAWDOWN_ALLOWANCES")
    if reserved["stress_loss"] > stress_available:
        raise ValueError("UNFUNDED_POD_STRESS_ALLOWANCES")
    return {
        "source": "PM03_RULEBOOK_SYNTHETIC",
        "rulebook_sha": account.rulebook.sha,
        "policy_sha": digest(policy),
        "reserve": str(reserve),
        "daily_reserved": str(reserved["daily_loss"]),
        "daily_available": str(daily_available),
        "drawdown_reserved": str(reserved["max_drawdown"]),
        "drawdown_available": str(drawdown_available),
        "stress_reserved": str(reserved["stress_loss"]),
        "stress_available": str(stress_available),
        "not_contractually_approved": True,
    }


def _make_intended(state: dict) -> IntendedVirtualBooks:
    row = state["intended"]
    return IntendedVirtualBooks(
        qty={
            p: {Instrument.parse(k): number(q) for k, q in b.items()} for p, b in row["qty"].items()
        },
        cash={p: number(q) for p, q in row["cash"].items()},
        last_prices={Instrument.parse(k): number(v) for k, v in row["marks"].items()},
        quality=row["quality"],
    )


def _store_intended(state: dict, intended: IntendedVirtualBooks) -> None:
    state["intended"] = {
        "qty": {
            p: {k.key: str(q) for k, q in sorted(b.items())}
            for p, b in sorted(intended.qty.items())
        },
        "cash": {p: str(q) for p, q in sorted(intended.cash.items())},
        "marks": {k.key: str(q) for k, q in sorted(intended.last_prices.items())},
        "quality": intended.quality,
    }


def _books(rows: dict[str, dict[str, str]]) -> dict[str, dict[Instrument, D]]:
    return {p: {Instrument.parse(k): number(q) for k, q in b.items()} for p, b in rows.items()}


def _net(rows: dict[str, dict[str, str]]) -> dict[Instrument, D]:
    out: dict[Instrument, D] = {}
    for book in _books(rows).values():
        for inst, qty in book.items():
            out[inst] = out.get(inst, ZERO) + qty
    return out


def _seal_economics(account: Account) -> None:
    state = account.pm04_state
    intended = _make_intended(state)
    # P&L is always read from existing Account PM books; no rival PM ledger.
    state["economics"] = explain_economics(account, intended, number(state["execution_drag"]))
    state["economics"]["executed_pod_fees"] = {
        p: str(account.pm_costs.get(p, ZERO)) for p in sorted(state["policy"]["pods"])
    }
    state["economics"]["executed_pod_funding"] = {
        p: str(account.pm_funding.get(p, ZERO)) for p in sorted(state["policy"]["pods"])
    }
    state["economics"]["internal_crosses"] = state["internal_crosses"]


def _stats(account: Account, shocks: tuple[dict[Instrument, D], ...] = ()) -> None:
    state = account.pm04_state
    policy = state["policy"]
    pnl = account.pm_equity_pnl()
    if shocks:
        state["last_shocks"] = [
            {k.key: str(q) for k, q in sorted(shock.items())} for shock in shocks
        ]
    else:
        shocks = tuple(
            {Instrument.parse(k): number(q) for k, q in row.items()} for row in state["last_shocks"]
        )
    for pod in sorted(policy["pods"]):
        data = state["pod_stats"][pod]
        value = pnl.get(pod, ZERO)
        if data["daily_key"] != account.daily_key:
            data["daily_key"] = account.daily_key
            data["day_start_pnl"] = str(value)
        data["peak_pnl"] = str(max(number(data["peak_pnl"]), value))
        drawdown = max(ZERO, number(data["peak_pnl"]) - value)
        data["max_drawdown_seen"] = str(max(number(data["max_drawdown_seen"]), drawdown))
        daily_loss = max(ZERO, number(data["day_start_pnl"]) - value)
        data["daily_loss"] = str(daily_loss)
        data["pnl"] = str(value)
        limits = policy["pods"][pod]
        daily_remaining = _positive(limits, "daily_loss") - daily_loss
        dd_remaining = _positive(limits, "max_drawdown") - drawdown
        data["remaining_daily"] = str(max(ZERO, daily_remaining))
        data["remaining_drawdown"] = str(max(ZERO, dd_remaining))
        book = account.pm_quantities.get(pod, {})
        stress = ZERO
        if book:
            if not shocks:
                stress = D("Infinity")
            else:
                stress = max(
                    (loss_under_shock(book, account.marks, s) for s in shocks), default=ZERO
                )
        data["stress_loss"] = str(stress)
        if daily_remaining <= ZERO or dd_remaining <= ZERO:
            data["state"] = "SUSPENDED"
            data["reason"] = "POD_DAILY_OR_DRAWDOWN_LIMIT"
        elif stress >= _positive(limits, "stress_loss"):
            if data["state"] != "SUSPENDED":
                data["state"] = "REDUCED"
                data["reason"] = "POD_STRESS_LIMIT"
        # REDUCED/SUSPENDED are latched pod vetoes. A favorable next mark
        # must never silently restore risk authority or replenish budgets.
        elif data["state"] == "RESTORED":
            data["state"] = "ACTIVE"
            data["reason"] = None
    _seal_economics(account)


def _outstanding(account: Account) -> None:
    state = account.pm04_state
    effective = _net(state["routed_targets"])
    outstanding = {}
    for instrument in set(account.quantities) | set(effective):
        actual = account.quantities.get(instrument, ZERO)
        wanted = effective.get(instrument, ZERO)
        if actual and (wanted == ZERO or (actual * wanted > ZERO and abs(wanted) < abs(actual))):
            outstanding[instrument.key] = str(wanted - actual)
    state["pending_reductions"] = dict(sorted(outstanding.items()))


def _exposure(account: Account, at: str) -> dict:
    state = account.pm04_state
    policy = state["policy"]
    inflight = pending_quantities(account)
    actual = account.gross()
    pending_notional = sum((qty * account.marks.get(k, ZERO) for k, qty in inflight.items()), ZERO)
    # Reserve every queued new pod increase, not only submitted broker intent.
    # Opposing/new virtual targets cannot cancel each other for risk reserve.
    queued: dict[Instrument, D] = {}
    for pod, wanted in state["pod_targets"].items():
        if state["pod_stats"][pod]["state"] in ("SUSPENDED", "REDUCED"):
            continue
        routed = state["routed_targets"][pod]
        for key, raw_qty in wanted.items():
            if key not in state["batch_open"]:
                continue
            proposed = number(raw_qty)
            old = number(routed.get(key, "0"))
            addition = (
                max(ZERO, abs(proposed) - abs(old)) if proposed * old >= ZERO else abs(proposed)
            )
            inst = Instrument.parse(key)
            queued[inst] = queued.get(inst, ZERO) + addition
    queued_notional = sum((qty * account.marks.get(k, ZERO) for k, qty in queued.items()), ZERO)
    current = actual + pending_notional + queued_notional
    cap = _positive(policy, "max_gross_notional")
    reasons = []
    if current > cap:
        reasons.append("MARKED_GROSS_LIMIT_BREACH")
    concentration_cap = account.equity * number(policy["max_instrument_fraction_equity"])
    if any(
        (abs(account.quantities.get(k, ZERO)) + inflight.get(k, ZERO) + queued.get(k, ZERO))
        * account.marks[k]
        > concentration_cap
        for k in set(account.quantities) | set(inflight) | set(queued)
        if k in account.marks
    ):
        reasons.append("MARKED_CONCENTRATION_BREACH")
    if any(k not in account.marks for k in set(inflight) | set(queued)):
        reasons.append("UNKNOWN_PENDING_INFLIGHT_MARK")
    state["exposure"] = {
        "actual_gross": str(actual),
        "pending_inflight_gross": str(pending_notional),
        "queued_new_risk_gross": str(queued_notional),
        "total_conservative_gross": str(current),
        "gross_limit": str(cap),
        "concentration_cap": str(concentration_cap),
    }
    if reasons:
        if account.risk != RiskState.HALT:
            account.risk = RiskState.RED
        account.risk_reasons = tuple(sorted(set(account.risk_reasons) | set(reasons)))
        signature = (at, *sorted(reasons))
        if not state["risk_breaches"] or state["risk_breaches"][-1]["signature"] != list(signature):
            state["risk_breaches"].append(
                {
                    "at": at,
                    "signature": list(signature),
                    "reasons": sorted(reasons),
                    "gross": str(current),
                    "limit": str(cap),
                    "unresolved_exposure": {
                        k.key: str(v) for k, v in account.quantities.items() if v
                    },
                }
            )
    _outstanding(account)
    return state["exposure"]


def refresh(account: Account, at: str) -> None:
    if not account.pm04_state:
        return
    state = account.pm04_state
    if state["policy"]["broker_required"] or state["broker"]["observations"]:
        reconcile(account, state["policy"], at)
    _stats(account)
    _exposure(account, at)


def on_account_event(account: Account, kind: str, raw: dict, at: str) -> None:
    """Reprice PM intended books and repair the report after legacy PM-03 events.

    Funding is booked exclusively through Account.post_funding, with no
    PM-04 duplicate cash ledger. Legacy PM-03 runs are untouched.
    """
    if not account.pm04_state:
        return
    if kind == "MARK" and raw.get("state_known", False):
        _desired_refresh(
            account.pm04_state,
            {Instrument.parse(k): number(v) for k, v in raw["prices"].items()},
        )
    refresh(account, at)
    if kind == "FUNDING" and _force_pod_reductions(account):
        # A funding-driven suspension requests an exit even when the funding
        # event has no executable quote. The actual holdings remain unchanged.
        _outstanding(account)
    if kind == "STAGE" and (
        account.rulebook.sha != account.pm04_state["budget_funding"]["rulebook_sha"]
    ):
        account.risk = RiskState.HALT
        reason = "PM04_POLICY_RULEBOOK_CHANGED_REAUTH_REQUIRED"
        account.halt_reason = reason
        account.risk_reasons = tuple(sorted(set(account.risk_reasons) | {reason}))


def bootstrap(account: Account, policy: dict, at: str) -> dict:
    if account.pm04_state:
        raise ValueError("PM04_POLICY_ALREADY_FROZEN")
    validate_policy(policy)
    funding_receipt = _fund_independent_pod_budgets(account, policy)
    if any(account.quantities.values()) or any(account.pm_quantities.values()):
        raise ValueError("PM04_CANNOT_BOOTSTRAP_UNRECONCILED_ACCOUNT")
    account.pm04_state = {
        "schema": STATE_SCHEMA,
        "policy": policy,
        "policy_sha": digest(policy),
        "budget_funding": funding_receipt,
        "created_at": at,
        "pod_targets": {p: {} for p in sorted(policy["pods"])},
        "routed_targets": {p: {} for p in sorted(policy["pods"])},
        "versions": {p: {} for p in sorted(policy["pods"])},
        "provenance": {p: {} for p in sorted(policy["pods"])},
        "batch_open": {},
        "pod_stats": {
            p: {
                "state": "ACTIVE",
                "reason": None,
                "daily_key": account.daily_key,
                "day_start_pnl": "0",
                "pnl": "0",
                "peak_pnl": "0",
                "max_drawdown_seen": "0",
                "daily_loss": "0",
                "remaining_daily": str(number(policy["pods"][p]["daily_loss"])),
                "remaining_drawdown": str(number(policy["pods"][p]["max_drawdown"])),
                "stress_loss": "0",
            }
            for p in sorted(policy["pods"])
        },
        "pending_reductions": {},
        "risk_breaches": [],
        "broker": empty_broker(),
        "last_shocks": [],
        "intended": {"qty": {}, "cash": {}, "marks": {}, "quality": "RESEARCH_SYNTHETIC_MID_PROXY"},
        "execution_drag": "0",
        "internal_crosses": [],
        "pod_rejections": [],
        "expired_targets": [],
        "blocked_observations": [],
        "economics": {},
        "exposure": {},
    }
    refresh(account, at)
    return {"status": "CONFIG_FROZEN", "policy_sha": digest(policy), "research_only": True}


def _check_target(row: dict, event: Event, state: dict) -> tuple[str, str, D]:
    pod = row.get("pod")
    if pod not in state["policy"]["pods"]:
        raise ValueError("UNAPPROVED_POD")
    inst = Instrument.parse(row["instrument"])
    if inst not in state["_permitted"]:
        raise ValueError("UNSUPPORTED_INSTRUMENT_ID")
    if row.get("budget_ref") != state["policy"]["pods"][pod]["budget_ref"]:
        raise ValueError("INVALID_POD_BUDGET_REF")
    source_sha = row.get("source_sha")
    if not (
        isinstance(source_sha, str)
        and len(source_sha) == 64
        and all(c in "0123456789abcdef" for c in source_sha)
    ):
        raise ValueError("INVALID_TARGET_SOURCE_SHA")
    source = clock(row["source_event_at"])
    known = clock(row["first_known_at"])
    decision = clock(event.decision_at)
    if not source <= known <= clock(event.first_known_at) <= decision:
        raise ValueError("TARGET_CAUSAL_SOURCE_CLOCK_VIOLATION")
    if (decision - known).total_seconds() > state["policy"]["max_signal_age_seconds"]:
        raise ValueError("STALE_FIRST_KNOWN_POD_TARGET")
    revision = row.get("revision")
    if not isinstance(revision, int) or revision <= state["versions"][pod].get(inst.key, 0):
        raise ValueError("CONFLICTING_POD_TARGET_REVISION")
    return pod, inst.key, number(row["quantity"])


def _desired_refresh(state: dict, obs: dict[Instrument, D]) -> None:
    intent = _make_intended(state)
    wanted = _books(state["pod_targets"])
    marks = {**intent.last_prices, **obs}
    intent.mark_and_target(wanted, marks)
    _store_intended(state, intent)


def _update_targets(account: Account, event: Event, payload: dict) -> bool:
    state = account.pm04_state
    changed_now = False
    policy = state["policy"]["execution_policy"]
    for row in payload.get("targets", []):
        pod, instrument, qty = _check_target(row, event, state)
        old = number(state["routed_targets"][pod].get(instrument, "0"))
        state["pod_targets"][pod][instrument] = str(qty)
        state["versions"][pod][instrument] = row["revision"]
        state["provenance"][pod][instrument] = {
            k: row[k]
            for k in ("source_event_at", "first_known_at", "source_sha", "budget_ref", "revision")
        }
        if state["pod_stats"][pod]["state"] in ("SUSPENDED", "REDUCED"):
            qty = ZERO
        if policy == "IMMEDIATE":
            state["routed_targets"][pod][instrument] = str(qty)
            changed_now = True
        elif policy == "ASYMMETRIC" and (
            qty == ZERO or (old * qty > ZERO and abs(qty) <= abs(old))
        ):
            state["routed_targets"][pod][instrument] = str(qty)
            changed_now = True
            if qty == number(state["pod_targets"][pod][instrument]):
                # No queued new risk on this pod/instrument.
                if all(
                    state["routed_targets"][p].get(instrument, "0")
                    == state["pod_targets"][p].get(instrument, "0")
                    for p in state["pod_targets"]
                ):
                    state["batch_open"].pop(instrument, None)
        elif policy == "ASYMMETRIC" and old * qty < ZERO:
            # Close old exposure promptly; never cross the sign in one order.
            state["routed_targets"][pod][instrument] = "0"
            changed_now = True
            state["batch_open"].setdefault(instrument, event.decision_at)
        else:
            state["batch_open"].setdefault(instrument, event.decision_at)
    return changed_now


def _batch_due(account: Account, event: Event) -> bool:
    state = account.pm04_state
    policy = state["policy"]
    changed = False
    for k, opened in list(sorted(state["batch_open"].items())):
        if (clock(event.decision_at) - clock(opened)).total_seconds() < policy["batch_seconds"]:
            continue
        still_pending = False
        instrument = Instrument.parse(k)
        for pod in sorted(state["pod_targets"]):
            desired = number(state["pod_targets"][pod].get(k, "0"))
            if state["pod_stats"][pod]["state"] in ("SUSPENDED", "REDUCED"):
                desired = ZERO
            old = number(state["routed_targets"][pod].get(k, "0"))
            provenance = state["provenance"][pod].get(k)
            expired = (
                desired != old
                and provenance is not None
                and (clock(event.decision_at) - clock(provenance["first_known_at"])).total_seconds()
                > policy["max_signal_age_seconds"]
            )
            if expired:
                # A scheduler delay is a rejected new proposal, not a crash,
                # implicit timestamp backfill, or permission to fill stale risk.
                state["expired_targets"].append(
                    {
                        "pod": pod,
                        "instrument": k,
                        "decision_at": event.decision_at,
                        "first_known_at": provenance["first_known_at"],
                        "revision": provenance["revision"],
                    }
                )
                state["routed_targets"][pod][k] = str(old)
            else:
                actual = account.quantities.get(instrument, ZERO)
                if actual and actual * desired < ZERO and abs(desired) > ZERO:
                    # Exit before reversal. A rejected close never becomes flat.
                    state["routed_targets"][pod][k] = "0"
                    still_pending = True
                else:
                    state["routed_targets"][pod][k] = str(desired)
            changed = changed or old != number(state["routed_targets"][pod][k])
        if not still_pending:
            state["batch_open"].pop(k)
    return changed


def _force_pod_reductions(account: Account) -> bool:
    state = account.pm04_state
    changed = False
    for pod, stats in state["pod_stats"].items():
        if stats["state"] in ("SUSPENDED", "REDUCED"):
            for inst, value in list(state["routed_targets"][pod].items()):
                if number(value):
                    state["routed_targets"][pod][inst] = "0"
                    changed = True
    return changed


def _vet_pod_new_risk(account: Account, shocks: tuple[dict[Instrument, D], ...], at: str) -> bool:
    """Veto unsafe virtual pod increases independently of central account HALT.

    Even two offsetting virtual pods can carry material hedge-break exposure.
    Failure here reduces only the offending pod, never unrelated PM targets.
    """
    state = account.pm04_state
    changed = False
    for pod in sorted(state["policy"]["pods"]):
        old_book = account.pm_quantities.get(pod, {})
        desired = _books({pod: state["routed_targets"][pod]})[pod]
        has_new_risk = any(
            abs(q) > abs(old_book.get(k, ZERO)) or (old_book.get(k, ZERO) * q < ZERO)
            for k, q in desired.items()
        )
        if not has_new_risk:
            continue
        reasons = []
        stats = state["pod_stats"][pod]
        if stats["state"] in ("SUSPENDED", "REDUCED"):
            reasons.append("POD_NOT_ACTIVE")
        elif not shocks or any(set(desired) - set(shock) for shock in shocks):
            reasons.append("UNKNOWN_POD_STRESS")
        else:
            worst = max((loss_under_shock(desired, account.marks, s) for s in shocks), default=ZERO)
            if worst > _positive(state["policy"]["pods"][pod], "stress_loss"):
                reasons.append("PRETRADE_POD_STRESS_BUDGET_REJECT")
        if number(stats["remaining_daily"]) <= ZERO or number(stats["remaining_drawdown"]) <= ZERO:
            reasons.append("POD_LOSS_BUDGET_EXHAUSTED")
        if reasons:
            for key, qty in list(state["routed_targets"][pod].items()):
                if number(qty):
                    state["routed_targets"][pod][key] = "0"
                    changed = True
            # Disallow re-entry on later ticks until an explicit restoration
            # event, while preserving the central account's independent veto.
            if stats["state"] != "SUSPENDED":
                stats["state"] = "REDUCED"
            stats["reason"] = ";".join(sorted(reasons))
            state["pod_rejections"].append(
                {
                    "at": at,
                    "pod": pod,
                    "reasons": sorted(reasons),
                    "requested": {k.key: str(v) for k, v in desired.items()},
                }
            )
    return changed


def _force_overcap_reductions(account: Account) -> bool:
    """Request a modeled reduction without assuming executable liquidity.

    This overlays already-held virtual pod books only; no change to target
    provenance, PM-03 financial holdings, or submitted broker orders occurs.
    """
    state = account.pm04_state
    cap = _positive(state["policy"], "max_gross_notional")
    actual_gross = account.gross()
    per_instrument = account.equity * number(state["policy"]["max_instrument_fraction_equity"])
    ratio = min(D("1"), cap / actual_gross) if actual_gross > ZERO else D("1")
    changed = False
    for inst, qty in account.quantities.items():
        if not qty or inst not in account.marks:
            continue
        marked = abs(qty * account.marks[inst])
        local_ratio = min(ratio, per_instrument / marked) if marked else ratio
        if local_ratio >= D("1"):
            continue
        for pod, book in account.pm_quantities.items():
            old = book.get(inst, ZERO)
            desired = old * local_ratio
            current = number(state["routed_targets"].get(pod, {}).get(inst.key, "0"))
            # Never increase exposure while trying to mitigate a limit breach.
            if old and (abs(current) > abs(desired) or current * old < ZERO):
                state["routed_targets"][pod][inst.key] = str(desired)
                changed = True
    return changed


def _pretrade_guard(
    account: Account,
    target: dict[Instrument, D],
    shocks: tuple[dict[Instrument, D], ...],
    at: str,
) -> tuple[list[str], bool]:
    state = account.pm04_state
    policy = state["policy"]
    pending = pending_quantities(account)
    marks = account.marks
    actual = account.quantities
    increase = any(
        abs(target.get(k, ZERO)) > abs(actual.get(k, ZERO))
        or (actual.get(k, ZERO) and target.get(k, ZERO) * actual.get(k, ZERO) < ZERO)
        for k in set(target) | set(actual)
    )
    if not increase:
        return [], False
    reasons: list[str] = []
    if any(k not in marks for k in set(target) | set(pending)):
        reasons.append("UNKNOWN_PRETRADE_MARK")
        return reasons, True
    if any(
        actual.get(k, ZERO) and target.get(k, ZERO) * actual.get(k, ZERO) < ZERO
        for k in set(target)
    ):
        reasons.append("REVERSAL_REQUIRES_CONFIRMED_FLAT")
    # Worst-case pending orders and new increases: do not credit an unfilled
    # reduction on another instrument (or opposing unknown in-flight side).
    incremental = {
        k: max(ZERO, abs(target.get(k, ZERO)) - abs(actual.get(k, ZERO)))
        for k in set(target) | set(actual)
    }
    projected = account.gross() + sum(
        (
            (incremental.get(k, ZERO) + pending.get(k, ZERO)) * marks[k]
            for k in set(incremental) | set(pending)
        ),
        ZERO,
    )
    if projected > _positive(policy, "max_gross_notional"):
        reasons.append("PRETRADE_GROSS_REJECT")
    concentration_cap = account.equity * number(policy["max_instrument_fraction_equity"])
    if any(
        (abs(actual.get(k, ZERO)) + incremental.get(k, ZERO) + pending.get(k, ZERO)) * marks[k]
        > concentration_cap
        for k in set(actual) | set(incremental) | set(pending)
    ):
        reasons.append("PRETRADE_CONCENTRATION_REJECT")
    if not shocks:
        reasons.append("UNKNOWN_PRETRADE_STRESS")
    else:
        if any(set(target) - set(s) for s in shocks):
            reasons.append("INCOMPLETE_PRETRADE_STRESS")
        else:
            pending_stress = max(
                (
                    sum(
                        (pending.get(k, ZERO) * marks[k] * abs(s.get(k, ZERO)) for k in pending),
                        ZERO,
                    )
                    for s in shocks
                ),
                default=ZERO,
            )
            worst = max((loss_under_shock(target, marks, s) for s in shocks), default=ZERO)
            total = worst + pending_stress
            floor, _ = account.floor()
            if total > _positive(policy, "max_stress_loss"):
                reasons.append("PRETRADE_STRESS_BUDGET_REJECT")
            if floor is None or account.equity - floor <= total + number(policy["reserve"]):
                reasons.append("PRETRADE_CONTRACTUAL_HEADROOM_REJECT")
    broker = state["broker"]
    if policy["broker_required"] and not broker["ready"]:
        reasons.append("AUTHORITATIVE_BROKER_UNRESOLVED")
    if broker["discrepancies"]:
        reasons.append("BROKER_DISCREPANCIES")
    if account.risk in (RiskState.RED, RiskState.HALT) or account.breached:
        reasons.append("ACCOUNT_RISK_STOP")
    if reasons:
        if account.risk != RiskState.HALT:
            account.risk = RiskState.RED
        account.risk_reasons = tuple(sorted(set(account.risk_reasons) | set(reasons)))
        state["risk_breaches"].append(
            {
                "at": at,
                "signature": [at, "PRETRADE"],
                "reasons": sorted(set(reasons)),
                "gross": str(projected),
                "limit": str(policy["max_gross_notional"]),
                "unresolved_exposure": {k.key: str(q) for k, q in actual.items() if q},
                "hard_pretrade_rejection": True,
            }
        )
    return sorted(set(reasons)), True


def _execute(
    account: Account,
    event: Event,
    raw: dict,
    policy: RiskPolicy,
    mode: str,
    obs: dict[Instrument, object],
    shocks: tuple[dict[Instrument, D], ...],
) -> dict:
    state = account.pm04_state
    evidence = _evidence(raw["evidence"])
    if evidence.input_status != mode:
        raise ValueError("RESEARCH_MODE_MISMATCH")
    target_books = _books(state["routed_targets"])
    # The account is the sole source of broker-equivalent holdings. A required
    # external position snapshot must reconcile before any new-risk attempt.
    proposed = account.external_targets(target_books)
    violations, has_increase = _pretrade_guard(account, proposed, shocks, event.decision_at)
    if violations and has_increase:
        _outstanding(account)
        return {
            "status": "BLOCKED_PRETRADE",
            "rejections": violations,
            "fills": [],
            "internal_crosses": [],
            "remaining": {
                k.key: str(proposed.get(k, ZERO) - account.quantities.get(k, ZERO))
                for k in set(proposed) | set(account.quantities)
            },
        }
    decision = classify(
        account, target_books, {k: q.mark for k, q in obs.items()}, shocks, evidence, policy
    )
    permitted = (
        mode == "RESEARCH_SYNTHETIC"
        and evidence.trusted
        and evidence.account_state_known
        and evidence.market_state_known
        and evidence.market_coverage_valid
        and not evidence.pending_unknown_orders
        and account.rulebook.confirmed
        and not (state["policy"]["broker_required"] and not state["broker"]["ready"])
        and not state["broker"]["discrepancies"]
    )
    report = execute_targets(
        account,
        decision["approved"],
        obs,
        _cost_model(raw["costs"]),
        decision_at=event.decision_at,
        hypothetical_fill_at=event.hypothetical_fill_at,
        permitted=permitted,
    )
    for fill in report["fills"]:
        q = number(fill["quantity"])
        drag = q * (number(fill["execution_price"]) - number(fill["mid_price"]))
        state["execution_drag"] = str(number(state["execution_drag"]) + drag)
    state["internal_crosses"].extend(report["internal_crosses"])
    state["last_risk_decision"] = {
        k: v for k, v in decision.items() if k not in ("approved", "proposed")
    }
    return report


def apply_pm04(account: Account, event: Event, policy: RiskPolicy, mode: str) -> dict:
    """Process one PM-04 event inside the existing replay-first ShadowRun."""
    kind = event.kind
    raw = event.payload["input"]
    if kind == "PM04_CONFIG":
        if mode != "RESEARCH_SYNTHETIC":
            raise ValueError("PM04_RESEARCH_CONFIGURATION_ONLY")
        return bootstrap(account, raw["policy"], event.decision_at)
    if not account.pm04_state or account.pm04_state.get("schema") != STATE_SCHEMA:
        raise ValueError("PM04_CONFIG_EVENT_REQUIRED")
    state = account.pm04_state
    if kind == "PM04_BROKER":
        if clock(raw["observation"]["first_known_at"]) > clock(event.first_known_at):
            raise ValueError("BROKER_OBSERVATION_NOT_YET_KNOWN")
        result = ingest(account, raw["observation"], state["policy"], event.decision_at)
        refresh(account, event.decision_at)
        return result
    if kind == "PM04_RESTORE":
        pod = raw["pod"]
        if pod not in state["pod_stats"] or not raw.get("authorization_reference"):
            raise ValueError("EXPLICIT_POD_RESTORE_AUTHORIZATION_REQUIRED")
        if account.risk in (RiskState.RED, RiskState.HALT) or account.breached:
            raise ValueError("ACCOUNT_STOP_OVERRIDES_POD_RESTORE")
        stats = state["pod_stats"][pod]
        limits = state["policy"]["pods"][pod]
        if number(stats["daily_loss"]) >= number(limits["daily_loss"]) or number(
            stats["max_drawdown_seen"]
        ) >= number(limits["max_drawdown"]):
            raise ValueError("POD_LOSS_BUDGET_NOT_REPLENISHED")
        stats["state"] = "RESTORED"
        stats["reason"] = None
        return {"status": "POD_EXPLICITLY_RESTORED", "pod": pod}
    if kind not in ("PM04_SIGNAL", "PM04_TICK"):
        raise ValueError("UNKNOWN_PM04_EVENT")
    if mode != "RESEARCH_SYNTHETIC":
        raise ValueError("PM04_NON_SYNTHETIC_ORDER_PATH_DISABLED")
    observations = _quotes(raw["observations"])
    if any(clock(q.first_known_at) > clock(event.first_known_at) for q in observations.values()):
        raise ValueError("MARKET_OBSERVATION_NOT_YET_KNOWN")
    for quote in observations.values():
        quote.validate(event.decision_at)
    tracked = set(account.quantities) | {
        k for b in account.pm_quantities.values() for k, q in b.items() if q
    }
    stale = [
        k.key
        for k, q in observations.items()
        if (clock(event.decision_at) - clock(q.first_known_at)).total_seconds()
        > _cost_model(raw["costs"]).max_age_seconds
    ]
    blocked = []
    if tracked - set(observations):
        blocked.append("MISSING_EXISTING_POSITION_MARK")
    if stale:
        blocked.append("STALE_MARKET_OBSERVATION")
    if not raw["evidence"].get("account_state_known") or not raw["evidence"].get(
        "market_state_known"
    ):
        blocked.append("UNKNOWN_AUTHORITATIVE_ACCOUNT_OR_MARKET")
    if blocked:
        # Record the fail-closed decision in the durable PM-03 event chain.
        # Never mark a stale price or pretend an absent account is flat.
        account.risk = RiskState.HALT
        account.halt_reason = ";".join(sorted(blocked))
        account.risk_reasons = tuple(sorted(set(account.risk_reasons) | set(blocked)))
        state["blocked_observations"].append(
            {
                "at": event.decision_at,
                "reasons": sorted(blocked),
                "stale": stale,
                "missing": sorted(k.key for k in tracked - set(observations)),
            }
        )
        refresh(account, event.decision_at)
        return {
            "status": "HALT_UNRECONCILED_MARKET_OR_ACCOUNT",
            "rejections": blocked,
            "no_live_order_path": True,
        }
    account.mark({k: q.mark for k, q in observations.items()}, event.decision_at)
    shocks = tuple(
        {Instrument.parse(k): number(v) for k, v in shock.items()} for shock in raw["shocks"]
    )
    # Temporary local check only; exact permitted markets come from PM-03.
    state["_permitted"] = account.rulebook.permitted
    try:
        refresh(account, event.decision_at)
        changed = False
        if kind == "PM04_SIGNAL":
            changed = _update_targets(account, event, raw)
            _desired_refresh(state, {k: q.mark for k, q in observations.items()})
        else:
            _desired_refresh(state, {k: q.mark for k, q in observations.items()})
        changed = _batch_due(account, event) or changed
        changed = _vet_pod_new_risk(account, shocks, event.decision_at) or changed
        changed = _force_pod_reductions(account) or changed
        changed = _force_overcap_reductions(account) or changed
        if not changed and not state["pending_reductions"]:
            result = {
                "status": "DEFERRED_BATCH_OR_NO_CHANGE",
                "fills": [],
                "internal_crosses": [],
                "rejections": [],
                "remaining": {},
            }
        else:
            result = _execute(account, event, raw, policy, mode, observations, shocks)
        _stats(account, shocks)
        _exposure(account, event.decision_at)
    finally:
        state.pop("_permitted", None)
    account.verify()
    return {
        "status": result["status"],
        "execution": result,
        "risk": account.risk.value,
        "batch_open": state["batch_open"],
        "pending_reductions": state["pending_reductions"],
        "economics": state["economics"],
        "no_live_order_path": True,
    }
