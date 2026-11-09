"""Source quarantine/recovery through actual observation and paper owners."""

import asyncio
from copy import deepcopy
from decimal import Decimal
from hashlib import sha256
import json

import pytest

from copytrade_pm.pm03_account import digest, RiskState
from copytrade_pm.pm03_memory import Event
from copytrade_pm.pm_forward_continuous import run_native_accounts
from copytrade_pm.pm_forward_continuous_transport import ConnectionBudget, SerialWriter
from copytrade_pm.pm_forward_journal import PaperJournal
from copytrade_pm.pm_forward_observed_paper import ObservedP1Paper
from copytrade_pm.pm_forward_public_trades import PersistentPublicMarket
from copytrade_pm.pm_forward_source_stream import PersistentAccount
from copytrade_pm.pm_forward_stream_journal import verify_streams
from copytrade_pm.pm_source_contracts import SourceObservationRejected
from copytrade_pm.pm_vike_market_catalog import NativePaperContract
from test_pm_forward_observed_paper import ADDRESSES, BTC, at, registry
from test_pm_vike_paper_integration import official_frame, official_observer, price


def paper_for(root, source, prices, *, restart=False):
    return ObservedP1Paper(
        source_db=source.path,
        price_db=prices.path,
        price_mode="vike_minute",
        state_root=root / "paper",
        run_id="continuity",
        registry_db=root / "registry.sqlite" if restart else registry(root / "registry.sqlite"),
        catalog={},
        native_contracts={
            BTC.key: NativePaperContract(
                instrument=BTC,
                amount_step=Decimal("0.001"),
                minimum_notional=Decimal("10"),
                active=True,
                market_known_at=at(0),
                catalog_sha=digest(["native", BTC.key]),
                hip3=False,
            )
        },
        **({} if restart else {"started_at": at(0)}),
    )


def test_cf01_malformed_pending_then_reconnect_cannot_resurrect_old_t0(tmp_path):
    source, prices = PaperJournal(tmp_path / "source"), PaperJournal(tmp_path / "prices")
    observer = official_observer(source)
    paper = paper_for(tmp_path, source, prices)
    observer.observe(official_frame(12, 20), at(13))
    pending = paper.step(at(14))["execution_intents"]["S035"]
    bad = official_frame(180, 0)
    del bad["data"]["clearinghouseStates"][0][1]["marginSummary"]
    wire = json.dumps(bad, indent=2)
    raw_sha = sha256(wire.encode()).hexdigest()
    with pytest.raises(SourceObservationRejected) as exc:
        observer.observe(bad, at(181), raw_sha=raw_sha, raw_text=wire)
    assert exc.value.availability.status == "INCOMPLETE"
    gap = observer.progress.head["event"]
    assert gap["raw_sha"] == raw_sha
    assert gap["first_known_at"] == at(181)
    assert gap["details"]["native_wire"] == wire
    assert gap["checkpoint"]["positions"][BTC.key] == "20"
    canceled = paper.step(at(182))
    assert canceled["execution_intents"]["S035"]["status"] == "CANCELED_SOURCE_GAP"
    restarted = paper_for(tmp_path, source, prices, restart=True)
    observer.begin(at(310), reason="CONTROLLED_RECONNECT")
    assert observer.observe(official_frame(310, 20), at(311))["classification"] == "BASELINE"
    price(prices, 312)
    result = restarted.step(at(313))
    assert result["positions"] == {}
    assert result["execution_intents"]["S035"]["intent_id"] == pending["intent_id"]
    assert result["execution_intents"]["S035"]["first_known_at"] == at(13)
    assert result["execution_intents"]["S035"]["status"] == "CANCELED_SOURCE_GAP"
    assert not any(r["event"]["kind"] == "PM04_PAPER_EXECUTE" for r in restarted.run.ledger.read())
    assert verify_streams(source.path)["integrity"] == "VERIFIED"


