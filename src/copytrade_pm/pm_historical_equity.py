"""Private historical source-equity observations for equity-normalized oracle replay.

No later-retrieved snapshot becomes an earlier first-known signal. This is only
a typed, strictly as-of historical *source* denominator. It cannot independently
certify the honesty of the upstream provider's reconciliation claim.
"""

from __future__ import annotations

from bisect import bisect_right
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal as D
from hashlib import sha256
import json
from pathlib import Path
from typing import Mapping

from .pm_wallet_replica import _decimal, _time

SCHEMA = "pm_q3_historical_source_equity_v1"
MAX_EQUITY_AGE_SECONDS = 3600
DEFINITION = "ACCOUNT_EQUITY_USDC_INCLUDES_UNREALIZED"


@dataclass(frozen=True)
class EquityPoint:
    at: datetime
    equity_usd: D
    source_sha256: str


@dataclass(frozen=True)
class HistoricalEquity:
    ledger_sha256: str
    scope: dict[str, str]
    points: dict[str, tuple[EquityPoint, ...]]

    def asof(self, wallet: str, decision_at: datetime) -> D:
        if decision_at.tzinfo is None or decision_at.utcoffset() is None:
            raise ValueError("EQUITY_NAIVE_ASOF")
        times = self.points.get(wallet)
        if not times:
            raise ValueError("EQUITY_WALLET_HISTORY_MISSING")
        when = decision_at.astimezone(UTC)
        index = bisect_right([p.at for p in times], when) - 1
        if index < 0:
            raise ValueError("EQUITY_PRIOR_SNAPSHOT_MISSING")
        point = times[index]
        if (when - point.at).total_seconds() > MAX_EQUITY_AGE_SECONDS:
            raise ValueError("EQUITY_SNAPSHOT_STALE_OR_GAP")
        return point.equity_usd


def load_equity(path: Path, *, identities: Mapping[str, str]) -> HistoricalEquity:
    """Load and validate a separate immutable equity ledger and alias binding.

    Source identities must come from the frozen cohort, never the ledger alone.
    Retrospective observations remain an oracle even with matching SHA fields.
    """
    blob = Path(path).read_bytes()
    obj = json.loads(blob)
    if obj.get("schema") != SCHEMA or not isinstance(obj.get("wallets"), list):
        raise ValueError("EQUITY_LEDGER_SCHEMA_INVALID")
    rows = obj["wallets"]
    if len(rows) != len(identities):
        raise ValueError("EQUITY_LEDGER_COHORT_MISMATCH")
    scope = {}
    points = {}
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("EQUITY_LEDGER_ROW_INVALID")
        wallet = row.get("wallet")
        if wallet not in identities or wallet in scope:
            raise ValueError("EQUITY_LEDGER_ALIAS_MISMATCH")
        if row.get("wallet_identity_sha256") != identities[wallet]:
            raise ValueError("EQUITY_LEDGER_SOURCE_IDENTITY_MISMATCH")
        account_scope = row.get("account_scope")
        if not isinstance(account_scope, str) or not account_scope.strip():
            raise ValueError("EQUITY_ACCOUNT_SCOPE_UNRESOLVED")
        values = row.get("points")
        if not isinstance(values, list):
            raise ValueError("EQUITY_SNAPSHOTS_MISSING")
        history = []
        previous = None
        for value in values:
            if not isinstance(value, dict) or value.get("equity_definition") != DEFINITION:
                raise ValueError("EQUITY_DEFINITION_NOT_RECONCILED")
            raw_sha = value.get("source_sha256")
            if (
                not isinstance(raw_sha, str)
                or len(raw_sha) != 64
                or any(ch not in "0123456789abcdef" for ch in raw_sha)
            ):
                raise ValueError("EQUITY_SOURCE_SHA_MISSING")
            if value.get("reconciled_funding_transfers") is not True:
                raise ValueError("EQUITY_FUNDING_TRANSFERS_UNVERIFIED")
            at = _time(value["source_event_at"])
            if previous is not None and at <= previous:
                raise ValueError("EQUITY_HISTORY_OUT_OF_ORDER")
            previous = at
            history.append(EquityPoint(at, _decimal(value["equity_usd"], positive=True), raw_sha))
        scope[wallet] = account_scope
        points[wallet] = tuple(history)
    return HistoricalEquity(
        ledger_sha256=sha256(blob).hexdigest(),
        scope=dict(sorted(scope.items())),
        points=dict(sorted(points.items())),
    )
