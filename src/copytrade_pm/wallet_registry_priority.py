"""Read-only latest research-priority overlay, separate from sealed WR selections.

The V2 priority file is an immutable user-approved *research* preference;
it does not rewrite WR-06 P1/P14 v2 source/provenance SHA contracts or the
Forward-Paper PR #73 P1/P14 engineering trial. No registry/database writes.
"""

from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path

SCHEMA = "gemini_research_portfolio_priority_v2"
SOURCE = "docs/decisions/2026-11-04-gemini-phase6-portfolio-freeze-v2.json"
SOURCE_SHA256 = "21f4e9406370fefcb0e38719c2a07bb57b68b073d70b3530034f7f5944c240fc"
SOURCE_COMMIT = "a87e587700282517d68524997486d5f2fa3efd57"
SOURCE_KNOWN_AT = "2026-11-04T09:06:33+00:00"
LEGACY_FP_BASELINES = {
    "P1": ("S035-ENA", "S051-BTC", "S053-HYPE"),
    "P14": ("S035-ENA", "S051-BTC", "S053-HYPE", "S064-xyz:BRENTOIL", "Whale_0x5f94"),
}
NEW_PRIORITY = ("E6", "E2", "P1", "E3", "B_phase5")
EXPECTED_STATUSES = {
    "E6": "PRIMARY_FORWARD_PAPER_RESEARCH",
    "E2": "THREE_POD_FORWARD_PAPER_CHALLENGER",
    "P1": "INCUMBENT_HISTORICAL_BASELINE_NO_NEW_PROMOTION",
    "P14": "ARCHIVED_PREVIOUS_FIVE_POD_CHALLENGER",
}


def _unique_object(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("PRIORITY_V2_DUPLICATE_JSON_KEY")
        result[key] = value
    return result


def _at(raw: str) -> datetime:
    point = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    if point.tzinfo is None:
        raise ValueError("PRIORITY_V2_ASOF_REQUIRES_OFFSET")
    return point.astimezone(timezone.utc)


def priority_v2(repo: Path, *, as_of: str) -> dict:
    """Versioned view only; missing/tampered source fails closed.

    Before the reviewed commit time, do not backdate the selection using the
    report date, a trader fill timestamp, or a file's current mtime.
    """
    known = _at(SOURCE_KNOWN_AT)
    now = _at(as_of)
    if now < known:
        return {
            "schema": "wallet_registry_priority_overlay_v1",
            "state": "UNKNOWN_AT_ASOF",
            "source_commit": SOURCE_COMMIT,
            "source_known_at": SOURCE_KNOWN_AT,
            "new_research_priorities": [],
            "paper_registry_changed": False,
            "forward_paper_portfolios_changed": False,
            "paper_admitted": False,
            "trading_authorized": False,
        }
    path = Path(repo) / SOURCE
    if path.is_symlink() or not path.is_file():
        raise ValueError("PRIORITY_V2_SOURCE_FILE_UNAVAILABLE")
    raw = path.read_bytes()
    if sha256(raw).hexdigest() != SOURCE_SHA256:
        raise ValueError("PRIORITY_V2_SOURCE_DOCUMENT_DRIFT")
    try:
        record = json.loads(raw, object_pairs_hook=_unique_object)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("PRIORITY_V2_INVALID_DOCUMENT") from exc
    if (
        not isinstance(record, dict)
        or record.get("schema") != SCHEMA
        or record.get("decision_authority") != "user_approved"
        or record.get("scope") != "NEW_FORWARD_PAPER_RESEARCH_ONLY"
        or record.get("status") != "SELECTION_SAVED_NOT_REGISTERED_OR_DEPLOYED"
        or record.get("new_forward_paper_priority") != list(NEW_PRIORITY)
        or not isinstance(record.get("portfolios"), dict)
        or record.get("research_contract", {}).get("virtual_initial_equity_usd") != 10000
        or record["research_contract"].get("equal_nominal_risk_budget_usd") != 600
        or record["research_contract"].get("manual_activation_allowed") is not False
        or record["research_contract"].get("trading_authorized") is not False
        or record.get("preservation", {}).get("existing_FP09_P1_P14_trial_unchanged") is not True
        or record["preservation"].get("previous_p1_p14_frozen_identifiers_unchanged") is not True
    ):
        raise ValueError("PRIORITY_V2_UNTRUSTED_SELECTION_CONTRACT")
    profiles = record["portfolios"]
    for name, status in EXPECTED_STATUSES.items():
        if profiles.get(name, {}).get("state") != status:
            raise ValueError("PRIORITY_V2_FROZEN_DISPOSITION_DRIFT")
    alias_sets = {}
    for name in ("E6", "E2", "P1", "P14"):
        profile = profiles[name]
        members = profile["members"]
        if not isinstance(members, list) or not members:
            raise ValueError("PRIORITY_V2_MEMBER_SCOPE_INVALID")
        aliases = tuple(row["canonical_alias"] for row in members)
        if not all(isinstance(alias, str) and alias for alias in aliases):
            raise ValueError("PRIORITY_V2_MEMBER_ALIAS_INVALID")
        if len(set(aliases)) != len(aliases) or profile.get("pod_count") != len(aliases):
            raise ValueError("PRIORITY_V2_MEMBER_IDENTITY_DUPLICATE_OR_COUNT")
        if profile.get("nominal_total_risk_budget_usd") != 600:
            raise ValueError("PRIORITY_V2_RISK_BUDGET_DRIFT")
        alias_sets[name] = aliases
    if any(
        set(alias_sets[name]) != set(expected) for name, expected in LEGACY_FP_BASELINES.items()
    ):
        raise ValueError("PRIORITY_V2_LEGACY_FP_MEMBERSHIP_DRIFT")
    if set(alias_sets["E2"]) != set(alias_sets["E6"]) - {"CM-002", "Whale_0x5f94"}:
        raise ValueError("PRIORITY_V2_E6_E2_OVERLAP_DRIFT")
    return {
        "schema": "wallet_registry_priority_overlay_v1",
        "state": "NEW_RESEARCH_ONLY_NOT_REGISTERED",
        "source_commit": SOURCE_COMMIT,
        "source_sha256": SOURCE_SHA256,
        "source_known_at": SOURCE_KNOWN_AT,
        "priority": list(NEW_PRIORITY),
        "portfolios": {
            name: {
                "research_disposition": profiles[name]["state"],
                "new_research_rank": profiles[name].get("priority"),
                "member_aliases": list(alias_sets[name]),
                "member_count": len(alias_sets[name]),
                "virtual_initial_equity_usd": 10000,
                "nominal_total_risk_budget_usd": 600,
                "wallet_identity_independently_proven": False,
                "registered_forward_paper_worker": False,
                "paper_admitted": False,
                "trading_authorized": False,
            }
            for name in ("E6", "E2", "P1", "P14")
        },
        "paper_registry_changed": False,
        "forward_paper_portfolios_changed": False,
        "paper_admitted": False,
        "trading_authorized": False,
    }
