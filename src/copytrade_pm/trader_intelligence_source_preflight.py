"""Privacy-safe live source-admission preflight; zero network or order mutations.

Reads the existing ensemble opportunity journal, original private alias locators,
and optionally the already SHA-verified native minute lake. It does not mint
first-known receipts, promote a dynamically inspected roster to independently
registered PIT, or infer coherent whole-account economics.
"""

from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from hashlib import sha256
import json
from pathlib import Path

from .pm_shadow import MarketDataBlocked, VerifiedHyperliquidMinuteSource
from .trader_intelligence import WalletIdentity, digest, norm_clock, utc
from .trader_intelligence_intake import from_opportunity_journal
from .trader_intelligence_native import lake_instrument
from .trader_intelligence_source_capture import _locate


@dataclass(frozen=True)
class SourcePreflight:
    schema: str
    status: str
    asof: str
    original_source: str
    roster_count: int
    roster_identity_sha256: str
    roster_registration: str
    matched_source_events: int
    potentially_directional_events: int
    observed_after_registration: int
    complete_source_book_events: int
    verifiable_equity_events: int
    market_attempts: int
    market_exact_mark_successes: int
    market_sample_is_complete: bool
    market_blockers: dict[str, int]
    reasons: tuple[str, ...]
    asof_snapshot_sha256: str
    input_sha256: str

    def as_wire(self) -> dict:
        return asdict(self)


