"""Read-only SQLite exclusion guard for retrospective Vike research rankings."""

from __future__ import annotations

from contextlib import closing
from hashlib import sha256
import json
from pathlib import Path
import sqlite3

import pytest

from scripts.run_vike_retrospective_screen import (
    apply_research_screening,
    registry_exclusions,
    run,
)
from test_pm_v4_retrospective_k import fixture_retro


def registry_db(root: Path, *, account: str, exclude: bool) -> Path:
    path = root / "registry.sqlite3"
    with closing(sqlite3.connect(path)) as conn, conn:
        conn.executescript(
            "CREATE TABLE wallets(wallet_id INTEGER PRIMARY KEY,address TEXT);"
            "CREATE TABLE exclusions(wallet_id INTEGER,reason TEXT);"
            "CREATE TABLE propfirm_exclusions(address TEXT,reason TEXT);"
        )
        conn.execute("INSERT INTO wallets VALUES(1,?)", (account,))
        if exclude:
            conn.execute("INSERT INTO exclusions VALUES(1,'UNDERWATER_BAGHOLDER')")
            conn.execute(
                "INSERT INTO propfirm_exclusions VALUES(?,'UNDERWATER_BAGHOLDER')",
                (account,),
            )
    return path


def test_registry_exclusions_are_readonly_and_sha_bound(tmp_path):
    address = "0x" + "a" * 40
    db = registry_db(tmp_path, account=address, exclude=True)
    original = db.read_bytes()
    statuses, fingerprint = registry_exclusions(db)
    assert db.read_bytes() == original
    identity = sha256(address.encode()).hexdigest()
    assert statuses[identity] == [
        "owner:UNDERWATER_BAGHOLDER",
        "prop:UNDERWATER_BAGHOLDER",
    ]
    assert len(fingerprint) == 64
    assert registry_exclusions(db) == (statuses, fingerprint)


def test_registry_unavailable_must_not_silently_admit(tmp_path):
    with pytest.raises(FileNotFoundError):
        registry_exclusions(tmp_path / "missing.sqlite3")


@pytest.mark.parametrize("excluded", [True, False])
def test_run_seals_all_source_wallets_and_vetoes_current_exclusions(tmp_path, excluded):
    job, source, market, policy = fixture_retro(tmp_path)
    original = json.loads((source / "wallet_fills_90d" / "one.json").read_bytes())
    address = original["address"].lower()
    wallet = sha256(address.encode()).hexdigest()
    db = registry_db(tmp_path, account=address, exclude=excluded)
    before = db.read_bytes()
    output = tmp_path / "derived"
    output.mkdir()
    args = {
        "jobfile": job,
        "input_root": tmp_path,
        "source_root": source,
        "market_root": market,
        "cache_root": tmp_path / "cache",
        "output_root": output,
        "registry_db": db,
    }
    first = run(**args)
    second = run(**args)
    assert first["sha256"] == second["sha256"]
    assert db.read_bytes() == before
    report = json.loads(Path(first["path"]).read_bytes())
    assert report["order_route"] == "NONE"
    assert report["scientifically_qualified"] is False
    assert report["historical_signed_k_release"] is False
    selected = next(x for x in report["ranking"] if x["wallet_sha256"] == wallet)
    assert selected["base"]["estimated_complete_episodes"] == 1
    if excluded:
        assert selected["research_selection"] == "EXCLUDED_BY_CURRENT_REGISTRY"
        assert len(report["vetoed_positive_wallets"]) == 1
    else:
        assert selected["research_selection"] == "BELOW_SHORTLIST_OBSERVATION_FLOOR"
        assert report["vetoed_positive_wallets"] == []
    assert report["research_shortlist_wallet_sha256s"] == []
    assert report["sqlite_integrity"] == "VERIFIED_READ_ONLY"


def test_full_eligible_wallet_survives_and_no_auto_promotion():
    wallet = sha256(b"test-address").hexdigest()
    positive = {
        "wallet_sha256": wallet,
        "base": {"estimated_complete_episodes": 33, "estimated_net_pnl": 20.0},
        "evaluation_observation_days": 45,
    }
    excluded = {
        "wallet_sha256": sha256(b"excluded").hexdigest(),
        "base": {"estimated_complete_episodes": 50, "estimated_net_pnl": 1_000.0},
        "evaluation_observation_days": 50,
    }
    selected, blocked = apply_research_screening(
        [positive, excluded], {excluded["wallet_sha256"]: ["owner:UNDERWATER_BAGHOLDER"]}
    )
    assert selected == [positive]
    assert blocked == [excluded]
    assert positive["research_selection"] == "RESEARCH_SHORTLIST_ONLY_NO_ADMISSION"
    assert excluded["research_selection"] == "EXCLUDED_BY_CURRENT_REGISTRY"