def test_malformed_frame_preserves_held_follower_inventory_and_durable_halt(tmp_path):
    source, prices = PaperJournal(tmp_path / "source"), PaperJournal(tmp_path / "prices")
    observer = official_observer(source)
    paper = paper_for(tmp_path, source, prices)
    observer.observe(official_frame(12, 20), at(13))
    paper.step(at(14))
    price(prices, 312)
    opened = paper.step(at(313))
    assert opened["positions"]
    paper.run.record(
        Event(
            "owner_halt",
            at(314),
            at(314),
            at(314),
            at(314),
            "HALT",
            {
                "run_id": "continuity",
                "rulebook_sha": paper.run.account.rulebook.sha,
                "input": {"reason": "INDEPENDENT_FINANCIAL_HALT"},
            },
            digest("halt"),
        )
    )
    bad = official_frame(315, 0)
    bad["data"]["clearinghouseStates"][0][1]["time"] = False
    with pytest.raises(SourceObservationRejected):
        observer.observe(bad, at(316))
    paper.step(at(601))  # No fresh executable price; uncertainty cannot become flat.
    restored = paper_for(tmp_path, source, prices, restart=True)
    assert restored.run.account.quantities == paper.run.account.quantities
    assert restored.run.account.quantities
    assert restored.run.account.risk == RiskState.HALT
    assert restored.run.account.halt_reason == "INDEPENDENT_FINANCIAL_HALT"


def test_targeted_scope_generation_does_not_reset_independent_account(tmp_path):
    source = PaperJournal(tmp_path / "source")
    a = official_observer(source)
    b = PersistentAccount(
        journal=source,
        alias="S051",
        address=ADDRESSES["S051"],
        dex_catalog=[None],
        subaccounts=None,
        parent_alias="S051",
        scope_sha="a" * 64,
    )
    b.begin(at(0))

    def b_frame(seconds, qty):
        f = official_frame(seconds, qty)
        f["data"]["user"] = ADDRESSES["S051"]
        return f

    b.observe(b_frame(1, 0), at(2))
    a.observe(official_frame(12, 20), at(13))
    b.observe(b_frame(12, 20), at(13))
    b_before = deepcopy(b.checkpoint)
    a.reconfigure(
        dex_catalog=[None],
        observer_generation="b" * 64,
        contract_generation="c" * 64,
        known_at=at(100),
    )
    assert not a.checkpoint["baseline_valid"]
    assert a.checkpoint["positions"][BTC.key] == "20"
    assert b.checkpoint == b_before
    assert b.observe(b_frame(101, 21), at(102))["classification"] == "OBSERVED_STATE_CHANGE"
    assert a.observe(official_frame(101, 20), at(102))["classification"] == "BASELINE"


@pytest.mark.parametrize("new_quantity, expected", [("0", "UNCHANGED_STATE"), ("3", "BASELINE")])
def test_unrelated_empty_dex_does_not_change_account_scope(tmp_path, new_quantity, expected):
    source = PaperJournal(tmp_path / "source")
    a = official_observer(source)
    a.observe(official_frame(12, 20), at(13))
    old_generation = a.checkpoint["account_scope_sha"]
    a.reconfigure(
        dex_catalog=[None, {"name": "new"}], observer_generation="b" * 64, known_at=at(20)
    )
    frame = official_frame(21, 20)
    extra = deepcopy(frame["data"]["clearinghouseStates"][0][1])
    extra["assetPositions"] = (
        [{"position": {"coin": "new:XYZ", "szi": new_quantity}}] if new_quantity != "0" else []
    )
    frame["data"]["clearinghouseStates"].append(["new", extra])
    assert a.observe(frame, at(22))["classification"] == expected
    assert (a.checkpoint["account_scope_sha"] == old_generation) == (new_quantity == "0")


def test_quarantine_budget_is_bounded_and_valid_recovery_is_only_baseline(tmp_path):
    source = PaperJournal(tmp_path / "source")
    a = official_observer(source)
    a.observe(official_frame(12, 20), at(13))
    bad = official_frame(20, 0)
    bad["data"]["unknownDelta"] = True
    start = a.progress.head["cursor"]
    for _ in range(20):
        with pytest.raises(SourceObservationRejected):
            a.observe(bad, at(21))
    assert a.progress.head["cursor"] == start + 16
    assert a.checkpoint["quarantine_budget_exhausted"]
    assert a.checkpoint["positions"][BTC.key] == "20"
    assert a.observe(official_frame(22, 20), at(23))["classification"] == "BASELINE"
    assert a.checkpoint["consecutive_rejections"] == 0


