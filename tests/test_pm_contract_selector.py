"""Native portfolio-contract component: evidence and rule boundary tests."""

from contextlib import closing
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
        "_roster_identity",
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
        "_roster_identity",
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


def test_real_roster_integrity_fail_closed(monkeypatch) -> None:
    monkeypatch.setattr(
        operations, "roster_authority", lambda _: {"status": "BLOCKED", "data": None}
    )
    with pytest.raises(ValueError, match="ROSTER_SQLITE_INTEGRITY"):
        selector._roster_identity("gemini.phase4/E6", db=Path("missing"), asof=None)
    with pytest.raises(ValueError, match="NAMESPACE"):
        selector._roster_identity("E6", db=Path("missing"), asof=None)


def test_operations_contracts_rule_and_parser(tmp_path: Path) -> None:
    assert operations.cli(["research", "contracts", "rules"]) == 0
    args = operations.parser().parse_args(
        [
            "research",
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
    """Two sealed roster accounts, one of them with a later generation after vetoes.

    The retired wallet registry is never read: the committed roster book is the
    seal, a `q3/B` label resolves through the shared `q3:B` campaign mapping, and
    an account with no committed book is an explicit not-registered result.
    """
    from copytrade_kernel import KnownAtTs
    from roster_fixture import MS, add_account

    from copytrade_pm.roster import RosterStore, reconcile_roster

    db_dir = tmp_path / "registry_dir"
    db_dir.mkdir(mode=0o700)
    db = db_dir / "roster.sqlite"
    veto_ms = MS + 3_599_000
    with RosterStore(db, create=True, writable=True) as store:
        add_account(store, "q3:B", {seat: _wallet(seat) for seat in Q3_B}, at_ms=MS)
        add_account(store, "gemini.phase4:E6", {seat: _wallet(seat) for seat in E6_V1}, at_ms=MS)
        # Three of the E6 sources decay: a veto hard-evicts them and frees the seats.
        for alias in ("CM-002", "S051-BTC", "Whale_0x5f94"):
            store.record_veto(
                _wallet(alias), reason="decayed source scope", actor="research", at_ms=veto_ms
            )
        at = KnownAtTs(veto_ms)
        book = store.book_at("gemini.phase4:E6", as_of=at)
        plan = reconcile_roster(
            current=book,
            scorecard=store.latest_scorecard(as_of=at, policy_epoch=book.policy_epoch),
            bench=store.latest_bench("gemini.phase4:E6", as_of=at),
            vetoes=store.active_vetoes(as_of=at),
            latches={},
            cooldowns=store.cooldowns(),
            as_of=at,
        )
        store.commit_plan(plan, committed_ms=MS + 3_600_000, with_proposal=False)
    db.chmod(0o600)
    return db, E6_V2_AT


def _wallet(alias: str) -> str:
    """Deterministic fictitious address per member label; never a real wallet."""
    from hashlib import sha256

    return "0x" + sha256(alias.encode()).hexdigest()[:40]


Q3_B = ("CA-005", "W031", "W044")
E6_V1 = ("ACT04", "CM-002", "S051-BTC", "S053-HYPE", "Whale_0x5f94")
E6_V2 = ("ACT04", "S053-HYPE")
E6_V1_AT = "2026-11-04T06:00:00+00:00"
E6_V2_AT = "2026-11-04T07:00:00+00:00"


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
    q3_b = selector._roster_identity("q3/B", db=db, asof=asof)
    e6 = selector._roster_identity("gemini.phase4/E6", db=db, asof=asof)
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
        definition_sha256=e6["definition_sha256"],
        members=e6["members"],
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
        "research",
        "contracts",
        "compare",
    ]
    for portfolio_id, tape_path in targets:
        cmd += ["--portfolio", portfolio_id, "--tape", str(tape_path)]
    cmd += ["--asof", asof, *_COMPARE_CLI_FLAGS]
    return subprocess.run(cmd, capture_output=True, text=True, check=False, timeout=60)


def test_native_blocked_selection_doctor_exit_2_allows_unaffected_sealed_comparison(
    tmp_path: Path,
) -> None:
    """Seam 2 (selector & compare_portfolios): namespaces, as-of generations, corrupt DB, zero writes."""
    import shutil
    import sqlite3

    db, v2_at = _blocked_selection_native_db(tmp_path)
    before_bytes = db.read_bytes()

    authority = operations.roster_authority(db)
    assert authority["status"] == "VERIFIED"
    assert authority["data"]["database_integrity"] == "VERIFIED"
    assert authority["data"]["inventory_sha256"] == authority["source"]["sha256"]

    # Namespace-qualified "q3/B" resolves the canonical roster account "q3:B", and
    # E6 keeps both generations selectable at their own as-of clocks.
    q3_b = selector._roster_identity("q3/B", db=db, asof=E6_V1_AT)
    assert q3_b["portfolio_id"] == "q3/B"
    assert q3_b["members"] == sorted(Q3_B)
    assert q3_b["trading_authorized"] is False

    e6_v1 = selector._roster_identity("gemini.phase4/E6", db=db, asof=E6_V1_AT)
    assert e6_v1["version"] == 1
    assert e6_v1["members"] == sorted(E6_V1)

    e6_v2 = selector._roster_identity("gemini.phase4/E6", db=db, asof=v2_at)
    assert e6_v2["version"] == 2
    assert e6_v2["members"] == sorted(E6_V2)
    assert e6_v1["definition_sha256"] != e6_v2["definition_sha256"]

    tape_q3b, tape_e6_v2 = _write_sealed_pair_tapes(tmp_path, db, asof=v2_at)
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
        [tape_q3b, tape_e6_v2],
        db=db,
        asof=v2_at,
        **options,
    )
    assert accepted["status"] == "SCENARIO_ONLY"
    assert accepted["selection_coverage_complete"] is True
    assert accepted["best_modeled_portfolio_contract"] is not None
    assert accepted["scientifically_qualified"] is False
    assert accepted["trading_authorized"] is False
    assert accepted["purchase_decision"] == "NO_AUTHORIZED_PURCHASE_RECOMMENDATION"

    # Negative: an account with no committed book stays BLOCKED; partial selection never promoted.
    unsealed_compare = selector.compare_portfolios(
        ["q3/B", "gemini.phase9/UNSEALED"],
        [tape_q3b, tape_e6_v2],
        db=db,
        asof=v2_at,
        **options,
    )
    assert unsealed_compare["status"] == "BLOCKED"
    assert unsealed_compare["best_modeled_portfolio_contract"] is None
    assert unsealed_compare["comparisons"][1]["error_code"] == "PORTFOLIO_NOT_REGISTERED_AT_ASOF"
    assert not unsealed_compare["scientifically_qualified"]
    assert not unsealed_compare["trading_authorized"]

    # Namespace & as-of negative checks.
    for bad_ns in ("B", "E6", "q3/", "/B", "a/b/c"):
        with pytest.raises(ValueError, match="NAMESPACE_QUALIFIED_PORTFOLIO_REQUIRED"):
            selector._roster_identity(bad_ns, db=db, asof=v2_at)
    with pytest.raises(ValueError, match="PORTFOLIO_NOT_REGISTERED_AT_ASOF"):
        selector._roster_identity("gemini.phase5/B", db=db, asof=v2_at)
    with pytest.raises(ValueError, match="PORTFOLIO_NOT_REGISTERED_AT_ASOF"):
        selector._roster_identity("q3/B", db=db, asof="2026-11-03T00:00:00+00:00")

    # True corrupt / missing DB remains blocked.
    corrupt_db = tmp_path / "corrupt.sqlite"
    corrupt_db.write_bytes(b"corrupt")
    for broken in (corrupt_db, tmp_path / "missing.sqlite"):
        with pytest.raises(ValueError, match="ROSTER_SQLITE_INTEGRITY_NOT_VERIFIED"):
            selector._roster_identity("q3/B", db=broken, asof=v2_at)

    assert db.read_bytes() == before_bytes

    # Any stored-payload drift invalidates the roster pin, so every lookup under it
    # is blocked instead of returning a silently narrower selection.
    tampered_db = db.parent / "tampered.sqlite"
    shutil.copyfile(db, tampered_db)
    tampered_db.chmod(0o600)
    with closing(sqlite3.connect(tampered_db)) as con, con:
        # Scorecards carry no append-only trigger, so this is stored-payload drift
        # rather than a schema/trigger tamper: the pin must still fail closed.
        con.execute("UPDATE scorecards SET payload = json_set(payload, '$.as_of_ms', as_of_ms + 1)")
    tampered_compare = selector.compare_portfolios(
        ["q3/B", "gemini.phase4/E6"],
        [tape_q3b, tape_e6_v2],
        db=tampered_db,
        asof=v2_at,
        **options,
    )
    assert tampered_compare["status"] == "BLOCKED"
    assert tampered_compare["best_modeled_portfolio_contract"] is None
    assert (
        tampered_compare["comparisons"][0]["error_code"] == "ROSTER_SQLITE_INTEGRITY_NOT_VERIFIED"
    )
    with pytest.raises(ValueError, match="ROSTER_SQLITE_INTEGRITY_NOT_VERIFIED"):
        selector._roster_identity("q3/B", db=tampered_db, asof=v2_at)


def test_cli_subprocess_contracts_compare_blocked_doctor_and_preservation(
    tmp_path: Path,
) -> None:
    """Seam 3 (CLI subprocess compare): catches exit codes, JSON schema & zero DB writes."""
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
