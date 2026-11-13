"""Independent official multi-DEX source census is strictly non-actionable."""

from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
import stat
import json

import pytest

from copytrade_pm.pm_vike_official_parity import (
    check_single_vike_event_against_official,
    independent_official_census,
    archive_independent_census,
    verify_archived_official_census,
    audit_selected_campaign,
)

ADDRESS = "0x" + "a" * 40
NOW_MS = int(datetime.now(UTC).timestamp() * 1000)


def provider(*, wrong_wallet=False, missing=False, skew_ms=500, bad_hash=False):
    def fetch(request):
        if request["type"] == "perpDexs":
            payload = [None, {"name": "xyz"}]
        elif request["type"] == "clearinghouseState":
            dex = request.get("dex", "default")
            payload = {
                "time": NOW_MS + (skew_ms if dex == "xyz" else 0),
                "marginSummary": {
                    "accountValue": "1000",
                    "totalNtlPos": "500",
                    "totalMarginUsed": "50",
                },
                "assetPositions": (
                    []
                    if missing and dex == "xyz"
                    else [
                        {
                            "position": {
                                "coin": "xyz:TSLA" if dex == "xyz" else "BTC",
                                "szi": "-2" if dex == "xyz" else "4",
                            }
                        }
                    ]
                ),
            }
        else:
            raise AssertionError("unexpected official request")
        raw = json.dumps(payload, sort_keys=True).encode()
        return payload, raw, ("0" * 64 if bad_hash else sha256(raw).hexdigest())

    return fetch


def event(*, quantity=4):
    return {
        "schema": "vike.event.v1",
        "event_id": f"hl.positions:{ADDRESS}:1794310000000:123",
        "source": "hl.positions",
        "kind": "position",
        "ts": datetime.fromtimestamp((NOW_MS - 1000) / 1000, UTC).isoformat(),
        "subject": {"wallet": ADDRESS, "symbol": "BTC"},
        "data": {
            "action": "increase",
            "side": "buy",
            "size_token": 1,
            "start_position": 3,
            "position_after": quantity,
            "trade_id": 123,
            "dex": "HL",
        },
    }


def test_independent_official_perp_census_all_dex_complete_but_not_actionable():
    snapshot = independent_official_census(ADDRESS, info=provider())
    assert snapshot["dex_count"] == 2
    assert snapshot["position_count"] == 2
    assert snapshot["positions"] == {
        "hyperliquid/mainnet:perp:default/BTC": "4",
        "hyperliquid/mainnet:perp:xyz/TSLA": "-2",
    }
    assert snapshot["provider_time_skew_ms"] == 500
    assert snapshot["scope_parity"] is True
    assert snapshot["new_risk_eligible"] is False
    assert snapshot["continuous_observation_proven"] is False
    assert snapshot["first_known_transition"] is None
    assert check_single_vike_event_against_official(event(), snapshot)["status"] == (
        "CONSISTENT_SINGLE_EVENT_NOT_COMPLETE_PROOF"
    )


def test_original_rest_responses_archived_with_private_manifest_last(tmp_path):
    root = tmp_path / "private-official"
    result = archive_independent_census(ADDRESS, root=root, info=provider())
    target = Path(result["archive"])
    assert result["dex_count"] == 2
    assert stat.S_IMODE(root.stat().st_mode) == 0o700
    report = json.loads((target / "manifest.json").read_text())
    assert report["schema"] == "copytrade_independent_official_rest_archive_v1"
    assert report["v4_paper_source_eligible"] is False
    assert len(report["original_files"]) == 3
    for item in report["original_files"]:
        original = target / item["name"]
        assert stat.S_IMODE(original.stat().st_mode) == 0o600
        assert sha256(original.read_bytes()).hexdigest() == item["sha256"]
    assert sha256((target / "manifest.json").read_bytes()).hexdigest() == result["manifest_sha256"]
    independent = verify_archived_official_census(
        ADDRESS, directory=target, manifest_sha256=result["manifest_sha256"]
    )
    assert independent["positions"] == report["census"]["positions"]
    assert independent["original_bytes_independently_verified"] is True
    assert independent["new_risk_eligible"] is False
    with pytest.raises(ValueError, match="ACCOUNT_MISMATCH"):
        verify_archived_official_census(
            "0x" + "b" * 40,
            directory=target,
            manifest_sha256=result["manifest_sha256"],
        )
    native_path = target / "raw-default.json"
    native_path.write_bytes(native_path.read_bytes() + b" ")
    with pytest.raises(ValueError, match="FILE_HASH_MISMATCH"):
        verify_archived_official_census(
            ADDRESS, directory=target, manifest_sha256=result["manifest_sha256"]
        )
    (tmp_path / "private-link").symlink_to(root, target_is_directory=True)
    with pytest.raises(ValueError, match="ARCHIVE_SYMLINK"):
        archive_independent_census(ADDRESS, root=tmp_path / "private-link", info=provider())