def test_wire_mismatch_and_duplicate_json_fields_cannot_evade_quarantine(tmp_path):
    source = PaperJournal(tmp_path / "source")
    a = official_observer(source)
    f = official_frame(12, 20)
    wire = json.dumps(official_frame(12, 21))
    with pytest.raises(SourceObservationRejected, match="WIRE_FRAME_MISMATCH"):
        a.observe(f, at(13), raw_sha=sha256(wire.encode()).hexdigest(), raw_text=wire)
    assert not a.checkpoint["baseline_valid"]
    wire = json.dumps(f).replace('"szi": "20"', '"szi": "21", "szi": "20"')
    with pytest.raises(SourceObservationRejected, match="DUPLICATE_JSON_FIELD"):
        a.observe(f, at(14), raw_sha=sha256(wire.encode()).hexdigest(), raw_text=wire)
    assert verify_streams(source.path)["integrity"] == "VERIFIED"


def test_optional_public_trade_gap_cannot_repair_or_break_official_continuity(tmp_path):
    source = PaperJournal(tmp_path / "source")
    a = official_observer(source)
    a.observe(official_frame(12, 20), at(13))
    official_before = deepcopy(a.checkpoint)
    feed = PersistentPublicMarket(
        source, BTC, {ADDRESSES["S035"]: "wallet:test"}, scope_sha="e" * 64
    )
    feed.begin(at(20))
    feed.gap(at(21), "OPTIONAL_TRADE_FEED_DISCONNECTED")
    assert a.checkpoint == official_before
    a.gap(at(22), "OFFICIAL_DISCONNECTED")
    feed.begin(at(23))
    assert not a.checkpoint["baseline_valid"]
    assert a.checkpoint["positions"][BTC.key] == "20"


def test_ambiguous_shared_transport_fences_all_subscribed_accounts(tmp_path, monkeypatch):
    async def run():
        source = PaperJournal(tmp_path / "source")
        a = official_observer(source)
        b = PersistentAccount(
            journal=source,
            alias="S051",
            address=ADDRESSES["S051"],
            dex_catalog=[None],
            subaccounts=None,
            parent_alias="S051",
            scope_sha="a" * 64,
        )
        stop = asyncio.Event()
        bad = official_frame(12, 20)
        bad["data"]["user"] = "0x" + "f" * 40
        wire = json.dumps(bad)

        async def failed_transport(**kwargs):
            stop.set()
            await kwargs["handle"](bad, at(13), sha256(wire.encode()).hexdigest(), wire)

        monkeypatch.setattr(
            "copytrade_pm.pm_forward_continuous_transport.native_session", failed_transport
        )
        stamps = iter((at(10), at(10), at(14), at(14)))
        async with SerialWriter() as writer:
            await run_native_accounts(
                {"S035": a, "S051": b},
                writer=writer,
                stop=stop,
                connect=None,
                now=lambda: next(stamps),
                limiter=ConnectionBudget(),
            )
        for account in (a, b):
            assert not account.checkpoint["baseline_valid"]
            assert account.checkpoint["gap_reason"] == "SOURCE_NATIVE_AMBIGUOUS_IDENTITY_OR_CHANNEL"
        assert verify_streams(source.path)["integrity"] == "VERIFIED"

    asyncio.run(run())


