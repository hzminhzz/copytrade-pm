"""Acceptance and regression tests for scoped SQLite wallet/portfolio metadata discovery (#337)."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import closing, contextmanager, redirect_stdout
from datetime import UTC, datetime
from hashlib import sha256
import io
import json
import os
from pathlib import Path
import re
import sqlite3
import subprocess
import sys

import pytest

from copytrade_pm import pm_operations as ops
from copytrade_pm import wallet_registry as reg
from copytrade_pm import wallet_registry_catalog as cat
from copytrade_pm import wallet_registry_fp_journal as fp_journal
from copytrade_pm import wallet_registry_native as native
from copytrade_pm import wallet_registry_qualification as qualification
from copytrade_pm import wallet_registry_runs as runs
from copytrade_pm.dashboard.adapter import DashboardReader, SmallTTLCache
from test_wallet_registry_catalog import AFTER, BEFORE, WHALE, _v2_snapshot

LEGACY_AT = "2026-10-01T00:00:00+00:00"
LOCK_AT = "2026-11-05T01:00:00+00:00"
NATIVE_AT = "2026-11-06T02:00:00+00:00"
RAW_ADDRESS = re.compile(r"0x[0-9a-fA-F]{40}\b")


@pytest.fixture(autouse=True)
def _pin_synthetic_whale(monkeypatch: pytest.MonkeyPatch) -> None:
    """Bind synthetic test whale hash so offline fixtures never require private owner inputs."""
    monkeypatch.setattr(cat, "WHALE_ADDRESS_SHA256", sha256(WHALE.encode()).hexdigest())


def _call_cli(argv: list[str]) -> tuple[int, dict]:
    """Run copytrade-pm operations CLI in-process and parse its JSON response."""
    buf = io.StringIO()
    with redirect_stdout(buf):
        code = ops.cli(argv)
    return code, json.loads(buf.getvalue())


def _call_reg_cli(argv: list[str]) -> tuple[int, dict]:
    """Run wallet_registry CLI in-process and parse its JSON response."""
    buf = io.StringIO()
    with redirect_stdout(buf):
        code = reg.cli(argv)
    return code, json.loads(buf.getvalue())


def _locked_registry_db(
    tmp_path: Path, *, before_lock: Callable[[sqlite3.Connection], None] | None = None
) -> Path:
    """Create a 0600 locked SQLite fixture whose legacy import clock is intentionally >24h old."""
    tmp_path.chmod(0o700)
    db, snapshot = _v2_snapshot(tmp_path)
    reg.apply(db, snapshot, AFTER)
    with closing(reg.connect(db, True)) as con:
        with con:
            if before_lock is not None:
                before_lock(con)
            con.execute(
                "INSERT OR REPLACE INTO snapshot_meta(key, value) VALUES('observed_at', ?)",
                (LEGACY_AT,),
            )
    (tmp_path / "backups").mkdir(mode=0o700, exist_ok=True)
    expected_sha = reg.db_authority_health(db)["inventory_sha256"]
    native.lock_legacy_import(db, expected=expected_sha, apply=True, now=LOCK_AT)
    return db


@contextmanager
def _forbid_broad_and_finance_readers(
    monkeypatch: pytest.MonkeyPatch, *, allow_selection: bool = False
) -> Iterator[None]:
    """Fail fast if metadata queries call broad status, paper, journal, or science readers."""

    def _boom(name: str):
        def _fail(*_args, **_kwargs):
            raise AssertionError(f"forbidden broad/finance reader called: {name}")

        return _fail

    with monkeypatch.context() as mp:
        mp.setattr(reg, "db_status", _boom("wallet_registry.db_status"))
        mp.setattr(reg, "registered_paper_status", _boom("registered_paper_status"))
        mp.setattr(runs, "inspect_run", _boom("wallet_registry_runs.inspect_run"))
        mp.setattr(reg.paper_contract, "inspect_run", _boom("paper_contract.inspect_run"))
        mp.setattr(fp_journal, "inspect_fp_journal", _boom("inspect_fp_journal"))
        mp.setattr(qualification, "status", _boom("qualification_contract.status"))
        if not allow_selection:
            mp.setattr(cat, "list_selection", _boom("catalog.list_selection"))
        yield


def _register_pm_vike_100(db: Path, tmp_path: Path) -> Path:
    """Natively register SQLite-only cohort pm_vike_100 without legacy CSV/JSON files."""
    manifests = tmp_path / "manifests"
    manifests.mkdir(mode=0o700, exist_ok=True)
    manifest = manifests / "pm_vike_100.json"
    manifest.write_text(
        json.dumps(
            {
                "schema": "sqlite_wallet_import_v1",
                "cohort": "pm_vike_100",
                "wallets": [
                    {"address": "0x" + "91" * 20, "aliases": ["VIKE_001"]},
                    {"address": "0x" + "92" * 20, "aliases": []},
                ],
            }
        ),
        encoding="utf-8",
    )
    manifest.chmod(0o600)
    expected_sha = reg.db_authority_health(db)["inventory_sha256"]
    native.register_cohort(db, manifest, expected=expected_sha, apply=True, now=NATIVE_AT)
    return db


def test_raw_address_pattern_detects_leaked_addresses() -> None:
    """Confirm RAW_ADDRESS catches full hex addresses inside JSON while allowing aliases."""
    assert RAW_ADDRESS.search(json.dumps({"address": "0x" + "ab" * 20})) is not None
    assert RAW_ADDRESS.search(json.dumps({"alias": "Whale_0x5f94"})) is None


def test_slice1_metadata_cli_verified_without_broad_or_finance_readers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db = _locked_registry_db(tmp_path)
    expected_sha = reg.db_authority_health(db)["inventory_sha256"]

    with _forbid_broad_and_finance_readers(monkeypatch, allow_selection=False):
        for argv in (
            ["--db", str(db), "wallets", "list", "--query", "W083", "--asof", AFTER],
            ["--db", str(db), "wallets", "show", "W083", "--asof", AFTER],
            ["--db", str(db), "portfolios", "list", "--asof", AFTER],
            ["--db", str(db), "portfolios", "show", "E6", "--asof", AFTER],
            ["--db", str(db), "portfolios", "show", "q3/B", "--asof", AFTER],
        ):
            code, payload = _call_cli(argv)
            assert code == 0, (argv, payload)
            assert payload["status"] == "VERIFIED", (argv, payload)
            assert payload["source"]["sha256"] == expected_sha
            assert payload["source"]["observed_at"] == LOCK_AT
            assert not RAW_ADDRESS.search(json.dumps(payload["data"]))


def test_slice1_selection_dashboard_and_doctor_avoid_paper_readers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db = _locked_registry_db(tmp_path)
    expected_sha = reg.db_authority_health(db)["inventory_sha256"]

    with _forbid_broad_and_finance_readers(monkeypatch, allow_selection=True):
        code, current = _call_cli(["--db", str(db), "portfolios", "current", "--asof", AFTER])
        assert code == 0
        assert current["status"] == "VERIFIED"
        assert current["source"]["sha256"] == expected_sha
        assert current["source"]["observed_at"] == LOCK_AT

        app = DashboardReader(db=db, clock=lambda: datetime.now(UTC), cache=SmallTTLCache())
        found = app.wallets(query="W083", asof=AFTER, limit=1)
        assert found["status"] == "VERIFIED"
        assert found["data"]["total"] == 1
        assert found["data"]["addresses_redacted"] is True
        assert not RAW_ADDRESS.search(json.dumps(found["data"]))

        doc_code, doc_payload = _call_reg_cli(["--db", str(db), "doctor"])
        assert doc_code == 0
        assert doc_payload["database_integrity"] == "VERIFIED"
        assert doc_payload["research_selection_integrity"] == "VERIFIED"
        assert doc_payload["indexed_import_clock_freshness"] == "STALE"
        assert doc_payload["indexed_research_unique"] > 0

        ops_doc = ops._doctor(db)
        assert ops_doc["status"] == "VERIFIED"
        assert ops_doc["data"]["inventory_sha256"] == expected_sha


def test_slice2_wallet_namespace_collision_fail_closed_and_explicit_lookup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def _seed_collision(con: sqlite3.Connection) -> None:
        wallets = [
            r[0] for r in con.execute("SELECT wallet_id FROM wallets ORDER BY wallet_id LIMIT 2")
        ]
        assert len(wallets) == 2
        con.execute(
            "INSERT INTO wallet_aliases(namespace, alias, wallet_id, known_at) VALUES(?,?,?,?)",
            ("frozen_pm01", "COLLIDE_W", wallets[0], LOCK_AT),
        )
        con.execute(
            "INSERT INTO wallet_aliases(namespace, alias, wallet_id, known_at) VALUES(?,?,?,?)",
            ("sqlite_primary", "COLLIDE_W", wallets[1], NATIVE_AT),
        )

    db = _locked_registry_db(tmp_path, before_lock=_seed_collision)

    with _forbid_broad_and_finance_readers(monkeypatch, allow_selection=False):
        ambiguous_code, ambiguous = _call_cli(["--db", str(db), "wallets", "show", "COLLIDE_W"])
        assert ambiguous_code == 2
        assert ambiguous["status"] == "UNKNOWN"
        assert ambiguous["error_code"] == "REGISTRY_READ_FAILED"

        code_frozen, frozen = _call_cli(
            [
                "--db",
                str(db),
                "wallets",
                "show",
                "COLLIDE_W",
                "--namespace",
                "frozen_pm01",
                "--asof",
                LOCK_AT,
            ]
        )
        assert code_frozen == 0 and frozen["status"] == "VERIFIED"
        assert frozen["data"]["found"] is True

        code_early, early = _call_cli(
            [
                "--db",
                str(db),
                "wallets",
                "show",
                "COLLIDE_W",
                "--namespace",
                "sqlite_primary",
                "--asof",
                LOCK_AT,
            ]
        )
        assert code_early == 0 and early["status"] == "NOT_REGISTERED_AT_ASOF"
        assert early["data"]["found"] is False

        code_native, native_hit = _call_cli(
            [
                "--db",
                str(db),
                "wallets",
                "show",
                "COLLIDE_W",
                "--namespace",
                "sqlite_primary",
                "--asof",
                NATIVE_AT,
            ]
        )
        assert code_native == 0 and native_hit["status"] == "VERIFIED"
        assert native_hit["data"]["found"] is True

        reg_code, reg_hit = _call_reg_cli(
            [
                "--db",
                str(db),
                "wallet",
                "--alias",
                "COLLIDE_W",
                "--namespace",
                "sqlite_primary",
                "--asof",
                NATIVE_AT,
            ]
        )
        assert reg_code == 0 and reg_hit["found"] is True


def test_slice2_portfolio_namespace_collision_and_disambiguation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db = _locked_registry_db(tmp_path)

    with _forbid_broad_and_finance_readers(monkeypatch, allow_selection=False):
        p_amb_code, p_amb = _call_cli(
            ["--db", str(db), "portfolios", "show", "B", "--asof", NATIVE_AT]
        )
        assert p_amb_code == 2
        assert p_amb["status"] == "UNKNOWN"
        assert p_amb["error_code"] == "REGISTRY_READ_FAILED"

        p1_code, p1 = _call_cli(
            ["--db", str(db), "portfolios", "show", "q3/B", "--asof", NATIVE_AT]
        )
        p2_code, p2 = _call_cli(
            ["--db", str(db), "portfolios", "show", "gemini.phase5/B", "--asof", NATIVE_AT]
        )
        assert p1_code == 0 and p1["status"] == "VERIFIED"
        assert p2_code == 0 and p2["status"] == "VERIFIED"
        assert set(p1["data"]) == {"B"}
        assert set(p2["data"]) == {"gemini.phase5/B"}


def test_slice3_unlocked_legacy_aged_clock_is_verified_and_preserves_lineage(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    tmp_path.chmod(0o700)
    db, snapshot = _v2_snapshot(tmp_path)
    reg.apply(db, snapshot, AFTER)
    with closing(reg.connect(db, True)) as con:
        with con:
            con.execute(
                "INSERT OR REPLACE INTO snapshot_meta(key, value) VALUES('observed_at', ?)",
                (LEGACY_AT,),
            )

    with _forbid_broad_and_finance_readers(monkeypatch, allow_selection=False):
        code, payload = _call_cli(["--db", str(db), "wallets", "list", "--query", "W083"])
        assert code == 0
        assert payload["status"] == "VERIFIED"
        assert payload["source"]["observed_at"] == LEGACY_AT
        assert not RAW_ADDRESS.search(json.dumps(payload["data"]))


def test_slice3_sqlite_only_cohort_pm_vike_100_asof_and_dashboard_parity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db = _register_pm_vike_100(_locked_registry_db(tmp_path), tmp_path)
    expected_health = reg.db_authority_health(db)
    expected_sha = expected_health["inventory_sha256"]
    assert expected_health["last_legacy_import_observed_at"] == LEGACY_AT
    assert expected_health["legacy_import_locked_at"] == LOCK_AT
    assert expected_health["sqlite_native_updated_at"] == NATIVE_AT
    assert expected_health["observed_at"] == NATIVE_AT
    assert expected_health["research_cohorts"]["pm_vike_100"] == 2
    assert expected_health["scientifically_qualified"] is False
    assert expected_health["trading_authorized"] is False

    with _forbid_broad_and_finance_readers(monkeypatch, allow_selection=False):
        early_list_code, early_list = _call_cli(
            ["--db", str(db), "wallets", "list", "--cohort", "pm_vike_100", "--asof", LOCK_AT]
        )
        assert early_list_code == 0 and early_list["status"] == "VERIFIED"
        assert early_list["data"]["total"] == 0

        early_show_code, early_show = _call_cli(
            [
                "--db",
                str(db),
                "wallets",
                "show",
                "VIKE_001",
                "--namespace",
                "sqlite_primary",
                "--asof",
                LOCK_AT,
            ]
        )
        assert early_show_code == 0 and early_show["status"] == "NOT_REGISTERED_AT_ASOF"

        vike_code, vike_list = _call_cli(
            ["--db", str(db), "wallets", "list", "--cohort", "pm_vike_100", "--asof", NATIVE_AT]
        )
        assert vike_code == 0 and vike_list["status"] == "VERIFIED"
        assert vike_list["source"]["sha256"] == expected_sha
        assert vike_list["source"]["observed_at"] == NATIVE_AT
        assert vike_list["data"]["total"] == 2
        assert all("pm_vike_100" in row["cohorts"] for row in vike_list["data"]["wallets"])
        assert not RAW_ADDRESS.search(json.dumps(vike_list["data"]))

        for ns_args in ([], ["--namespace", "sqlite_primary"]):
            show_code, show_vike = _call_cli(
                ["--db", str(db), "wallets", "show", "VIKE_001", *ns_args, "--asof", NATIVE_AT]
            )
            assert show_code == 0 and show_vike["status"] == "VERIFIED"
            assert show_vike["source"]["observed_at"] == NATIVE_AT
            assert show_vike["data"]["cohorts"] == ["pm_vike_100"]
            assert show_vike["data"]["authorized"] is False

        cohort_code, cohort_info = _call_reg_cli(["--db", str(db), "cohort", "pm_vike_100"])
        assert cohort_code == 0 and cohort_info["registered"] is True
        assert cohort_info["count"] == 2
        assert cohort_info["scientifically_qualified"] is False
        assert cohort_info["trading_authorized"] is False

    with _forbid_broad_and_finance_readers(monkeypatch, allow_selection=True):
        dash = DashboardReader(db=db, clock=lambda: datetime.now(UTC), cache=SmallTTLCache())
        dash_vike = dash.wallets(cohort="pm_vike_100", asof=NATIVE_AT)
        assert dash_vike["status"] == "VERIFIED"
        assert dash_vike["data"]["total"] == 2
        assert not RAW_ADDRESS.search(json.dumps(dash_vike["data"]))


def test_slice3_missing_and_corrupt_db_distinct_from_not_registered_at_asof(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db = _locked_registry_db(tmp_path)
    with _forbid_broad_and_finance_readers(monkeypatch, allow_selection=True):
        for argv in (
            ["--db", str(db), "wallets", "show", "W083", "--asof", BEFORE],
            ["--db", str(db), "portfolios", "current", "--asof", BEFORE],
            ["--db", str(db), "portfolios", "show", "E6", "--asof", BEFORE],
        ):
            code, payload = _call_cli(argv)
            assert code == 0, (argv, payload)
            assert payload["status"] == "NOT_REGISTERED_AT_ASOF", (argv, payload)
            assert payload["error_code"] is None
            dumped = json.dumps(payload["data"]).lower()
            assert '"authorized": true' not in dumped
            assert '"pnl"' not in dumped

        missing = tmp_path / "missing.sqlite"
        corrupt = tmp_path / "corrupt.sqlite"
        corrupt.write_text("not-a-sqlite-database", encoding="utf-8")
        os.chmod(corrupt, 0o600)

        for bad_db in (missing, corrupt):
            for argv, expected_error in (
                (["--db", str(bad_db), "wallets", "list"], "WALLET_INVENTORY_READ_FAILED"),
                (["--db", str(bad_db), "wallets", "show", "W083"], "REGISTRY_READ_FAILED"),
                (["--db", str(bad_db), "portfolios", "list"], "REGISTRY_READ_FAILED"),
                (["--db", str(bad_db), "portfolios", "current"], "REGISTRY_READ_FAILED"),
                (["--db", str(bad_db), "portfolios", "show", "E6"], "REGISTRY_READ_FAILED"),
            ):
                code, payload = _call_cli(argv)
                assert code == 2, (bad_db, argv, payload)
                assert payload["status"] == "UNKNOWN"
                assert payload["error_code"] == expected_error


def test_slice3_doctor_preserves_blocked_selection_exit_2_without_paper_reads(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db = _locked_registry_db(
        tmp_path,
        before_lock=lambda con: con.execute(
            "UPDATE research_selections SET source_sha256=?", ("a" * 64,)
        ),
    )

    with _forbid_broad_and_finance_readers(monkeypatch, allow_selection=True):
        code, report = _call_reg_cli(["--db", str(db), "doctor"])
        assert code == 2
        assert report["database_integrity"] == "VERIFIED"
        assert report["research_selection_integrity"] == "BLOCKED_MISSING_EXTERNAL_PROOF"
        assert report["indexed_import_clock_freshness"] == "STALE"
        assert report["trading_authorized"] is False
        assert report["scientifically_qualified"] is False


def test_slice3_unmocked_subprocess_cli_verified(tmp_path: Path) -> None:
    db = _register_pm_vike_100(_locked_registry_db(tmp_path), tmp_path)

    for subcmd in (
        ["wallets", "list", "--cohort", "pm_vike_100", "--asof", NATIVE_AT],
        ["wallets", "show", "VIKE_001", "--namespace", "sqlite_primary", "--asof", NATIVE_AT],
        ["portfolios", "list", "--asof", NATIVE_AT],
        ["portfolios", "current", "--asof", NATIVE_AT],
        ["portfolios", "show", "q3/B", "--asof", NATIVE_AT],
    ):
        proc = subprocess.run(
            [sys.executable, "-m", "copytrade_pm.pm_operations", "--db", str(db), *subcmd],
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
        )
        assert proc.returncode == 0, proc.stderr
        parsed = json.loads(proc.stdout)
        assert parsed["status"] == "VERIFIED", (subcmd, parsed)
        assert parsed["source"]["observed_at"] == NATIVE_AT
        assert not RAW_ADDRESS.search(json.dumps(parsed["data"]))

    cap_proc = subprocess.run(
        [sys.executable, "-m", "copytrade_pm.pm_operations", "capabilities", "validate"],
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    assert cap_proc.returncode == 0, cap_proc.stderr
    assert json.loads(cap_proc.stdout)["status"] == "VERIFIED"
