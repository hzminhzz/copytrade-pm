"""Provider account limits apply across connections, not separately per shard."""

import asyncio

import pytest

from copytrade_pm.pm_e4_stream import account_window
from copytrade_pm.pm_source_rotation import observer_lock, rotate


def test_account_windows_cover_all_accounts_without_exceeding_provider_limit():
    subjects = {f"P{i:02d}": str(i) for i in range(24)}
    windows = [account_window(subjects, i) for i in range(3)]
    assert [len(part) for part, count in windows] == [10, 10, 4]
    assert all(count == 3 for part, count in windows)
    assert set().union(*(set(part) for part, _ in windows)) == set(subjects)
    assert not (set(windows[0][0]) & set(windows[1][0]))
    with pytest.raises(ValueError, match="ACCOUNT_WINDOW"):
        account_window(subjects, 3)


def test_single_observer_lock_rejects_second_concurrent_process(tmp_path):
    path = tmp_path / "observer.lock"
    with observer_lock(path):
        with pytest.raises(ValueError, match="ALREADY_RUNNING"):
            with observer_lock(path):
                pass
    with observer_lock(path):
        pass


def test_rotation_visits_every_frozen_portfolio_and_c_subaccount_window(tmp_path):
    calls = []

    async def receiver(root, store, **kwargs):
        calls.append((kwargs["pods"], kwargs["account_window_index"]))
        return {
            "account_window_count": 2 if kwargs["pods"][0] == "CO-001" else 1,
            "errors": [],
            "generation": "synthetic",
        }

    async def check():
        await rotate(
            tmp_path,
            tmp_path / "out",
            forever=False,
            session_seconds=10,
            sample_seconds=15,
            receiver=receiver,
            cooldown_seconds=0,
        )

    asyncio.run(check())
    assert [pods[0] for pods, _ in calls] == ["W028", "W044", "CO-001", "CO-001"]
    assert [index for _, index in calls] == [0, 0, 0, 1]
