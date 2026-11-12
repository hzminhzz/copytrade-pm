"""Canonical source->PaperJournal bridge: complete original proofs and finance."""

from __future__ import annotations

from dataclasses import replace
from decimal import Decimal
from pathlib import Path
import sqlite3
from contextlib import closing

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from copytrade_pm.pm03_account import digest
from copytrade_pm.pm_cwsa_chapter2_mirror import (
    consume_canonical_paper,
    mirror_source,
)
from copytrade_pm.pm_checkpoint_journal import stream_key
from copytrade_pm.pm_forward_journal import PaperJournal
from copytrade_pm.production_manifest import sign
from test_checkpoint_paper import (
    BOUNDARY,
    BTC,
    GRID,
    checkpoint,
    quote,
    setup_paper,
)
from test_checkpoint_source import scope
from test_pm_forward_ccxt_market import ccxt_market
from test_pm_forward_journal import manifest


def source_and_follower(tmp_path: Path):
    source, sp, mandate, p = setup_paper(tmp_path / "source")
    follower = PaperJournal(tmp_path / "follower")
    fresh_manifest = manifest("p1", "fixture-account")
    allowed_rules = replace(fresh_manifest.rulebook, permitted=(BTC,), confirmed=True)
    follower.register(replace(fresh_manifest, rulebook=allowed_rules, policy_sha=digest(p)))
    key = Ed25519PrivateKey.generate()
    follower.activate_copy_mandate(
        sign(mandate.model_dump(mode="json"), key, "copy-mandate-v1"),
        key.public_key(),
        account_id="fixture-account",
        at_ms=BOUNDARY - 1,
    )
    return source, follower, sp, mandate, p


def test_mirror_original_source_and_consume_baseline_entry_and_restart(tmp_path):
    source, follower, sp, mandate, p = source_and_follower(tmp_path)
    stream = stream_key(scope(), sp.epoch)
    baseline = checkpoint(source, sp, 0)
    first = consume_canonical_paper(
        journal=follower,
        run_id="p1",
        owner=mandate.owner,
        outcome_id=baseline.outcome_id,
        source_db=source.path,
        quote_db=source.path,
        policy=p,
        catalog={"BTC/USDC:USDC": ccxt_market()},
        at_ms=BOUNDARY + 102,
    )
    assert first["status"] == "BASELINE"
    changed = checkpoint(source, sp, 1, "3")
    now = BOUNDARY + GRID + 102
    quote(source, now)
    second = consume_canonical_paper(
        journal=follower,
        run_id="p1",
        owner=mandate.owner,
        outcome_id=changed.outcome_id,
        source_db=source.path,
        quote_db=source.path,
        policy=p,
        catalog={"BTC/USDC:USDC": ccxt_market()},
        at_ms=now + 2,
    )
    assert second["status"] == "COMMITTED_ONCE"
    assert Decimal(follower.restore("p1")["account"]["costs"]) > 0
    assert mirror_source(source.path, follower, stream) == ()
    assert PaperJournal(follower.root).restore("p1") == follower.restore("p1")


def test_mirror_rejects_tampered_source_without_mutating_follower(tmp_path):
    source, follower, sp, _, _ = source_and_follower(tmp_path)
    stream = stream_key(scope(), sp.epoch)
    checkpoint(source, sp, 0)
    before = follower.restore("p1")
    with closing(sqlite3.connect(source.path)) as db, db:
        db.execute(
            "UPDATE cwsa_transitions SET sha=? WHERE stream=? AND seq=2",
            ("f" * 64, stream),
        )
    with pytest.raises(ValueError, match="CWSA_MIRROR_SOURCE_CHAIN"):
        mirror_source(source.path, follower, stream)
    assert follower.restore("p1") == before
    with closing(sqlite3.connect(follower.path)) as db:
        assert db.execute("SELECT COUNT(*) FROM cwsa_outcomes").fetchone()[0] == 0
