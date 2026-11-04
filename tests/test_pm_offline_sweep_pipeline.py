"""Synthetic-only manifest-to-Polars-to-PM03 sweep and cache resume contract."""

from dataclasses import fields
from datetime import UTC, datetime, timedelta
from decimal import Decimal as D
from hashlib import sha256
import json

import pytest

from copytrade_pm.pm03_account import Instrument, Rulebook
from copytrade_pm.pm03_risk import RiskPolicy
from copytrade_pm.pm_offline_manifest import ManifestBlocked
from copytrade_pm.pm_offline_sweep import run_synthetic_fixture_study
from copytrade_pm.pm_shadow import VerifiedHyperliquidMinuteSource

pl = pytest.importorskip("polars")
START = datetime(2026, 10, 20, 12, 0, tzinfo=UTC)
BTC = "hyperliquid:mainnet:perp:default:BTC"


def seal(root, path, contents):
    file = root / path
    file.parent.mkdir(parents=True, exist_ok=True)
    file.write_bytes(contents)
    return {"path": path, "sha256": sha256(contents).hexdigest()}


def sample(tmp_path, *, managers=5, fixture=True):
    root = tmp_path / "inputs"
    root.mkdir()
    cache = tmp_path / "private-cache"
    symbols = []
    for i in range(managers):
        pm = f"W{i + 1:03d}"
        book = seal(
            root,
            f"{pm}/book.json",
            json.dumps(
                {
                    "initial_books": [
                        {
                            "account": pm,
                            "dex": "default",
                            "atomic_source_verified": True,
                            "first_known_at": (START - timedelta(minutes=1)).isoformat(),
                            "positions": {"BTC": "0"},
                        }
                    ],
                    "fills": [
                        {
                            "account": pm,
                            "dex": "default",
                            "instrument": "BTC",
                            "event_id": "1",
                            "source_event_at": START.isoformat(),
                            "first_known_at": START.isoformat(),
                            "position_before": "0",
                            "position_after": "1",
                            "leader_prices": {"BTC": "100"},
                        }
                    ],
                },
                sort_keys=True,
            ).encode(),
        )
        equity = seal(
            root,
            f"{pm}/equity.json",
            json.dumps(
                {
                    "snapshots": [
                        {
                            "account": pm,
                            "dex": "default",
                            "source_verified": True,
                            "first_known_at": (START - timedelta(minutes=1)).isoformat(),
                            "equity": "1000",
                        }
                    ]
                },
                sort_keys=True,
            ).encode(),
        )
        symbols.append(
            {
                "account": pm,
                "dex": "default",
                "instrument": "BTC",
                "book_path": book["path"],
                "book_sha256": book["sha256"],
                "equity_path": equity["path"],
                "equity_sha256": equity["sha256"],
                "first_known_basis": "HISTORICAL_ORACLE",
            }
        )
    relative = VerifiedHyperliquidMinuteSource._family(BTC)
    folder = root / relative / "year=2026/month=10/day=20"
    folder.mkdir(parents=True)
    rows = [
        {
            "timestamp": START + timedelta(minutes=i),
            "symbol": "BTC",
            "open": 100.0,
            "high": 101.0,
            "low": 99.0,
            "close": 100.0,
            "volume": 100.0,
        }
        for i in range(20)
    ]
    data = folder / "data.parquet"
    pl.DataFrame(rows).write_parquet(data)
    market_sha = sha256(data.read_bytes()).hexdigest()
    sidecar = folder / "source.json"
    sidecar.write_text(
        json.dumps(
            {
                "source_type": "trades",
                "sha256": market_sha,
                "exchange": "hyperliquid_futures",
                "source_symbol": "BTC",
            }
        )
    )
    source_meta_sha = sha256(sidecar.read_bytes()).hexdigest()
    source_path = str(data.relative_to(root))
    r = Rulebook(
        program="SYNTHETIC",
        stage="test",
        source="owner fixture",
        observed_at=(START - timedelta(days=1)).isoformat(),
        version="test-v1",
        timezone="UTC",
        initial_balance=D("10000"),
        profit_target=D("1000"),
        daily_loss=D("500"),
        static_loss=D("1000"),
        trailing_loss=D("800"),
        confirmed=True,
        permitted=(Instrument("hyperliquid", "perp", "BTC"),),
        max_gross_leverage=D("2"),
    )
    rules = seal(root, "rulebook.json", json.dumps(r.to_dict()).encode())
    costs = seal(
        root,
        "cost_model.json",
        json.dumps(
            {
                "fee_bps": "1",
                "full_spread_bps": "0",
                "slippage_bps": "0",
                "impact_bps_at_full_participation": "0",
                "max_participation": "0.5",
                "max_age_seconds": 60,
                "latency_seconds": 0,
            }
        ).encode(),
    )
    risk = RiskPolicy()
    risk_file = seal(
        root,
        "risk_policy.json",
        json.dumps({f.name: str(getattr(risk, f.name)) for f in fields(RiskPolicy)}).encode(),
    )
    manifest = {
        "schema": "pm_offline_sweep_manifest_v1",
        "study_id": "synthetic-five-wallet-fixture",
        "start": (START + timedelta(minutes=1)).isoformat(),
        "end": (START + timedelta(minutes=16)).isoformat(),
        "selection_cutoff": (START - timedelta(days=1)).isoformat(),
        "clock_basis": "HISTORICAL_ORACLE",
        "policy": "PER_FILL_ELIGIBILITY",
        "delays_minutes": [10, 0, 1, 5, 2],
        "mode": "CERTIFIED",
        "follower_initial_equity": "10000",
        "source_equity_max_age_minutes": 1440,
        "synthetic_funding_evidence_complete": True,
        "synthetic_fixture": fixture,
        "sources": symbols,
        "market_days": [
            {
                "dex": "default",
                "instrument": "BTC",
                "date": "2026-10-20",
                "path": source_path,
                "sha256": market_sha,
                "metadata_path": str(sidecar.relative_to(root)),
                "metadata_sha256": source_meta_sha,
            }
        ],
        "rulebook": rules,
        "cost_model": costs,
        "risk_policy": risk_file,
        "scenarios": [
            {
                "id": "three-wallet",
                "k_by_account": {x["account"]: "0.01" for x in symbols[:3]},
                "stress_shocks": [{BTC: "-0.02"}, {BTC: "0.02"}],
                "hedge_break_loss": "1",
                "stressed_liquidity_loss": "1",
            },
            {
                "id": "five-wallet",
                "k_by_account": {x["account"]: "0.01" for x in symbols},
                "stress_shocks": [{BTC: "-0.02"}, {BTC: "0.02"}],
                "hedge_break_loss": "1",
                "stressed_liquidity_loss": "1",
            },
            {
                "id": "five-wallet-cost-stress",
                "k_by_account": {x["account"]: "0.01" for x in symbols},
                "stress_shocks": [{BTC: "-0.02"}, {BTC: "0.02"}],
                "hedge_break_loss": "1",
                "stressed_liquidity_loss": "1",
                "cost_multiplier": "3",
            },
        ],
    }
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(manifest))
    return path, root, cache, manifest


