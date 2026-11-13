"""Native portfolio-contract component: evidence and rule boundary tests."""

from datetime import UTC, datetime, timedelta
import json
from pathlib import Path

import pytest

np = pytest.importorskip("numpy")

from copytrade_pm import pm_contract_selector as selector  # noqa: E402
from copytrade_pm import pm_operations as operations  # noqa: E402


def _fixture(
    path: Path,
    *,
    days: int = 49,
    pnl_a: float = 7.0,
    pnl_b: float = -2.0,
    peak_leverage: float | None = 3.0,
) -> dict:
    start = datetime(2026, 1, 1, tzinfo=UTC)
    records = []
    for t in range(days * 4):
        records.append(
            {
                "timestamp": (start + timedelta(hours=t * 6)).isoformat(),
                "pnl_by_member": {"podA": str(pnl_a), "podB": str(pnl_b)},
            }
        )
    data = {
        "schema": selector.SCHEMA,
        "portfolio_id": "demo/AB",
        "portfolio_definition_sha256": "a" * 64,
        "members": ["podA", "podB"],
        "source_status": "SYNTHETIC_FIXTURE",
        "observed_at": (start + timedelta(days=days)).isoformat(),
        "pnl_basis": "FOLLOWER_NET_MARK_TO_MARKET_USD",
        "initial_capital_usd": 10000,
        "step_minutes": 360,
        "costs_included": {key: True for key in selector.COSTS},
        "peak_gross_leverage": peak_leverage,
        "rows": records,
    }
    path.write_text(json.dumps(data))
    return data


def _identity() -> dict:
    return {
        "portfolio_id": "demo/AB",
        "definition_sha256": "a" * 64,
        "members": ["podA", "podB"],
        "version": 1,
        "selection_known_at": "2026-01-01T00:00:00+00:00",
        "registry_generation_sha256": "b" * 64,
        "registry_observed_at": "2026-02-20",
        "registry_state": "RESEARCH_SELECTION_ONLY",
        "trading_authorized": False,
    }


def test_rulebook_versions_are_stable_and_never_account_authority() -> None:
    a = selector.rules_catalog()
    b = selector.rules_catalog()
    assert a == b
    assert len(a["contracts"]) == 3
    assert all(not x["account_trading_authorized"] for x in a["contracts"])
    assert any("daily-stop" in x.lower() for x in selector.RULE_UNKNOWNS["C 2-Step"])


def test_complete_joint_pnl_and_causal_utc_grid(tmp_path: Path) -> None:
    path = tmp_path / "pnl.json"
    _fixture(path)
    tape = selector.load_tape(path)
    assert tape.days == 49
    assert tape.increments.shape == (49, 4, 2)
    assert np.array_equal(tape.increments[0, 0], [7, -2])
    bootstrap = selector.JointBlockBootstrap(tape, paths=15, max_days=15, block_days=7, seed=43)
    assert np.all(bootstrap(0, 0) == 5)
    assert np.all(bootstrap(13, 3) == 5)


@pytest.mark.parametrize(
    ("mutate", "error"),
    [
        (lambda d: d["rows"].pop(5), "INSUFFICIENT_OR_EXCESSIVE"),
        (
            lambda d: d["rows"][8].update({"timestamp": d["rows"][7]["timestamp"]}),
            "GAPPED_DUPLICATED",
        ),
        (lambda d: d["rows"][0]["pnl_by_member"].pop("podB"), "MISSING_OR_UNEXPECTED"),
        (lambda d: d["costs_included"].update({"funding": False}), "INCOMPLETE_EXECUTION"),
        (lambda d: d.update({"pnl_basis": "LEADER_REALIZED_PNL"}), "LEADER_OR_REALIZED"),
        (lambda d: d["rows"][0]["pnl_by_member"].update({"podA": "NaN"}), "NONFINITE"),
        (lambda d: d.update({"observed_at": "2026-01-01T00:00:00+00:00"}), "OBSERVED_BEFORE"),
        (lambda d: d.update({"peak_gross_leverage": -1}), "NEGATIVE_GROSS"),
        (lambda d: d.update({"members": ["podA", "podA"]}), "INVALID_PORTFOLIO_MEMBERS"),
    ],
)
def test_invalid_tapes_fail_closed(tmp_path: Path, mutate, error: str) -> None:
    file = tmp_path / "pnl.json"
    data = _fixture(file)
    mutate(data)
    file.write_text(json.dumps(data))
    with pytest.raises(ValueError, match=error):
        selector.load_tape(file)


