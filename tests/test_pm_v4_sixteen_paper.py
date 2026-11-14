"""V4 sixteen-campaign identity, sizing and no-trading guard regressions."""

from __future__ import annotations

from contextlib import closing
from hashlib import sha256
import json
from pathlib import Path
import sqlite3

import pytest

from copytrade_pm.pm_forward_observed_paper import ObservedP1Paper, PAPER_PROFILES
from copytrade_pm import pm_source_campaign_roster as scenarios


ORIGINALS = {
    "P1": ("S035-ENA", "S051-BTC", "S053-HYPE"),
    "P14": ("S035-ENA", "S051-BTC", "S053-HYPE", "S064-xyz:BRENTOIL", "Whale_0x5f94"),
    "P15": ("S035-ENA", "S051-BTC", "S053-HYPE", "S064-xyz:BRENTOIL", "Whale_0x5f94"),
    "P16": ("S035-ENA", "S051-BTC", "S053-HYPE", "Whale_0x5f94"),
    "E1": ("W016", "W080", "W083"),
    "E2": ("ACT04", "W083", "W080"),
    "E3": ("ACT04", "W083", "CM-002"),
    "E4": ("ACT04", "W083", "HL Perps Whale"),
    "E5": ("ACT04", "W083", "ACT08"),
    "E6": ("ACT04", "W083", "W080", "CM-002", "HL Perps Whale"),
    "E7": ("ACT04", "W083", "W080", "CM-002", "HL Perps Whale"),
    "E8": ("ACT04", "W083", "W080", "CM-002", "N051-HYPE"),
    "E9": ("ACT04", "W083", "W080", "CM-002", "ACT08"),
    "E10": ("ACT06", "ACT10", "ACT08"),
    "E11": ("W083", "ACT08", "ACT10", "W100", "W028"),
    "E12": ("ACT04", "W080", "CM-002", "W004", "VS005"),
}


def _sample(tmp_path: Path, monkeypatch):
    canonical = scenarios.CANONICAL
    all_names = sorted({canonical.get(a, a) for x in ORIGINALS.values() for a in x})
    addrs = {name: "0x" + f"{index:040x}" for index, name in enumerate(all_names, 1)}
    db = tmp_path / "registry.sqlite"
    with closing(sqlite3.connect(db)) as con:
        con.executescript(
            "CREATE TABLE wallets (wallet_id INTEGER PRIMARY KEY,address TEXT UNIQUE);"
            "CREATE TABLE wallet_aliases (alias TEXT,wallet_id INTEGER,known_at TEXT);"
            "CREATE TABLE exclusions (wallet_id INTEGER,known_at TEXT);"
            "CREATE TABLE propfirm_exclusions (wallet_id INTEGER,known_at TEXT);"
        )
        for index, name in enumerate(all_names, 1):
            con.execute("INSERT INTO wallets VALUES(?,?)", (index, addrs[name]))
        for alias in {name for values in ORIGINALS.values() for name in values}:
            name = canonical.get(alias, alias)
            if alias in ("W004", "N051-HYPE", "VS005"):
                continue  # Exist in current SQLite by address but have no alias.
            con.execute(
                "INSERT INTO wallet_aliases VALUES(?,?,?)",
                (alias, all_names.index(name) + 1, "2026-11-04T00:00:00+00:00"),
            )
        for name in ("S035", "S051", "S053", "S064", "Whale_0x5f94"):
            con.execute(
                "INSERT INTO wallet_aliases VALUES(?,?,?)",
                (name, all_names.index(name) + 1, "2026-11-04T00:00:00+00:00"),
            )
        con.execute(
            "INSERT INTO propfirm_exclusions VALUES(?,?)",
            (all_names.index("Whale_0x5f94") + 1, "2026-11-05T00:00:00+00:00"),
        )
        con.execute(
            "INSERT INTO propfirm_exclusions VALUES(?,?)",
            (all_names.index("CM-002") + 1, "2026-11-05T00:00:00+00:00"),
        )
        con.commit()
    rows = []
    for pid, originals in ORIGINALS.items():
        high_risk = pid in ("P15", "E7", "E8", "E9", "E11", "E12")
        budget = 1000 if high_risk else 600
        reason = {
            "P15": ["MISSING_ORIGINAL_P15_K_VALUES"],
            "E2": ["REPORT_P8_K_CONFLICT"],
            "E9": ["REPORT_P9_K_CONFLICT"],
            "E10": ["NO_STOPS_MTM_DAILY_BREACH"],
        }.get(pid, [])
        rows.append(
            {
                "portfolio_id": pid,
                "original_source_aliases": list(originals),
                "member_addresses": [addrs[canonical.get(x, x)] for x in originals],
                "total_nominal_pod_risk_usd": budget,
                "equal_nominal_pod_risk_usd": budget // len(originals),
                "blockers": reason,
                "k_factors_reported_100k": (
                    ",".join(f"{a}:0.47" for a in originals) if pid.startswith("E") else None
                ),
            }
        )
    document = {
        "schema": "gemini_source_preserving_eligibility_manifest_v1",
        "authority": "research registration only; no live/paper activation",
        "portfolios": rows,
    }
    raw = json.dumps(document, sort_keys=True).encode()
    manifest = tmp_path / "manifest.json"
    manifest.write_bytes(raw)
    manifest.chmod(0o600)
    sha = sha256(raw).hexdigest()
    monkeypatch.setattr(scenarios, "MANIFEST_SHA256", sha)
    return manifest, db, sha


