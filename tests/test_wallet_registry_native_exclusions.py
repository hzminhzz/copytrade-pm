"""Native exclusion decisions are immutable owner-private metadata, never trading approval."""

from __future__ import annotations

from contextlib import closing
from hashlib import sha256
import json
from pathlib import Path

import pytest

from copytrade_pm import pm_capabilities, wallet_registry as registry
from copytrade_pm import wallet_registry_catalog as catalog
from copytrade_pm import wallet_registry_native as native
from test_wallet_registry import address
from test_wallet_registry_native import NOW, seed


def decision_file(tmp_path: Path, decisions: list[dict] | None = None) -> tuple[Path, str]:
    directory = tmp_path / "private_decisions"
    directory.mkdir(mode=0o700, exist_ok=True)
    path = directory / "decision.json"
    path.write_text(
        json.dumps(
            {
                "schema": "sqlite_wallet_exclusions_v1",
                "decisions": decisions
                if decisions is not None
                else [{"address": address(2), "reason_code": "OWNER_REJECTED"}],
            }
        ),
        encoding="utf-8",
    )
    path.chmod(0o600)
    return path, sha256(path.read_bytes()).hexdigest()


def locked_seed(tmp_path: Path) -> tuple[Path, str]:
    db, _, baseline = seed(tmp_path)
    result = native.lock_legacy_import(db, expected=baseline, apply=True, now=NOW)
    return db, result["inventory_sha256"]


def test_append_exclusions_preserves_history_and_asof_without_leaking_address(
    tmp_path: Path,
) -> None:
    db, baseline = locked_seed(tmp_path)
    manifest, source_sha = decision_file(tmp_path)
    with closing(registry.connect(db, False)) as con:
        wid = con.execute(
            "SELECT wallet_id FROM wallets WHERE address=?", (address(2),)
        ).fetchone()[0]
        previous_monitoring = con.execute("SELECT * FROM monitoring ORDER BY wallet_id").fetchall()
        previous_portfolios = con.execute("SELECT * FROM portfolio_memberships").fetchall()
        previous_paper = con.execute("SELECT * FROM portfolio_runs").fetchall()
    preview = native.append_exclusions(
        db, manifest, expected=baseline, expected_manifest_sha=source_sha, now=NOW
    )
    assert preview["applied"] is False
    assert preview["would_append_only"] is True
    assert preview["exclusion_count"] == 1
    assert registry.db_authority_health(db)["inventory_sha256"] == baseline
    assert address(2) not in json.dumps(preview)

    applied = native.append_exclusions(
        db,
        manifest,
        expected=baseline,
        expected_manifest_sha=source_sha,
        apply=True,
        now=NOW,
    )
    assert applied["backup_verified"] is True
    assert applied["trading_authorized"] is False
    assert applied["inventory_sha256"] != baseline
    assert address(2) not in json.dumps(applied)
    archive = db.parent / "evidence" / "native-exclusions" / f"{source_sha}.json"
    assert sha256(archive.read_bytes()).hexdigest() == source_sha
    assert archive.stat().st_mode & 0o777 == 0o600
    with closing(registry.connect(Path(applied["backup"]), False)) as con:
        assert con.execute("SELECT COUNT(*) FROM exclusions").fetchone()[0] == 1
        assert con.execute("PRAGMA foreign_key_check").fetchall() == []
    with closing(registry.connect(db, False)) as con:
        assert (
            con.execute("SELECT * FROM monitoring ORDER BY wallet_id").fetchall()
            == previous_monitoring
        )
        assert con.execute("SELECT * FROM portfolio_memberships").fetchall() == previous_portfolios
        assert con.execute("SELECT * FROM portfolio_runs").fetchall() == previous_paper
        assert con.execute("SELECT COUNT(*) FROM exclusions").fetchone()[0] == 2
        assert (
            con.execute("SELECT known_at FROM exclusions WHERE wallet_id=?", (wid,)).fetchone()[0]
            == NOW
        )
        before = catalog.list_wallets(con, "2026-11-04T23:59:59+00:00", limit=20)
        after = catalog.list_wallets(con, "2026-11-05T04:00:00+00:00", limit=20)
        assert (
            next(row for row in before["wallets"] if row["registry_wallet_id"] == wid)["excluded"]
            is False
        )
        assert (
            next(row for row in after["wallets"] if row["registry_wallet_id"] == wid)["excluded"]
            is True
        )
    assert registry.db_status(db)["counts"]["owner_excluded"] == 2
    assert registry.db_authority_health(db)["database_integrity"] == "VERIFIED"
    unchanged = native.append_exclusions(
        db,
        manifest,
        expected=applied["inventory_sha256"],
        expected_manifest_sha=source_sha,
        apply=True,
    )
    assert unchanged["unchanged"] is True
    assert unchanged["inventory_sha256"] == applied["inventory_sha256"]


