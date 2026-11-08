"""Pinned, owner-requested 16-scenario V4 *virtual-paper* research campaign.

This is a separate prospective experiment, NOT a replacement for SQLite's
versioned portfolio approvals, its exclusion records, or source PnL.
Private manifest addresses never enter Git or stdout. No broker capability.
"""

from __future__ import annotations

from contextlib import closing
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from hashlib import sha256
import json
from pathlib import Path
import re
import sqlite3
import stat

from .pm03_account import digest
from .pm_forward_observed_paper import PAPER_PROFILES, PaperPortfolioSpec

MANIFEST_SHA256 = "7c0b2a021a449c06f818cacf2f757a4d40b89e77669316107dc08ca659237e6f"
CAMPAIGN = "v4_sixteen_virtual_paper_20261109"
IDENTITIES = ("P1", "P14", "P15", "P16") + tuple(f"E{i}" for i in range(1, 13))
CANONICAL = {
    "W016": "S035",
    "W080": "S051",
    "W083": "S053",
    "W100": "S064",
    "S035-ENA": "S035",
    "S051-BTC": "S051",
    "S053-HYPE": "S053",
    "S064-xyz:BRENTOIL": "S064",
    "HL Perps Whale": "Whale_0x5f94",
}
# Resolving conflicts does NOT repair the historical Gemini evidence.
# These are newly defined, conservative and explicitly hypothetical paper k.
E2_CONSERVATIVE_100K = {"ACT04": "0.0374", "W083": "0.2749", "W080": "0.1747"}
E9_CONSERVATIVE_100K = {"ACT08": "0.0199"}
ADDRESS = re.compile(r"0x[0-9a-f]{40}\Z")
SHA = re.compile(r"[0-9a-f]{64}\Z")


@dataclass(frozen=True)
class V4Campaign:
    profiles: dict[str, PaperPortfolioSpec]
    parents: dict[str, str]
    account_hashes: dict[str, dict[str, str]]
    seals: dict[str, dict]
    flags: dict[str, tuple[str, ...]]
    manifest_sha256: str

    def public_status(self) -> dict:
        """Redact raw source addresses, retain negative evidence and research status."""
        return {
            "campaign": CAMPAIGN,
            "source_manifest_sha256": self.manifest_sha256,
            "portfolio_count": len(self.profiles),
            "unique_parent_count": len(self.parents),
            "portfolios": {
                key: {
                    "members": list(profile.full_aliases),
                    "sizing_evidence": profile.sizing_evidence,
                    "review_flags": list(self.flags[key]),
                    "selection_kind": self.seals[key]["selection_kind"],
                    "definition_sha256": self.seals[key]["definition_sha256"],
                    "trading_authorized": False,
                }
                for key, profile in self.profiles.items()
            },
            "order_route": "NONE",
            "scientifically_qualified": False,
            "trading_authorized": False,
        }


def _ro_database(path: Path) -> sqlite3.Connection:
    if not path.is_file() or path.is_symlink():
        raise ValueError("V4_CAMPAIGN_SQLITE_MISSING")
    con = sqlite3.connect(f"file:{path.resolve()}?mode=ro", uri=True, timeout=5)
    con.execute("PRAGMA query_only=ON")
    return con


def _parse_pairs(raw: str) -> dict[str, Decimal]:
    if not raw:
        raise ValueError("V4_CAMPAIGN_MISSING_K")
    result: dict[str, Decimal] = {}
    for item in raw.split(","):
        alias, sep, value = item.rpartition(":")
        if not sep or not alias or alias in result:
            raise ValueError("V4_CAMPAIGN_BAD_K_SOURCE")
        try:
            d = Decimal(value)
        except ArithmeticError as exc:
            raise ValueError("V4_CAMPAIGN_BAD_K_NUMBER") from exc
        if not d.is_finite() or d <= 0:
            raise ValueError("V4_CAMPAIGN_NONPOSITIVE_K")
        result[alias] = d
    return result


