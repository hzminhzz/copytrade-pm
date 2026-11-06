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


def test_shared_ip_reserved_slots_and_socket_packing_preserve_every_subject():
    subjects = {f"P{i:02d}": str(i) for i in range(24)}
    reserved = [account_window(subjects, i, max_accounts_per_window=7) for i in range(4)]
    assert [len(chunk) for chunk, _ in reserved] == [7, 7, 7, 3]
    assert all(count == 4 for _, count in reserved)
    assert set().union(*(set(chunk) for chunk, _ in reserved)) == set(subjects)
    assert not any(
        set(reserved[i][0]) & set(reserved[j][0]) for i in range(4) for j in range(i + 1, 4)
    )
    for invalid in (0, 11, -1, True):
        with pytest.raises(ValueError, match="SHARED_IP_ACCOUNT"):
            account_window(subjects, 0, max_accounts_per_window=invalid)


def test_socket_packing_preserves_original_default_and_configurable_limits(tmp_path):
    from copytrade_pm.pm_e4_prospective import SUBSCRIPTIONS
    from copytrade_pm.pm_e4_stream import MAX_SUBSCRIPTIONS_PER_CONNECTION
    from copytrade_pm.pm_source_rotation import rotate

    assert MAX_SUBSCRIPTIONS_PER_CONNECTION == 15
    assert len(SUBSCRIPTIONS) == 5
    assert (7 * len(SUBSCRIPTIONS) + 64 - 1) // 64 == 1

    async def bogus_receiver(*args, **kwargs):
        raise AssertionError("invalid reservation must fail before any network call")

    async def invalid():
        with pytest.raises(ValueError, match="SHARED_IP_ACCOUNT"):
            await rotate(
                tmp_path,
                tmp_path / "unused",
                forever=False,
                receiver=bogus_receiver,
                max_accounts_per_window=11,
            )
        with pytest.raises(ValueError, match="SUBSCRIPTION_SOCKET_BOUND"):
            await rotate(
                tmp_path,
                tmp_path / "unused",
                forever=False,
                receiver=bogus_receiver,
                max_subscriptions_per_connection=129,
            )

    asyncio.run(invalid())


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
        assert kwargs["max_accounts_per_window"] == 7
        assert kwargs["max_subscriptions_per_connection"] == 64
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
            max_accounts_per_window=7,
            max_subscriptions_per_connection=64,
        )

    asyncio.run(check())
    assert [pods[0] for pods, _ in calls] == ["W028", "W044", "CO-001", "CO-001"]
    assert [index for _, index in calls] == [0, 0, 0, 1]