@pytest.mark.parametrize(
    ("decisions", "problem"),
    [
        (
            [{"address": address(4), "reason_code": "OWNER_REJECTED"}],
            "EXCLUSION_WALLET_NOT_REGISTERED",
        ),
        ([{"address": address(9), "reason_code": "OWNER_REJECTED"}], "EXCLUSION_ALREADY_RECORDED"),
        (
            [
                {"address": address(2), "reason_code": "OWNER_REJECTED"},
                {"address": address(2), "reason_code": "TAIL_RISK"},
            ],
            "DUPLICATE_EXCLUSION_IDENTITY",
        ),
        ([{"address": address(2), "reason_code": "free text"}], "INVALID_EXCLUSION_REASON_CODE"),
        ([{"address": 2, "reason_code": "OWNER_REJECTED"}], "INVALID_EXCLUSION_IDENTITY"),
        (
            [{"address": address(2), "reason_code": "OWNER_REJECTED", "known_at": NOW}],
            "INVALID_EXCLUSION_DECISION",
        ),
        (
            [{"address": address(2), "reason_code": "REVOKE", "action": "DELETE"}],
            "INVALID_EXCLUSION_DECISION",
        ),
    ],
)
def test_invalid_or_conflicting_decisions_cannot_mutate_registry(
    tmp_path: Path, decisions: list[dict], problem: str
) -> None:
    db, baseline = locked_seed(tmp_path)
    manifest, source_sha = decision_file(tmp_path, decisions)
    with pytest.raises(ValueError, match=problem):
        native.append_exclusions(
            db, manifest, expected=baseline, expected_manifest_sha=source_sha, apply=True, now=NOW
        )
    assert registry.db_authority_health(db)["inventory_sha256"] == baseline


def test_sha_and_privacy_guards_require_exact_reviewed_source(tmp_path: Path) -> None:
    db, baseline = locked_seed(tmp_path)
    manifest, source_sha = decision_file(tmp_path)
    with pytest.raises(ValueError, match="EXCLUSION_MANIFEST_SHA_CHANGED"):
        native.append_exclusions(
            db, manifest, expected=baseline, expected_manifest_sha="0" * 64, apply=True
        )
    with pytest.raises(ValueError, match="SQLITE_INVENTORY_SHA_CHANGED"):
        native.append_exclusions(
            db, manifest, expected="0" * 64, expected_manifest_sha=source_sha, apply=True
        )
    manifest.chmod(0o644)
    with pytest.raises(PermissionError, match="PRIVATE_EXCLUSION_MANIFEST_REQUIRED"):
        native.append_exclusions(
            db, manifest, expected=baseline, expected_manifest_sha=source_sha, apply=True
        )
    manifest.chmod(0o600)
    assert registry.db_authority_health(db)["inventory_sha256"] == baseline


def test_exclusion_rejects_unlocked_legacy_writer_and_backdating(tmp_path: Path) -> None:
    db, _, baseline = seed(tmp_path)
    manifest, source_sha = decision_file(tmp_path)
    with pytest.raises(ValueError, match="LOCK_LEGACY_IMPORT_BEFORE_NATIVE_EXCLUSION"):
        native.append_exclusions(
            db, manifest, expected=baseline, expected_manifest_sha=source_sha, apply=True
        )
    assert registry.db_authority_health(db)["inventory_sha256"] == baseline


def test_failure_mid_transaction_rolls_back_database_and_allows_safe_retry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db, baseline = locked_seed(tmp_path)
    manifest, source_sha = decision_file(tmp_path)
    setter = native._set

    def fail_after_inserts(*args: object) -> None:
        raise RuntimeError("INJECTED_FAILURE")

    monkeypatch.setattr(native, "_set", fail_after_inserts)
    with pytest.raises(RuntimeError, match="INJECTED_FAILURE"):
        native.append_exclusions(
            db, manifest, expected=baseline, expected_manifest_sha=source_sha, apply=True, now=NOW
        )
    assert registry.db_authority_health(db)["inventory_sha256"] == baseline
    with closing(registry.connect(db, False)) as con:
        assert con.execute("SELECT COUNT(*) FROM exclusions").fetchone()[0] == 1
        assert (
            con.execute(
                "SELECT COUNT(*) FROM evidence_artifacts WHERE source_key=?",
                (f"sqlite_primary:exclusions:{source_sha}",),
            ).fetchone()[0]
            == 0
        )
    monkeypatch.setattr(native, "_set", setter)
    result = native.append_exclusions(
        db, manifest, expected=baseline, expected_manifest_sha=source_sha, apply=True, now=NOW
    )
    assert result["applied"] is True


def test_reapplying_changed_or_deleted_evidence_fails_closed(tmp_path: Path) -> None:
    db, baseline = locked_seed(tmp_path)
    manifest, source_sha = decision_file(tmp_path)
    applied = native.append_exclusions(
        db, manifest, expected=baseline, expected_manifest_sha=source_sha, apply=True, now=NOW
    )
    archive = db.parent / "evidence" / "native-exclusions" / f"{source_sha}.json"
    archive.unlink()
    with pytest.raises(ValueError, match="EXCLUSION_EVIDENCE_INTEGRITY_FAILED"):
        native.append_exclusions(
            db,
            manifest,
            expected=applied["inventory_sha256"],
            expected_manifest_sha=source_sha,
            apply=True,
        )
    with pytest.raises(ValueError, match="EXCLUSION_EVIDENCE_INTEGRITY_FAILED"):
        registry.db_authority_health(db)


def test_cli_preview_is_redacted_and_mutation_is_protected(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    db, baseline = locked_seed(tmp_path)
    manifest, source_sha = decision_file(tmp_path)
    assert (
        registry.cli(
            [
                "--db",
                str(db),
                "native",
                "exclude",
                "--manifest",
                str(manifest),
                "--expected-manifest-sha",
                source_sha,
                "--expected-inventory-sha",
                baseline,
            ]
        )
        == 0
    )
    printed = capsys.readouterr().out
    assert json.loads(printed)["would_append_only"] is True
    assert address(2) not in printed
    assert pm_capabilities.REGISTRY_OPERATIONS["native exclude"] == "READ_ONLY"
    assert pm_capabilities.REGISTRY_OPERATIONS["native exclude --apply"] == "PROTECTED_MUTATION"
    assert registry.db_authority_health(db)["inventory_sha256"] == baseline