def test_five_delays_three_and_five_wallets_are_repeatable(tmp_path):
    path, root, cache, doc = sample(tmp_path)
    a = run_synthetic_fixture_study(path, input_root=root, market_root=root, cache_root=cache)
    b = run_synthetic_fixture_study(path, input_root=root, market_root=root, cache_root=cache)
    assert a["status"] == "COMPLETE_SYNTHETIC_FIXTURE_ONLY"
    assert a["requested_scenarios"] == 15
    assert len(a["scenarios"]) == 15
    assert a["cache_hits"] == 0
    assert a["tape_cache_hits"] == 0
    assert b["cache_hits"] == 15
    assert b["tape_cache_hits"] == 5
    assert a["logical_sha256"] == b["logical_sha256"]
    assert a["financial_certified_real"] is False
    assert a["scientifically_qualified"] is False
    assert all(x["status"] == "SYNTHETIC_PM03_OPEN" for x in a["scenarios"])
    assert {x["delay_minutes"] for x in a["scenarios"]} == {0, 1, 2, 5, 10}
    five_base = next(
        x for x in a["scenarios"] if x["scenario"] == "five-wallet" and x["delay_minutes"] == 0
    )
    five_costly = next(
        x
        for x in a["scenarios"]
        if x["scenario"] == "five-wallet-cost-stress" and x["delay_minutes"] == 0
    )
    assert D(five_costly["fees"]) > D(five_base["fees"])


