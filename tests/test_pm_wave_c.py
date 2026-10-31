"""Wave C intake contract: versioned two-wallet cohort beside the frozen 36."""

from __future__ import annotations

import gzip
from datetime import UTC, datetime
from hashlib import sha256
import json
from pathlib import Path

import pytest

from copytrade_pm.pm_portfolio import (
    Coverage,
    WalletSource,
    validate_36_wallet_cohort,
    validate_38_wallet_cohort,
)
from copytrade_pm.pm_sources import CohortEntry
from copytrade_pm.pm_wave_c import (
    ACCEPTED,
    IDENTITY,
    MANIFEST,
    REPLAY_WINDOW_START,
    TARGETS,
    _write_manifest,
    audit_generation,
    load_wave_c,
)

ADDRESS_A = "0x" + "a" * 40
ADDRESS_B = "0x" + "b" * 40
ALIAS_A = "N001-HYPE"
ALIAS_B = "S031-BTC"
WINDOW_MS = int(REPLAY_WINDOW_START.timestamp() * 1000) + 86_400_000
DAY = datetime.fromtimestamp(WINDOW_MS / 1000, UTC).date().isoformat()


def _fill(
    tid: int, when: int, coin: str, *, before: str = "0", size: str = "1"
) -> dict[str, object]:
    return {
        "tid": tid,
        "time": when,
        "coin": coin,
        "side": "B",
        "sz": size,
        "start_position": before,
        "px": "100",
        "user": "0x" + "0" * 40,
    }


def _generation(gen: Path, pairs: dict[str, dict[str, list[list[dict[str, object]]]]]) -> Path:
    gen.mkdir(parents=True, exist_ok=True)
    summary = {
        "schema": "wavec_hyperx_fills_generation_v1",
        "adapter_sha256": "e" * 64,
        "created_at_utc": "2026-10-31T06:30:04+00:00",
        "no_live_orders": True,
        "no_trading_api": True,
    }
    (gen / "run-summary.json").write_text(json.dumps(summary))
    addresses = {ALIAS_A: ADDRESS_A, ALIAS_B: ADDRESS_B}
    for alias, coins in pairs.items():
        address = addresses[alias]
        for coin, pages in coins.items():
            directory = gen / alias / coin
            directory.mkdir(parents=True, exist_ok=True)
            for number, fills in enumerate(pages, 1):
                document = {
                    "address": address,
                    "page": number,
                    "page_size": 2000,
                    "has_more": number < len(pages),
                    "fills": fills,
                }
                raw = json.dumps(document).encode()
                (directory / f"page-{number:05d}.json.gz").write_bytes(gzip.compress(raw))
                (directory / f"page-{number:05d}.meta.json").write_text(
                    json.dumps(
                        {
                            "alias": alias,
                            "coin": coin,
                            "page": number,
                            "sha256": sha256(raw).hexdigest(),
                            "address_sha256": sha256(address.encode()).hexdigest(),
                        }
                    )
                )
    return gen


def _market_day(store: Path, coin: str, day: str) -> None:
    year, month, date = day.split("-")
    directory = (
        store
        / f"crypto_futures_ohlcv_1m_HYPERLIQUID_{coin}_PERP"
        / f"year={year}/month={month}/day={date}"
    )
    directory.mkdir(parents=True, exist_ok=True)
    data = b"parquet"
    (directory / "data.parquet").write_bytes(data)
    (directory / "source.json").write_text(
        json.dumps(
            {
                "exchange": "hyperliquid_futures",
                "source_symbol": coin,
                "sha256": sha256(data).hexdigest(),
            }
        )
    )


def _propr(root: Path, coins: tuple[str, ...]) -> None:
    (root / "PROPR_PUBLIC_ASSET_UNIVERSE_20261030.json").write_text(
        json.dumps(
            {
                "schema": "propr_public_universe_browser_snapshot_v1",
                "market_symbols": {"crypto": list(coins)},
            }
        )
    )


def _chain(alias: str, coin: str, *, broken: bool = False) -> list[list[dict[str, object]]]:
    if broken:
        return [[_fill(1, WINDOW_MS, coin), _fill(2, WINDOW_MS + 1000, coin, before="5")]]
    return [[_fill(1, WINDOW_MS, coin), _fill(2, WINDOW_MS + 1000, coin, before="1")]]


def _accepted(tmp_path: Path) -> tuple[Path, Path, Path]:
    root = tmp_path / "research"
    root.mkdir()
    market = tmp_path / "store"
    generation = _generation(
        root / "slow_pod_data_v1/wave_c_v1/gTEST",
        {
            ALIAS_A: {"HYPE": _chain(ALIAS_A, "HYPE")},
            ALIAS_B: {"BTC": _chain(ALIAS_B, "BTC")},
        },
    )
    _write_manifest(generation)
    _market_day(market, "HYPE", DAY)
    _market_day(market, "BTC", DAY)
    _propr(root, ("BTC", "HYPE"))
    return root, generation, market