def test_scorecard_requires_multiple_paths(tmp_path: Path) -> None:
    path = tmp_path / "pnl.json"
    _fixture(path)
    with pytest.raises(ValueError, match="MINIMUM_TWO_PATHS"):
        selector.compare_contracts(
            selector.load_tape(path),
            _identity(),
            paths=1,
            evaluation_days=5,
            funded_days=10,
        )


def test_reject_identity_drift(tmp_path: Path) -> None:
    path = tmp_path / "pnl.json"
    _fixture(path)
    tape = selector.load_tape(path)
    wrong = {**_identity(), "definition_sha256": "0" * 64}
    with pytest.raises(ValueError, match="MISMATCH"):
        selector.compare_contracts(tape, wrong, paths=20, evaluation_days=5, funded_days=15)


def test_scorecard_and_no_purchase_authorization(tmp_path: Path) -> None:
    path = tmp_path / "pnl.json"
    _fixture(path, pnl_a=90, pnl_b=-10)
    tape = selector.load_tape(path)
    result = selector.compare_contracts(
        tape,
        _identity(),
        paths=128,
        seed=4,
        evaluation_days=20,
        funded_days=42,
        evaluation_scales=(0.5, 1),
        funded_scales=(0.5,),
    )
    assert result["status"] == "SCENARIO_ONLY"
    assert len(result["scorecard"]) == 6
    assert result["best_modeled_choice"]["net_ev"] > 0
    assert not result["scientifically_qualified"]
    assert not result["trading_authorized"]
    assert result["purchase_decision"] == "NO_AUTHORIZED_PURCHASE_RECOMMENDATION"
    repeat = selector.compare_contracts(
        tape,
        _identity(),
        paths=128,
        seed=4,
        evaluation_days=20,
        funded_days=42,
        evaluation_scales=(0.5, 1),
        funded_scales=(0.5,),
    )
    assert result == repeat


def test_unknown_leverage_blocks_all_contract_comparison(tmp_path: Path) -> None:
    path = tmp_path / "pnl.json"
    _fixture(path, peak_leverage=None)
    result = selector.compare_contracts(
        selector.load_tape(path),
        _identity(),
        paths=20,
        evaluation_days=5,
        funded_days=10,
        evaluation_scales=(1,),
        funded_scales=(1,),
    )
    assert result["status"] == "BLOCKED"
    assert result["best_modeled_choice"] is None
    assert any(row["status"] == "BLOCKED_LEVERAGE_UNKNOWN" for row in result["scorecard"])


def test_coarse_historical_mark_grid_refused(tmp_path: Path) -> None:
    path = tmp_path / "pnl.json"
    data = _fixture(path)
    data["source_status"] = "HISTORICAL_HYPOTHETICAL"
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="SAMPLING_TOO_COARSE"):
        selector.compare_contracts(selector.load_tape(path), _identity(), paths=10)


def test_ruin_constraint_can_reject_every_modeled_purchase(tmp_path: Path) -> None:
    path = tmp_path / "pnl.json"
    _fixture(path, pnl_a=-100, pnl_b=0)
    result = selector.compare_contracts(
        selector.load_tape(path),
        _identity(),
        paths=50,
        evaluation_days=10,
        funded_days=21,
        evaluation_scales=(1,),
        funded_scales=(1,),
        max_no_first_payout_probability=0.01,
    )
    assert result["status"] == "SCENARIO_ONLY"
    assert not result["risk_constraint_feasible"]
    assert result["best_modeled_choice"] is None
    assert result["scenario_decision"] == "NO_BUY_OR_INCOMPLETE_EVIDENCE"


def test_over_leverage_scenario_blocks_optimum(tmp_path: Path) -> None:
    path = tmp_path / "pnl.json"
    _fixture(path, peak_leverage=40)
    result = selector.compare_contracts(
        selector.load_tape(path),
        _identity(),
        paths=20,
        evaluation_days=5,
        funded_days=10,
        evaluation_scales=(1,),
        funded_scales=(1,),
    )
    assert result["status"] == "BLOCKED"
    assert any(row["status"] == "BLOCKED_LEVERAGE_LIMIT" for row in result["scorecard"])


