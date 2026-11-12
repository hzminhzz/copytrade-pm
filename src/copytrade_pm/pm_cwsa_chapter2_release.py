"""Strict opt-in, externally signed Chapter 2 virtual-paper activation bundle.

A SQLite portfolio seal proves membership, not k, risk or paper authorization.
This module never signs mandates or invents missing coefficients.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from hashlib import sha256
import json
from pathlib import Path
from contextlib import closing
import sqlite3

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from .pm03_account import Instrument, Rulebook, digest
from .pm03_rules import propr_rulebook
from .pm_checkpoint_journal import CwsaPolicy
from .pm_checkpoint_paper import _policy
from .pm_checkpoint_source import CheckpointScope
from .pm_copy_mandate import CopyMandate, verify_mandate


@dataclass(frozen=True)
class ApprovedPortfolio:
    policy: dict
    catalog: dict
    mandates: tuple[tuple[CopyMandate, dict], ...]
    rulebook: Rulebook
    trusted_authority: Ed25519PublicKey


def read_activation_bundle(
    *,
    path: Path | None,
    expected_sha256: str | None,
    trusted_authority_hex: str | None,
    seals: dict,
    configs: dict,
    run_label: str,
    source_db: Path,
) -> dict[str, ApprovedPortfolio]:
    """Require a SHA-pinned release and independently supplied public authority."""
    if path is None and expected_sha256 is None and trusted_authority_hex is None:
        return {}
    if path is None or expected_sha256 is None or trusted_authority_hex is None:
        raise ValueError("CHAPTER2_INCOMPLETE_RELEASE_BINDING")
    if path.is_symlink() or not path.is_file():
        raise ValueError("CHAPTER2_APPROVAL_BUNDLE_NOT_FOUND")
    raw = path.read_bytes()
    if sha256(raw).hexdigest() != expected_sha256:
        raise ValueError("CHAPTER2_APPROVAL_BUNDLE_SHA_MISMATCH")
    try:
        key = Ed25519PublicKey.from_public_bytes(bytes.fromhex(trusted_authority_hex))
        release = json.loads(raw)
    except (ValueError, TypeError, json.JSONDecodeError) as exc:
        raise ValueError("CHAPTER2_APPROVAL_BUNDLE_INVALID") from exc
    if (
        not isinstance(release, dict)
        or set(release) != {"schema", "epoch", "portfolios"}
        or release["schema"] != "cwsa_chapter2_paper_release_v1"
        or release["epoch"] != run_label
        or not isinstance(release["portfolios"], dict)
        or not release["portfolios"]
        or set(release["portfolios"]) - set(configs)
    ):
        raise ValueError("CHAPTER2_APPROVAL_BUNDLE_SCHEMA")
    with closing(sqlite3.connect(f"file:{source_db.resolve()}?mode=ro", uri=True)) as db:
        scopes = {}
        for raw_scope, raw_policy in db.execute("SELECT scope,policy FROM cwsa_heads"):
            scope = CheckpointScope.model_validate_json(raw_scope)
            policy = CwsaPolicy.model_validate_json(raw_policy)
            if scope.source_id in scopes:
                raise ValueError("CHAPTER2_SOURCE_SCOPE_AMBIGUOUS")
            scopes[scope.source_id] = (scope, policy.epoch)
    approved = {}
    for pid, item in release["portfolios"].items():
        if (
            not isinstance(item, dict)
            or set(item) != {"seal_sha", "policy", "catalog", "mandates"}
            or item["seal_sha"] != seals[pid]["definition_sha256"]
            or not isinstance(item["catalog"], dict)
            or not item["catalog"]
            or not isinstance(item["mandates"], list)
        ):
            raise ValueError("CHAPTER2_PORTFOLIO_APPROVAL_SCHEMA")
        risk_policy = item["policy"]
        _policy(risk_policy)
        allowed: set[Instrument] = set()
        mandates = []
        member_ids = set(configs[pid]["members"])
        members_seen: set[str] = set()
        account_id = f"acct_{configs[pid]['folder'].lower()}_{run_label}"
        for envelope in item["mandates"]:
            m = verify_mandate(envelope, key, account_id=account_id)
            if (
                m.source_id not in member_ids
                or m.source_id in members_seen
                or m.pod_id != m.source_id
                or m.source_id not in scopes
                or m.policy_epoch != scopes[m.source_id][1]
                or m.source_account_sha != scopes[m.source_id][0].account_sha
                or m.source_scope_generation != scopes[m.source_id][0].generation
                or m.risk_policy_sha != digest(risk_policy)
            ):
                raise ValueError("CHAPTER2_SIGNED_MANDATE_SOURCE_POLICY_MISMATCH")
            allowed.update(Instrument.parse(market) for market in m.allowed_markets)
            members_seen.add(m.source_id)
            mandates.append((m, envelope))
        if members_seen != member_ids or len(mandates) != len(member_ids):
            raise ValueError("CHAPTER2_INCOMPLETE_SIGNED_MANDATES")
        base = propr_rulebook(
            "classic_1step",
            "evaluation",
            configs[pid]["starting_balance"],
            observed_at=seals[pid]["selection_known_at"],
        )
        rulebook = replace(
            base, permitted=tuple(sorted(allowed, key=lambda x: x.key)), confirmed=True
        )
        if any(m.rulebook_sha != rulebook.sha for m, _ in mandates):
            raise ValueError("CHAPTER2_SIGNED_MANDATE_RULEBOOK_DRIFT")
        approved[pid] = ApprovedPortfolio(
            policy=risk_policy,
            catalog=item["catalog"],
            mandates=tuple(mandates),
            rulebook=rulebook,
            trusted_authority=key,
        )
    return approved


class FinanceScan:
    """Durable, owner-local nonfinancial cursor for unchanged source checkpoints."""

    def __init__(self, journal) -> None:
        self.journal = journal
        with journal._writer() as db:
            db.execute(
                "CREATE TABLE IF NOT EXISTS chapter2_finance_scan ("
                "owner TEXT PRIMARY KEY,checkpoint_ms INTEGER NOT NULL,"
                "outcome_id TEXT NOT NULL,receipt_sha TEXT NOT NULL)"
            )

    def current(self, owner: str, *, effective_from_ms: int) -> int:
        with closing(sqlite3.connect(f"file:{self.journal.path}?mode=ro", uri=True)) as db:
            row = db.execute(
                "SELECT checkpoint_ms,outcome_id,receipt_sha FROM chapter2_finance_scan "
                "WHERE owner=?",
                (owner,),
            ).fetchone()
        if row is None:
            return effective_from_ms - 1
        checkpoint_ms, outcome_id, sha = row
        if sha != digest(["chapter2_finance_scan_v1", owner, checkpoint_ms, outcome_id]):
            raise ValueError("CHAPTER2_FINANCE_SCAN_TAMPERED")
        return checkpoint_ms

    def advance(self, owner: str, checkpoint_ms: int, outcome_id: str) -> None:
        sha = digest(["chapter2_finance_scan_v1", owner, checkpoint_ms, outcome_id])
        with self.journal._writer() as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                row = db.execute(
                    "SELECT checkpoint_ms,outcome_id,receipt_sha FROM chapter2_finance_scan "
                    "WHERE owner=?",
                    (owner,),
                ).fetchone()
                if row is not None and (
                    row[2] != digest(["chapter2_finance_scan_v1", owner, row[0], row[1]])
                    or checkpoint_ms < row[0]
                    or (checkpoint_ms == row[0] and outcome_id != row[1])
                ):
                    raise ValueError("CHAPTER2_FINANCE_SCAN_REORDER")
                if row is None:
                    db.execute(
                        "INSERT INTO chapter2_finance_scan VALUES (?,?,?,?)",
                        (owner, checkpoint_ms, outcome_id, sha),
                    )
                elif checkpoint_ms > row[0]:
                    db.execute(
                        "UPDATE chapter2_finance_scan SET checkpoint_ms=?,outcome_id=?,"
                        "receipt_sha=? WHERE owner=?",
                        (checkpoint_ms, outcome_id, sha, owner),
                    )
                db.execute("COMMIT")
            except BaseException:
                db.execute("ROLLBACK")
                raise