def _load(manifest, db, sha):
    return scenarios.load_campaign(
        manifest=manifest,
        registry_db=db,
        expected_sha256=sha,
        at="2026-11-09T01:00:00+07:00",
    )


def test_sixteen_scenarios_share_14_canonical_accounts_and_isolated_risk(tmp_path, monkeypatch):
    manifest, db, sha = _sample(tmp_path, monkeypatch)
    campaign = _load(manifest, db, sha)
    assert set(campaign.profiles) == set(scenarios.IDENTITIES)
    assert len(campaign.parents) == 14
    assert campaign.profiles["P1"] == PAPER_PROFILES["P1"]
    assert campaign.profiles["P14"] == PAPER_PROFILES["P14"]
    assert campaign.profiles["P16"] == PAPER_PROFILES["P16"]
    assert campaign.profiles["E1"].k["S035"] == "0.047000000000"
    assert campaign.profiles["E2"].k == {
        "ACT04": "0.003740000000",
        "S053": "0.027490000000",
        "S051": "0.017470000000",
    }
    assert campaign.profiles["E9"].k["ACT08"] == "0.001194000000"
    assert campaign.profiles["E10"].k["ACT06"] == "0.023500000000"
    assert campaign.profiles["P15"].k["S035"] == "0.016900000000"
    assert campaign.profiles["P15"].nominal_risk == "600"
    assert campaign.profiles["E7"].nominal_risk == "600"
    assert campaign.profiles["E7"].risk == {
        "ACT04": "120",
        "S053": "120",
        "S051": "120",
        "CM-002": "120",
        "Whale_0x5f94": "120",
    }
    assert "MISSING_ORIGINAL_P15_K_VALUES" in campaign.flags["P15"]
    assert "HISTORICAL_1000_RISK_REDUCED_TO_600_FOR_PM04" in campaign.flags["P15"]
    assert "NO_STOPS_MTM_DAILY_BREACH" in campaign.flags["E10"]
    assert "PREEXISTING_EXCLUSION:CM-002" in campaign.flags["E3"]
    assert "PREEXISTING_EXCLUSION:Whale_0x5f94" in campaign.flags["P14"]
    assert campaign.seals["E2"]["selection_kind"].startswith("UNSIGNED_PROSPECTIVE")
    assert campaign.public_status()["order_route"] == "NONE"
    assert campaign.public_status()["scientifically_qualified"] is False


def test_sixteen_rejects_tamper_or_unmapped_wallet(tmp_path, monkeypatch):
    manifest, db, sha = _sample(tmp_path, monkeypatch)
    with pytest.raises(ValueError, match="UNREVIEWED_MANIFEST_SHA"):
        scenarios.load_campaign(
            manifest=manifest,
            registry_db=db,
            expected_sha256="0" * 64,
            at="2026-11-09T01:00:00+07:00",
        )
    manifest.write_bytes(manifest.read_bytes() + b" ")
    with pytest.raises(ValueError, match="MANIFEST_DRIFT"):
        _load(manifest, db, sha)


def test_sixteen_rejects_canonical_alias_identity_collision(tmp_path, monkeypatch):
    manifest, db, sha = _sample(tmp_path, monkeypatch)
    with closing(sqlite3.connect(db)) as con:
        con.execute("UPDATE wallet_aliases SET wallet_id=999 WHERE alias='W016'")
        con.commit()
    with pytest.raises(ValueError, match="ALIAS_CONFLICT"):
        _load(manifest, db, sha)


def test_paper_constructor_rejects_unsourced_external_profile(tmp_path, monkeypatch):
    manifest, db, sha = _sample(tmp_path, monkeypatch)
    campaign = _load(manifest, db, sha)
    with pytest.raises(ValueError, match="EXTERNAL_STUDY_NOT_VERIFIED"):
        ObservedP1Paper(
            source_db=tmp_path / "absent.sqlite",
            state_root=tmp_path / "run",
            run_id="e1",
            catalog={},
            registry_db=db,
            portfolio_id="E1",
            study_profile=campaign.profiles["E1"],
        )