def inspect_live_source(
    *,
    journal_db: Path,
    source_root: Path,
    aliases: tuple[str, ...],
    asof: str,
    registered_at: str | None = None,
    market_root: Path | None = None,
    market_limit: int = 25,
    lookback_hours: int = 24,
) -> SourcePreflight:
    """Observe existing records as of a real timestamp without writing data.

    A registered_at supplied by an operator is a descriptive assertion only;
    independent registration and economic truth are separate protected gates.
    """
    if not aliases or len(aliases) > 50 or len(set(aliases)) != len(aliases):
        raise ValueError("INVALID_SOURCE_PREFLIGHT_ROSTER")
    if not 1 <= market_limit <= 500 or not 1 <= lookback_hours <= 24:
        raise ValueError("INVALID_SOURCE_PREFLIGHT_BOUNDS")
    cut = utc(asof)
    known_at = utc(registered_at) if registered_at is not None else cut
    if known_at > cut:
        raise ValueError("FUTURE_ROSTER_REGISTRATION_NOT_ELIGIBLE")
    identities = tuple((alias, *_locate(source_root, alias)) for alias in aliases)
    if len({address for _, address, _ in identities}) != len(identities):
        raise ValueError("CONFLICTING_PRIVATE_ROSTER_IDENTITIES")
    wallets = tuple(
        WalletIdentity(alias=address, identity_sha256=sha256(address.encode()).hexdigest())
        for _, address, _ in identities
    )
    roster_sha = digest(
        [
            (alias, wallet.identity_sha256, locator_hash)
            for (alias, _, locator_hash), wallet in zip(identities, wallets)
        ]
    )
    snapshot = from_opportunity_journal(
        journal_db=journal_db,
        decision_at=cut.isoformat(),
        roster_id=f"ti-preflight-{roster_sha}",
        roster_known_at=known_at.isoformat(),
        wallets=wallets,
        maximum_source_rows=50_000,
        lookback_hours=lookback_hours,
    )
    directional = [event for event in snapshot.events if event.direction is not None]
    admitted = [
        event for event in directional if registered_at is not None and event.known_at >= known_at
    ]
    market = VerifiedHyperliquidMinuteSource(market_root) if market_root else None
    # Market-day provenance can be diagnosed independently even when source
    # continuity prevents a directional, economically eligible decision.
    # Do not mistake these diagnostic observations for admitted trades.
    sample = snapshot.events[:market_limit]
    counts: Counter[str] = Counter()
    success = 0
    for event in sample:
        if market is None:
            counts["NATIVE_MINUTE_SOURCE_NOT_CONFIGURED"] += 1
            continue
        try:
            native = lake_instrument(event.instrument)
            entry_time = event.known_at + timedelta(seconds=300)
            if entry_time + timedelta(minutes=60) > cut:
                counts["FOLLOWER_HORIZON_NOT_YET_MATURE"] += 1
                continue
            # This validates SHA-backed native minutes, not executable bid/ask,
            # funding, actual source books or account margin.
            entry_bar = market.get(native, entry_time)
            for horizon in (5, 15, 60):
                market.get(native, entry_bar.timestamp + timedelta(minutes=horizon))
        except (MarketDataBlocked, ValueError) as exc:
            counts[str(exc)[:100]] += 1
            continue
        success += 1
    complete = len(snapshot.events) <= market_limit
    reasons = {
        "INDEPENDENT_REGISTRATION_ATTESTATION_UNAVAILABLE",
        "SOURCE_BOOK_AND_EQUITY_NOT_INDEPENDENTLY_RECONCILED",
        "EXECUTABLE_FOLLOWER_CONTROL_COSTS_NOT_INDEPENDENTLY_ATTESTED",
        "SIGNED_MATURE_WHOLE_ACCOUNT_OUTCOMES_NOT_AVAILABLE",
    }
    if registered_at is None:
        reasons.add("NO_PIT_ROSTER_REGISTRATION_CLOCK")
    if not snapshot.events:
        reasons.add("NO_RECENT_WALLET_OPPORTUNITY_DECISIONS")
    if not admitted:
        reasons.add("NO_POST_REGISTRATION_DIRECTIONAL_EVENTS")
    if market_root is None:
        reasons.add("NATIVE_MINUTE_SOURCE_NOT_CONFIGURED")
    if not complete:
        reasons.add("MARKET_COVERAGE_ONLY_BOUNDED_SAMPLE")
    if success != len(sample):
        reasons.add("NATIVE_MINUTE_COVERAGE_MISSING_OR_BLOCKED")
    input_hash = digest(
        {
            "snapshot": snapshot.sha256,
            "roster": roster_sha,
            "registered_at": norm_clock(registered_at) if registered_at else None,
            "asof": norm_clock(cut),
            "market_attempts": len(sample),
            "market_blockers": sorted(counts.items()),
            "native_market_days": sorted(market.source_days.items()) if market else [],
        }
    )
    return SourcePreflight(
        schema="ti_private_source_preflight_v1",
        status="NOT_SCIENTIFICALLY_QUALIFIED",
        asof=norm_clock(cut),
        original_source="READ_ONLY_EXISTING_ENSEMBLE_OPPORTUNITY_JOURNAL",
        roster_count=len(wallets),
        roster_identity_sha256=roster_sha,
        roster_registration=(
            "OPERATOR_DECLARED_UNATTESTED" if registered_at else "UNREGISTERED_DYNAMIC_INSPECTION"
        ),
        matched_source_events=len(snapshot.events),
        potentially_directional_events=len(directional),
        observed_after_registration=len(admitted),
        complete_source_book_events=sum(e.book_complete is True for e in admitted),
        verifiable_equity_events=sum(
            e.book_complete is True and e.source_equity_usd is not None for e in admitted
        ),
        market_attempts=len(sample),
        market_exact_mark_successes=success,
        market_sample_is_complete=complete,
        market_blockers=dict(sorted(counts.items())),
        reasons=tuple(sorted(reasons)),
        asof_snapshot_sha256=snapshot.sha256,
        input_sha256=input_hash,
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Read-only live TI source/market qualification preflight"
    )
    parser.add_argument("--journal", type=Path, required=True)
    parser.add_argument("--private-source-files", type=Path, required=True)
    parser.add_argument("--aliases", required=True)
    parser.add_argument("--asof", default=None)
    parser.add_argument("--registered-at", default=None)
    parser.add_argument("--market-root", type=Path, default=None)
    parser.add_argument("--market-limit", type=int, default=25)
    parser.add_argument("--lookback-hours", type=int, default=24)
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()
    report = inspect_live_source(
        journal_db=args.journal,
        source_root=args.private_source_files,
        aliases=tuple(a.strip() for a in args.aliases.split(",")),
        asof=args.asof or datetime.now(UTC).isoformat(),
        registered_at=args.registered_at,
        market_root=args.market_root,
        market_limit=args.market_limit,
        lookback_hours=args.lookback_hours,
    )
    body = json.dumps(report.as_wire(), sort_keys=True)
    if args.output is None:
        print(body)
    else:
        from .pm_hyperx_account_triage import _write_immutable_private

        # An O_EXCL owner-private audit artifact, NOT a new data/event ledger.
        artifact_sha = _write_immutable_private(args.output, (body + "\n").encode())
        print(
            json.dumps(
                {
                    "status": report.status,
                    "artifact_file": str(args.output),
                    "artifact_sha256": artifact_sha,
                    "registered": report.roster_registration,
                    "source_events": report.matched_source_events,
                    "eligible_events": report.observed_after_registration,
                    "verified_native_minute_probes": report.market_exact_mark_successes,
                    "economic_evidence_attested": False,
                },
                sort_keys=True,
            )
        )


if __name__ == "__main__":
    main()