def test_missing_tapes_return_blocked_for_each_saved_portfolio(monkeypatch) -> None:
    monkeypatch.setattr(
        selector,
        "_registry_identity",
        lambda pid, **k: {
            **_identity(),
            "portfolio_id": pid,
        },
    )
    result = selector.compare_portfolios(["demo/AB", "demo/CD"])
    assert result["status"] == "BLOCKED"
    assert result["best_modeled_portfolio_contract"] is None
    assert len(result["comparisons"]) == 2
    assert all(
        r["error_code"] == "MISSING_COMPLETE_NET_FOLLOWER_MTM_TAPE" for r in result["comparisons"]
    )


def test_global_portfolio_winner_requires_identical_pnl_windows(
    tmp_path: Path,
    monkeypatch,
) -> None:
    p1 = tmp_path / "ab.json"
    p2 = tmp_path / "cd.json"
    first = _fixture(p1, days=49, pnl_a=40)
    second = _fixture(p2, days=49, pnl_a=20)
    second["portfolio_id"] = "demo/CD"
    second["portfolio_definition_sha256"] = "b" * 64
    # A different (valid, complete) 49-day UTC window is not a paired comparison.
    for row in second["rows"]:
        row["timestamp"] = (
            datetime.fromisoformat(row["timestamp"]) + timedelta(days=1)
        ).isoformat()
    second["observed_at"] = (
        datetime.fromisoformat(second["observed_at"]) + timedelta(days=1)
    ).isoformat()
    p2.write_text(json.dumps(second))
    monkeypatch.setattr(
        selector,
        "_registry_identity",
        lambda pid, **kw: {
            **_identity(),
            "portfolio_id": pid,
            "definition_sha256": first["portfolio_definition_sha256"]
            if pid == "demo/AB"
            else second["portfolio_definition_sha256"],
        },
    )
    options = dict(
        paths=50, evaluation_days=10, funded_days=21, evaluation_scales=(1,), funded_scales=(0.5,)
    )
    mismatch = selector.compare_portfolios(["demo/AB", "demo/CD"], [p1, p2], **options)
    assert mismatch["status"] == "BLOCKED"
    assert mismatch["best_modeled_portfolio_contract"] is None
    assert not mismatch["portfolio_window_alignment_verified"]
    assert mismatch["comparison_blockers"]
    for row, template in zip(second["rows"], first["rows"]):
        row["timestamp"] = template["timestamp"]
    second["observed_at"] = first["observed_at"]
    p2.write_text(json.dumps(second))
    matched = selector.compare_portfolios(["demo/AB", "demo/CD"], [p1, p2], **options)
    assert matched["status"] == "SCENARIO_ONLY"
    assert matched["best_modeled_portfolio_contract"] is not None
    assert matched["portfolio_window_alignment_verified"]


def test_real_registry_integrity_fail_closed(monkeypatch) -> None:
    monkeypatch.setattr(operations, "_doctor", lambda _: {"status": "STALE"})
    with pytest.raises(ValueError, match="REGISTRY_SQLITE_INTEGRITY"):
        selector._registry_identity("gemini.phase4/E6", db=Path("missing"), asof=None)
    with pytest.raises(ValueError, match="NAMESPACE"):
        selector._registry_identity("E6", db=Path("missing"), asof=None)


def test_operations_contracts_rule_and_parser(tmp_path: Path) -> None:
    assert operations.cli(["contracts", "rules"]) == 0
    args = operations.parser().parse_args(
        [
            "contracts",
            "compare",
            "--portfolio",
            "gemini.phase4/E6",
            "--portfolio",
            "gemini.phase4/E2",
            "--paths",
            "64",
        ]
    )
    assert args.portfolio == ["gemini.phase4/E6", "gemini.phase4/E2"]
    assert args.paths == 64


def _write_portfolio_tape(
    path: Path,
    *,
    portfolio_id: str,
    definition_sha256: str,
    members: list[str],
    days: int = 49,
    base_pnl: float = 8.0,
) -> Path:
    start = datetime(2026, 1, 1, tzinfo=UTC)
    records = []
    for t in range(days * 4):
        records.append(
            {
                "timestamp": (start + timedelta(hours=t * 6)).isoformat(),
                "pnl_by_member": {
                    member: str(base_pnl if idx == 0 else -1.0)
                    for idx, member in enumerate(members)
                },
            }
        )
    path.write_text(
        json.dumps(
            {
                "schema": selector.SCHEMA,
                "portfolio_id": portfolio_id,
                "portfolio_definition_sha256": definition_sha256,
                "members": members,
                "source_status": "SYNTHETIC_FIXTURE",
                "observed_at": (start + timedelta(days=days)).isoformat(),
                "pnl_basis": "FOLLOWER_NET_MARK_TO_MARKET_USD",
                "initial_capital_usd": 10000,
                "step_minutes": 360,
                "costs_included": {key: True for key in selector.COSTS},
                "peak_gross_leverage": 2.5,
                "rows": records,
            }
        ),
        encoding="utf-8",
    )
    return path


