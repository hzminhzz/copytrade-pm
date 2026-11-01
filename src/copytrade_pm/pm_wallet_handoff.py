"""Persist E0 whole-wallet intent through the existing PM03/PM04 authority.

This seam never creates a second account, sizes independent legs, filters an
unsupported hedge, authorizes a broker, or promotes source intent into profit.
"""

from __future__ import annotations

from dataclasses import replace
from decimal import Decimal as D

from .pm03_memory import Event, clock
from .pm03_run import ShadowRun
from .pm_portfolio_e0 import PORTFOLIOS, PortfolioE0
from .pm_wallet_replica import MAX_SOURCE_AGE_SECONDS


def _lineage(prepared: PortfolioE0, decision_at: str) -> dict:
    if (
        prepared.name not in PORTFOLIOS
        or prepared.status != "SOURCE_INTENT_READY_NOT_AUTHORIZED"
        or prepared.blocked
        or set(prepared.books) != set(PORTFOLIOS[prepared.name])
    ):
        raise ValueError("E0_BLOCKED_OR_INCOMPLETE_PORTFOLIO")
    books = {}
    for pod, replica in sorted(prepared.books.items()):
        if replica.wallet != pod or clock(replica.decision_at) != clock(decision_at):
            raise ValueError("E0_DECISION_OR_WALLET_MISMATCH")
        if (
            not clock(replica.source_event_at)
            <= clock(replica.first_known_at)
            <= clock(decision_at)
        ):
            raise ValueError("E0_NONCAUSAL_SOURCE_CLOCK")
        if (
            clock(decision_at) - clock(replica.source_event_at)
        ).total_seconds() > MAX_SOURCE_AGE_SECONDS:
            raise ValueError("E0_STALE_SOURCE_STATE")
        if (
            not replica.scale.is_finite()
            or replica.scale <= 0
            or set(replica.source) != set(replica.intended)
        ):
            raise ValueError("E0_INVALID_REPLICA")
        if any(
            not q.is_finite() or replica.intended[k] != q * replica.scale
            for k, q in replica.source.items()
        ):
            raise ValueError("E0_NONPROPORTIONAL_REPLICA")
        books[pod] = {
            "account_scope": replica.account_scope,
            "source_sha256": replica.source_sha256,
            "source_event_at": replica.source_event_at,
            "first_known_at": replica.first_known_at,
            "equity_usd": str(replica.equity_usd),
            "scale": str(replica.scale),
            "source_positions": {k: str(v) for k, v in sorted(replica.source.items())},
            "intended_positions": {k: str(v) for k, v in sorted(replica.intended.items())},
            "source_leverage": (
                {k: str(v) for k, v in replica.source_leverage.items()}
                if replica.source_leverage is not None
                else None
            ),
            "source_margin_usd": (
                {k: str(v) for k, v in replica.source_margin_usd.items()}
                if replica.source_margin_usd is not None
                else None
            ),
        }
    return {
        "schema": "e0_pm04_wallet_intent_v1",
        "portfolio": prepared.name,
        "books": books,
        "financial_authority": "PM03_PM04",
        "economic_outcome_verified": False,
        "trading_authorized": False,
    }


def record_wallet_signal(shadow: ShadowRun, prepared: PortfolioE0, event: Event) -> dict:
    """Bind a full book to PM04, including explicit zeros for removed source legs.

    The caller supplies the existing shadow event and market/cost evidence.
    Revision numbers and budget references come from PM04's persisted state.
    PM04 retains all permission, risk, HALT, race and financial checks.
    """
    if event.kind != "PM04_SIGNAL":
        raise ValueError("E0_REQUIRES_PM04_SIGNAL")
    raw = dict(event.payload["input"])
    if "targets" in raw or "e0_intent" in raw:
        raise ValueError("E0_CALLER_CANNOT_OVERRIDE_WHOLE_BOOK")
    lineage = _lineage(prepared, event.decision_at)
    rows = shadow.ledger.read()
    old = next((r["event"] for r in rows if r["event"]["event_id"] == event.event_id), None)
    if old is not None:
        prior = old["payload"]["input"]
        if {k: v for k, v in prior.items() if k != "targets"} != {**raw, "e0_intent": lineage}:
            raise ValueError("CONFLICTING_E0_EVENT_REVISION")
        targets = prior["targets"]
    else:
        state = shadow.state()["account"].get("pm04")
        if not state or set(state["policy"]["pods"]) != set(prepared.books):
            raise ValueError("E0_PM04_POLICY_ROSTER_MISMATCH")
        targets = []
        for pod, replica in sorted(prepared.books.items()):
            keys = set(replica.intended) | set(state["pod_targets"][pod])
            for key in sorted(keys):
                targets.append(
                    {
                        "pod": pod,
                        "instrument": key,
                        "quantity": str(replica.intended.get(key, D("0"))),
                        "revision": state["versions"][pod].get(key, 0) + 1,
                        "source_event_at": replica.source_event_at,
                        "first_known_at": replica.first_known_at,
                        "source_sha": replica.source_sha256,
                        "budget_ref": state["policy"]["pods"][pod]["budget_ref"],
                    }
                )
    bound = replace(
        event,
        payload={
            **event.payload,
            "input": {**raw, "targets": targets, "e0_intent": lineage},
        },
    )
    return shadow.record(bound)
