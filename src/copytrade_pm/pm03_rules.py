"""Dated public Propr rules: research contract snapshots, never account authorization.

Terms are owned by the single canonical ``copytrade_kernel.RulebookCatalog``.
The observed public page is quoted below only as evidence for the snapshot
digest, and every quoted fraction is reconciled against the catalog at
construction time: drift fails closed instead of silently re-deriving a second
rulebook.

Source: https://www.propr.xyz/rules (consulted 2026-10-31)
Cross-check: owner-private 2026-10-30 risk/contract snapshot.
Published conditions can differ from the user's purchased/account-specific terms.
"""

from __future__ import annotations

from decimal import Decimal as D

from copytrade_kernel import RulebookCatalog

from .pm03_account import Rulebook, clock, digest

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
TERM_SOURCES = tuple(RulebookCatalog.list_keys("propr"))


def _challenge_key(program: str, stage: str) -> str:
    """Resolve the catalog key for a Propr program/stage; the catalog decides existence."""
    if program not in PUBLIC_RULES:
        raise ValueError("UNKNOWN_PROPR_PROGRAM")
    if stage not in ("evaluation", "step1", "step2", "funded"):
        raise ValueError("UNKNOWN_PROPR_STAGE")
    if program == "classic_2step":
        if stage == "evaluation":
            raise ValueError("USE_EXPLICIT_TWO_STEP_STAGE")
        phase = {"step1": "phase_1", "step2": "phase_2", "funded": "funded"}[stage]
    elif stage in ("step1", "step2"):
        raise ValueError("STAGE_NOT_APPLICABLE")
    else:
        phase = "phase_1" if stage == "evaluation" else "funded"
    return f"propr:{program}:{phase}"


def _reconcile(spec, program: str, stage: str) -> None:
    """Fail closed when the quoted page and the canonical catalog disagree."""
    base = D(spec.initial)
    quoted = PUBLIC_RULES[program]
    checks = [(spec.daily_loss, quoted["daily"])]
    if "target" in quoted or stage in quoted:
        checks.append((spec.target, quoted[stage]))
    if spec.trailing_basis == "STATIC":
        checks.append((spec.trailing_loss, quoted["static"]))
    else:
        checks.append((spec.trailing_loss, quoted["trailing"]))
    for amount, fraction in checks:
        if D(amount) != D(fraction) * base:
            raise ValueError("PROPR_RULEBOOK_CATALOG_DRIFT")


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
        raise ValueError("PUBLIC_RULE_OBSERVATION_CANNOT_BACKDATED")
    key = _challenge_key(program, stage)
    spec = RulebookCatalog.get(key)
    _reconcile(spec, program, stage)
    data = PUBLIC_RULES[program]
    if program == "classic_2step":
        fraction = None if stage == "funded" else data[stage]
    else:
        fraction = data["evaluation"] if stage == "evaluation" else None
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