def _fmt(value: Decimal) -> str:
    return format(value.quantize(Decimal("0.000000000001")), "f")


def _fixed_k(
    item: dict, pid: str, aliases: tuple[str, ...], *, risk_scale: Decimal
) -> tuple[tuple[str, ...], str]:
    if pid == "P15":
        # Original P15 is historically DEFERRED and contains no native k.
        # This is an EXPLICIT NEW P14-scaled sensitivity, not recovered values.
        reference = PAPER_PROFILES["P14"]
        base = dict(zip(reference.full_aliases, reference.k_by_pod, strict=True))
        if set(aliases) != set(reference.full_aliases):
            raise ValueError("V4_P15_ORIGINAL_ROSTER_DRIFT")
        vals = tuple(_fmt(Decimal(base[a]) * Decimal(5) / Decimal(3) * risk_scale) for a in aliases)
        return vals, "P15_DERIVED_P14_RISK_CAPPED_CONTROL_NOT_ORIGINAL_K"
    raw = item.get("k_factors_reported_100k")
    original = _parse_pairs(raw)
    if set(original) != set(aliases):
        raise ValueError("V4_CAMPAIGN_K_MEMBER_MISMATCH")
    if pid == "E2":
        for a, alt in E2_CONSERVATIVE_100K.items():
            original[a] = min(original[a], Decimal(alt))
    if pid == "E9":
        for a, alt in E9_CONSERVATIVE_100K.items():
            original[a] = min(original[a], Decimal(alt))
    values = []
    for a in aliases:
        # A 100k source report does not directly size a $10k virtual account.
        k = original[a] / Decimal("10") * risk_scale
        if pid == "E10":
            # Negative-control scenario: reduce already-rejected position scale.
            k = k / Decimal("2")
        values.append(_fmt(k))
    origin = "100K_REFERENCE_SCALED_TO_10K_HYPOTHESIS"
    if pid in ("E2", "E9"):
        origin += "_CONFLICT_CONSERVATIVE_LOWER"
    if risk_scale < Decimal("1"):
        origin += "_HISTORICAL_RISK_CAPPED_TO_600"
    if pid == "E10":
        origin += "_DAILY_BREACH_REMEDIATION_HALF_K_NEGATIVE_CONTROL"
    return tuple(values), origin


