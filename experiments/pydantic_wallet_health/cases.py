"""Predeclared synthetic accounting oracles, independent of task responses.

These are transparent engineering labels, not independent human/provider labels.
Wallet/date holdouts share scenario templates and cannot establish field accuracy.
No real wallet, transaction, financial journal or API is read.
"""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from hashlib import sha256

from contracts import ABSTAIN, Diagnosis, Evidence, TaskInput, canonical

KINDS = ("DEPOSIT", "WITHDRAWAL", "REALIZED_PNL", "UNREALIZED_DELTA", "FEES", "FUNDING")
ZERO = ("0",) * 6
MISSING = (None,) * 6


@dataclass(frozen=True)
class Profile:
    name: str
    after: str
    parts: tuple[str | None, ...]
    label: str
    activity: int | None = 3
    complete: bool = True
    stale: bool = False
    liquidation: bool = False
    delayed: str | None = None
    later_correction: bool = False


# The reference labels come from declared cash-flow facts, not an LLM judge.
PROFILES = (
    Profile("withdrawal_not_loss", "800", ("0", "-200", "0", "0", "0", "0"), "WITHDRAWAL"),
    Profile(
        "realized_loss_not_transfer", "800", ("0", "0", "-200", "0", "0", "0"), "REALIZED_LOSS"
    ),
    Profile("top_up_not_profit", "1200", ("200", "0", "0", "0", "0", "0"), "TOP_UP"),
    Profile(
        "explicit_liquidation",
        "0",
        ("0", "0", "-1000", "0", "0", "0"),
        "LIQUIDATION",
        liquidation=True,
    ),
    Profile("zero_equity_unknown_cause", "0", MISSING, "INSUFFICIENT_EVIDENCE", complete=False),
    Profile("inactive_solvent", "1000", ZERO, "INACTIVE_SOLVENT", activity=0),
    Profile("stale_equity", "800", ("0", "0", "-200", "0", "0", "0"), "STALE_EVIDENCE", stale=True),
    Profile("ambiguous_equity_decline", "800", MISSING, "INSUFFICIENT_EVIDENCE", complete=False),
    Profile("deposit_and_loss", "800", ("300", "0", "-500", "0", "0", "0"), "MIXED_FLOWS"),
    Profile(
        "withdrawal_known_only_later",
        "800",
        ("0", "-200", "0", "0", "0", "0"),
        "INSUFFICIENT_EVIDENCE",
        delayed="WITHDRAWAL",
    ),
    Profile(
        "later_mark_correction",
        "800",
        ("0", "0", "-200", "0", "0", "0"),
        "REALIZED_LOSS",
        later_correction=True,
    ),
    Profile("fees_and_funding", "993", ("0", "0", "0", "0", "-5", "-2"), "COST_DRAG"),
    Profile(
        "unrealized_loss_not_liquidation",
        "800",
        ("0", "0", "0", "-200", "0", "0"),
        "UNREALIZED_LOSS",
    ),
    Profile(
        "offsetting_transfers",
        "1000",
        ("400", "-400", "0", "0", "0", "0"),
        "MIXED_FLOWS",
        activity=0,
    ),
    Profile("missing_activity_coverage", "1000", ZERO, "INSUFFICIENT_EVIDENCE", activity=None),
    Profile("realized_gain_not_top_up", "1200", ("0", "0", "200", "0", "0", "0"), "EQUITY_GAIN"),
)


@dataclass(frozen=True)
class LabeledCase:
    inputs: TaskInput
    expected: Diagnosis
    split: str
    scenario: str


def evidence(
    receipt_id,
    kind,
    observed_at,
    known_at,
    *,
    value=None,
    count=None,
    complete=False,
    window_start=None,
):
    raw = canonical(
        {
            "kind": kind,
            "observed_at": observed_at.isoformat(),
            "known_at": known_at.isoformat(),
            "value": value,
            "count": count,
            "complete": complete,
            "window_start": window_start.isoformat() if window_start is not None else None,
        }
    ).decode()
    return Evidence(receipt_id=receipt_id, raw=raw, raw_sha=sha256(raw.encode()).hexdigest())


def build_cases() -> tuple[LabeledCase, ...]:
    result = []
    for split_index, split in enumerate(("development", "holdout")):
        as_of = datetime(2026, 10 + split_index, 1, 12, tzinfo=UTC)
        scale = Decimal(1 if split == "development" else 7)
        for index, profile in enumerate(PROFILES):
            number = split_index * 100 + index + 1
            end = as_of - timedelta(days=2) if profile.stale else as_of - timedelta(minutes=1)
            start = end - timedelta(days=14)
            receipts = [
                evidence("e00", "EQUITY_BEFORE", start, start, value=str(1000 * scale)),
                evidence(
                    "e01", "EQUITY_AFTER", end, end, value=str(Decimal(profile.after) * scale)
                ),
            ]
            for n, (kind, value) in enumerate(zip(KINDS, profile.parts), 2):
                if value is not None:
                    known = as_of + timedelta(hours=1) if profile.delayed == kind else end
                    receipts.append(
                        evidence(
                            f"e{n:02}",
                            kind,
                            end,
                            known,
                            value=str(Decimal(value) * scale),
                            window_start=start,
                        )
                    )
            if profile.activity is not None:
                receipts.append(
                    evidence(
                        "e08",
                        "ACTIVITY",
                        end,
                        end,
                        count=profile.activity,
                        complete=profile.complete,
                        window_start=start,
                    )
                )
            receipts.append(
                evidence("e09", "COVERAGE", end, end, complete=profile.complete, window_start=start)
            )
            if profile.liquidation:
                receipts.append(evidence("e10", "LIQUIDATION", end, end, complete=True))
            if profile.later_correction:
                receipts.append(
                    evidence(
                        "e11",
                        "EQUITY_AFTER",
                        end,
                        as_of + timedelta(hours=1),
                        value=str(1000 * scale),
                    )
                )
            inputs = TaskInput(
                case_id=f"c{number:03}",
                wallet_alias=f"FAKE{number:03}",
                as_of=as_of,
                receipts=tuple(receipts),
            )
            visible = inputs.pit_view().receipts
            if profile.label == "LIQUIDATION":
                required = ("e01", "e10")
            elif profile.label == "STALE_EVIDENCE":
                required = ("e01",)
            elif profile.label in ABSTAIN:
                required = ("e00", "e01")
            else:
                required = tuple(r.receipt_id for r in visible)
            expected = Diagnosis(
                label=profile.label,
                confidence=0.0 if profile.label in ABSTAIN else 1.0,
                evidence_ids=required,
            )
            result.append(LabeledCase(inputs, expected, split, profile.name))
    return tuple(result)


def corpus_sha(cases: tuple[LabeledCase, ...]) -> str:
    return sha256(
        canonical(
            [
                {
                    "input": c.inputs.model_dump(mode="json"),
                    "expected": c.expected.model_dump(mode="json"),
                    "split": c.split,
                    "scenario": c.scenario,
                }
                for c in cases
            ]
        )
    ).hexdigest()
