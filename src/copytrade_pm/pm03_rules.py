"""Dated public Propr rules: research contract snapshots, never account authorization.

Source: https://www.propr.xyz/rules (consulted 2026-10-31)
Cross-check: owner-private 2026-10-30 risk/contract snapshot.
Published conditions can differ from the user's purchased/account-specific terms.
"""

from __future__ import annotations

from decimal import Decimal as D

from .pm03_account import Rulebook, digest, clock

SOURCE = "https://www.propr.xyz/rules"
TERMS = "https://www.propr.xyz/terms"
SOURCE_VERSION = "propr-public-v1.0.5-2026-07-27"
PUBLIC_RULES = {
    "classic_1step": {"evaluation": "0.10", "daily": "0.03", "static": "0.06"},
    "turbo_1step": {"evaluation": "0.09", "daily": "0.03", "static": "0.03"},
    "classic_2step": {"step1": "0.05", "step2": "0.10", "daily": "0.05", "trailing": "0.08"},
}
PUBLIC_SNAPSHOT_SHA = digest(
    {
        "schema": "pm03_propr_public_rules_v1",
        "source": SOURCE,
        "terms": TERMS,
        "version": SOURCE_VERSION,
        "observed_utc_date": "2026-10-31",
        "rules": PUBLIC_RULES,
        "reset_timezone": "UTC",
        "balance_reference": "REALIZED_ONLY",
        "breach_equity_includes_unrealized": True,
        "trailing_cap": "INITIAL_BALANCE",
        "instrument_acceptance": "UNKNOWN",
        "account_specific_terms": "UNCONFIRMED",
    }
)


def propr_rulebook(
    program: str,
    stage: str,
    initial_balance: D,
    *,
    observed_at: str,
) -> Rulebook:
    """Construct publicly sourced defaults, always blocked for real risk.

    Exact allowed markets and user-account stage terms are not attested;
    this factory deliberately cannot set confirmed=True.
    """
    if clock(observed_at) < clock("2026-10-31T00:00:00+00:00"):
        raise ValueError("PUBLIC_RULE_OBSERVATION_CANNOT_BE_BACKDATED")
    if program not in PUBLIC_RULES:
        raise ValueError("UNKNOWN_PROPR_PROGRAM")
    data = PUBLIC_RULES[program]
    if stage not in ("evaluation", "step1", "step2", "funded"):
        raise ValueError("UNKNOWN_PROPR_STAGE")
    if program == "classic_2step":
        if stage == "evaluation":
            raise ValueError("USE_EXPLICIT_TWO_STEP_STAGE")
        fraction = data.get(stage)
    elif stage in ("step1", "step2"):
        raise ValueError("STAGE_NOT_APPLICABLE")
    else:
        fraction = data.get("evaluation") if stage == "evaluation" else None
    starting = D(str(initial_balance))
    return Rulebook(
        program=program,
        stage=stage,
        source=SOURCE,
        version=SOURCE_VERSION,
        observed_at=observed_at,
        effective_at="2026-07-27T00:00:00+00:00",
        timezone="UTC",
        initial_balance=starting,
        profit_target=starting * D(fraction) if fraction is not None else None,
        daily_loss=None,
        daily_loss_rate=D(data["daily"]),
        static_loss=starting * D(data["static"]) if "static" in data else None,
        trailing_loss=starting * D(data["trailing"]) if "trailing" in data else None,
        trailing_cap=starting if "trailing" in data else None,
        # Neither display-universe nor vendor HIP3 coins confirm an executable market id.
        permitted=(),
        confirmed=False,
        account_terms_confirmed=False,
        max_gross_leverage=None,
        snapshot_sha=PUBLIC_SNAPSHOT_SHA,
    )
