"""Shared Vike fill journal: native identity, PIT clocks and restart recovery."""

from contextlib import closing
from datetime import UTC, datetime, timedelta

import pytest

from copytrade_pm.pm_vike_selected_fills import (
    apply_frame,
    current_cursor,
    had_gap,
    open_selected_journal,
    record_event,
    selected_subscription,
    selected_campaign_wallets,
    selected_wallets_from_registry,
)


W1 = "0x" + "a" * 40
W2 = "0x" + "b" * 40
T = datetime.now(UTC)


def event(wallet=W1, tid=101, *, usd=3.5):
    return {
        "schema": "vike.event.v1",
        "source": "hl.fills",
        "kind": "fill",
        "event_id": f"hl.fills:{wallet}:test:{tid}",
        "subject": {"wallet": wallet, "symbol": "xyz:BRENTOIL"},
        "ts": (T - timedelta(seconds=2)).isoformat(),
        "data": {"trade_id": tid, "price": 65, "size_token": 0.05, "size_usd": usd, "side": "buy"},
    }


def frame(wallet=W1, tid=101, cursor="1793930404464-0001"):
    return {
        "type": "event",
        "ids": ["copytrade_selected"],
        "cursor": cursor,
        "event": event(wallet, tid),
    }


def test_selected_wallets_derive_from_sealed_registry_without_addresses_in_output(
    tmp_path,
    monkeypatch,
):
    from test_pm_forward_multi_portfolio import full_registry, pin_reviewed_registry
    from test_pm_forward_observed_paper import at

    pin_reviewed_registry(monkeypatch)
    database = full_registry(tmp_path)
    selected = selected_wallets_from_registry(
        database,
        portfolios=("P14", "P16"),
        as_of=at(0),
    )
    assert len(selected) == 5
    assert selected == tuple(sorted(set(selected)))
    assert all(addr.startswith("0x") and len(addr) == 42 for addr in selected)
    with pytest.raises(ValueError, match="PORTFOLIO_IDS_INVALID"):
        selected_wallets_from_registry(
            database,
            portfolios=("P14", "P14"),
            as_of=at(0),
        )
    # Legacy fixture lacks authentic P1 portfolio seal; it is not silently
    # promoted to a live allowlist by merely matching alias names.
    with pytest.raises(ValueError, match="SEAL_NOT_VERIFIED"):
        selected_wallets_from_registry(
            database,
            portfolios=("P1",),
            as_of=at(0),
        )


def test_sixteen_campaign_selects_exactly_fourteen_unique_registry_checked_parents(
    monkeypatch, tmp_path
):
    from types import SimpleNamespace
    from copytrade_pm import pm_source_campaign_roster as scenarios

    expected = tuple("0x" + format(i, "040x") for i in range(1, 15))
    seen = {}

    def stub_load_campaign(**kwargs):
        seen.update(kwargs)
        return SimpleNamespace(
            profiles={pid: object() for pid in scenarios.IDENTITIES},
            parents={str(i): address for i, address in enumerate(reversed(expected))},
        )

    monkeypatch.setattr(scenarios, "load_campaign", stub_load_campaign)
    wallets = selected_campaign_wallets(
        registry_db=tmp_path / "registry.sqlite",
        manifest=tmp_path / "sealed-private.json",
        manifest_sha256="a" * 64,
        as_of="2026-11-11T10:00:00+00:00",
    )
    assert wallets == expected
    assert seen["registry_db"] == tmp_path / "registry.sqlite"
    assert seen["manifest"] == tmp_path / "sealed-private.json"
    assert seen["expected_sha256"] == "a" * 64
    assert selected_subscription(wallets, None)["filter"]["min_usd"] == 0

    def duplicate_campaign(**kwargs):
        return SimpleNamespace(
            profiles={pid: object() for pid in scenarios.IDENTITIES},
            parents={str(i): expected[0] for i in range(14)},
        )

    monkeypatch.setattr(scenarios, "load_campaign", duplicate_campaign)
    with pytest.raises(ValueError, match="COHORT_NOT_14"):
        selected_campaign_wallets(
            registry_db=tmp_path / "registry.sqlite",
            manifest=tmp_path / "sealed-private.json",
            manifest_sha256="a" * 64,
            as_of="2026-11-11T10:00:00+00:00",
        )


def test_shared_subscription_zero_minimum_and_distinct_native_wallets():
    sub = selected_subscription((W2, W1), None)
    assert sub["filter"] == {"wallet": [W1, W2], "min_usd": 0}
    with pytest.raises(ValueError, match="UNIVERSE_INVALID"):
        selected_subscription((W1, W1), None)


