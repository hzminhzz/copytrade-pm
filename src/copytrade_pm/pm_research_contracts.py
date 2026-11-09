"""Research projections with explicit limits; no qualification or trading issuer."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

Count = Annotated[int, Field(ge=0)]


class RetrospectiveEvidence(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)
    kind: Literal["RETROSPECTIVE_ESTIMATE"] = "RETROSPECTIVE_ESTIMATE"
    clock_basis: Literal["SOURCE_EVENT_TIME_NOT_FIRST_KNOWN"] = "SOURCE_EVENT_TIME_NOT_FIRST_KNOWN"
    account_scope: Literal["VENDOR_LISTED_PARTIAL_ACCOUNT"] = "VENDOR_LISTED_PARTIAL_ACCOUNT"
    source_gaps: tuple[str, ...] = ()
    prospective_source_book: Literal[False] = False
    original_first_known_verified: Literal[False] = False
    scientifically_qualified: Literal[False] = False
    trading_authorized: Literal[False] = False

    def as_wire(self) -> dict:
        return self.model_dump()


class ChallengeLifecycleSummary(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)
    kind: Literal["RESEARCH_SCENARIO_SIMULATION"] = "RESEARCH_SCENARIO_SIMULATION"
    paths: Annotated[int, Field(gt=0)]
    ever_funded_count: Count
    currently_active_count: Count
    currently_funded_count: Count
    historical_payout_count: Count
    forward_observed: Literal[False] = False
    scientifically_qualified: Literal[False] = False
    trading_authorized: Literal[False] = False

    @model_validator(mode="after")
    def subsets(self) -> ChallengeLifecycleSummary:
        if (
            not self.currently_funded_count <= self.currently_active_count <= self.paths
            or not self.currently_funded_count <= self.ever_funded_count <= self.paths
            or self.historical_payout_count > self.ever_funded_count
        ):
            raise ValueError("INCONSISTENT_CHALLENGE_LIFECYCLE_COUNTS")
        return self
