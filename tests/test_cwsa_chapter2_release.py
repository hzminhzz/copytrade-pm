"""Signed-approval admission for Chapter 2: no self-issued k or retroactive promotion."""

from __future__ import annotations

from dataclasses import replace
from decimal import Decimal
from hashlib import sha256
import json
from pathlib import Path
from time import time_ns

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
import pytest

from copytrade_pm.pm03_account import digest
from copytrade_pm.pm03_rules import propr_rulebook
from copytrade_pm.pm_cwsa_chapter2_release import read_activation_bundle
from copytrade_pm.pm_cwsa_six_paper import (
    EPOCH_ID,
    PORTFOLIO_CONFIGS,
    Chapter2PaperSupervisor,
    load_registry_seals,
)
from copytrade_pm.pm_forward_journal import PaperJournal
from copytrade_pm.production_manifest import sign
from test_checkpoint_journal import register, sample
from test_checkpoint_paper import BTC, GRID, policy, quote
from test_checkpoint_source import BOUNDARY, scope
from test_pm_forward_ccxt_market import ccxt_market
from test_copy_mandates import mandate

REGISTRY = Path("/home/quant/.local/share/copytrade/registry/wallet_registry.sqlite")


def source_address(alias: str) -> str:
    return "0x" + sha256(alias.encode()).hexdigest()[:40]


def signed_a(tmp_path, *, anchor_ms: int | None = None):
    source = PaperJournal(tmp_path / "source")
    cp = register(source)
    members = PORTFOLIO_CONFIGS["A"]["members"]
    seals = load_registry_seals(REGISTRY)
    p = policy()
    r = replace(
        propr_rulebook(
            "classic_1step",
            "evaluation",
            PORTFOLIO_CONFIGS["A"]["starting_balance"],
            observed_at=seals["A"]["selection_known_at"],
        ),
        permitted=(BTC,),
        confirmed=True,
    )
    key = Ed25519PrivateKey.generate()
    now = time_ns() // 1_000_000 if anchor_ms is None else anchor_ms
    future_offset = 60_000 if anchor_ms is None else 0
    signed = []
    for alias in members:
        sc = scope().model_copy(
            update={
                "source_id": alias,
                "account_sha": sha256(source_address(alias).encode()).hexdigest(),
            }
        )
        source.register_checkpoint_source(sc, cp, first_checkpoint_ms=BOUNDARY, at_ms=BOUNDARY - 1)
        m = mandate().model_copy(
            update={
                "mandate_id": "a-" + alias,
                "generation": 1,
                "source_id": alias,
                "source_account_sha": sc.account_sha,
                "source_scope_generation": sc.generation,
                "account_id": "acct_a_" + EPOCH_ID,
                "pod_id": alias,
                "k": Decimal("0.01"),
                "allowed_markets": (BTC.key,),
                "policy_epoch": cp.epoch,
                "risk_policy_sha": digest(p),
                "rulebook_sha": r.sha,
                "effective_from_ms": now + future_offset,
                "effective_until_ms": now + 24 * 3600_000,
            }
        )
        signed.append(sign(m.model_dump(mode="json"), key, "copy-mandate-v1"))
    bundle = {
        "schema": "cwsa_chapter2_paper_release_v1",
        "epoch": EPOCH_ID,
        "portfolios": {
            "A": {
                "seal_sha": seals["A"]["definition_sha256"],
                "policy": p,
                "catalog": {"BTC/USDC:USDC": ccxt_market()},
                "mandates": signed,
            }
        },
    }
    original = json.dumps(bundle, separators=(",", ":"), sort_keys=True).encode()
    path = tmp_path / "approved.json"
    path.write_bytes(original)
    return (
        path,
        sha256(original).hexdigest(),
        key.public_key().public_bytes_raw().hex(),
        source.path,
    )


def test_external_signature_sha_and_complete_membership_required(tmp_path):
    path, sha, pub, source = signed_a(tmp_path)
    seals = load_registry_seals(REGISTRY)
    approved = read_activation_bundle(
        path=path,
        expected_sha256=sha,
        trusted_authority_hex=pub,
        seals=seals,
        configs=PORTFOLIO_CONFIGS,
        run_label=EPOCH_ID,
        source_db=source,
    )
    assert set(approved) == {"A"}
    assert len(approved["A"].mandates) == 3
    assert {m.source_id for m, _ in approved["A"].mandates} == set(
        PORTFOLIO_CONFIGS["A"]["members"]
    )
    with pytest.raises(ValueError, match="SHA_MISMATCH"):
        read_activation_bundle(
            path=path,
            expected_sha256="0" * 64,
            trusted_authority_hex=pub,
            seals=seals,
            configs=PORTFOLIO_CONFIGS,
            run_label=EPOCH_ID,
            source_db=source,
        )
    with pytest.raises(ValueError):
        read_activation_bundle(
            path=path,
            expected_sha256=sha,
            trusted_authority_hex="a" * 64,
            seals=seals,
            configs=PORTFOLIO_CONFIGS,
            run_label=EPOCH_ID,
            source_db=source,
        )


