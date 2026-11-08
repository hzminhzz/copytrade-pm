"""Consumable, durable forward PAPER execution opportunities.

Targets are descriptions of desired inventory, never standing order authority.
Only a PM-03 ledger event may consume an opportunity or change virtual inventory.
No broker transport, live orders, or historical-fill reconstruction exists here.
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal as D
from typing import Mapping

from .pm03_account import Account, Instrument, ZERO, clock, digest, number
from .pm03_memory import Event
from .pm03_risk import RiskPolicy

ENTRY_DELAY_SECONDS = 300
ENTRY_GRACE_SECONDS = 30
POLICY_VERSION = "single_shot_market_paper_v3"
ESTIMATED_POLICY_VERSION = "single_shot_vike_minute_estimated_v4"


def _price_order(
    delta: D,
    quote: Mapping,
    *,
    step: D,
    minimum_notional: D,
    decision_at: str,
    policy_version: str,
) -> dict:
    if policy_version == ESTIMATED_POLICY_VERSION:
        if quote.get("schema") != "paper_vike_minute_estimated_quote_v1":
            raise ValueError("PAPER_VIKE_ESTIMATED_PRICE_REQUIRED")
        from .pm_vike_minute import EstimatedMinuteExecutionModel

        return EstimatedMinuteExecutionModel().price(
            delta,
            quote["vike_observation"],
            step=step,
            minimum_notional=minimum_notional,
            decision_at=decision_at,
        )
    if policy_version != POLICY_VERSION or "vike_observation" in quote:
        raise ValueError("PAPER_L2_PRICE_REQUIRED")
    return SingleShotMarketExecutionModel().price(
        delta,
        quote,
        step=step,
        minimum_notional=minimum_notional,
    )


def _time_plus(stamp: str, seconds: int) -> str:
    return (clock(stamp) + timedelta(seconds=seconds)).isoformat()


def _new_state(account: Account) -> dict:
    return account.pm04_state.setdefault(
        "paper_execution",
        {
            "schema": "pm04_single_shot_intents_v2",
            "active": {},
            "history": {},
            "last_source_seq": {},
            "last_source_positions": {},
            "outcomes": {},
            "exits": {},
            "exit_history": {},
            "unresolved_exposures": {},
            "consumed_quotes": {},
        },
    )


def _claim_quote_once(
    state: dict,
    instrument: Instrument,
    delta: D,
    quote_sha: str,
    order_id: str,
    intent_id: str,
    at: str,
) -> bool:
    """One locally observed L2 side cannot support multiple modeled fills.

    This claim is replayed atomically with the PM-03 financial event.
    """
    side = "BUY" if delta > ZERO else "SELL"
    key = digest([instrument.key, side, quote_sha])
    if key in state["consumed_quotes"]:
        return False
    state["consumed_quotes"][key] = {
        "order_id": order_id,
        "intent_id": intent_id,
        "attempted_at": at,
    }
    return True


class SingleShotMarketExecutionModel:
    """Prices ONE market-order opportunity against known, executable-side depth."""

    def __init__(self, *, taker_fee_bps: D = D("5"), extra_slippage_bps: D = D("2")):
        self.taker_fee_bps = number(taker_fee_bps)
        self.extra_slippage_bps = number(extra_slippage_bps)
        if self.taker_fee_bps < ZERO or self.extra_slippage_bps < ZERO:
            raise ValueError("NEGATIVE_PAPER_EXECUTION_COST")

    def price(
        self,
        quantity: D,
        quote: Mapping,
        *,
        step: D,
        minimum_notional: D,
    ) -> dict:
        qty = number(quantity)
        step = number(step)
        minimum_notional = number(minimum_notional)
        if not qty or step <= ZERO or minimum_notional <= ZERO:
            return {"status": "REJECTED_NATIVE_AMOUNT"}
        if abs(qty) % step != ZERO:
            return {"status": "REJECTED_NATIVE_STEP"}
        side = "ask_levels" if qty > ZERO else "bid_levels"
        px_key = "best_ask" if qty > ZERO else "best_bid"
        size_key = "ask_size" if qty > ZERO else "bid_size"
        levels = quote.get(side) or [[quote[px_key], quote[size_key]]]
        if not isinstance(levels, list) or not levels:
            return {"status": "UNPRICEABLE_MARKET_ORDER"}
        prior = None
        available = ZERO
        fills = []
        remaining = abs(qty)
        cost = ZERO
        direction = D("1") if qty > ZERO else D("-1")
        for level in levels:
            if not isinstance(level, (tuple, list)) or len(level) != 2:
                return {"status": "UNPRICEABLE_MARKET_ORDER"}
            price, depth = number(level[0]), number(level[1])
            if price <= ZERO or depth <= ZERO:
                return {"status": "UNPRICEABLE_MARKET_ORDER"}
            if prior is None and price != number(quote[px_key]):
                return {"status": "UNPRICEABLE_MARKET_ORDER"}
            if prior is not None and (
                (qty > ZERO and price < prior) or (qty < ZERO and price > prior)
            ):
                return {"status": "UNPRICEABLE_MARKET_ORDER"}
            prior = price
            available += depth
            amount = min(remaining, depth)
            if amount:
                modeled_price = price * (D("1") + direction * self.extra_slippage_bps / D("10000"))
                fills.append(
                    {
                        "quantity": str(amount * direction),
                        "displayed_price": str(price),
                        "modeled_price": str(modeled_price),
                    }
                )
                cost += amount * modeled_price
                remaining -= amount
            if not remaining:
                break
        if remaining:
            return {
                "status": "UNPRICEABLE_MARKET_ORDER",
                "observed_depth": str(available),
                "required_quantity": str(abs(qty)),
                "unfilled_quantity": str(qty),
            }
        vwap = (cost / abs(qty)).quantize(D("0.00000001"))
        if abs(qty) * vwap < minimum_notional:
            return {"status": "REJECTED_MIN_NOTIONAL"}
        fee = (abs(qty * vwap) * self.taker_fee_bps / D("10000")).quantize(D("0.00000001"))
        return {
            "status": "FILLED",
            "quantity": str(qty),
            "vwap": str(vwap),
            "fee": str(fee),
            "fills": fills,
            "displayed_depth_consumed": str(abs(qty)),
            "modeled_only": True,
            "real_order_count": 0,
            "single_market_intent": True,
        }


def apply_paper_event(account: Account, event: Event, policy: RiskPolicy, mode: str) -> dict:
    """Replay-deterministic PM-04 PAPER path; never enters legacy PM04_TICK."""
    if mode != "RESEARCH_SYNTHETIC":
        raise ValueError("SINGLE_SHOT_RESEARCH_ONLY")
    raw = event.payload["input"]
    state = _new_state(account)
    version = account.pm04_state["policy"].get("version", POLICY_VERSION)
    if version not in (POLICY_VERSION, ESTIMATED_POLICY_VERSION):
        raise ValueError("PAPER_EXECUTION_POLICY_UNRECOGNIZED")
    if event.kind == "PM04_PAPER_SOURCE":
        pod = raw["pod"]
        seq = raw["source_seq"]
        if pod not in account.pm04_state["policy"]["pods"]:
            raise ValueError("UNSELECTED_PAPER_POD")
        if type(seq) is not int or seq <= state["last_source_seq"].get(pod, 0):
            raise ValueError("REPEATED_OR_REGRESSED_SOURCE_RECEIPT")
        positions = {key: str(number(qty)) for key, qty in raw["positions"].items() if number(qty)}
        for key in positions:
            if Instrument.parse(key) not in account.rulebook.permitted:
                raise ValueError("PAPER_UNPERMITTED_SOURCE_INSTRUMENT")
        prev = state["last_source_positions"].get(pod, {})
        state["last_source_seq"][pod] = seq
        state["last_source_positions"][pod] = positions
        held = account.pm_quantities.get(pod, {})
        k = number(account.pm04_state["policy"]["fixed_k_by_pod"][pod])
        # An EXIT is authorized by a *new reduction in the leader's book*,
        # never by a residual difference from a previously failed paper exit.
        leader_reduced = any(
            number(previous)
            and (
                number(previous) * number(positions.get(inst, "0")) <= ZERO
                or abs(number(positions.get(inst, "0"))) < abs(number(previous))
            )
            for inst, previous in prev.items()
        )
        reduction_needed = any(
            qty
            and (
                number(positions.get(inst.key, "0")) * k * qty <= ZERO
                or abs(number(positions.get(inst.key, "0")) * k) < abs(qty)
            )
            for inst, qty in held.items()
        )
        pending_exit = state["exits"].get(pod)
        if pending_exit and pending_exit["status"] == "PENDING_EXIT":
            # One queued market attempt is retained through source revisions.
            # Changes may revise its size, but NEVER its identity or deadline.
            if pending_exit.get("reason") != "POD_RISK_LATCHED":
                if reduction_needed:
                    pending_exit["positions"] = positions
                    pending_exit["source_seq"] = seq
                    pending_exit["source_sha"] = raw["source_sha"]
                    pending_exit.setdefault("updates", []).append(
                        {
                            "source_seq": seq,
                            "source_sha": raw["source_sha"],
                            "known_at": raw["first_known_at"],
                        }
                    )
                else:
                    pending_exit["status"] = "CANCELED_SOURCE_RESTORED"
                    pending_exit["terminal_at"] = event.decision_at
        elif (
            leader_reduced
            and reduction_needed
            and not (pending_exit is not None and pending_exit.get("reason") == "POD_RISK_LATCHED")
        ):
            exit_id = digest([event.payload["run_id"], pod, seq, "EXIT", version])
            row = {
                "exit_id": exit_id,
                "pod": pod,
                "source_seq": seq,
                "source_sha": raw["source_sha"],
                "first_known_at": raw["first_known_at"],
                "source_event_at": event.source_event_at,
                "positions": positions,
                "created_at": event.decision_at,
                "deadline_at": _time_plus(raw["first_known_at"], ENTRY_GRACE_SECONDS),
                "status": "PENDING_EXIT",
                "updates": [],
            }
            state["exits"][pod] = row
            state["exit_history"][exit_id] = row
        active_id = state["active"].get(pod)
        active = state["history"].get(active_id) if active_id else None
        if positions == prev:
            return {"status": "UNCHANGED_SOURCE", "source_seq": seq}
        if active is not None and active["status"] == "PENDING_5M":
            active["source_seq"] = seq
            active["source_sha"] = raw["source_sha"]
            active["source_event_at"] = event.source_event_at
            active["positions"] = positions
            active["updated_at"] = event.decision_at
            active["updates"].append(
                {"at": event.decision_at, "source_seq": seq, "source_sha": raw["source_sha"]}
            )
            if not positions:
                active["status"] = "CANCELED"
                active["terminal_at"] = event.decision_at
                return {"status": "CANCELED_BEFORE_DUE", "intent_id": active_id}
            return {"status": "PENDING_UPDATED", "intent_id": active_id}
        if not positions:
            return {
                "status": "EXIT_REQUESTED"
                if leader_reduced and reduction_needed
                else "SOURCE_CLOSED",
                "source_seq": seq,
            }
        needs_new_risk = any(
            not held.get(Instrument.parse(key), ZERO)
            or held[Instrument.parse(key)] * number(qty) < ZERO
            or abs(k * number(qty)) > abs(held[Instrument.parse(key)])
            for key, qty in positions.items()
        )
        if not needs_new_risk:
            return {
                "status": "EXIT_REQUESTED"
                if leader_reduced and reduction_needed
                else "SOURCE_UPDATED_NO_NEW_RISK",
                "source_seq": seq,
            }
        known = raw["first_known_at"]
        if clock(known) > clock(event.decision_at) or clock(known) < clock(event.source_event_at):
            raise ValueError("SOURCE_FIRST_KNOWN_CLOCK_INVALID")
        intent_id = digest([event.payload["run_id"], pod, seq, known, version])
        if intent_id in state["history"]:
            raise ValueError("PAPER_INTENT_ID_COLLISION")
        intent = {
            "intent_id": intent_id,
            "pod": pod,
            "source_seq": seq,
            "source_sha": raw["source_sha"],
            "source_event_at": event.source_event_at,
            "first_known_at": known,
            "due_at": _time_plus(known, ENTRY_DELAY_SECONDS),
            "deadline_at": _time_plus(known, ENTRY_DELAY_SECONDS + ENTRY_GRACE_SECONDS),
            "created_at": event.decision_at,
            "updated_at": event.decision_at,
            "status": "PENDING_5M",
            "positions": positions,
            "updates": [
                {"at": event.decision_at, "source_seq": seq, "source_sha": raw["source_sha"]}
            ],
        }
        state["history"][intent_id] = intent
        state["active"][pod] = intent_id
        return {"status": "PENDING_5M", "intent_id": intent_id, "due_at": intent["due_at"]}
    if event.kind == "PM04_PAPER_SOURCE_GAP":
        # A disconnected official source cannot authorize pending new risk.
        # Do not touch held inventory, pod risk latches or unresolved exits.
        pod = raw["pod"]
        intent_id = raw["intent_id"]
        if pod not in account.pm04_state["policy"]["pods"]:
            raise ValueError("UNSELECTED_PAPER_POD")
        if state["active"].get(pod) != intent_id:
            raise ValueError("SOURCE_GAP_INTENT_MISMATCH")
        intent = state["history"].get(intent_id)
        if intent is None or intent["status"] != "PENDING_5M":
            raise ValueError("SOURCE_GAP_INTENT_NOT_PENDING")
        intent["status"] = "CANCELED_SOURCE_GAP"
        intent["terminal_at"] = event.decision_at
        intent["reason"] = "OFFICIAL_POSITION_STREAM_NOT_CONTINUOUS"
        return {"status": "CANCELED_SOURCE_GAP", "intent_id": intent_id}
    if event.kind == "PM04_PAPER_EXPIRE":
        intent = state["history"].get(raw["intent_id"])
        if intent is None or intent["status"] != "PENDING_5M":
            raise ValueError("PAPER_INTENT_NOT_PENDING")
        if clock(event.decision_at) <= clock(intent["deadline_at"]):
            raise ValueError("PREMATURE_PAPER_EXPIRATION")
        intent["status"] = "EXPIRED_NO_TRADE"
        intent["terminal_at"] = event.decision_at
        intent["reason"] = raw["reason"]
        return {"status": "EXPIRED_NO_TRADE", "intent_id": intent["intent_id"]}
    if event.kind == "PM04_PAPER_RISK_TRIGGER":
        pod = raw["pod"]
        if pod not in account.pm04_state["policy"]["pods"]:
            raise ValueError("UNSELECTED_RISK_EXIT_POD")
        if account.pm04_state["pod_stats"][pod]["state"] not in ("SUSPENDED", "REDUCED"):
            raise ValueError("PAPER_RISK_EXIT_NOT_LATCHED")
        if not any(account.pm_quantities.get(pod, {}).values()):
            raise ValueError("PAPER_RISK_EXIT_NO_INVENTORY")
        pending = state["exits"].get(pod)
        if pending is not None and pending.get("reason") == "POD_RISK_LATCHED":
            raise ValueError("PAPER_RISK_EXIT_DUPLICATE")
        if pending is not None and pending["status"] == "PENDING_EXIT":
            # Escalation is a risk authorization, not a second market order.
            # Preserve the original opportunity's clock, deadline and ID.
            pending["positions"] = {}
            pending["reason"] = "POD_RISK_LATCHED"
            pending["risk_trigger_at"] = event.decision_at
            return {"status": "PENDING_RISK_EXIT_ESCALATED", "exit_id": pending["exit_id"]}
        exit_id = digest([event.payload["run_id"], pod, event.event_id, version])
        row = {
            "exit_id": exit_id,
            "pod": pod,
            "source_seq": state["last_source_seq"].get(pod, 0),
            "source_sha": raw.get("quote_sha", ""),
            "first_known_at": event.decision_at,
            "source_event_at": event.decision_at,
            "positions": {},
            "created_at": event.decision_at,
            "deadline_at": _time_plus(event.decision_at, ENTRY_GRACE_SECONDS),
            "status": "PENDING_EXIT",
            "reason": "POD_RISK_LATCHED",
        }
        state["exits"][pod] = row
        state["exit_history"][exit_id] = row
        return {"status": "PENDING_RISK_EXIT", "exit_id": exit_id}
    if event.kind == "PM04_PAPER_EXIT":
        pod = raw["pod"]
        pending = state["exits"].get(pod)
        if pending is None or pending["exit_id"] != raw["exit_id"]:
            raise ValueError("PAPER_EXIT_INTENT_UNKNOWN")
        if pending["status"] != "PENDING_EXIT":
            raise ValueError("PAPER_EXIT_ALREADY_ATTEMPTED")
        if pending["source_seq"] != raw["source_seq"]:
            raise ValueError("PAPER_EXIT_SOURCE_REVISION")
        quotes = raw["quotes"]
        for key, quote in quotes.items():
            if digest(quote) != raw["quote_shas"][key]:
                raise ValueError("PAPER_EXIT_QUOTE_HASH_MISMATCH")
            age = (clock(event.decision_at) - clock(quote["first_known_at"])).total_seconds()
            if not 0 <= age <= 30:
                raise ValueError("PAPER_EXIT_STALE_QUOTE")
        prices = {Instrument.parse(key): number(q["mid_quote"]) for key, q in quotes.items()}
        held = {k for k, qty in account.quantities.items() if qty}
        if held - set(prices):
            raise ValueError("PAPER_EXIT_UNMARKED_INVENTORY")
        account.mark(prices, event.decision_at)
        targets = {Instrument.parse(key): number(qty) for key, qty in raw["targets"].items()}
        attempts = {}
        for inst, actual in sorted(account.pm_quantities.get(pod, {}).items()):
            if not actual:
                continue
            wanted = targets.get(inst, ZERO)
            if wanted * actual <= ZERO:
                wanted = ZERO
            if abs(wanted) >= abs(actual):
                continue
            delta = wanted - actual
            row = raw["markets"][inst.key]
            priced = _price_order(
                delta,
                quotes[inst.key],
                step=number(row["amount_step"]),
                minimum_notional=number(row["minimum_notional"]),
                decision_at=event.decision_at,
                policy_version=version,
            )
            order_id = digest([pending["exit_id"], inst.key, version])
            if priced["status"] == "FILLED" and not _claim_quote_once(
                state,
                inst,
                delta,
                raw["quote_shas"][inst.key],
                order_id,
                pending["exit_id"],
                event.decision_at,
            ):
                priced = {
                    "status": (
                        "REJECTED_REUSED_PRICE_OBSERVATION"
                        if version == ESTIMATED_POLICY_VERSION
                        else "REJECTED_REUSED_L2_QUOTE"
                    )
                }
            attempts[inst.key] = {"order_id": order_id, "requested": str(delta), **priced}
            if priced["status"] == "FILLED":
                account.simulate_fill(
                    inst,
                    number(priced["quantity"]),
                    number(priced["vwap"]),
                    number(priced["fee"]),
                    accepted=True,
                    allocated={pod: number(priced["quantity"])},
                )
                account.pm04_state["execution_drag"] = str(
                    number(account.pm04_state["execution_drag"])
                    + number(priced["quantity"]) * (number(priced["vwap"]) - prices[inst])
                )
        from .pm04_shadow import _exposure, _stats

        state["outcomes"][pending["exit_id"]] = attempts
        incomplete = {
            inst.key: str(qty)
            for inst, qty in account.pm_quantities.get(pod, {}).items()
            if qty
            and (
                number(raw["targets"].get(inst.key, "0")) * qty <= ZERO
                or abs(number(raw["targets"].get(inst.key, "0"))) < abs(qty)
            )
        }
        pending["status"] = "UNRESOLVED_EXPOSURE" if incomplete else "EXIT_FILLED"
        pending["attempted_at"] = event.decision_at
        pending["terminal_at"] = event.decision_at
        if incomplete:
            state["unresolved_exposures"][pod] = incomplete
        else:
            state["unresolved_exposures"].pop(pod, None)
        _stats(
            account,
            (
                {inst: D("-0.05") for inst in prices},
                {inst: D("0.05") for inst in prices},
            ),
        )
        _exposure(account, event.decision_at)
        account.verify()
        return {
            "status": pending["status"],
            "attempts": attempts,
            "unresolved_exposure": incomplete,
            "no_broker_orders": True,
        }
    if event.kind == "PM04_PAPER_EXIT_UNRESOLVED":
        pod = raw["pod"]
        pending = state["exits"].get(pod)
        if pending is None or pending["status"] != "PENDING_EXIT":
            raise ValueError("PAPER_EXIT_NOT_PENDING")
        pending["status"] = "UNRESOLVED_EXPOSURE"
        pending["terminal_at"] = event.decision_at
        pending["reason"] = raw["reason"]
        state["unresolved_exposures"][pod] = {
            inst.key: str(qty) for inst, qty in account.pm_quantities.get(pod, {}).items() if qty
        }
        return {"status": "UNRESOLVED_EXPOSURE", "pod": pod}
    if event.kind != "PM04_PAPER_EXECUTE":
        raise ValueError("UNKNOWN_SINGLE_SHOT_EVENT")
    intent = state["history"].get(raw["intent_id"])
    if intent is None or intent["status"] != "PENDING_5M":
        raise ValueError("PAPER_INTENT_NOT_PENDING")
    if not clock(intent["due_at"]) <= clock(event.decision_at) <= clock(intent["deadline_at"]):
        raise ValueError("PAPER_ATTEMPT_OUTSIDE_WINDOW")
    if raw["source_seq"] != intent["source_seq"] or raw["source_sha"] != intent["source_sha"]:
        raise ValueError("PAPER_ATTEMPT_STALE_SOURCE")
    pod = intent["pod"]
    targets = {Instrument.parse(key): number(qty) for key, qty in raw["targets"].items()}
    if set(targets) != {Instrument.parse(k) for k in intent["positions"]}:
        raise ValueError("PAPER_TARGET_SOURCE_SCOPE_MISMATCH")
    if any(inst not in account.rulebook.permitted for inst in targets):
        raise ValueError("PAPER_UNPERMITTED_ORDER_INSTRUMENT")
    for key, quote in raw["quotes"].items():
        if digest(quote) != raw["quote_shas"][key]:
            raise ValueError("PAPER_QUOTE_HASH_MISMATCH")
        if (
            not 0
            <= (clock(event.decision_at) - clock(quote["first_known_at"])).total_seconds()
            <= 30
        ):
            raise ValueError("PAPER_ATTEMPT_STALE_QUOTE")
    prices = {Instrument.parse(k): number(q["mid_quote"]) for k, q in raw["quotes"].items()}
    held = {k for k, q in account.quantities.items() if q}
    if held - set(prices):
        raise ValueError("PAPER_HELD_INVENTORY_UNMARKED")
    account.mark(prices, event.decision_at)
    from .pm04_shadow import _exposure, _pretrade_guard, _stats

    quotes = raw["quotes"]
    # A single batch is one decision. Each instrument has at most one
    # market-order intent, even when the book has multiple matching levels.
    shocks = (
        {inst: D("-0.05") for inst in prices},
        {inst: D("0.05") for inst in prices},
    )
    destination = {**account.pm_quantities.get(pod, {}), **targets}
    # A reversal must close first. Never open opposite risk in this entry event.
    destination = {
        inst: (
            ZERO if account.pm_quantities.get(pod, {}).get(inst, ZERO) * wanted < ZERO else wanted
        )
        for inst, wanted in destination.items()
    }
    consolidated = dict(account.quantities)
    for inst in set(destination) | set(account.pm_quantities.get(pod, {})):
        consolidated[inst] = (
            consolidated.get(inst, ZERO)
            - account.pm_quantities.get(pod, {}).get(inst, ZERO)
            + destination.get(inst, ZERO)
        )
    reasons, has_increase = _pretrade_guard(account, consolidated, shocks, event.decision_at)
    stats = account.pm04_state["pod_stats"][pod]
    if has_increase and stats["state"] in ("SUSPENDED", "REDUCED"):
        reasons.append("POD_RISK_LATCHED")
    if has_increase and any(
        abs(qty * prices[inst] * D("0.05"))
        > number(account.pm04_state["policy"]["pods"][pod]["stress_loss"])
        for inst, qty in destination.items()
        if qty
    ):
        reasons.append("POD_STRESS_LIMIT")
    attempts = {}
    for inst, target in sorted(destination.items()):
        actual = account.pm_quantities.get(pod, {}).get(inst, ZERO)
        delta = target - actual
        if not delta:
            continue
        if delta * actual < ZERO and abs(delta) > abs(actual):
            delta = -actual
        order_id = digest([intent["intent_id"], inst.key, version])
        if reasons and has_increase and abs(target) > abs(actual):
            attempts[inst.key] = {
                "order_id": order_id,
                "status": "REJECTED_RISK",
                "rejections": sorted(set(reasons)),
                "requested": str(delta),
            }
            continue
        if delta and (delta * actual >= ZERO or abs(delta) <= abs(actual)):
            market = raw["markets"][inst.key]
            priced = _price_order(
                delta,
                quotes[inst.key],
                step=number(market["amount_step"]),
                minimum_notional=number(market["minimum_notional"]),
                decision_at=event.decision_at,
                policy_version=version,
            )
            if priced["status"] == "FILLED" and not _claim_quote_once(
                state,
                inst,
                delta,
                raw["quote_shas"][inst.key],
                order_id,
                intent["intent_id"],
                event.decision_at,
            ):
                priced = {
                    "status": (
                        "REJECTED_REUSED_PRICE_OBSERVATION"
                        if version == ESTIMATED_POLICY_VERSION
                        else "REJECTED_REUSED_L2_QUOTE"
                    )
                }
            attempts[inst.key] = {"order_id": order_id, "requested": str(delta), **priced}
            if priced["status"] == "FILLED":
                qty = number(priced["quantity"])
                account.simulate_fill(
                    inst,
                    qty,
                    number(priced["vwap"]),
                    number(priced["fee"]),
                    accepted=True,
                    allocated={pod: qty},
                )
                account.pm04_state["execution_drag"] = str(
                    number(account.pm04_state["execution_drag"])
                    + qty * (number(priced["vwap"]) - prices[inst])
                )
        else:
            attempts[inst.key] = {
                "order_id": order_id,
                "status": "REJECTED_REVERSAL",
                "requested": str(delta),
            }
    account.pm04_state["routed_targets"][pod] = {k.key: str(q) for k, q in destination.items()}
    _stats(account, shocks)
    _exposure(account, event.decision_at)
    account.verify()
    statuses = {row["status"] for row in attempts.values()}
    intent["status"] = (
        "FILLED" if statuses == {"FILLED"} else "PARTIAL" if "FILLED" in statuses else "REJECTED"
    )
    intent["attempted_at"] = event.decision_at
    intent["terminal_at"] = event.decision_at
    intent["order_ids"] = {key: value["order_id"] for key, value in attempts.items()}
    state["outcomes"][intent["intent_id"]] = attempts
    return {
        "status": intent["status"],
        "intent_id": intent["intent_id"],
        "attempts": attempts,
        "no_broker_orders": True,
    }