def test_scope_fence_reaches_only_dependent_portfolio_pods(tmp_path, monkeypatch):
    from test_pm_forward_multi_portfolio import full_registry, pin_reviewed_registry

    pin_reviewed_registry(monkeypatch)
    registry_db = full_registry(tmp_path)
    source, prices = PaperJournal(tmp_path / "source"), PaperJournal(tmp_path / "prices")
    healthy = official_observer(source)
    affected = PersistentAccount(
        journal=source,
        alias="S064",
        address="0x" + "04" * 20,
        dex_catalog=[None],
        subaccounts=None,
        parent_alias="S064",
        scope_sha="a" * 64,
    )
    affected.begin(at(0))
    for seconds, qty in ((1, 0), (12, 20)):
        f = official_frame(seconds, qty)
        f["data"]["user"] = affected.address
        affected.observe(f, at(seconds + 1))
    healthy.observe(official_frame(12, 20), at(13))
    portfolios = {}
    for name in ("P14", "P16"):
        portfolios[name] = ObservedP1Paper(
            source_db=source.path,
            price_db=prices.path,
            price_mode="vike_minute",
            registry_db=registry_db,
            state_root=tmp_path / name,
            run_id="scope_" + name,
            portfolio_id=name,
            started_at=at(0),
            catalog={},
            native_contracts={
                BTC.key: NativePaperContract(
                    instrument=BTC,
                    amount_step=Decimal("0.001"),
                    minimum_notional=Decimal("10"),
                    active=True,
                    market_known_at=at(0),
                    catalog_sha=digest(["native", BTC.key]),
                    hip3=False,
                )
            },
        )
        portfolios[name].step(at(14))
    affected.reconfigure(
        dex_catalog=[None],
        observer_generation="b" * 64,
        contract_generation="c" * 64,
        known_at=at(100),
    )
    p14 = portfolios["P14"].step(at(101))
    p16 = portfolios["P16"].step(at(101))
    assert p14["execution_intents"]["S064"]["status"] == "CANCELED_SOURCE_GAP"
    assert "S064" not in p16["execution_intents"]
    assert all(p["execution_intents"]["S035"]["status"] == "PENDING_5M" for p in (p14, p16))
    healthy.observe(official_frame(300, 20), at(301))
    price(prices, 312)
    for paper in portfolios.values():
        result = paper.step(at(313))
        assert result["execution_intents"]["S035"]["status"] == "FILLED"
        assert result["positions"]


def test_same_clock_conflict_is_per_dex_even_if_another_dex_advances(tmp_path):
    from datetime import timedelta
    from test_pm_forward_persistent_source import account, shifted, T

    source, _ = account(tmp_path)
    source.observe(shifted(0, "20"), T.isoformat())
    bad = shifted(1, "21")
    bad["data"]["clearinghouseStates"][0][1]["time"] -= 1000
    with pytest.raises(SourceObservationRejected, match="SAME_CLOCK_CONFLICTING_POSITIONS"):
        source.observe(bad, (T + timedelta(seconds=1)).isoformat())
    assert not source.checkpoint["baseline_valid"]
    assert source.checkpoint["positions"][BTC.key] == "20"


def test_observer_metadata_refresh_retains_account_epoch_and_socket(tmp_path):
    from copytrade_pm.pm_forward_continuous import ContinuousObserver, SubscriptionBudget
    from test_pm_forward_continuous_integration import FakeEnvironment, BTC, BRENT

    async def run():
        env = FakeEnvironment()
        base_info = env.info
        revisions = 0

        def info(request):
            nonlocal revisions
            payload, raw, fingerprint = base_info(request)
            if request["type"] == "perpDexs":
                revisions += 1
                payload[1]["diagnostic_revision"] = revisions
                raw = json.dumps(payload).encode()
                fingerprint = sha256(raw).hexdigest()
            return payload, raw, fingerprint

        journal = PaperJournal(tmp_path / "refresh")
        manifest = {
            "schema": "paper_continuous_preflight_v1",
            "revision": "a" * 40,
            "source_nav_attested": False,
            "order_route": "NONE",
        }
        manifest["manifest_sha"] = digest(manifest)
        observer = ContinuousObserver(
            journal=journal,
            manifest=manifest,
            parents={"S035": "0x" + "a" * 40},
            watched={"0x" + "a" * 40: "wallet:17"},
            configured=(BTC, BRENT),
            budget=SubscriptionBudget(),
            info=info,
            connect=env.connect,
            ccxt_factory=env.factory,
            receipt_clock_factory=lambda client: client.timer,
            now=env.now,
            refresh_seconds=0.12,
            heartbeat_seconds=0.04,
            min_free_bytes=0,
        )
        await observer.run(asyncio.Event(), duration_seconds=0.6)
        assert revisions >= 2
        account = verify_streams(journal.path)["streams"]["account:S035"]
        assert account["epoch_count"] == 1
        assert account["baseline_count"] == 1
        assert len(env.sockets) == 2  # One account socket plus public trades.
        assert all(socket.closed for socket in env.sockets)

    asyncio.run(run())
