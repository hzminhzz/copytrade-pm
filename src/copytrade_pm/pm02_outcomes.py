"""Versioned independent whole-account outcome contract; no signing capability."""

from decimal import Decimal, InvalidOperation
import re

from .pm03_account import Instrument

SCHEMA = "pm02_independent_matched_outcome_v2"
DIGEST_FIELDS = (
    "selection_plan_sha256",
    "source_book_evidence_sha256",
    "source_equity_evidence_sha256",
    "whole_account_reconciliation_sha256",
    "execution_cost_evidence_sha256",
    "funding_evidence_sha256",
    "capacity_evidence_sha256",
    "episode_census_sha256",
    "control_plan_sha256",
    "uncertainty_audit_sha256",
)
CLAIM_FIELDS = (
    "selection_plan_independently_reviewed",
    "whole_account_reconciled",
    "complete_episode_census",
    "execution_costs_verified",
    "funding_verified",
    "capacity_verified",
    "predeclared_control",
    "tail_uncertainty_reviewed",
)
NUMBER_FIELDS = ("source_net_r", "risk_unit_usd", "source_scale_factor")
CONSUMER_FIELDS = (
    *DIGEST_FIELDS,
    *CLAIM_FIELDS,
    *NUMBER_FIELDS,
    "source_event_id",
    "horizon_minutes",
    "decision_at",
)


def validate_whole_account(attestation: dict) -> None:
    if attestation.get("schema") != SCHEMA:
        raise ValueError("UNKNOWN_WHOLE_ACCOUNT_OUTCOME_SCHEMA")
    if any(attestation.get(key) is not True for key in CLAIM_FIELDS):
        raise ValueError("UNVERIFIED_WHOLE_ACCOUNT_ECONOMICS")
    if any(
        not isinstance(attestation.get(key), str)
        or re.fullmatch("[0-9a-f]{64}", attestation[key]) is None
        for key in DIGEST_FIELDS
    ):
        raise ValueError("MISSING_WHOLE_ACCOUNT_EVIDENCE")
    for key in NUMBER_FIELDS:
        try:
            value = Decimal(str(attestation[key]))
        except (InvalidOperation, KeyError) as exc:
            raise ValueError("INVALID_WHOLE_ACCOUNT_ECONOMICS") from exc
        if not value.is_finite() or (key != "source_net_r" and value <= 0):
            raise ValueError("INVALID_WHOLE_ACCOUNT_ECONOMICS")
    exposures = attestation.get("signed_exposures_r")
    if not isinstance(exposures, dict) or not exposures:
        raise ValueError("UNKNOWN_SIGNED_EXPOSURES")
    for key in exposures:
        try:
            instrument = Instrument.parse(key)
        except (TypeError, ValueError) as exc:
            raise ValueError("NON_NATIVE_WHOLE_ACCOUNT_EXPOSURE") from exc
        if (
            instrument.venue != "hyperliquid"
            or not instrument.market.startswith("mainnet:perp:")
            or len(instrument.market.split(":")) != 3
            or ":" in instrument.symbol
        ):
            raise ValueError("NON_NATIVE_WHOLE_ACCOUNT_EXPOSURE")
