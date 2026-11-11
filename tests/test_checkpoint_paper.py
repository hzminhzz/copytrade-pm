"""S1: native checkpoint -> signed mandate -> existing PM03 paper journal."""

from dataclasses import asdict, replace
from datetime import UTC, datetime
from decimal import Decimal as D

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from copytrade_pm.pm03_account import Instrument, digest
from copytrade_pm.pm03_risk import RiskPolicy
from copytrade_pm.pm_forward_ccxt_market import parse_ccxt_book, parse_ccxt_market
from copytrade_pm.pm_forward_journal import PaperJournal
from copytrade_pm.production_manifest import sign
from test_checkpoint_journal import register, sample
from test_checkpoint_source import BOUNDARY, scope
from test_copy_mandates import mandate
from test_pm_forward_ccxt_market import ccxt_market
from test_pm_forward_journal import manifest

BTC = Instrument("hyperliquid", "mainnet:perp:default", "BTC")
GRID = 300_000


def stamp(ms):
    return datetime.fromtimestamp(ms / 1000, UTC).isoformat()


def policy():
    return {
        "schema": "checkpoint_paper_policy_v3",
        "max_quote_age_ms": 2000,
        "pod_loss_limit": "200",
        "max_gross_notional": "20000",
        "risk": {k: str(v) for k, v in asdict(RiskPolicy()).items()},
        "shocks": [{BTC.key: "-0.1"}, {BTC.key: "0.1"}],
        "costs": {
            "fee_bps": "5",
            "full_spread_bps": "0",
            "slippage_bps": "2",
            "impact_bps_at_full_participation": "0",
            "max_participation": "0.1",
            "max_age_seconds": 2,
            "latency_seconds": 0,
        },
    }


def setup_paper(tmp_path, *, run="p1", account="fixture-account", journal=None):
    journal = journal or PaperJournal(tmp_path / "paper")
    source_policy = register(journal)
    p = policy()
    mfest = manifest(run, account)
    rules = replace(mfest.rulebook, permitted=(BTC,), confirmed=True)
    mfest = replace(mfest, rulebook=rules, policy_sha=digest(p))
    journal.register(mfest)
    m = mandate().model_copy(
        update={
            "account_id": account,
            "source_account_sha": scope().account_sha,
            "policy_epoch": source_policy.epoch,
            "risk_policy_sha": digest(p),
            "rulebook_sha": rules.sha,
        }
    )
    key = Ed25519PrivateKey.generate()
    journal.activate_copy_mandate(
        sign(m.model_dump(mode="json"), key, "copy-mandate-v1"),
        key.public_key(),
        account_id=account,
        at_ms=BOUNDARY - 1,
    )
    return journal, source_policy, m, p


def checkpoint(journal, source_policy, index, quantity="2", *, fail=False):
    at = BOUNDARY + index * GRID
    return journal.append_checkpoint_sample(
        source_policy.epoch, sample(journal, at, quantity, fail=fail), at + 101
    )


def quote(journal, at, *, depth=200):
    raw = ccxt_market()
    native = parse_ccxt_market(raw, first_known_at=stamp(BOUNDARY - 1000), expected=BTC)
    row = parse_ccxt_book(
        native,
        {
            "symbol": raw["symbol"],
            "timestamp": at,
            "bids": [[9999, depth]],
            "asks": [[10001, depth]],
        },
        first_known_at=stamp(at + 1),
        max_age_seconds=2,
    )
    journal.append_market_quote(row.payload())
    return {raw["symbol"]: raw}


def consume(journal, m, outcome, p, at, *, run="p1"):
    return journal.consume_checkpoint(
        run,
        m.owner,
        outcome.outcome_id,
        at_ms=at,
        policy=p,
        catalog={"BTC/USDC:USDC": ccxt_market()},
    )