def test_legacy_provisional_cannot_be_promoted_to_approved_finance(tmp_path):
    path, sha, pub, source = signed_a(tmp_path)
    state = tmp_path / "six"
    initial = Chapter2PaperSupervisor(
        state_root=state,
        source_db=source,
        registry_db=REGISTRY,
        publication_grace_override_ms=180_000,
    )
    assert not initial.approved
    with pytest.raises(ValueError, match="CHAPTER2_FINANCIAL_RELEASE_DRIFT"):
        Chapter2PaperSupervisor(
            state_root=state,
            source_db=source,
            registry_db=REGISTRY,
            approval_path=path,
            approval_sha256=sha,
            trusted_authority_hex=pub,
            quote_db=source,
            publication_grace_override_ms=180_000,
        )
    fresh = Chapter2PaperSupervisor(
        state_root=tmp_path / "approved-new-epoch",
        source_db=source,
        registry_db=REGISTRY,
        approval_path=path,
        approval_sha256=sha,
        trusted_authority_hex=pub,
        quote_db=source,
        publication_grace_override_ms=180_000,
    )
    assert set(fresh.approved) == {"A"}
    assert fresh.journals["A"].restore("A")["cursor"] == 0
    for m, _ in fresh.approved["A"].mandates:
        assert fresh.journals["A"].copy_mandate_state(m.owner).phase == "AWAITING_BASELINE"


def test_signed_three_wallet_portfolio_runs_pm03_entry_and_restart(tmp_path):
    path, sha, pub, source_db = signed_a(tmp_path, anchor_ms=BOUNDARY)
    source = PaperJournal(source_db.parent)
    approved_root = tmp_path / "prospective"
    settings = dict(
        state_root=approved_root,
        source_db=source_db,
        registry_db=REGISTRY,
        approval_path=path,
        approval_sha256=sha,
        trusted_authority_hex=pub,
        quote_db=source_db,
        publication_grace_override_ms=5000,
    )
    paper = Chapter2PaperSupervisor(**settings, activation_now_ms=BOUNDARY - 1)
    members = PORTFOLIO_CONFIGS["A"]["members"]
    assert len(paper.approved["A"].mandates) == 3

    def source_wave(ms: int, *, changed: bool):
        for alias in members:
            sc = scope().model_copy(
                update={
                    "source_id": alias,
                    "account_sha": sha256(source_address(alias).encode()).hexdigest(),
                }
            )
            original = sample(
                source,
                ms,
                "3" if changed and alias == "W028" else "2",
                source_scope=sc,
                address=source_address(alias),
            )
            outcome = source.append_checkpoint_sample(
                paper.approved["A"].mandates[0][0].policy_epoch,
                original,
                ms + 101,
            )
            expected = (
                "CHANGED" if changed and alias == "W028" else "UNCHANGED" if changed else "BASELINE"
            )
            assert outcome.kind == expected

    source_wave(BOUNDARY, changed=False)
    assert paper.poll_once(now_ms=BOUNDARY + 102) == 1
    a = paper.journals["A"].restore("A")
    assert a["cursor"] == 3
    assert not a["account"]["quantities"]
    for m, _ in paper.approved["A"].mandates:
        assert paper.journals["A"].copy_mandate_state(m.owner).phase == "ACTIVE"

    source_wave(BOUNDARY + GRID, changed=True)
    quote(source, BOUNDARY + GRID + 102)
    # Prior wave ages to a gap for unrelated portfolios while A advances independently.
    assert paper.poll_once(now_ms=BOUNDARY + GRID + 105) == 2
    a = paper.journals["A"].restore("A")
    assert a["cursor"] > 3
    assert Decimal(a["account"]["costs"]) > 0
    assert Decimal(a["account"]["quantities"][BTC.key]) > 0
    assert paper.poll_once(now_ms=BOUNDARY + GRID + 106) == 0
    reopened = Chapter2PaperSupervisor(**settings, activation_now_ms=BOUNDARY + GRID + 106)
    assert reopened.poll_once(now_ms=BOUNDARY + GRID + 107) == 0
    assert reopened.journals["A"].restore("A") == a
