"""Bounded, real-source-journal tests for shared-IP native user rotation.

Provider budget is across sockets/IP, not per connection. Fake original WS
frames exercise real PersistentAccount/PaperJournal contracts without touching
real 0811/0911 journals or asserting continuous coverage while unsubscribed.
"""

from __future__ import annotations

import asyncio
from contextlib import closing
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from hashlib import sha256
import json
import sqlite3

import pytest

from copytrade_pm.pm_forward_continuous import (
    _native_account_cohorts,
    run_native_accounts,
)
from copytrade_pm.pm_forward_continuous_transport import ConnectionBudget, SerialWriter
from copytrade_pm.pm_forward_journal import PaperJournal
from copytrade_pm.pm_forward_source_stream import PersistentAccount
from copytrade_pm.pm_forward_stream_journal import verify_streams
from test_pm_e4_prospective import sample_state


def _accounts(tmp_path, count: int = 14):
    journal = PaperJournal(tmp_path / "source")
    accounts = {}
    for i in range(count):
        alias = f"W{i:02d}"
        address = "0x" + f"{i + 1:040x}"
        accounts[alias] = PersistentAccount(
            journal=journal,
            alias=alias,
            address=address,
            dex_catalog=[None, {"name": "xyz"}],
            subaccounts=None,
            parent_alias=alias,
            scope_sha="d" * 64,
        )
    return journal, accounts


def _clock():
    base = datetime.now(UTC) - timedelta(minutes=2)
    counter = 0

    def now():
        nonlocal counter
        counter += 1
        return (base + timedelta(microseconds=counter * 100)).isoformat(timespec="microseconds")

    return now


def test_cohort_policy_deduplicates_and_refuses_unbudgeted_14(tmp_path):
    _, accounts = _accounts(tmp_path)
    with pytest.raises(ValueError, match="EXPLICIT_USER_BUDGET_REQUIRED"):
        _native_account_cohorts(accounts, user_budget=None)
    cohorts = _native_account_cohorts(accounts, user_budget=7)
    assert [len(group) for group in cohorts] == [7, 7]
    assert set().union(*(set(group) for group in cohorts)) == set(accounts)
    for invalid in (False, 0, -1, 11, "7"):
        with pytest.raises(ValueError, match="USER_BUDGET_INVALID"):
            _native_account_cohorts(accounts, user_budget=invalid)


def test_14_official_snapshots_rotate_with_explicit_gaps_and_single_socket(tmp_path, monkeypatch):
    async def run():
        journal, accounts = _accounts(tmp_path)
        now = _clock()
        global_stop = asyncio.Event()
        calls = []

        async def session(**kwargs):
            # These sessions run *serially*, never 14 user-specific subs on a
            # live socket. The real provider connection is replaced here.
            subs = kwargs["subscriptions"]
            assert 1 <= len(subs) <= 7
            assert not kwargs["stop"].is_set()
            calls.append(tuple(s["user"] for s in subs))
            for sub in subs:
                await kwargs["on_ack"](sub, now())
                row = deepcopy(sample_state())
                row["user"] = sub["user"]
                for _, dex in row["clearinghouseStates"]:
                    dex["time"] = int((datetime.now(UTC) - timedelta(minutes=3)).timestamp() * 1000)
                frame = {"channel": "allDexsClearinghouseState", "data": row}
                wire = json.dumps(frame, sort_keys=True)
                await kwargs["handle"](frame, now(), sha256(wire.encode()).hexdigest(), wire)
            kwargs["stop"].set()
            if len(calls) == 2:
                global_stop.set()

        async def no_delay(stop, seconds):
            return None

        monkeypatch.setattr("copytrade_pm.pm_forward_continuous_transport.native_session", session)
        monkeypatch.setattr("copytrade_pm.pm_forward_continuous_transport.wait_or_stop", no_delay)
        async with SerialWriter() as writer:
            result = await run_native_accounts(
                accounts,
                writer=writer,
                stop=global_stop,
                connect=None,
                now=now,
                limiter=ConnectionBudget(),
                user_budget=7,
                rotation_seconds=420,
            )

        assert result["cohort_count"] == 2
        assert result["rotation_enabled"] is True
        assert result["trading_authorized"] is False
        assert len(calls) == 2
        assert len(set(calls[0] + calls[1])) == 14
        assert verify_streams(journal.path)["integrity"] == "VERIFIED"
        with closing(sqlite3.connect(journal.path)) as db:
            for alias, account in accounts.items():
                rows = db.execute(
                    "SELECT json_extract(payload,'$.kind'),"
                    "json_extract(payload,'$.checkpoint.baseline_valid') "
                    "FROM observer_stream_events WHERE stream_id=? ORDER BY seq",
                    ("account:" + alias,),
                ).fetchall()
                assert any(kind == "BASELINE" for kind, _ in rows), alias
                assert rows[-1][0] == "GAP"
                assert account.checkpoint["baseline_valid"] is False
                assert account.checkpoint["gap_reason"] in {
                    "NATIVE_BUDGET_ROTATION_GAP",
                    "ORDERLY_STOP",
                }

    asyncio.run(run())


def test_rejected_ws_subscription_shuts_down_without_retry_gap_flood(tmp_path, monkeypatch):
    async def run():
        journal, accounts = _accounts(tmp_path)
        now = _clock()
        stop = asyncio.Event()
        calls = []

        async def rejected(**kwargs):
            calls.append(len(kwargs["subscriptions"]))
            raise ValueError("STREAM_NATIVE_SUBSCRIPTION_REJECTED")

        monkeypatch.setattr("copytrade_pm.pm_forward_continuous_transport.native_session", rejected)
        async with SerialWriter() as writer:
            result = await run_native_accounts(
                accounts,
                writer=writer,
                stop=stop,
                connect=None,
                now=now,
                limiter=ConnectionBudget(),
                user_budget=7,
                rotation_seconds=420,
            )
        assert result["status"] == "STOPPED_NATIVE_SUBSCRIPTION_BLOCKED"
        assert stop.is_set()
        assert calls == [7]
        assert writer.write_failures == 0
        assert all(not a.checkpoint["baseline_valid"] for a in accounts.values())
        assert verify_streams(journal.path)["integrity"] == "VERIFIED"

    asyncio.run(run())


def test_insufficient_rotation_window_rejected_before_any_journal_append(tmp_path):
    async def run():
        journal, accounts = _accounts(tmp_path)
        async with SerialWriter() as writer:
            with pytest.raises(ValueError, match="ROTATION_MUST_COVER_T300"):
                await run_native_accounts(
                    accounts,
                    writer=writer,
                    stop=asyncio.Event(),
                    connect=None,
                    now=_clock(),
                    limiter=ConnectionBudget(),
                    user_budget=7,
                    rotation_seconds=120,
                )
        with closing(sqlite3.connect(journal.path)) as db:
            assert db.execute("SELECT COUNT(*) FROM observer_stream_events").fetchone() == (0,)

    asyncio.run(run())
