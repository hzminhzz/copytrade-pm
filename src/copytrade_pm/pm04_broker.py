"""PM-04 read-only execution-observation reconciliation.

These are externally supplied observations, NOT authenticated broker connectivity.
Never creates or routes an order. Reconciliation is against the sole PM-03
shadow account; discrepancies block further risk rather than fabricating fills.
"""

from __future__ import annotations

from decimal import Decimal as D

from .pm03_account import Account, Instrument, RiskState, clock, digest, number, ZERO

BROKER_SCHEMA = "pm04_broker_observation_v1"
ORDER_KINDS = {"ORDER_INTENT", "ACK", "PARTIAL_FILL", "FILL", "CANCEL", "REJECT"}
SNAPSHOT_KINDS = {"POSITION_SNAPSHOT", "BALANCE_SNAPSHOT", "FEES_FUNDING", "RECONNECT"}


def empty_broker() -> dict:
    return {
        "schema": "pm04_broker_state_v1",
        "observations": {},
        "orders": {},
        "position_snapshot": None,
        "balance_snapshot": None,
        "fee_snapshot": None,
        "reconnect_at": None,
        "discrepancies": [],
        "ready": False,
    }


def _snapshot(account: Account, broker: dict, policy: dict, at: str) -> list[str]:
    """Refresh as-of reconciliation; do not equate missing observations with flat."""
    reasons: list[str] = []
    tolerance = number(policy["reconcile_tolerance"])
    max_age = int(policy["broker_max_age_seconds"])
    required = policy["broker_required"]
    snapshots = (
        ("position_snapshot", "POSITION"),
        ("balance_snapshot", "BALANCE"),
        ("fee_snapshot", "FEES_FUNDING"),
    )
    for field, name in snapshots:
        snap = broker[field]
        if snap is None:
            if required:
                reasons.append(f"MISSING_{name}_SNAPSHOT")
            continue
        if (clock(at) - clock(snap["first_known_at"])).total_seconds() > max_age:
            reasons.append(f"STALE_{name}_SNAPSHOT")
        if broker["reconnect_at"] is not None and (
            clock(snap["first_known_at"]) <= clock(broker["reconnect_at"])
        ):
            reasons.append(f"RECONNECT_{name}_UNRESOLVED")
    p = broker["position_snapshot"]
    if p is not None:
        observed = {Instrument.parse(k): number(v) for k, v in p["positions"].items()}
        keys = set(observed) | set(account.quantities)
        if any(
            abs(observed.get(k, ZERO) - account.quantities.get(k, ZERO)) > tolerance for k in keys
        ):
            reasons.append("POSITION_MISMATCH")
    b = broker["balance_snapshot"]
    if b is not None and (
        abs(number(b["balance"]) - account.balance) > tolerance
        or abs(number(b["equity"]) - account.equity) > tolerance
    ):
        reasons.append("BALANCE_MISMATCH")
    fees = broker["fee_snapshot"]
    if fees is not None and (
        abs(number(fees["fee_total"]) - account.costs) > tolerance
        or abs(number(fees["funding_total"]) - account.funding) > tolerance
    ):
        reasons.append("FEES_FUNDING_MISMATCH")
    for order in broker["orders"].values():
        if order["status"] == "UNKNOWN":
            reasons.append("UNKNOWN_ORDER")
        if order["status"] == "CANCELED" or order["status"] == "CANCELED_PARTIAL":
            # A cancel acknowledgement does not prove a fill/cancel race is over.
            if p is None or clock(p["first_known_at"]) <= clock(order["last_known_at"]):
                reasons.append("CANCEL_FILL_RACE_UNRESOLVED")
    broker["discrepancies"] = sorted(set(reasons))
    broker["ready"] = (
        all(broker[key] is not None for key, _ in snapshots)
        and not broker["discrepancies"]
        and policy["broker_required"]
    )
    if any(
        x in reasons
        for x in (
            "POSITION_MISMATCH",
            "BALANCE_MISMATCH",
            "FEES_FUNDING_MISMATCH",
            "UNKNOWN_ORDER",
            "CANCEL_FILL_RACE_UNRESOLVED",
        )
    ):
        account.risk = RiskState.HALT
        account.halt_reason = "BROKER_RECONCILIATION_DISCREPANCY"
        account.risk_reasons = tuple(sorted(set(account.risk_reasons) | set(reasons)))
    return broker["discrepancies"]


