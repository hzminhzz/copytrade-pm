"""FP-05 pure, causal, five-minute source-equity proportional target planner.

This is a non-executing seam. PM-04 remains the target-batching and risk
authority; no fixed-k scaling, broker interface or implied live admission.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta
from decimal import Decimal

from .pm03_account import Instrument, clock, number
from .pm_forward_admission import Admission


@dataclass
class ForwardBatch:
    follower_allocated_equity: Decimal
    opened_at: str | None = None
    due_at: str | None = None
    latest: Admission | None = None
    latest_first_known_at: str | None = None
    dispatched: bool = False
    events_seen: int = 0
    blocked_reasons: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        self.follower_allocated_equity = number(self.follower_allocated_equity)
        if self.follower_allocated_equity <= 0:
            raise ValueError("INVALID_FOLLOWER_ALLOCATION")

    def ingest(self, admission: Admission, *, first_known_at: str) -> dict:
        clock(first_known_at)
        if self.dispatched:
            raise ValueError("ALREADY_DISPATCHED")
        if not admission.admitted or admission.source_equity is None:
            self.blocked_reasons = admission.reason_codes or ("SOURCE_NOT_ADMITTED",)
            return {"status": "BLOCKED", "reasons": list(self.blocked_reasons)}
        if self.latest_first_known_at and clock(first_known_at) < clock(self.latest_first_known_at):
            raise ValueError("BACKDATED_SOURCE_RECEIPT")
        if self.opened_at is None:
            self.opened_at = first_known_at
            self.due_at = (clock(first_known_at) + timedelta(seconds=300)).isoformat()
        self.latest_first_known_at = first_known_at
        self.latest = admission
        self.events_seen += 1
        return {"status": "QUEUED", "due_at": self.due_at, "events_seen": self.events_seen}

    def preview_due(self, *, decision_at: str) -> dict:
        if not self.due_at or not self.latest:
            return {"status": "BLOCKED", "reasons": ["NO_ADMITTED_SOURCE"]}
        if self.dispatched:
            return {"status": "BLOCKED", "reasons": ["ALREADY_DISPATCHED"]}
        if clock(decision_at) < clock(self.due_at):
            return {"status": "WAIT", "due_at": self.due_at}
        if self.latest_first_known_at and clock(decision_at) < clock(self.latest_first_known_at):
            raise ValueError("FUTURE_SOURCE_AT_DUE")
        if self.latest.source_equity is None or self.latest.source_equity <= 0:
            return {"status": "BLOCKED", "reasons": ["SOURCE_EQUITY_UNKNOWN"]}
        ratio = self.follower_allocated_equity / self.latest.source_equity
        targets: dict[Instrument, Decimal] = {
            instrument: quantity * ratio for instrument, quantity in self.latest.positions.items()
        }
        return {
            "status": "DUE",
            "target_quantities": {key.key: str(value) for key, value in sorted(targets.items())},
            "source_sha": self.latest.snapshot_sha,
            "source_equity": str(self.latest.source_equity),
            "follower_allocated_equity": str(self.follower_allocated_equity),
            "due_at": self.due_at,
            "decision_at": decision_at,
            "unexecuted_notional": "UNKNOWN_UNTIL_PRICED",
        }