def test_checkpoint_one_shot_has_independent_marks_costs_and_restart(tmp_path):
    j, source_policy, m, p = setup_paper(tmp_path)
    baseline = checkpoint(j, source_policy, 0)
    assert consume(j, m, baseline, p, BOUNDARY + 102)["status"] == "BASELINE"
    assert not j.restore("p1")["account"]["quantities"]
    assert j.restore("p1")["account"]["costs"] == "0"
    changed = checkpoint(j, source_policy, 1, "3")
    now = BOUNDARY + GRID + 102
    blocked = consume(j, m, changed, p, now)
    assert blocked["status"] == "PRE_DISPATCH_BLOCKED"
    deadline = blocked["opportunity"]["deadline_ms"]
    quote(j, now + 1)
    result = consume(j, m, changed, p, now + 3)
    assert result["status"] == "COMMITTED_ONCE"
    assert result["signal_id"] == changed.signal_id
    assert result["opportunity"]["deadline_ms"] == deadline
    account = j.restore("p1")["account"]
    # Native source value 3 * 10000; target notional 750; follower ASK 10001.
    assert D(result["requested_targets"][m.owner][BTC.key]) == D("0.07499")
    assert result["risk"]["state"] == "YELLOW"
    assert D(account["quantities"][BTC.key]) == D("0.05624")  # Existing risk policy scales 0.75.
    assert D(account["cash"]) < D("10000")
    reopened = PaperJournal(j.root)
    assert consume(reopened, m, changed, p, now + 4) == result
    assert reopened.restore("p1")["account"] == account
    assert reopened.restore("p1")["cursor"] == 3


def test_expired_block_never_retries_on_unchanged_but_new_change_can_enter(tmp_path):
    j, sp, m, p = setup_paper(tmp_path)
    consume(j, m, checkpoint(j, sp, 0), p, BOUNDARY + 102)
    changed = checkpoint(j, sp, 1, "3")
    blocked = consume(j, m, changed, p, BOUNDARY + GRID + 102)
    deadline = blocked["opportunity"]["deadline_ms"]
    quote(j, deadline - 1)
    assert consume(j, m, changed, p, deadline)["status"] == "MISSED"
    same = checkpoint(j, sp, 2, "3")
    assert consume(j, m, same, p, BOUNDARY + 2 * GRID + 102)["status"] == "UNCHANGED"
    assert not j.restore("p1")["account"]["quantities"]
    later = checkpoint(j, sp, 3, "4")
    now = BOUNDARY + 3 * GRID + 102
    quote(j, now)
    assert consume(j, m, later, p, now + 2)["status"] == "COMMITTED_ONCE"
    assert D(j.restore("p1")["account"]["quantities"][BTC.key]) == D("0.07499")


def test_gap_and_recovery_do_not_invent_close_or_opening(tmp_path):
    j, sp, m, p = setup_paper(tmp_path)
    consume(j, m, checkpoint(j, sp, 0), p, BOUNDARY + 102)
    changed = checkpoint(j, sp, 1, "3")
    now = BOUNDARY + GRID + 102
    quote(j, now)
    consume(j, m, changed, p, now + 2)
    before = j.restore("p1")["account"]["quantities"]
    gap = checkpoint(j, sp, 2, "0", fail=True)
    assert consume(j, m, gap, p, BOUNDARY + 2 * GRID + 102)["status"] == "COVERAGE_GAP"
    recovery = checkpoint(j, sp, 3, "0")
    assert consume(j, m, recovery, p, BOUNDARY + 3 * GRID + 102)["status"] == "RECOVERY_BASELINE"
    assert j.restore("p1")["account"]["quantities"] == before


def test_mandate_policy_or_account_mismatch_cannot_mutate_account(tmp_path):
    j, sp, m, p = setup_paper(tmp_path)
    baseline = checkpoint(j, sp, 0)
    with pytest.raises(ValueError, match="POLICY"):
        consume(j, m, baseline, dict(p, pod_loss_limit="999"), BOUNDARY + 102)
    assert j.restore("p1")["cursor"] == 0


