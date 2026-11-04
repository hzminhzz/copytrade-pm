"""Exact contractual fixture certification using the existing PM-03 Decimal account.

This is a verdict on a specified synthetic trajectory, never a real challenge
outcome or scientific qualification. SCREEN_ONLY returns no financial verdict.
The PM-03 Account retains exclusive cash, equity, floors and HALT authority.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from .pm03_account import Account, RiskState, Rulebook
from .pm_offline_manifest import ManifestInvalid

VERDICTS = frozenset({"PASS", "BREACH", "UNKNOWN", "AMBIGUOUS"})


def certify_account_fixture(
    account: Account,
    *,
    mode: str,
    full_minute_coverage: bool,
    complete_source_book: bool,
    complete_equity: bool,
    complete_funding: bool,
    intrabar_order_known: bool,
    right_censored: bool,
) -> dict[str, Any]:
    """Certify path-independent *reported* account status at current PM03 state.

    Incomplete observations cannot produce a contractual PASS or BREACH.
    An exact PM03 breach is only reportable after complete, independently
    verified inputs. UNKNOWN/AMBIGUOUS never become favorable PASS.
    """
    if mode not in ("SCREEN_ONLY", "CERTIFIED"):
        raise ManifestInvalid("UNKNOWN_CERTIFICATION_MODE")
    account.verify()
    evidence = {
        "complete_source_book": complete_source_book,
        "complete_equity": complete_equity,
        "complete_funding": complete_funding,
        "full_minute_coverage": full_minute_coverage,
        "intrabar_order_known": intrabar_order_known,
        "right_censored": right_censored,
        "account_terms_confirmed": account.rulebook.account_terms_confirmed,
    }
    if mode == "SCREEN_ONLY":
        return {
            "verdict": "UNKNOWN",
            "status": "SCREEN_ONLY",
            "certified": False,
            "evidence": evidence,
            "reason": "APPROXIMATE_SCREENING_NEVER_CERTIFIES",
        }
    if not account.rulebook.account_terms_confirmed or not account.rulebook.confirmed:
        return {
            "verdict": "UNKNOWN",
            "status": "UNCONFIRMED_CONTRACTUAL_RULEBOOK",
            "certified": False,
            "evidence": evidence,
            "reason": "RULEBOOK_NEEDS_OWNER_ACCOUNT_PROVENANCE",
        }
    if not all((complete_source_book, complete_equity, complete_funding, full_minute_coverage)):
        return {
            "verdict": "UNKNOWN",
            "status": "INSUFFICIENT_ACCOUNT_EVIDENCE",
            "certified": False,
            "evidence": evidence,
            "reason": "MISSING_SOURCE_EQUITY_FUNDING_OR_MINUTE_MARKS",
        }
    if account.breached:
        return {
            "verdict": "BREACH",
            "status": "SYNTHETIC_CONTRACTUAL_BREACH",
            "certified": True,
            "evidence": evidence,
            "reason": account.halt_reason or "CONTRACTUAL_EQUITY_FLOOR",
            "equity": str(account.equity),
            "floor": str(account.floor()[0]),
        }
    if not intrabar_order_known:
        return {
            "verdict": "AMBIGUOUS",
            "status": "INTRABAR_PATH_AMBIGUOUS",
            "certified": False,
            "evidence": evidence,
            "reason": "OHLCV_DOES_NOT_RESOLVE_INTRABAR_EVENT_ORDER",
        }
    if right_censored:
        return {
            "verdict": "UNKNOWN",
            "status": "RIGHT_CENSORED",
            "certified": False,
            "evidence": evidence,
            "reason": "OPEN_RISK_OR_UNMATURED_EVENTS",
        }
    if account.stage_passed:
        return {
            "verdict": "PASS",
            "status": "SYNTHETIC_TARGET_REACHED",
            "certified": True,
            "evidence": evidence,
            "equity": str(account.equity),
            "profit_target": str(account.rulebook.profit_target),
        }
    return {
        "verdict": "UNKNOWN",
        "status": "TARGET_NOT_REACHED",
        "certified": False,
        "evidence": evidence,
        "reason": "COMPLETE_PATH_WITHOUT_TARGET_IS_NOT_PASS",
    }


def exact_floor_state(
    rulebook: Rulebook,
    *,
    observed_equity: Decimal,
    high_water: Decimal,
    day_start_balance: Decimal,
) -> dict[str, str | bool]:
    """Independent fixture probing uses PM03's actual inclusive floor logic."""
    account = Account.start(rulebook, rulebook.observed_at)
    account.cash = observed_equity
    account.equity = observed_equity
    account.high_water = high_water
    account.daily_start_balance = day_start_balance
    account._check_breach()
    floor, components = account.floor()
    return {
        "equity": str(account.equity),
        "floor": str(floor) if floor is not None else "UNKNOWN",
        "daily_floor": str(components["daily"]) if "daily" in components else "UNKNOWN",
        "trailing_floor": str(components["trailing"]) if "trailing" in components else "UNKNOWN",
        "breached": account.breached,
        "halt": account.risk == RiskState.HALT,
    }