def load_campaign(
    *,
    manifest: Path,
    registry_db: Path,
    at: str,
    expected_sha256: str = MANIFEST_SHA256,
) -> V4Campaign:
    """Verify all sixteen identities against the *current* SQLite registry.

    A private, SHA-pinned historical research manifest is NOT a signed SQLite
    portfolio selection. The new prospective paper seals say so explicitly.
    """
    if expected_sha256 != MANIFEST_SHA256 or not SHA.fullmatch(expected_sha256):
        raise ValueError("V4_CAMPAIGN_UNREVIEWED_MANIFEST_SHA")
    if manifest.is_symlink() or not manifest.is_file():
        raise ValueError("V4_CAMPAIGN_PRIVATE_MANIFEST_MISSING")
    mode = stat.S_IMODE(manifest.stat().st_mode)
    if mode != 0o600:
        raise PermissionError("V4_CAMPAIGN_MANIFEST_NOT_PRIVATE")
    raw = manifest.read_bytes()
    if sha256(raw).hexdigest() != expected_sha256:
        raise ValueError("V4_CAMPAIGN_MANIFEST_DRIFT")
    doc = json.loads(raw)
    if (
        doc.get("schema") != "gemini_source_preserving_eligibility_manifest_v1"
        or "no live/paper activation" not in doc.get("authority", "")
    ):
        raise ValueError("V4_CAMPAIGN_HISTORICAL_AUTHORITY_INVALID")
    rows = {item["portfolio_id"]: item for item in doc["portfolios"]}
    if len(doc["portfolios"]) != len(IDENTITIES) or set(rows) != set(IDENTITIES):
        raise ValueError("V4_CAMPAIGN_ROSTER_DRIFT")
    observed = datetime.fromisoformat(at)
    if observed.tzinfo is None or observed < datetime.fromisoformat("2026-11-09T00:00:00+07:00"):
        raise ValueError("V4_CAMPAIGN_REQUIRES_PROSPECTIVE_CLOCK")
    parents: dict[str, str] = {}
    hashes: dict[str, dict[str, str]] = {}
    profiles: dict[str, PaperPortfolioSpec] = {}
    seals: dict[str, dict] = {}
    flags: dict[str, tuple[str, ...]] = {}
    alias_for_address: dict[str, str] = {}
    with closing(_ro_database(registry_db)) as con:
        con.execute("BEGIN")
        try:
            for pid in IDENTITIES:
                item = rows[pid]
                originals = tuple(item["original_source_aliases"])
                addresses = tuple(item["member_addresses"])
                if (
                    not originals
                    or len(originals) != len(addresses)
                    or len(set(originals)) != len(originals)
                ):
                    raise ValueError("V4_CAMPAIGN_DUPLICATE_MEMBERS")
                ids: list[str] = []
                seen: set[str] = set()
                exclusion_flags: list[str] = []
                account_hashes: dict[str, str] = {}
                for alias, raw_address in zip(originals, addresses, strict=True):
                    addr = raw_address.lower()
                    if not ADDRESS.fullmatch(addr):
                        raise ValueError("V4_CAMPAIGN_BAD_ADDRESS")
                    wallets = con.execute(
                        "SELECT wallet_id FROM wallets WHERE lower(address)=?", (addr,)
                    ).fetchall()
                    if len(wallets) != 1:
                        raise ValueError("V4_CAMPAIGN_WALLET_NOT_UNIQUE_IN_SQLITE:" + pid)
                    wallet_id = wallets[0][0]
                    existing = con.execute(
                        "SELECT DISTINCT lower(w.address) FROM wallet_aliases a "
                        "LEFT JOIN wallets w ON w.wallet_id=a.wallet_id "
                        "WHERE a.alias=? AND a.known_at<=?",
                        (alias, at),
                    ).fetchall()
                    if existing and (len(existing) != 1 or existing[0][0] != addr):
                        raise ValueError("V4_CAMPAIGN_ALIAS_CONFLICT:" + pid)
                    canonical = CANONICAL.get(alias, alias)
                    canonical_rows = con.execute(
                        "SELECT DISTINCT lower(w.address) FROM wallet_aliases a "
                        "LEFT JOIN wallets w ON w.wallet_id=a.wallet_id "
                        "WHERE a.alias=? AND a.known_at<=?",
                        (canonical, at),
                    ).fetchall()
                    if canonical_rows and (
                        len(canonical_rows) != 1 or canonical_rows[0][0] != addr
                    ):
                        raise ValueError("V4_CAMPAIGN_CANONICAL_ALIAS_DRIFT")
                    if addr in alias_for_address and alias_for_address[addr] != canonical:
                        raise ValueError("V4_CAMPAIGN_SHARED_PARENT_ALIAS_CONFLICT")
                    alias_for_address[addr] = canonical
                    if canonical in parents and parents[canonical] != addr:
                        raise ValueError("V4_CAMPAIGN_PARENT_COLLISION")
                    parents[canonical] = addr
                    if canonical in seen:
                        raise ValueError("V4_CAMPAIGN_DUPLICATE_PARENT_IN_PORTFOLIO")
                    seen.add(canonical)
                    ids.append(canonical)
                    account_hashes[canonical] = sha256(addr.encode()).hexdigest()
                    excluded = con.execute(
                        "SELECT 1 FROM exclusions WHERE wallet_id=? AND known_at<=? "
                        "UNION SELECT 1 FROM propfirm_exclusions WHERE wallet_id=? "
                        "AND known_at<=?",
                        (wallet_id, at, wallet_id, at),
                    ).fetchone()
                    if excluded:
                        exclusion_flags.append("PREEXISTING_EXCLUSION:" + canonical)
                if pid in PAPER_PROFILES:
                    profile = PAPER_PROFILES[pid]
                    if (
                        tuple(profile.source_ids) != tuple(ids)
                        or tuple(profile.full_aliases) != originals
                    ):
                        raise ValueError("V4_CAMPAIGN_LEGACY_PROFILE_DRIFT")
                    if pid == "P1" and profile.k_by_pod != ("0.0282", "0.0430", "0.0296"):
                        raise ValueError("V4_CAMPAIGN_P1_K_POLICY_DRIFT")
                    seal_kind = "SQLITE_APPROVED_HISTORICAL_V4_PROFILE"
                else:
                    historical_risk = Decimal(str(item["total_nominal_pod_risk_usd"]))
                    historical_pod_risk = Decimal(str(item["equal_nominal_pod_risk_usd"]))
                    if (
                        historical_risk != historical_pod_risk * len(ids)
                        or historical_pod_risk <= 0
                        or historical_risk not in (Decimal("600"), Decimal("1000"))
                    ):
                        raise ValueError("V4_CAMPAIGN_RISK_DISTRIBUTION_INVALID")
                    # PM03 daily budget 500, static 1000, reserve 10 and PM04
                    # stress budget 700 cannot fund five $200 pods. Never relax
                    # those constraints to rescue a historical 1000-risk idea.
                    risk_usd = min(historical_risk, Decimal("600"))
                    risk_scale = risk_usd / historical_risk
                    pod_risk = risk_usd / Decimal(len(ids))
                    k_values, evidence = _fixed_k(item, pid, originals, risk_scale=risk_scale)
                    profile = PaperPortfolioSpec(
                        registry_id=pid,
                        source_ids=tuple(ids),
                        full_aliases=originals,
                        k_by_pod=k_values,
                        losses=tuple(str(pod_risk) for _ in ids),
                        sizing_evidence=evidence,
                        nominal_risk=str(risk_usd),
                    )
                    seal_kind = "UNSIGNED_PROSPECTIVE_PAPER_SCENARIO_NOT_SQLITE_SELECTION"
                if set(account_hashes) != set(profile.source_ids):
                    raise ValueError("V4_CAMPAIGN_PROFILE_ACCOUNT_MISMATCH")
                original_flags = tuple(item.get("blockers") or ())
                if pid not in PAPER_PROFILES and risk_scale < Decimal("1"):
                    original_flags += ("HISTORICAL_1000_RISK_REDUCED_TO_600_FOR_PM04",)
                review_flags = original_flags + tuple(exclusion_flags)
                flags[pid] = review_flags
                profiles[pid] = profile
                hashes[pid] = account_hashes
                selection = {
                    "campaign": CAMPAIGN,
                    "source_sha256": expected_sha256,
                    "portfolio_id": pid,
                    "source_accounts": {key: account_hashes[key] for key in sorted(account_hashes)},
                    "source_ids": profile.source_ids,
                    "full_aliases": profile.full_aliases,
                    "k": profile.k_by_pod,
                    "losses": profile.losses,
                    "sizing_evidence": profile.sizing_evidence,
                    "flags": review_flags,
                    "selected_at": at,
                }
                # The selection digest is *not* a signature or trading permit.
                seal_sha = digest(
                    {key: value for key, value in selection.items() if key != "selected_at"}
                )
                seals[pid] = {
                    "portfolio_id": pid,
                    "version": 1,
                    "definition_sha256": seal_sha,
                    "selection_kind": seal_kind,
                    "review_flags": review_flags,
                    "source_manifest_sha256": expected_sha256,
                }
        finally:
            con.execute("ROLLBACK")
    if len(parents) > 32 or len(parents) < 8:
        raise ValueError("V4_CAMPAIGN_UNEXPECTED_PARENT_COUNT")
    return V4Campaign(
        profiles=profiles,
        parents=dict(sorted(parents.items())),
        account_hashes=hashes,
        seals=seals,
        flags=flags,
        manifest_sha256=expected_sha256,
    )