def _blocked_selection_native_db(tmp_path: Path) -> tuple[Path, str]:
    """Build a locked SQLite fixture with valid SQLite integrity and native exit-2 selection block."""
    from contextlib import closing
    from hashlib import sha256
    from test_wallet_registry_catalog import AFTER, WHALE, _v2_snapshot
    from test_wallet_registry_signed_catalog import _signed_source

    from copytrade_pm import wallet_registry as reg
    from copytrade_pm import wallet_registry_catalog as cat
    from copytrade_pm import wallet_registry_native as native
    from copytrade_pm import wallet_registry_signed_catalog as signed

    cat.WHALE_ADDRESS_SHA256 = sha256(WHALE.encode()).hexdigest()
    db_dir = tmp_path / "registry_dir"
    db_dir.mkdir(mode=0o700)
    db, snapshot = _v2_snapshot(db_dir)
    reg.apply(db, snapshot, AFTER)
    src, sig, pub, fp = _signed_source(db_dir, replace_e6=True)
    now = datetime.now(UTC)
    signed_at = (now - timedelta(seconds=5)).isoformat()
    record = signed.inspect(src, sig, pub, expected_public_key_sha256=fp, first_known_at=signed_at)
    with closing(reg.connect(db, True)) as con, con:
        signed.store(con, record)
        # Explicitly unsealed candidate and unproved seal for negative compare coverage.
        con.execute(
            "INSERT INTO portfolio_versions VALUES(?,?,?,?,?,?)",
            (
                "gemini.phase9/UNSEALED",
                1,
                "RESEARCH_ONLY",
                "docs/unsealed.md",
                AFTER,
                "NON_EXECUTABLE",
            ),
        )
        con.execute(
            "INSERT INTO portfolio_versions VALUES(?,?,?,?,?,?)",
            (
                "gemini.phase9/UNPROVED_SEAL",
                1,
                "RESEARCH_SELECTION_ONLY",
                "docs/unproved.md",
                AFTER,
                "NON_EXECUTABLE",
            ),
        )
        con.execute(
            "INSERT INTO portfolio_seals VALUES(?,?,?,?,?,?)",
            ("gemini.phase9/UNPROVED_SEAL", 1, "c" * 64, "d" * 64, "0" * 40, AFTER),
        )
        # Unsigned latest research selection triggers native doctor exit 2 with SQLite VERIFIED.
        unsigned_at = (now - timedelta(seconds=2)).isoformat()
        con.execute(
            "INSERT INTO research_selections VALUES(?,?,?,?,?,?,?)",
            (
                "a" * 64,
                "NEW_FORWARD_PAPER_RESEARCH",
                "gemini.phase9/UNSEALED",
                1,
                "UNVERIFIED_LATEST_CANDIDATE",
                1,
                unsigned_at,
            ),
        )
    (db_dir / "backups").mkdir(mode=0o700, exist_ok=True)
    expected_sha = reg.db_authority_health(db)["inventory_sha256"]
    native.lock_legacy_import(
        db, expected=expected_sha, apply=True, now="2026-11-05T01:00:00+00:00"
    )
    return db, signed_at


_COMPARE_CLI_FLAGS = (
    "--paths",
    "32",
    "--evaluation-days",
    "10",
    "--funded-days",
    "21",
    "--evaluation-scales",
    "1",
    "--funded-scales",
    "0.5",
)


def _write_sealed_pair_tapes(
    tmp_path: Path, db: Path, *, asof: str, prefix: str = ""
) -> tuple[Path, Path]:
    q3_b = selector._registry_identity("q3/B", db=db, asof=asof)
    e6_v2 = selector._registry_identity("gemini.phase4/E6", db=db, asof=asof)
    tape_q3b = _write_portfolio_tape(
        tmp_path / f"{prefix}q3b.json",
        portfolio_id="q3/B",
        definition_sha256=q3_b["definition_sha256"],
        members=q3_b["members"],
        base_pnl=9.0,
    )
    tape_e6 = _write_portfolio_tape(
        tmp_path / f"{prefix}e6.json",
        portfolio_id="gemini.phase4/E6",
        definition_sha256=e6_v2["definition_sha256"],
        members=e6_v2["members"],
        base_pnl=7.0,
    )
    return tape_q3b, tape_e6


