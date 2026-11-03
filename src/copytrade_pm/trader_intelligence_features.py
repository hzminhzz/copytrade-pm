"""Conservative as-of wallet specialization and exposure features.

Features are descriptive evidence, not a calibrated skill score or an order.
Unknown book scope, marks and opening history remain explicit NULL values.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from decimal import Decimal

from .trader_intelligence import ObservationSnapshot, WalletEvent, decimal, digest, norm_clock, utc


@dataclass(frozen=True)
class TraderFeature:
    wallet: str
    instrument: str
    direction: str | None
    strategy_style: str
    latest_transition: str
    independent_group: str | None
    holding_minutes_lower_bound: int | None
    exposure_fraction_of_equity: str | None
    first_known_at: str | None
    evidence_status: str
    source_event_ids: tuple[str, ...]

    def as_wire(self) -> dict:
        return asdict(self)


def extract_asof_features(
    snapshot: ObservationSnapshot, *, decision_at: str
) -> tuple[TraderFeature, ...]:
    """Compute per-wallet/instrument features strictly from knowable transitions.

    A holding age is emitted only when this observed continuous chain includes
    a genuine zero-to-position OPEN or a REVERSE. It is not lifetime tenure.
    """
    cut = utc(decision_at)
    if utc(snapshot.roster_known_at) > cut:
        raise ValueError("FUTURE_ROSTER")
    roster = {w.alias: w for w in snapshot.wallets}
    scope: dict[tuple[str, str], list[WalletEvent]] = {}
    unique: dict[str, WalletEvent] = {e.event_id: e for e in snapshot.events}
    for e in unique.values():
        if e.known_at <= cut and utc(e.event_at) <= cut:
            scope.setdefault((e.wallet, e.instrument), []).append(e)
    features: list[TraderFeature] = []
    for (wallet, instrument), events in sorted(scope.items()):
        events.sort(key=lambda e: (e.known_at, utc(e.event_at), e.event_id))
        latest = events[-1]
        reason = "OBSERVED"
        open_clock: datetime | None = None
        old_after: Decimal | None = None
        witnessed: list[str] = []
        for e in events:
            witnessed.append(e.event_id)
            if (
                e.transition == "UNKNOWN"
                or e.position_before is None
                or e.position_after is None
                or (old_after is not None and decimal(e.position_before) != old_after)
            ):
                reason = "UNKNOWN_OR_DISCONTINUOUS_POSITION_CHAIN"
                open_clock = None
            elif reason != "UNKNOWN_OR_DISCONTINUOUS_POSITION_CHAIN":
                if e.transition in ("OPEN", "REVERSE"):
                    open_clock = e.known_at
                elif e.transition == "EXIT":
                    open_clock = None
            # A later verified flat-to-open transition establishes a *new*
            # observable tenure even if an earlier segment was incomplete.
            if e.transition in ("OPEN", "REVERSE") and decimal(e.position_before or "0") == 0:
                open_clock = e.known_at
                reason = "OBSERVED"
            old_after = decimal(e.position_after) if e.position_after is not None else None
        if latest.origin == "HISTORICAL_PROXY":
            reason = "RETROSPECTIVE_VENDOR_CLOCK_ONLY"
            open_clock = None
        if latest.position_after is None or decimal(latest.position_after) == 0:
            direction = None
            tenure = None
        else:
            direction = "LONG" if decimal(latest.position_after) > 0 else "SHORT"
            tenure = (
                int((cut - open_clock).total_seconds() // 60)
                if open_clock is not None and reason == "OBSERVED"
                else None
            )
        exposure = None
        if (
            latest.book_complete is True
            and latest.source_equity_usd is not None
            and latest.observed_price is not None
            and latest.position_after is not None
            and reason == "OBSERVED"
        ):
            exposure = str(
                abs(decimal(latest.position_after))
                * decimal(latest.observed_price)
                / decimal(latest.source_equity_usd)
            )
        if latest.origin == "HISTORICAL_PROXY":
            reason = "RETROSPECTIVE_VENDOR_CLOCK_ONLY"
        elif latest.book_complete is not True:
            reason = "INCOMPLETE_OR_UNKNOWN_BOOK"
        elif latest.strategy_style != "DIRECTIONAL":
            reason = "NON_DIRECTIONAL_OR_UNKNOWN_STYLE"
        identity = roster[wallet]
        group = f"parent:{identity.parent}" if identity.parent else identity.cluster
        features.append(
            TraderFeature(
                wallet=wallet,
                instrument=instrument,
                direction=direction,
                strategy_style=latest.strategy_style,
                latest_transition=latest.transition,
                independent_group=group,
                holding_minutes_lower_bound=tenure,
                exposure_fraction_of_equity=exposure,
                first_known_at=norm_clock(latest.known_at)
                if latest.origin != "HISTORICAL_PROXY"
                else None,
                evidence_status=reason,
                source_event_ids=tuple(witnessed),
            )
        )
    return tuple(features)


def feature_report(snapshot: ObservationSnapshot, *, decision_at: str) -> dict:
    features = extract_asof_features(snapshot, decision_at=decision_at)
    payload = {
        "schema": "ti_asof_features_v1",
        "decision_at": norm_clock(decision_at),
        "snapshot_sha256": ObservationSnapshot(
            roster_id=snapshot.roster_id,
            roster_known_at=snapshot.roster_known_at,
            wallets=snapshot.wallets,
            events=tuple(
                e
                for e in snapshot.events
                if e.known_at <= utc(decision_at) and utc(e.event_at) <= utc(decision_at)
            ),
            roster_origin=snapshot.roster_origin,
        ).sha256,
        "features": [f.as_wire() for f in features],
        "scientific_qualification": "NOT_QUALIFIED",
    }
    return {**payload, "sha256": digest(payload)}