def reconcile(account: Account, policy: dict, at: str) -> list[str]:
    return _snapshot(account, account.pm04_state["broker"], policy, at)


def pending_quantities(account: Account) -> dict[Instrument, D]:
    """Conservatively count each unresolved in-flight order at full remaining size."""
    result: dict[Instrument, D] = {}
    broker = account.pm04_state["broker"]
    for order in broker["orders"].values():
        if order["status"] in ("FILLED", "REJECTED", "UNKNOWN"):
            continue
        last = broker["position_snapshot"]
        if (
            order["status"].startswith("CANCELED")
            and last is not None
            and (clock(last["first_known_at"]) > clock(order["last_known_at"]))
        ):
            # A later independently complete position snapshot resolves the
            # outstanding canceled balance, not a cancel receipt alone.
            continue
        inst = Instrument.parse(order["instrument"])
        qty = abs(number(order["quantity"])) - number(order["cumulative_filled"])
        if qty > ZERO:
            result[inst] = result.get(inst, ZERO) + qty
    return result


def ingest(account: Account, observation: dict, policy: dict, at: str) -> dict:
    if observation.get("schema") != BROKER_SCHEMA:
        raise ValueError("INVALID_BROKER_OBSERVATION_SCHEMA")
    oid = observation.get("evidence_id")
    kind = observation.get("kind")
    if not isinstance(oid, str) or not oid or kind not in ORDER_KINDS | SNAPSHOT_KINDS:
        raise ValueError("INVALID_BROKER_OBSERVATION")
    if not all(x in observation for x in ("event_at", "first_known_at")):
        raise ValueError("BROKER_CAUSAL_PROVENANCE_REQUIRED")
    if not (clock(observation["event_at"]) <= clock(observation["first_known_at"]) <= clock(at)):
        raise ValueError("BROKER_CAUSAL_CLOCK_VIOLATION")
    broker = account.pm04_state["broker"]
    frozen = digest(observation)
    if oid in broker["observations"]:
        if broker["observations"][oid] != frozen:
            raise ValueError("CONFLICTING_BROKER_OBSERVATION_REVISION")
        return {"status": "DUPLICATE", "evidence_id": oid}
    # Only append a receipt once validation has succeeded. Entire PM-03 event
    # applies to a staged account and is committed atomically by ShadowRun.
    if kind in ORDER_KINDS:
        order_id = observation.get("order_id")
        if not order_id or not isinstance(order_id, str):
            raise ValueError("MISSING_ORDER_ID")
        seq = observation.get("provider_sequence")
        if not isinstance(seq, int) or seq < 0:
            raise ValueError("INVALID_PROVIDER_SEQUENCE")
        order = broker["orders"].get(order_id)
        if kind == "ORDER_INTENT":
            if order is not None:
                raise ValueError("CONFLICTING_ORDER_INTENT")
            instrument = Instrument.parse(observation["instrument"])
            if instrument not in account.rulebook.permitted:
                raise ValueError("UNSUPPORTED_BROKER_INSTRUMENT")
            qty = number(observation["quantity"])
            if qty == ZERO:
                raise ValueError("ZERO_ORDER_INTENT")
            order = {
                "instrument": instrument.key,
                "quantity": str(qty),
                "cumulative_filled": "0",
                "status": "INTENT",
                "last_sequence": seq,
                "last_known_at": observation["first_known_at"],
            }
            broker["orders"][order_id] = order
        elif order is None:
            # Unknown external order is evidence of unsafe authority, not an
            # invitation to silently create an account position or order.
            broker["orders"][order_id] = {
                "instrument": observation.get("instrument", ""),
                "quantity": "0",
                "cumulative_filled": "0",
                "status": "UNKNOWN",
                "last_sequence": seq,
                "last_known_at": observation["first_known_at"],
            }
        else:
            previous = number(order["cumulative_filled"])
            if kind in ("FILL", "PARTIAL_FILL"):
                cumulative = number(observation["cumulative_filled"])
                if cumulative < ZERO or cumulative > abs(number(order["quantity"])):
                    raise ValueError("BROKER_FILL_EXCEEDS_ORDER")
                if cumulative > previous:
                    order["cumulative_filled"] = str(cumulative)
                    order["status"] = (
                        "FILLED"
                        if cumulative == abs(number(order["quantity"]))
                        else "CANCELED_PARTIAL"
                        if order["status"].startswith("CANCELED")
                        else "PARTIAL"
                    )
            elif seq > order["last_sequence"]:
                if kind == "ACK" and order["status"] == "INTENT":
                    order["status"] = "ACK"
                elif kind == "CANCEL" and order["status"] != "FILLED":
                    order["status"] = "CANCELED"
                elif kind == "REJECT" and not previous:
                    order["status"] = "REJECTED"
            order["last_sequence"] = max(order["last_sequence"], seq)
            if clock(observation["first_known_at"]) > clock(order["last_known_at"]):
                order["last_known_at"] = observation["first_known_at"]
    elif kind == "POSITION_SNAPSHOT":
        if observation.get("complete") is not True:
            raise ValueError("INCOMPLETE_BROKER_POSITION_SNAPSHOT")
        positions = observation.get("positions")
        if not isinstance(positions, dict):
            raise ValueError("INVALID_BROKER_POSITIONS")
        parsed = {Instrument.parse(k).key: str(number(v)) for k, v in positions.items()}
        previous = broker["position_snapshot"]
        if previous is None or clock(observation["event_at"]) > clock(previous["event_at"]):
            broker["position_snapshot"] = {
                "positions": parsed,
                "event_at": observation["event_at"],
                "first_known_at": observation["first_known_at"],
            }
        elif (
            clock(observation["event_at"]) == clock(previous["event_at"])
            and parsed != previous["positions"]
        ):
            raise ValueError("CONFLICTING_SAME_TIME_BROKER_SNAPSHOT")
    elif kind == "BALANCE_SNAPSHOT":
        snap = {
            "balance": str(number(observation["balance"])),
            "equity": str(number(observation["equity"])),
            "event_at": observation["event_at"],
            "first_known_at": observation["first_known_at"],
        }
        previous = broker["balance_snapshot"]
        if previous is None or clock(snap["event_at"]) > clock(previous["event_at"]):
            broker["balance_snapshot"] = snap
        elif clock(snap["event_at"]) == clock(previous["event_at"]) and (
            snap["balance"] != previous["balance"] or snap["equity"] != previous["equity"]
        ):
            raise ValueError("CONFLICTING_SAME_TIME_BROKER_SNAPSHOT")
    elif kind == "FEES_FUNDING":
        snap = {
            "fee_total": str(number(observation["fee_total"])),
            "funding_total": str(number(observation["funding_total"])),
            "event_at": observation["event_at"],
            "first_known_at": observation["first_known_at"],
        }
        previous = broker["fee_snapshot"]
        if previous is None or clock(snap["event_at"]) > clock(previous["event_at"]):
            broker["fee_snapshot"] = snap
        elif clock(snap["event_at"]) == clock(previous["event_at"]) and (
            snap["fee_total"] != previous["fee_total"]
            or snap["funding_total"] != previous["funding_total"]
        ):
            raise ValueError("CONFLICTING_SAME_TIME_BROKER_SNAPSHOT")
    elif kind == "RECONNECT":
        broker["reconnect_at"] = observation["first_known_at"]
    broker["observations"][oid] = frozen
    discrepancies = _snapshot(account, broker, policy, at)
    return {
        "status": "OBSERVED",
        "kind": kind,
        "evidence_id": oid,
        "discrepancies": discrepancies,
        "ready": broker["ready"],
        "no_order_submission": True,
    }
