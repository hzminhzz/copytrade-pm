"""Read-only Track B v2 census from independently verified V4 source events."""

from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path

from .strategy_health import (
    Campaign,
    MissingInterval,
    Opportunity,
    StrategyAssessment,
    StrategyScope,
    seal,
)
from .strategy_source_verify import verify_packet


def assess_verified_packet(
    packet: dict,
    public_key,
    *,
    source_journal,
    selected: dict[str, str],
    source_after: dict[str, int],
    scope: StrategyScope,
    campaign: Campaign,
    as_of: datetime,
    created_at: datetime,
    registry_db: Path | None = None,
) -> StrategyAssessment:
    if scope.tier != "SELECTED":
        raise ValueError("PROSPECTIVE_CENSUS_SELECTED_ONLY")
    if scope.source_alias not in selected:
        raise ValueError("CENSUS_SOURCE_OUT_OF_SELECTION")
    if len(selected) != 1:
        # No implicit blending across portfolio or source identities.
        raise ValueError("CENSUS_ONE_STRATEGY_PER_REPORT")
    if registry_db is not None:
        from .strategy_selection import verify_selected_registry

        binding = verify_selected_registry(scope, registry_db)
        if binding["selected"] != selected:
            raise ValueError("SOURCE_SIGNED_SCOPE_NOT_SQLITE_SELECTED")
    verified = verify_packet(
        packet,
        public_key,
        selected=selected,
        original_journal=source_journal,
        after=source_after,
        as_of=as_of,
        policy_version=scope.k_version,
        frozen_k=str(scope.frozen_k),
    )
    opportunities = tuple(
        Opportunity.model_validate_json(json.dumps(o)) for o in verified["opportunities"]
    )
    missing = tuple(
        MissingInterval.model_validate_json(json.dumps(gap))
        for gap in verified["missing_intervals"]
    )
    return seal(
        StrategyAssessment(
            created_at=created_at,
            as_of=as_of,
            strategy=scope,
            campaign=campaign,
            source_observability=(
                "INCOMPLETE_SCOPE"
                if registry_db is None
                else "GAP"
                if verified["source_status"] == "GAP"
                else "VERIFIED_CONTINUOUS"
            ),
            opportunities=opportunities,
            missing_intervals=missing,
        )
    )