def test_server_pings_are_persisted_without_any_selected_wallet_fills(tmp_path):
    root = tmp_path / "selected"
    with closing(open_selected_journal(root)) as db:
        assert (
            apply_frame(
                db,
                {
                    "type": "subscribed",
                    "id": "copytrade_selected",
                    "channel": "hl.fills",
                    "cursor": "1793930404464-0000",
                },
                (W1, W2),
                T.isoformat(),
            )
            == "SUBSCRIBED"
        )
        assert (
            apply_frame(
                db,
                {"type": "ping"},
                (W1, W2),
                T.isoformat(),
            )
            == "PONG_REQUIRED"
        )
        assert (
            apply_frame(
                db,
                {"type": "ping"},
                (W1, W2),
                T.isoformat(),
            )
            == "PONG_REQUIRED"
        )
    with closing(open_selected_journal(root)) as db:
        assert db.execute(
            "SELECT ping_count, subscription_count FROM selected_transport WHERE id=1"
        ).fetchone() == (2, 1)
        assert db.execute("SELECT COUNT(*) FROM selected_fills").fetchone()[0] == 0


def test_two_wallets_atomic_cursor_dedupe_and_private_restart(tmp_path):
    root = tmp_path / "selected"
    with closing(open_selected_journal(root)) as db:
        assert apply_frame(db, frame(), (W1, W2), T.isoformat()) == "PROSPECTIVE_FILL"
        assert (
            apply_frame(db, frame(W2, 102, "1793930404464-0002"), (W1, W2), T.isoformat())
            == "PROSPECTIVE_FILL"
        )
        assert apply_frame(db, frame(), (W1, W2), T.isoformat()) == "DUPLICATE"
        assert current_cursor(db) == "1793930404464-0002"
        assert db.execute("SELECT count(*) FROM selected_fills").fetchone()[0] == 2
        assert db.execute("SELECT min(prospective) FROM selected_fills").fetchone()[0] == 1
    with closing(open_selected_journal(root)) as db:
        assert current_cursor(db) == "1793930404464-0002"
        assert db.execute("SELECT count(*) FROM selected_fills").fetchone()[0] == 2
    assert root.stat().st_mode & 0o777 == 0o700
    assert (root / "selected-fills.sqlite3").stat().st_mode & 0o777 == 0o600


def test_duplicate_payload_drift_does_not_advance_checkpoint(tmp_path):
    with closing(open_selected_journal(tmp_path / "selected")) as db:
        apply_frame(db, frame(), (W1, W2), T.isoformat())
        altered = frame(cursor="1793930404464-0002")
        altered["event"]["data"]["price"] = 80
        with pytest.raises(ValueError, match="PAYLOAD_DRIFT"):
            apply_frame(db, altered, (W1, W2), T.isoformat())
        assert current_cursor(db) == "1793930404464-0001"


def test_retroactive_rest_does_not_manufacture_prospective_known_time(tmp_path):
    with closing(open_selected_journal(tmp_path / "selected")) as db:
        result = record_event(
            db,
            event(),
            cursor="1793930404464-0001",
            known_at=T.isoformat(),
            wallets=(W1, W2),
            prospective=False,
        )
        assert result == "RECOVERED_FILL"
        assert db.execute("SELECT prospective FROM selected_fills").fetchone()[0] == 0
        assert apply_frame(db, frame(), (W1, W2), T.isoformat()) == "DUPLICATE"
        assert db.execute("SELECT prospective FROM selected_fills").fetchone()[0] == 0


def test_gap_remains_latched_and_cannot_be_explained_away(tmp_path):
    with closing(open_selected_journal(tmp_path / "selected")) as db:
        assert (
            apply_frame(
                db,
                {"type": "gap", "channel": "hl.fills", "cursor": "1793930404464-0001"},
                (W1, W2),
                T.isoformat(),
            )
            == "GAP"
        )
        assert had_gap(db) is True
        assert (
            apply_frame(db, frame(cursor="1793930404464-0002"), (W1, W2), T.isoformat())
            == "PROSPECTIVE_FILL"
        )
        assert had_gap(db) is True


def test_wallet_unknown_and_future_event_rejected(tmp_path):
    with closing(open_selected_journal(tmp_path / "selected")) as db:
        with pytest.raises(ValueError, match="WALLET_UNKNOWN"):
            apply_frame(db, frame("0x" + "c" * 40), (W1, W2), T.isoformat())
        future = frame()
        future["event"]["ts"] = (T + timedelta(seconds=15)).isoformat()
        with pytest.raises(ValueError, match="AFTER_RECEIPT"):
            apply_frame(db, future, (W1, W2), T.isoformat())
        assert db.execute("SELECT count(*) FROM selected_fills").fetchone()[0] == 0