def test_campaign_verification_report_never_promotes_rest_census(monkeypatch, tmp_path):
    from types import SimpleNamespace
    from copytrade_pm import pm_v4_sixteen_scenarios

    def campaign(**kwargs):
        return SimpleNamespace(parents={str(i): "0x" + format(i, "040x") for i in range(1, 15)})

    monkeypatch.setattr(pm_v4_sixteen_scenarios, "load_campaign", campaign)
    report = audit_selected_campaign(
        registry_db=tmp_path / "registry.sqlite",
        manifest=tmp_path / "manifest.json",
        manifest_sha256="a" * 64,
        root=tmp_path / "captured",
        at="2026-11-11T12:00:00Z",
        info=provider(),
    )
    assert report["selected_parent_count"] == 14
    assert report["independent_census_verified"] == 14
    assert report["continuous_coverage_verified"] == 0
    assert report["paper_new_risk_eligible"] == 0
    assert len(report["accounts"]) == 14


def test_independent_census_rejects_skew_and_tampered_raw_bytes():
    with pytest.raises(ValueError, match="NONATOMIC_SKEW"):
        independent_official_census(ADDRESS, info=provider(skew_ms=31_000))
    with pytest.raises(ValueError, match="CATALOG_HASH"):
        independent_official_census(ADDRESS, info=provider(bad_hash=True))


def test_independent_census_detects_event_disagreement_without_admitting_exit():
    snapshot = independent_official_census(ADDRESS, info=provider())
    result = check_single_vike_event_against_official(event(quantity=5), snapshot)
    assert result["status"] == "DIVERGENT_REQUIRES_CAUSAL_FILL_RECONCILIATION"
    assert result["paper_eligible"] is False
    assert result["whole_book_complete_history_proven"] is False
    with pytest.raises(ValueError, match="ACCOUNT_MISMATCH"):
        corrupted = event()
        corrupted["subject"]["wallet"] = "0x" + "b" * 40
        corrupted["event_id"] = corrupted["event_id"].replace(
            ADDRESS, corrupted["subject"]["wallet"]
        )
        check_single_vike_event_against_official(corrupted, snapshot)


def test_stale_or_future_vendor_events_cannot_be_reinterpreted_as_source_entry():
    snapshot = independent_official_census(ADDRESS, info=provider())
    late = event()
    late["ts"] = datetime.fromtimestamp((NOW_MS - 300_000) / 1000, UTC).isoformat()
    assert (
        check_single_vike_event_against_official(late, snapshot)["status"]
        == "INDETERMINATE_TEMPORAL_SCOPE"
    )


def test_official_rest_incomplete_per_dex_fails_closed():
    def incomplete(request):
        payload, raw, digest = provider()(request)
        if request["type"] == "clearinghouseState" and request.get("dex") == "xyz":
            del payload["marginSummary"]
            raw = json.dumps(payload, sort_keys=True).encode()
            digest = sha256(raw).hexdigest()
        return payload, raw, digest

    with pytest.raises(ValueError, match="MISSING_MARGIN"):
        independent_official_census(ADDRESS, info=incomplete)