def test_one_vs_two_workers_have_identical_logical_financial_results(tmp_path):
    path, root, cache, _ = sample(tmp_path)
    single = run_synthetic_fixture_study(
        path, input_root=root, market_root=root, cache_root=cache, workers=1
    )
    parallel = run_synthetic_fixture_study(
        path,
        input_root=root,
        market_root=root,
        cache_root=tmp_path / "parallel-cache",
        workers=2,
    )
    assert single["logical_sha256"] == parallel["logical_sha256"]
    assert single["scenarios"] == parallel["scenarios"]
    assert parallel["cache_hits"] == 0
    assert parallel["tape_cache_hits"] == 0
    again = run_synthetic_fixture_study(
        path,
        input_root=root,
        market_root=root,
        cache_root=tmp_path / "parallel-cache",
        workers=2,
    )
    assert again["cache_hits"] == 15
    assert again["tape_cache_hits"] == 5


def test_unbounded_worker_count_fails_closed(tmp_path):
    path, root, cache, _ = sample(tmp_path)
    with pytest.raises(ValueError, match="INVALID_BOUNDED_WORKER_COUNT"):
        run_synthetic_fixture_study(
            path, input_root=root, market_root=root, cache_root=cache, workers=8
        )


def test_pm03_code_fingerprint_change_invalidates_scenario_cache(tmp_path, monkeypatch):
    import copytrade_pm.pm_offline_sweep as module

    path, root, cache, _ = sample(tmp_path)
    first = run_synthetic_fixture_study(path, input_root=root, market_root=root, cache_root=cache)
    assert first["cache_hits"] == 0
    monkeypatch.setattr(module, "_software_sha", lambda: "b" * 64)
    changed = run_synthetic_fixture_study(path, input_root=root, market_root=root, cache_root=cache)
    assert changed["cache_hits"] == 0
    assert changed["tape_cache_hits"] == 0
    assert changed["logical_sha256"] != first["logical_sha256"]
    assert changed["scenarios"] == first["scenarios"]
    warm = run_synthetic_fixture_study(path, input_root=root, market_root=root, cache_root=cache)
    assert warm["cache_hits"] == 15


