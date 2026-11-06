"""Fixture-only PM-04 bridge for the forward-paper journal.

This adapter retains PM-03/PM-04 as the single accounting and batching
authority. An independently authenticated live source is NOT admitted here;
it only accepts explicitly synthetic whole-book fixtures, cost and quote
contracts, and their SHA-bound already-journaled first-known receipts.
"""

from __future__ import annotations

from decimal import Decimal

from .pm03_account import Account, Instrument, RiskState, clock, digest, number
from .pm03_memory import Event
from .pm03_risk import RiskPolicy
from .pm04_shadow import apply_pm04
from .pm_forward_admission import admit_source_book
from .pm_forward_market import market_contract_reasons

_PAPER_CLASS = "FORWARD_PAPER_SIMULATED_v1"
_ALLOWED = frozenset({"PM04_CONFIG", "PM04_SIGNAL", "PM04_TICK"})


def _check_source_target(account: Account, event: dict) -> dict | None:
    book = event.get("source_book")
    admission = admit_source_book(
        book,
        decision_at=event["event_at"],
        fill_at=event["hypothetical_fill_at"],
        allow_synthetic_fixture=event.get("fixture_attested") is True,
    )
    if not admission.admitted:
        account.risk = RiskState.RED
        account.risk_reasons = admission.reason_codes
        return {"status": "BLOCKED_SOURCE", "reason_codes": list(admission.reason_codes)}
    if not isinstance(book, dict) or "source_ref" not in event:
        raise ValueError("SOURCE_RECEIPT_ATOMIC_BINDING_REQUIRED")
    source_id = book["wallet_id"]
    if event["source_ref"].get("source_id") != source_id:
        raise ValueError("PM04_SOURCE_WALLET_MISMATCH")
    policy = account.pm04_state.get("policy", {})
    allocations = policy.get("follower_allocations")
    if not isinstance(allocations, dict) or source_id not in allocations:
        raise ValueError("PM04_FROZEN_FOLLOWER_ALLOCATION_REQUIRED")
    allocation = number(allocations[source_id])
    if allocation <= 0 or allocation > account.rulebook.initial_balance:
        raise ValueError("PM04_INVALID_FOLLOWER_ALLOCATION")
    current = account.pm04_state["pod_targets"].get(source_id)
    if current is None:
        raise ValueError("PM04_SOURCE_NOT_IN_FROZEN_PODS")
    # The native exposure contract uses source signed NOTIONAL / source
    # equity and converts it at a causally known FOLLOWER quote. Quantity
    # ratios alone are only valid when both market marks happen to match.
    from .pm_exposure_sizing import calculate_weights, target_from_weights

    quotes = {}
    for observation in event["input"]["observations"]:
        instrument = Instrument.parse(observation["instrument"])
        if instrument.key in quotes:
            raise ValueError("PM04_DUPLICATE_FOLLOWER_MARK")
        if clock(observation["first_known_at"]) > clock(event["event_at"]):
            raise ValueError("PM04_FUTURE_FOLLOWER_MARK")
        quotes[instrument.key] = number(observation["mark"])
    weights = calculate_weights(
        source_quantities={key.key: qty for key, qty in admission.positions.items()},
        source_equity_usd=admission.source_equity,
        source_marks={key.key: mark for key, mark in admission.source_marks.items()},
    )
    _, target_quantities = target_from_weights(
        weights=weights, pod_capital_usd=allocation, follower_marks=quotes
    )
    expected = {Instrument.parse(key): qty for key, qty in target_quantities.items()}
    # A verified complete book permits zero targets for a leg the source exited.
    for key in current:
        expected.setdefault(Instrument.parse(key), Decimal("0"))
    received: set[Instrument] = set()
    for row in event["input"]["targets"]:
        if row["pod"] != source_id:
            raise ValueError("PM04_CROSS_WALLET_TARGET")
        instrument = Instrument.parse(row["instrument"])
        if instrument in received:
            raise ValueError("PM04_DUPLICATE_TARGET")
        received.add(instrument)
        if instrument not in expected:
            raise ValueError("PM04_TARGET_NOT_IN_WHOLE_SOURCE_BOOK")
        if number(row["quantity"]) != expected[instrument]:
            raise ValueError("PM04_SOURCE_EQUITY_SIZING_MISMATCH")
        if (
            row.get("source_sha") != admission.snapshot_sha
            or row.get("source_event_at") != book["source_event_at"]
            or row.get("first_known_at") != book["first_known_at"]
        ):
            raise ValueError("PM04_SOURCE_TARGET_PROVENANCE_MISMATCH")
    if received != set(expected):
        raise ValueError("PM04_WHOLE_BOOK_TARGET_OMISSION")
    return None


