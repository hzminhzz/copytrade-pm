"""Paper-only k research release gate: externally attested evidence, never auto-sign.

A Track C research proposal or registry seal is insufficient. The research signer
must be explicitly used outside runtime, with a separately pinned public key.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from hashlib import sha256
import json
from pathlib import Path
import time

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from .production_manifest import verify as verify_envelope


def _sha(value: object) -> bool:
    return (
        isinstance(value, str) and len(value) == 64 and all(x in "0123456789abcdef" for x in value)
    )


def qualification_blockers(payload: dict, seals: dict, *, now_ms: int) -> list[str]:
    """Deterministic validation of six individually scoped original costed OOS receipts."""
    from .pm_cwsa_six_paper import PORTFOLIO_CONFIGS

    problems: set[str] = set()
    if not isinstance(payload, dict) or payload.get("schema") != "cwsa_paper_k_qualification_v1":
        return ["K_QUALIFICATION_SCHEMA"]
    if payload.get("scope") != "PAPER_ONLY":
        problems.add("K_SCOPE_NOT_PAPER_ONLY")
    if payload.get("order_route") != "NONE" or payload.get("trading_authorized") is not False:
        problems.add("K_PAPER_ONLY_NO_TRADE_CONTRACT")
    if type(payload.get("known_at_ms")) is not int or payload["known_at_ms"] > now_ms:
        problems.add("K_EVIDENCE_FUTURE_KNOWLEDGE")
    if type(payload.get("effective_from_ms")) is not int or payload["effective_from_ms"] <= now_ms:
        problems.add("K_RELEASE_NOT_PROSPECTIVE")
    portfolio_records = payload.get("portfolios")
    if not isinstance(portfolio_records, dict) or set(portfolio_records) != set(PORTFOLIO_CONFIGS):
        return sorted(problems | {"K_SIX_PORTFOLIOS_NOT_COVERED"})
    for pid, cfg in PORTFOLIO_CONFIGS.items():
        row = portfolio_records[pid]
        if not isinstance(row, dict):
            problems.add(f"K_INVALID_RECORD:{pid}")
            continue
        if pid not in seals or row.get("seal_sha256") != seals[pid].get("definition_sha256"):
            problems.add(f"K_REGISTRY_SEAL_MISMATCH:{pid}")
        if row.get("qualification") != "QUALIFIED" or row.get("negative_findings"):
            problems.add(f"UNQUALIFIED_K:{pid}")
        if row.get("policy") != "ONE_SHOT_CHECKPOINT_V3":
            problems.add(f"K_POLICY_MISMATCH:{pid}")
        members = row.get("members")
        if not isinstance(members, dict) or set(members) != set(cfg["members"]):
            problems.add(f"K_MEMBER_COVERAGE_MISMATCH:{pid}")
            continue
        for alias, item in members.items():
            if not isinstance(item, dict):
                problems.add(f"K_BAD_MEMBER:{pid}/{alias}")
                continue
            try:
                k = Decimal(str(item["frozen_k"]))
                max_k = Decimal(str(item["risk_approved_max_k"]))
                if not (k.is_finite() and max_k.is_finite() and 0 < k <= max_k <= 10):
                    problems.add(f"K_RISK_LIMIT:{pid}/{alias}")
            except KeyError, InvalidOperation, TypeError:
                problems.add(f"K_INVALID_DECIMAL:{pid}/{alias}")
            if item.get("research_basis") != "POINT_IN_TIME" or item.get("oos_status") != "PASS":
                problems.add(f"K_NOT_PIT_OOS:{pid}/{alias}")
            if (
                item.get("original_cost_evidence") is not True
                or item.get("independent_market_evidence") is not True
            ):
                problems.add(f"K_MARKET_COST_UNVERIFIED:{pid}/{alias}")
            for name in (
                "track_c_report_sha256",
                "source_sha256",
                "market_sha256",
                "cost_sha256",
                "oos_report_sha256",
            ):
                if not _sha(item.get(name)):
                    problems.add(f"K_PROVENANCE_MISSING:{pid}/{alias}/{name}")
    return sorted(problems)


def read_qualification(path: Path, public_key_hex: str, seals: dict, source_db: Path) -> dict:
    """Verify external research signature, PIT/OOS/risk schema and source availability."""
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 2_000_000:
        raise ValueError("K_QUALIFICATION_PATH_UNSAFE")
    key = Ed25519PublicKey.from_public_bytes(bytes.fromhex(public_key_hex))
    envelope = json.loads(path.read_text())
    payload = verify_envelope(envelope, key, "cwsa-paper-k-research-only")
    problems = qualification_blockers(payload, seals, now_ms=int(time.time() * 1000))
    if not source_db.is_file():
        problems.append("K_ORIGINAL_SOURCE_JOURNAL_UNAVAILABLE")
    if problems:
        raise ValueError("K_QUALIFICATION_BLOCKED:" + ",".join(problems))
    return payload


def mandate_k_blockers(approved: dict, qualified: dict) -> list[str]:
    """Bind signed CopyMandate native k and activation to independently approved k."""
    problems = []
    members = qualified["portfolios"]
    for pid, bundle in approved.items():
        if pid not in members:
            problems.append("K_UNKNOWN_SIGNED_PORTFOLIO:" + pid)
            continue
        for mandate, _envelope in bundle.mandates:
            candidate = members[pid]["members"].get(mandate.source_id)
            if candidate is None:
                problems.append("K_MANDATE_SOURCE_NOT_QUALIFIED:" + pid)
                continue
            if mandate.k != Decimal(str(candidate["frozen_k"])):
                problems.append("K_SIGNED_MANDATE_VALUE_MISMATCH:" + pid + "/" + mandate.source_id)
            if mandate.effective_from_ms < qualified["effective_from_ms"]:
                problems.append(
                    "K_RELEASE_EFFECTIVE_BEFORE_RESEARCH:" + pid + "/" + mandate.source_id
                )
    return problems


def inspect_qualification(
    path: Path | None, public_key_hex: str | None, seals: dict, source_db: Path
):
    from .pm_cwsa_chapter2_gate import GateCheck

    if path is None or public_key_hex is None:
        return GateCheck(
            "frozen_k_qualification",
            "BLOCKED_EVIDENCE",
            "UNQUALIFIED_K:RESEARCH_ATTESTATION_AND_PINNED_PUBLIC_KEY_REQUIRED",
        )
    try:
        payload = read_qualification(path, public_key_hex, seals, source_db)
        return GateCheck(
            "frozen_k_qualification",
            "PASS",
            "INDEPENDENT_RESEARCH_SIGNATURE_AND_SIX_K_QUALIFIED",
            {
                "attestation_sha256": sha256(path.read_bytes()).hexdigest(),
                "effective_from_ms": payload["effective_from_ms"],
            },
        )
    except (ValueError, OSError, TypeError, KeyError) as exc:
        return GateCheck(
            "frozen_k_qualification", "FAIL", "K_QUALIFICATION_INVALID:" + type(exc).__name__
        )


def paper_candidate(seals: dict, *, now_ms: int | None = None) -> dict:
    """A review template is never a qualified release or signed mandate."""
    from .pm_cwsa_six_paper import PORTFOLIO_CONFIGS

    now_ms = now_ms or int(time.time() * 1000)
    return {
        "schema": "cwsa_paper_k_qualification_v1",
        "scope": "PAPER_ONLY",
        "order_route": "NONE",
        "known_at_ms": now_ms,
        "effective_from_ms": now_ms + 600_000,
        "portfolios": {
            pid: {
                "seal_sha256": seals[pid]["definition_sha256"],
                "qualification": "UNQUALIFIED_K",
                "negative_findings": ["ORIGINAL_OOS_COST_AND_RISK_APPROVAL_REQUIRED"],
                "policy": "ONE_SHOT_CHECKPOINT_V3",
                "members": {
                    alias: {
                        "frozen_k": None,
                        "risk_approved_max_k": None,
                        "research_basis": "UNKNOWN",
                        "oos_status": "UNQUALIFIED_K",
                        "original_cost_evidence": False,
                        "independent_market_evidence": False,
                        "track_c_report_sha256": None,
                        "source_sha256": None,
                        "market_sha256": None,
                        "cost_sha256": None,
                        "oos_report_sha256": None,
                    }
                    for alias in cfg["members"]
                },
            }
            for pid, cfg in PORTFOLIO_CONFIGS.items()
        },
        "trading_authorized": False,
    }