def _install(root: Path, generation: Path, market: Path, *, verdict: str | None = None) -> None:
    result = audit_generation(generation, root, market)
    if verdict is not None:
        result["verdict"] = verdict
    integrity = root / "slow_pod_data_v1/wave_c_v1/wave-c-integrity-test.json"
    integrity.write_text(json.dumps(result, sort_keys=True))
    identities = {ALIAS_A: ADDRESS_A, ALIAS_B: ADDRESS_B}
    identity = root / IDENTITY
    identity.write_text(json.dumps(identities))
    identity.chmod(0o600)
    targets = {
        "schema": "wave_c_cohort_targets_v1",
        "cohort": "waveC",
        "count": 2,
        "replay_window_start": REPLAY_WINDOW_START.isoformat(),
        "generation": str(generation.relative_to(root)),
        "generation_manifest_sha256": sha256((generation / MANIFEST).read_bytes()).hexdigest(),
        "integrity_result": str(integrity.relative_to(root)),
        "targets": [
            {"alias": ALIAS_A, "address_sha256": sha256(ADDRESS_A.encode()).hexdigest(), "coins": ["HYPE"]},
            {"alias": ALIAS_B, "address_sha256": sha256(ADDRESS_B.encode()).hexdigest(), "coins": ["BTC"]},
        ],
    }
    path = root / TARGETS
    path.write_text(json.dumps(targets, sort_keys=True))
    path.chmod(0o600)


def _frozen(alias: str = "W044", address: str = "0x" + "c" * 40) -> tuple[CohortEntry, ...]:
    return (
        CohortEntry(
            alias,
            "original",
            address,
            sha256(address.encode()).hexdigest(),
            "VENDOR_ROSTER_CACHED_HISTORICAL_ONLY",
            1,
            1,
        ),
    )


def _frozen36() -> tuple[CohortEntry, ...]:
    groups = (("original", 6), ("wave1", 10), ("wave2", 20))
    entries = []
    for cohort, count in groups:
        for index in range(count):
            address = "0x" + f"{cohort[:1]}{index:039d}"
            entries.append(
                CohortEntry(
                    f"{cohort}{index}",
                    cohort,
                    address,
                    sha256(address.encode()).hexdigest(),
                    "VENDOR_ROSTER_CACHED_HISTORICAL_ONLY",
                    1,
                    1,
                )
            )
    return tuple(entries)


def test_audit_accepts_contiguous_in_window_generation(tmp_path):
    root, generation, market = _accepted(tmp_path)
    result = audit_generation(generation, root, market)
    assert result["verdict"] == ACCEPTED
    assert result["blockers"] == []
    assert result["source_fills_in_window"] == 4
    assert result["source_fills_before_window"] == 0
    assert result["frozen_cohort_rewritten"] is False
    assert result["scientifically_qualified"] is False
    assert result["prospective_first_known"] == "UNKNOWN"
    assert [wallet["chain_breaks_in_window"] for wallet in result["wallets"]] == [0, 0]


def test_audit_blocks_in_window_chain_break(tmp_path):
    root = tmp_path / "research"
    root.mkdir()
    market = tmp_path / "store"
    generation = _generation(
        root / "slow_pod_data_v1/wave_c_v1/gTEST",
        {
            ALIAS_A: {"HYPE": _chain(ALIAS_A, "HYPE", broken=True)},
            ALIAS_B: {"BTC": _chain(ALIAS_B, "BTC")},
        },
    )
    _write_manifest(generation)
    _market_day(market, "HYPE", DAY)
    _market_day(market, "BTC", DAY)
    _propr(root, ("BTC", "HYPE"))
    result = audit_generation(generation, root, market)
    assert result["verdict"] == "BLOCKED"
    assert f"{ALIAS_A}:CHAIN_BREAK_IN_WINDOW" in result["blockers"]


def test_audit_blocks_unverified_native_market_day(tmp_path):
    root, generation, market = _accepted(tmp_path)
    (market / "crypto_futures_ohlcv_1m_HYPERLIQUID_BTC_PERP").rename(
        market / "moved"
    )
    result = audit_generation(generation, root, market)
    assert result["verdict"] == "BLOCKED"
    assert f"{ALIAS_B}:UNVERIFIED_NATIVE_MARKET_DAY" in result["blockers"]