def apply_forward_pm04(account: Account, event: dict) -> dict:
    """Invoke the native PM-04 coordinator with a strictly fixture-only seal."""
    kind = event.get("kind")
    if kind not in _ALLOWED:
        raise ValueError("UNSUPPORTED_FORWARD_PM04_EVENT")
    if (
        event.get("order_route") != "NONE"
        or event.get("evidence_class") != _PAPER_CLASS
        or event.get("fixture_attested") is not True
    ):
        raise ValueError("PM04_PAPER_ONLY_CONTRACT_REQUIRED")
    if not account.rulebook.confirmed:
        raise ValueError("PM04_UNCONFIRMED_PAPER_RULEBOOK")
    inputs = event.get("input")
    if not isinstance(inputs, dict):
        raise ValueError("PM04_INPUT_REQUIRED")
    policy_sha = event.get("sealed_policy_sha")
    if kind == "PM04_CONFIG":
        policy = inputs.get("policy")
        if not isinstance(policy, dict) or digest(policy) != policy_sha:
            raise ValueError("PM04_CONFIG_POLICY_SHA_MISMATCH")
        allocations = policy.get("follower_allocations")
        if not isinstance(allocations, dict) or set(allocations) != set(policy.get("pods", {})):
            raise ValueError("PM04_ALLOCATION_CENSUS_MISMATCH")
        total = sum((number(v) for v in allocations.values()), Decimal("0"))
        if number(policy.get("nominal_portfolio_risk", "0")) != Decimal("600"):
            raise ValueError("PM04_UNAPPROVED_NOMINAL_PORTFOLIO_RISK")
        if (
            any(number(v) <= 0 for v in allocations.values())
            or total > account.rulebook.initial_balance
        ):
            raise ValueError("PM04_UNFUNDED_FOLLOWER_ALLOCATION")
    elif not account.pm04_state or policy_sha != account.pm04_state["policy_sha"]:
        raise ValueError("PM04_ACTIVE_POLICY_SHA_MISMATCH")

    if kind == "PM04_SIGNAL":
        blocked = _check_source_target(account, event)
        if blocked is not None:
            return blocked

    if kind != "PM04_CONFIG":
        observations = inputs.get("observations")
        if not isinstance(observations, list):
            raise ValueError("PM04_MARKET_OBSERVATIONS_REQUIRED")
        contracts = event.get("market_contracts")
        if not isinstance(contracts, dict):
            contracts = {}
        reasons: list[str] = []
        frozen_targets = account.pm04_state["pod_targets"]
        proposed_targets = {
            pod: {key: number(q) for key, q in book.items()} for pod, book in frozen_targets.items()
        }
        if kind == "PM04_SIGNAL":
            for target in inputs["targets"]:
                proposed_targets[target["pod"]][target["instrument"]] = number(target["quantity"])
        for row in observations:
            instrument = Instrument.parse(row["instrument"])
            contract = contracts.get(instrument.key)
            target_qty = sum(
                (book.get(instrument.key, Decimal("0")) for book in proposed_targets.values()),
                Decimal("0"),
            )
            delta = target_qty - account.quantities.get(instrument, Decimal("0"))
            reasons.extend(
                market_contract_reasons(
                    contract,
                    instrument=instrument,
                    observed_quality=row.get("quality", "SYNTHETIC"),
                    decision_at=event["event_at"],
                    target_quantity=delta,
                    costs_sha=digest(inputs["costs"]),
                    observation=row,
                    quote_evidence=event.get("market_evidence", {}).get(instrument.key),
                    costs=inputs["costs"],
                )
            )
        if reasons:
            account.risk = RiskState.RED
            account.risk_reasons = tuple(sorted(set(reasons)))
            return {"status": "BLOCKED_MARKET", "reason_codes": list(account.risk_reasons)}

    source_at = event.get("source_event_at")
    first_known = event.get("first_known_at")
    at = event["event_at"]
    fill_at = event.get("hypothetical_fill_at")
    if not all(isinstance(value, str) for value in (source_at, first_known, fill_at)):
        raise ValueError("PM04_MISSING_CAUSAL_CLOCKS")
    if not clock(source_at) <= clock(first_known) <= clock(at) <= clock(fill_at):
        raise ValueError("PM04_CAUSAL_CLOCK_ORDER_INVALID")
    if kind == "PM04_SIGNAL":
        book = event["source_book"]
        if book["source_event_at"] != source_at or book["first_known_at"] != first_known:
            raise ValueError("PM04_CLOCK_SOURCE_BOOK_MISMATCH")

    pm_event = Event(
        event_id=digest(event),
        source_event_at=source_at,
        first_known_at=first_known,
        decision_at=at,
        hypothetical_fill_at=fill_at,
        kind=kind,
        payload={
            "run_id": event.get("run_id"),
            "rulebook_sha": account.rulebook.sha,
            "input": inputs,
        },
        source_sha=event.get("source_book", {}).get("snapshot_sha")
        or event.get("source_sha")
        or digest(inputs),
    )
    pm_event.validate()
    return apply_pm04(account, pm_event, RiskPolicy(), "RESEARCH_SYNTHETIC")