def test_crash_mid_sweep_resumes_immutable_completed_scenarios(tmp_path, monkeypatch):
    import copytrade_pm.pm_offline_sweep as module

    path, root, cache, _ = sample(tmp_path)
    original = module.replay_fixture
    calls = 0

    def fault_once(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError("SIMULATED_WORKER_CRASH")
        return original(*args, **kwargs)

    with monkeypatch.context() as context:
        context.setattr(module, "replay_fixture", fault_once)
        with pytest.raises(RuntimeError, match="SIMULATED_WORKER_CRASH"):
            run_synthetic_fixture_study(path, input_root=root, market_root=root, cache_root=cache)
    resumed = run_synthetic_fixture_study(path, input_root=root, market_root=root, cache_root=cache)
    assert resumed["status"] == "COMPLETE_SYNTHETIC_FIXTURE_ONLY"
    assert resumed["cache_hits"] == 1
    assert resumed["tape_cache_hits"] == 1
    assert resumed["requested_scenarios"] == 15


def test_one_unadmitted_wallet_blocks_only_affected_scenarios(tmp_path):
    path, root, cache, doc = sample(tmp_path)
    book_file = root / "W005/book.json"
    equity_file = root / "W005/equity.json"
    book = json.loads(book_file.read_text())
    equity = json.loads(equity_file.read_text())
    known = START + timedelta(minutes=20)
    fill = known + timedelta(minutes=1)
    book["initial_books"][0]["first_known_at"] = known.isoformat()
    book["fills"][0]["source_event_at"] = fill.isoformat()
    book["fills"][0]["first_known_at"] = fill.isoformat()
    equity["snapshots"][0]["first_known_at"] = known.isoformat()
    for file, data, part in (
        (book_file, book, "book"),
        (equity_file, equity, "equity"),
    ):
        payload = json.dumps(data).encode()
        file.write_bytes(payload)
        doc["sources"][4][f"{part}_sha256"] = sha256(payload).hexdigest()
    path.write_text(json.dumps(doc))
    first = run_synthetic_fixture_study(path, input_root=root, market_root=root, cache_root=cache)
    second = run_synthetic_fixture_study(
        path, input_root=root, market_root=root, cache_root=cache, workers=2
    )
    assert first["status"] == "PARTIAL_SYNTHETIC_FIXTURE_WITH_BLOCKERS"
    assert first["requested_scenarios"] == 15
    assert first["completed_scenarios"] == 5
    assert first["blocked_scenarios"] == 10
    assert second["cache_hits"] == 5
    assert first["logical_sha256"] == second["logical_sha256"]
    assert all(
        x["reason"] == "MISSING_COMPLETE_MANAGER_BOOK_WITHIN_WINDOW"
        for x in first["scenarios"]
        if x["status"] == "BLOCKED"
    )
    assert all(
        x["scenario"] == "three-wallet" for x in first["scenarios"] if x["status"] != "BLOCKED"
    )


def test_cross_dex_same_manager_fails_closed(tmp_path):
    path, root, cache, doc = sample(tmp_path)
    duplicate = dict(doc["sources"][0])
    duplicate["dex"] = "xyz"
    doc["sources"].append(duplicate)
    for scenario in doc["scenarios"]:
        for shock in scenario["stress_shocks"]:
            shock["hyperliquid:mainnet:perp:xyz:BTC"] = shock[BTC]
    path.write_text(json.dumps(doc))
    with pytest.raises(ManifestBlocked, match="CROSS_DEX_ACCOUNT_NEEDS_CONSOLIDATED_SOURCE_BOOK"):
        run_synthetic_fixture_study(path, input_root=root, market_root=root, cache_root=cache)


def test_vendor_fixture_flag_required(tmp_path):
    path, root, cache, doc = sample(tmp_path, fixture=False)
    with pytest.raises(ManifestBlocked, match="REAL_SOURCE_SWEEP_NOT_YET_CERTIFIED"):
        run_synthetic_fixture_study(path, input_root=root, market_root=root, cache_root=cache)


def test_nonflat_initial_book_fails_without_first_target_evidence(tmp_path):
    path, root, cache, doc = sample(tmp_path)
    file = root / "W001/book.json"
    contents = json.loads(file.read_text())
    contents["initial_books"][0]["positions"]["BTC"] = "1"
    contents["fills"][0]["position_before"] = "1"
    contents["fills"][0]["position_after"] = "2"
    data = json.dumps(contents).encode()
    file.write_bytes(data)
    doc["sources"][0]["book_sha256"] = sha256(data).hexdigest()
    path.write_text(json.dumps(doc))
    with pytest.raises(ManifestBlocked, match="MISSING_NONZERO_HEDGE_LEADER_PRICE"):
        run_synthetic_fixture_study(path, input_root=root, market_root=root, cache_root=cache)


def test_nonflat_initial_book_with_independent_marks_is_admitted(tmp_path):
    path, root, cache, doc = sample(tmp_path)
    file = root / "W001/book.json"
    contents = json.loads(file.read_text())
    contents["initial_books"][0]["positions"]["BTC"] = "1"
    contents["initial_books"][0]["leader_prices"] = {"BTC": "100"}
    contents["fills"][0]["position_before"] = "1"
    contents["fills"][0]["position_after"] = "2"
    raw = json.dumps(contents).encode()
    file.write_bytes(raw)
    doc["sources"][0]["book_sha256"] = sha256(raw).hexdigest()
    path.write_text(json.dumps(doc))
    out = run_synthetic_fixture_study(path, input_root=root, market_root=root, cache_root=cache)
    assert out["status"] == "COMPLETE_SYNTHETIC_FIXTURE_ONLY"
    assert out["requested_scenarios"] == 15
    assert all(x["status"] == "SYNTHETIC_PM03_OPEN" for x in out["scenarios"])


def test_prospective_synthetic_receipts_are_joined_to_actual_fill_ids(tmp_path):
    path, root, cache, doc = sample(tmp_path)
    doc["clock_basis"] = "PROSPECTIVE_FIRST_KNOWN"
    for item in doc["sources"]:
        manager = item["account"]
        book_file = root / item["book_path"]
        book = json.loads(book_file.read_text())
        anchor = book["initial_books"][0]
        anchor["source_event_at"] = (START - timedelta(minutes=2)).isoformat()
        fill = book["fills"][0]
        fill["first_known_at"] = (START + timedelta(seconds=5)).isoformat()
        raw = json.dumps(book).encode()
        book_file.write_bytes(raw)
        item["book_sha256"] = sha256(raw).hexdigest()
        observations = [
            {
                "account": manager,
                "dex": "default",
                "instrument": "*",
                "event_id": "__opening__",
                "source_event_at": anchor["source_event_at"],
                "first_known_at": anchor["first_known_at"],
            },
            {
                "account": manager,
                "dex": "default",
                "instrument": "BTC",
                "event_id": "1",
                "source_event_at": fill["source_event_at"],
                "first_known_at": fill["first_known_at"],
            },
        ]
        receipts = root / manager / "receipts.json"
        payload = {
            "schema": "pm_offline_receipt_bundle_v1",
            "producer": "synthetic-receipt-fixture",
            "capture_method": "PERSISTED_LOCAL_RECEIPT",
            "observations": observations,
        }
        receipts.write_text(json.dumps(payload))
        item.update(
            first_known_basis="PROSPECTIVE_FIRST_KNOWN",
            receipt_path=str(receipts.relative_to(root)),
            receipt_sha256=sha256(receipts.read_bytes()).hexdigest(),
        )
    path.write_text(json.dumps(doc))
    result = run_synthetic_fixture_study(path, input_root=root, market_root=root, cache_root=cache)
    assert result["status"] == "COMPLETE_SYNTHETIC_FIXTURE_ONLY"
    assert result["financial_certified_real"] is False
    # A changed receipt file that still hashes correctly cannot backdate a
    # source fill without changing its independently matched source clock.
    receipts = root / "W001" / "receipts.json"
    tampered = json.loads(receipts.read_text())
    tampered["observations"][1]["first_known_at"] = (START + timedelta(minutes=1)).isoformat()
    receipts.write_text(json.dumps(tampered))
    doc["sources"][0]["receipt_sha256"] = sha256(receipts.read_bytes()).hexdigest()
    path.write_text(json.dumps(doc))
    with pytest.raises(ManifestBlocked, match="SOURCE_AND_RECEIPT_CLOCK_MISMATCH"):
        run_synthetic_fixture_study(path, input_root=root, market_root=root, cache_root=cache)


def test_mismatched_follower_equity_and_rulebook_rejected(tmp_path):
    path, root, cache, doc = sample(tmp_path)
    doc["follower_initial_equity"] = "9999"
    path.write_text(json.dumps(doc))
    with pytest.raises(ValueError, match="FOLLOWER_EQUITY_RULEBOOK_CONFLICT"):
        run_synthetic_fixture_study(path, input_root=root, market_root=root, cache_root=cache)


def test_market_metadata_tampering_blocks_even_with_sealed_warm_cache(tmp_path):
    path, root, cache, doc = sample(tmp_path)
    first = run_synthetic_fixture_study(path, input_root=root, market_root=root, cache_root=cache)
    assert first["requested_scenarios"] == 15
    sidecar = root / doc["market_days"][0]["metadata_path"]
    sidecar.write_text(sidecar.read_text() + " ")
    with pytest.raises(ManifestBlocked, match="MARKET_METADATA_SHA_MISMATCH"):
        run_synthetic_fixture_study(path, input_root=root, market_root=root, cache_root=cache)


def test_source_sha_tamper_blocks_without_cache_reuse(tmp_path):
    path, root, cache, doc = sample(tmp_path)
    (root / "W001/book.json").write_text("changed")
    with pytest.raises(ManifestBlocked, match="BOOK_SHA_MISMATCH"):
        run_synthetic_fixture_study(path, input_root=root, market_root=root, cache_root=cache)