def test_audit_blocks_duplicate_tid_across_pages(tmp_path):
    root = tmp_path / "research"
    root.mkdir()
    market = tmp_path / "store"
    generation = _generation(
        root / "slow_pod_data_v1/wave_c_v1/gTEST",
        {
            ALIAS_A: {
                "HYPE": [
                    [_fill(1, WINDOW_MS, "HYPE")],
                    [_fill(1, WINDOW_MS + 1000, "HYPE", before="1")],
                ]
            },
            ALIAS_B: {"BTC": _chain(ALIAS_B, "BTC")},
        },
    )
    _write_manifest(generation)
    _market_day(market, "HYPE", DAY)
    _market_day(market, "BTC", DAY)
    _propr(root, ("BTC", "HYPE"))
    result = audit_generation(generation, root, market)
    assert result["verdict"] == "BLOCKED"
    assert f"{ALIAS_A}:DUPLICATE_TIDS" in result["blockers"]


def test_audit_rejects_manifest_drift(tmp_path):
    root, generation, market = _accepted(tmp_path)
    manifest = json.loads((generation / MANIFEST).read_text())
    manifest["source_fills"] += 1
    (generation / MANIFEST).write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="WAVE_C_GENERATION_MANIFEST_DRIFT"):
        audit_generation(generation, root, market)


def test_loader_extends_frozen_cohort_to_38(tmp_path):
    root, generation, market = _accepted(tmp_path)
    _install(root, generation, market)
    frozen = _frozen36()
    entries, fingerprints = load_wave_c(root, frozen)
    assert [entry.alias for entry in entries] == [ALIAS_A, ALIAS_B]
    assert all(entry.cohort == "waveC" for entry in entries)
    assert {entry.address for entry in entries} == {ADDRESS_A, ADDRESS_B}
    assert fingerprints["wave_c_generation_manifest"] == sha256(
        (generation / MANIFEST).read_bytes()
    ).hexdigest()
    wallets = [entry.wallet for entry in (*frozen, *entries)]
    validate_38_wallet_cohort(wallets)
    with pytest.raises(ValueError):
        validate_36_wallet_cohort(wallets)


def test_loader_rejects_alias_collision_with_frozen_cohort(tmp_path):
    root, generation, market = _accepted(tmp_path)
    _install(root, generation, market)
    with pytest.raises(ValueError, match="collides with frozen cohort"):
        load_wave_c(root, _frozen(alias=ALIAS_A))


def test_loader_rejects_address_collision_with_frozen_cohort(tmp_path):
    root, generation, market = _accepted(tmp_path)
    _install(root, generation, market)
    with pytest.raises(ValueError, match="collides with frozen cohort"):
        load_wave_c(root, _frozen(address=ADDRESS_B))


def test_loader_rejects_unaccepted_integrity(tmp_path):
    root, generation, market = _accepted(tmp_path)
    _install(root, generation, market, verdict="BLOCKED")
    with pytest.raises(ValueError, match="not independently accepted"):
        load_wave_c(root, _frozen())


def test_loader_rejects_replay_window_drift(tmp_path):
    root, generation, market = _accepted(tmp_path)
    _install(root, generation, market)
    targets = json.loads((root / TARGETS).read_text())
    targets["replay_window_start"] = "2026-01-01T00:00:00+00:00"
    (root / TARGETS).write_text(json.dumps(targets))
    with pytest.raises(ValueError, match="replay window changed"):
        load_wave_c(root, _frozen())


def test_loader_rejects_generation_manifest_lineage(tmp_path):
    root, generation, market = _accepted(tmp_path)
    _install(root, generation, market)
    targets = json.loads((root / TARGETS).read_text())
    targets["generation_manifest_sha256"] = "f" * 64
    (root / TARGETS).write_text(json.dumps(targets))
    with pytest.raises(ValueError, match="lineage mismatch"):
        load_wave_c(root, _frozen())


def test_validate_38_rejects_37_wallets():
    wallets = [
        *(WalletSource(f"o{i}", "original", Coverage.HISTORICAL_ONLY) for i in range(6)),
        *(WalletSource(f"a{i}", "wave1", Coverage.HISTORICAL_ONLY) for i in range(10)),
        *(WalletSource(f"b{i}", "wave2", Coverage.HISTORICAL_ONLY) for i in range(20)),
        WalletSource(ALIAS_A, "waveC", Coverage.HISTORICAL_ONLY),
    ]
    with pytest.raises(ValueError, match="incomplete PM cohort"):
        validate_38_wallet_cohort(wallets)
    wallets.append(WalletSource(ALIAS_B, "waveC", Coverage.HISTORICAL_ONLY))
    assert len(validate_38_wallet_cohort(wallets)) == 38
