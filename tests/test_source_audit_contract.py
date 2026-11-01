"""Byte-level source audit adversarial cases; all addresses and books are synthetic."""

import asyncio
from datetime import UTC, datetime
from hashlib import sha256
import json

import pytest

from copytrade_pm.pm_e4_prospective import SUBSCRIPTIONS
from copytrade_pm.pm_e4_source_readiness import audit
from copytrade_pm.pm_e4_stream import _receive, capture_book_change

START = "2026-11-01T12:00:00+00:00"
AT = "2026-11-01T12:00:01+00:00"
END = "2026-11-01T12:00:02+00:00"
PODS = ("W028", "W042", "W030")


def write(path, value):
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    raw = json.dumps(value, sort_keys=True).encode()
    path.write_bytes(raw)
    path.chmod(0o600)
    return sha256(raw).hexdigest()


def fixture(root):
    root.chmod(0o700)
    directory = root / "gE420261101T120000000000Z-12345678"
    directory.mkdir(mode=0o700)
    addresses = {p: "0x" + str(i + 1) * 40 for i, p in enumerate(PODS)}
    report = {
        "schema": "e4_live_readonly_stream_session_v2",
        "started_at": START,
        "finished_at": END,
        "trading_authorized": False,
        "errors": [],
        "disconnect_reason": "BOUNDED_SESSION_ROTATION",
        "subjects": {p: sha256(a.encode()).hexdigest() for p, a in addresses.items()},
        "snapshots": {},
        "subaccount_counts": dict.fromkeys(PODS, 0),
        "discovery_receipts": {},
    }
    catalog_sha = write(directory / "discovery/dex_catalog.json", [None])
    report["dex_catalog_sha256"] = catalog_sha
    report["discovery_receipts"]["dex_catalog.json"] = {
        "sha256": catalog_sha,
        "requested_at": START,
        "received_at": AT,
    }
    serial = 0
    for pod, address in addresses.items():
        census_sha = write(directory / f"discovery/{pod}-subaccounts.json", None)
        report["discovery_receipts"][f"{pod}-subaccounts.json"] = {
            "sha256": census_sha,
            "requested_at": START,
            "received_at": AT,
            "request": {"type": "subAccounts", "user": address},
        }
        frames = [
            {
                "channel": "subscriptionResponse",
                "data": {
                    "subscription": {"type": kind, "user": address},
                },
            }
            for kind in SUBSCRIPTIONS
        ]
        frames.append(
            {
                "channel": "allDexsClearinghouseState",
                "data": {
                    "user": address,
                    "clearinghouseStates": [
                        [
                            "",
                            {
                                "marginSummary": {
                                    "accountValue": "10",
                                    "totalNtlPos": "0",
                                    "totalMarginUsed": "0",
                                },
                                "assetPositions": [],
                                "time": 1793534400000,
                            },
                        ]
                    ],
                },
            }
        )
        for frame in frames:
            name = f"{serial:08d}.json"
            frame_sha = write(directory / "frames" / name, frame)
            write(
                directory / "metadata" / name,
                {
                    "filename": name,
                    "source_raw_sha256": frame_sha,
                    "channel": frame["channel"],
                    "subject": pod,
                    "locally_received_at": AT,
                },
            )
            if frame["channel"] == "allDexsClearinghouseState":
                report["snapshots"][pod] = {
                    "locally_received_at": AT,
                    "nonzero_positions": 0,
                    "perp_dexs_seen": 1,
                    "official_dex_catalog_parity": True,
                    "last_frame_sha256": frame_sha,
                }
            serial += 1
    report["frames_stored"] = serial
    write(directory / "session-report.json", report)
    return directory


def test_verified_bounded_capture_is_never_qualified(tmp_path):
    fixture(tmp_path)
    result = audit(tmp_path, "A", as_of=datetime.fromisoformat(END))
    assert result["all_generations_integrity_pass"]
    assert result["recent_completed_capture"]
    assert not result["scientifically_qualified"]
    assert not result["continuous_account_book_qualified"]
    assert not result["equity_collateral_funding_transfers_reconciled"]


@pytest.mark.parametrize("tamper", ["receipt", "census", "snapshot", "permission", "symlink"])
def test_tampering_with_receipts_identity_claims_or_permissions_fails(tmp_path, tamper):
    directory = fixture(tmp_path)
    if tamper == "receipt":
        path = directory / "metadata/00000005.json"
        value = json.loads(path.read_text())
        value["locally_received_at"] = "2026-11-01T13:00:00+00:00"
        write(path, value)
    elif tamper == "census":
        write(directory / "discovery/W028-subaccounts.json", [{"master": "wrong"}])
    elif tamper == "snapshot":
        path = directory / "session-report.json"
        value = json.loads(path.read_text())
        value["snapshots"]["W028"]["nonzero_positions"] = 100
        write(path, value)
    elif tamper == "permission":
        (directory / "frames/00000005.json").chmod(0o644)
    else:
        original = directory / "frames/00000005.json"
        other = directory / "original.json"
        original.rename(other)
        original.symlink_to(other)
    assert not audit(tmp_path, "A")["all_generations_integrity_pass"]


def test_partial_account_window_is_integrity_only_and_records_missing_accounts(tmp_path):
    directory = fixture(tmp_path)
    path = directory / "session-report.json"
    report = json.loads(path.read_text())
    report["observed_scope_subjects"] = ["W028", "W042"]
    report["snapshots"].pop("W030")
    for serial in range(12, 18):
        (directory / f"frames/{serial:08d}.json").unlink()
        (directory / f"metadata/{serial:08d}.json").unlink()
    report["frames_stored"] = 12
    write(path, report)
    result = audit(tmp_path, "A", as_of=datetime.fromisoformat(END))
    assert result["all_generations_integrity_pass"]
    assert result["prospective_generations"][0]["unobserved_subjects"] == ["W030"]
    assert not result["prospective_generations"][0]["complete_account_scope_observed"]
    assert not result["recent_discovered_accounts_observed"]


def test_first_receipt_is_captured_before_downstream_processing():
    async def check():
        class Socket:
            async def recv(self):
                return "wire"

        received_at, raw = await _receive(Socket())
        processing_at = datetime.now(UTC)
        assert received_at <= processing_at
        assert raw == "wire"

    asyncio.run(check())


def test_leverage_change_is_captured_before_periodic_checkpoint():
    at = datetime.fromisoformat(AT)
    last = {}
    kwargs = dict(
        subject="W028", positions={"BTC": "1"}, observed_at=at, last=last, sample_seconds=300
    )
    capture_book_change(**kwargs, risk_metadata={"BTC": {"leverage": 2}})
    assert capture_book_change(**kwargs, risk_metadata={"BTC": {"leverage": 3}}) == (True, False)