def _run_compare_cli(db: Path, targets: list[tuple[str, Path]], *, asof: str):
    import subprocess
    import sys

    cmd = [
        sys.executable,
        "-m",
        "copytrade_pm.pm_operations",
        "--db",
        str(db),
        "contracts",
        "compare",
    ]
    for portfolio_id, tape_path in targets:
        cmd += ["--portfolio", portfolio_id, "--tape", str(tape_path)]
    cmd += ["--asof", asof, *_COMPARE_CLI_FLAGS]
    return subprocess.run(cmd, capture_output=True, text=True, check=False, timeout=30)


def test_native_blocked_selection_doctor_exit_2_allows_unaffected_sealed_comparison(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Seam 2 (selector & compare_portfolios): catches exit-2 isolation, namespaces, as-of & unverified blocks; misses CLI exit codes."""
    from contextlib import closing
    from hashlib import sha256
    import shutil
    from test_wallet_registry_catalog import WHALE

    from copytrade_pm import wallet_registry as reg
    from copytrade_pm import wallet_registry_catalog as cat

    monkeypatch.setattr(cat, "WHALE_ADDRESS_SHA256", sha256(WHALE.encode()).hexdigest())
    db, signed_at = _blocked_selection_native_db(tmp_path)
    before_bytes = db.read_bytes()

    doctor = operations._doctor(db)
    assert doctor["status"] == "BLOCKED"
    assert doctor["error_code"] != "REGISTRY_SQLITE_INTEGRITY_FAILED"
    assert doctor["data"]["database_integrity"] == "VERIFIED"
    assert doctor["data"]["research_selection_integrity"] == "BLOCKED_MISSING_EXTERNAL_PROOF"

    # Namespace-qualified "q3/B" resolves canonical SQLite key "B", and signed E6 keeps both v1 & v2 as-of.
    q3_b = selector._registry_identity("q3/B", db=db, asof="2026-11-03T00:00:00+00:00")
    assert q3_b["portfolio_id"] == "q3/B"
    assert q3_b["members"] == ["CA-005", "W031", "W044"]
    assert q3_b["trading_authorized"] is False

    e6_v1 = selector._registry_identity("gemini.phase4/E6", db=db, asof="2026-11-04T09:06:33+00:00")
    assert e6_v1["version"] == 1
    assert e6_v1["members"] == ["ACT04", "CM-002", "S051-BTC", "S053-HYPE", "Whale_0x5f94"]

    e6_v2 = selector._registry_identity("gemini.phase4/E6", db=db, asof=signed_at)
    assert e6_v2["version"] == 2
    assert e6_v2["members"] == ["ACT04", "S053-HYPE"]

    tape_q3b, tape_e6 = _write_sealed_pair_tapes(tmp_path, db, asof=signed_at)
    options = dict(
        paths=32,
        seed=9,
        evaluation_days=10,
        funded_days=21,
        evaluation_scales=(1,),
        funded_scales=(0.5,),
    )
    accepted = selector.compare_portfolios(
        ["q3/B", "gemini.phase4/E6"],
        [tape_q3b, tape_e6],
        db=db,
        asof=signed_at,
        **options,
    )
    assert accepted["status"] == "SCENARIO_ONLY"
    assert accepted["selection_coverage_complete"] is True
    assert accepted["best_modeled_portfolio_contract"] is not None
    assert accepted["scientifically_qualified"] is False
    assert accepted["trading_authorized"] is False
    assert accepted["purchase_decision"] == "NO_AUTHORIZED_PURCHASE_RECOMMENDATION"

    # Negative: unsealed portfolio and unproved seal stay BLOCKED; partial selection never promoted.
    unsealed_compare = selector.compare_portfolios(
        ["q3/B", "gemini.phase9/UNSEALED"],
        [tape_q3b, tape_e6],
        db=db,
        asof=signed_at,
        **options,
    )
    assert unsealed_compare["status"] == "BLOCKED"
    assert unsealed_compare["best_modeled_portfolio_contract"] is None
    assert unsealed_compare["comparisons"][1]["error_code"] == "PORTFOLIO_SOURCE_NOT_SEALED"
    assert not unsealed_compare["scientifically_qualified"]
    assert not unsealed_compare["trading_authorized"]

    unproved_compare = selector.compare_portfolios(
        ["gemini.phase4/E6", "gemini.phase9/UNPROVED_SEAL"],
        [tape_e6, tape_e6],
        db=db,
        asof=signed_at,
        **options,
    )
    assert unproved_compare["status"] == "BLOCKED"
    assert unproved_compare["best_modeled_portfolio_contract"] is None
    assert unproved_compare["comparisons"][1]["error_code"] == "PORTFOLIO_SELECTION_PROOF_BLOCKED"

    # Namespace & as-of negative checks.
    for bad_ns in ("B", "E6", "q3/", "/B", "a/b/c"):
        with pytest.raises(ValueError, match="NAMESPACE_QUALIFIED_PORTFOLIO_REQUIRED"):
            selector._registry_identity(bad_ns, db=db, asof=signed_at)
    with pytest.raises(ValueError, match="PORTFOLIO_NOT_REGISTERED_AT_ASOF"):
        selector._registry_identity("gemini.phase5/B", db=db, asof="2026-11-03T00:00:00+00:00")

    # True corrupt / missing DB remains blocked.
    corrupt_db = tmp_path / "corrupt.sqlite"
    corrupt_db.write_bytes(b"corrupt")
    for broken in (corrupt_db, tmp_path / "missing.sqlite"):
        with pytest.raises(ValueError, match="REGISTRY_SQLITE_INTEGRITY_NOT_VERIFIED"):
            selector._registry_identity("q3/B", db=broken, asof=signed_at)

    assert db.read_bytes() == before_bytes

    # Tampered stored proof keeps requested portfolio BLOCKED without breaking unaffected sealed lookups.
    tampered_db = db.parent / "tampered.sqlite"
    shutil.copyfile(db, tampered_db)
    tampered_db.chmod(0o600)
    with closing(reg.connect(tampered_db, True)) as con, con:
        # Bypass immutability trigger on the temp copy to exercise runtime signature verification failure.
        con.execute("DROP TRIGGER guard_research_selection_proof_update")
        con.execute("UPDATE research_selection_proofs SET signature_hex=?", ("00" * 64,))
    tampered_compare = selector.compare_portfolios(
        ["q3/B", "gemini.phase4/E6"],
        [tape_q3b, tape_e6],
        db=tampered_db,
        asof=signed_at,
        **options,
    )
    assert tampered_compare["status"] == "BLOCKED"
    assert tampered_compare["best_modeled_portfolio_contract"] is None
    assert tampered_compare["comparisons"][1]["error_code"] == "PORTFOLIO_SELECTION_PROOF_BLOCKED"
    assert selector._registry_identity("q3/B", db=tampered_db, asof=signed_at)["members"] == [
        "CA-005",
        "W031",
        "W044",
    ]


def test_cli_subprocess_contracts_compare_blocked_doctor_and_preservation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Seam 3 (CLI subprocess compare): catches exit codes, JSON schema & zero DB writes; misses dashboard wallets."""
    from hashlib import sha256
    from test_wallet_registry_catalog import WHALE

    from copytrade_pm import wallet_registry_catalog as cat

    monkeypatch.setattr(cat, "WHALE_ADDRESS_SHA256", sha256(WHALE.encode()).hexdigest())
    db, signed_at = _blocked_selection_native_db(tmp_path)
    before_bytes = db.read_bytes()

    tape_q3b, tape_e6 = _write_sealed_pair_tapes(tmp_path, db, asof=signed_at, prefix="cli_")
    ok_proc = _run_compare_cli(
        db, [("q3/B", tape_q3b), ("gemini.phase4/E6", tape_e6)], asof=signed_at
    )
    assert ok_proc.returncode == 0, ok_proc.stderr
    ok_payload = json.loads(ok_proc.stdout)
    assert ok_payload["status"] == "SCENARIO_ONLY"
    assert ok_payload["scientifically_qualified"] is False
    assert ok_payload["trading_authorized"] is False
    assert ok_payload["purchase_decision"] == "NO_AUTHORIZED_PURCHASE_RECOMMENDATION"

    for bad_target in ("gemini.phase9/UNSEALED", "gemini.phase9/UNPROVED_SEAL", "B"):
        bad_proc = _run_compare_cli(db, [(bad_target, tape_q3b)], asof=signed_at)
        assert bad_proc.returncode == 2
        bad_payload = json.loads(bad_proc.stdout)
        assert bad_payload["status"] == "BLOCKED"
        assert bad_payload["best_modeled_portfolio_contract"] is None
        assert bad_payload["scientifically_qualified"] is False
        assert bad_payload["trading_authorized"] is False

    assert db.read_bytes() == before_bytes