def crash_paper(root, owner, outcome_id, now, point):
    import os
    import signal
    from contextlib import contextmanager
    from pathlib import Path

    j = PaperJournal(Path(root))
    original = j._writer

    @contextmanager
    def writer():
        with original() as db:
            if point == "before_commit":

                def trace(sql):
                    if sql == "COMMIT":
                        os.kill(os.getpid(), signal.SIGKILL)

                db.set_trace_callback(trace)
            yield db

    j._writer = writer
    j.consume_checkpoint(
        "p1",
        owner,
        outcome_id,
        at_ms=int(now),
        policy=policy(),
        catalog={"BTC/USDC:USDC": ccxt_market()},
    )
    os.kill(os.getpid(), signal.SIGKILL)


@pytest.mark.parametrize("point", ["before_commit", "after_commit"])
def test_checkpoint_financial_effect_sigkill_is_atomic(tmp_path, point):
    import os
    import signal
    import subprocess
    import sys

    j, sp, m, p = setup_paper(tmp_path)
    consume(j, m, checkpoint(j, sp, 0), p, BOUNDARY + 102)
    changed = checkpoint(j, sp, 1, "3")
    now = BOUNDARY + GRID + 102
    quote(j, now)
    process = subprocess.run(
        [
            sys.executable,
            "-c",
            "from test_checkpoint_paper import crash_paper;import sys;crash_paper(*sys.argv[1:])",
            str(j.root),
            m.owner,
            changed.outcome_id,
            str(now + 2),
            point,
        ],
        env=os.environ | {"PYTHONPATH": os.pathsep.join(sys.path)},
        timeout=15,
    )
    assert process.returncode == -signal.SIGKILL
    j = PaperJournal(j.root)
    assert bool(j.restore("p1")["account"]["quantities"]) == (point == "after_commit")
    result = consume(j, m, changed, p, now + 2)
    assert result["status"] == "COMMITTED_ONCE"
    saved = j.restore("p1")
    assert saved["cursor"] == 2
    assert consume(j, m, changed, p, now + 3) == result
    assert j.restore("p1") == saved


def test_source_reduces_exits_and_reverses_keep_native_rounding(tmp_path):
    j, sp, m, p = setup_paper(tmp_path)
    consume(j, m, checkpoint(j, sp, 0), p, BOUNDARY + 102)
    for index, source_quantity, expected_sign in [
        (1, "3", 1),
        (2, "1", 1),
        (3, "0", 0),
        (4, "-3", -1),
    ]:
        outcome = checkpoint(j, sp, index, source_quantity)
        now = BOUNDARY + index * GRID + 102
        quote(j, now)
        result = consume(j, m, outcome, p, now + 2)
        assert result["status"] == "COMMITTED_ONCE"
        quantity = D(j.restore("p1")["account"]["quantities"].get(BTC.key, "0"))
        assert (1 if quantity > 0 else -1 if quantity < 0 else 0) == expected_sign
        assert abs(quantity) % D("0.00001") == 0
    assert D(j.restore("p1")["account"]["costs"]) > 0


def test_independent_halt_stops_opening_without_waiting_for_grid(tmp_path):
    j, sp, m, p = setup_paper(tmp_path)
    consume(j, m, checkpoint(j, sp, 0), p, BOUNDARY + 102)
    j.append(
        "p1",
        "risk-halt",
        {"kind": "HALT", "event_at": stamp(BOUNDARY + 1000), "reason": "independent risk stop"},
    )
    changed = checkpoint(j, sp, 1, "3")
    now = BOUNDARY + GRID + 102
    quote(j, now)
    result = consume(j, m, changed, p, now + 2)
    assert result["status"] == "MISSED"
    assert j.restore("p1")["account"]["risk"] == "HALT"
    assert not j.restore("p1")["account"]["quantities"]
