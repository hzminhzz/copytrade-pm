"""Sixteen independently accounted consumers of one canonical source history."""

from decimal import Decimal as D

from copytrade_pm.pm_forward_journal import PaperJournal
from copytrade_pm.pm_forward_paper import PaperCampaign
from copytrade_pm.pm_v4_sixteen_scenarios import IDENTITIES
from test_checkpoint_paper import BOUNDARY, GRID, BTC, checkpoint, quote, setup_paper, stamp
from test_checkpoint_source import scope


def test_sixteen_consumer_wave_isolated_finance_and_restart(tmp_path):
    journal = PaperJournal(tmp_path / "paper")
    campaign = PaperCampaign(journal=journal)
    members = {}
    for index, name in enumerate(IDENTITIES):
        j, source_policy, mandate, policy = setup_paper(
            tmp_path,
            run=name,
            account="acct_" + name,
            journal=journal,
            k=str(D("0.001") * (index + 1)),
        )
        members[name] = (mandate, policy)
    baseline = checkpoint(journal, source_policy, 0)
    requests = {
        name: {"owner": mandate.owner, "outcome_id": baseline.outcome_id, "policy": p}
        for name, (mandate, p) in members.items()
    }
    from test_pm_forward_ccxt_market import ccxt_market

    catalog = {"BTC/USDC:USDC": ccxt_market()}
    result = campaign.record_checkpoint_wave(requests, at_ms=BOUNDARY + 102, catalog=catalog)
    assert len(result["portfolios"]) == 16
    assert {row["status"] for row in result["portfolios"].values()} == {"BASELINE"}
    journal.append(
        "E10",
        "independent-halt",
        {
            "kind": "HALT",
            "event_at": stamp(BOUNDARY + 1000),
            "reason": "negative-control",
        },
    )
    changed = checkpoint(journal, source_policy, 1, "3")
    now = BOUNDARY + GRID + 102
    quote(journal, now)
    requests = {name: dict(row, outcome_id=changed.outcome_id) for name, row in requests.items()}
    result = campaign.record_checkpoint_wave(requests, at_ms=now + 2, catalog=catalog)
    assert {row["signal_id"] for row in result["portfolios"].values()} == {changed.signal_id}
    assert result["portfolios"]["E10"]["status"] == "MISSED"
    assert sum(row["status"] == "COMMITTED_ONCE" for row in result["portfolios"].values()) == 15
    statuses = {name: campaign.checkpoint_status(name) for name in IDENTITIES}
    assert not statuses["E10"]["account"]["quantities"]
    assert (
        len(
            {
                statuses[name]["account"]["quantities"][BTC.key]
                for name in IDENTITIES
                if name != "E10"
            }
        )
        == 15
    )
    assert all(D(statuses[name]["account"]["costs"]) > 0 for name in IDENTITIES if name != "E10")
    reopened = PaperCampaign(journal=PaperJournal(journal.root))
    assert reopened.record_checkpoint_wave(requests, at_ms=now + 3, catalog=catalog) == result
    assert {name: reopened.checkpoint_status(name) for name in IDENTITIES} == statuses
    assert len(journal.checkpoint_history(scope(), source_policy.epoch)) == 3


def test_missing_b_preserves_its_inventory_while_healthy_a_can_proceed(tmp_path):
    from hashlib import sha256
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from copytrade_pm.production_manifest import sign
    from test_checkpoint_journal import sample
    from test_checkpoint_paper import consume

    j, sp, a, p = setup_paper(tmp_path, k="0.001")
    address = "0x" + "b" * 40
    other_scope = scope().model_copy(
        update={
            "source_id": "fixture-other",
            "account_sha": sha256(address.encode()).hexdigest(),
        }
    )
    j.register_checkpoint_source(other_scope, sp, first_checkpoint_ms=BOUNDARY, at_ms=BOUNDARY - 1)
    b = a.model_copy(
        update={
            "mandate_id": "fixture-other-copy",
            "pod_id": "pod-b",
            "source_id": other_scope.source_id,
            "source_account_sha": other_scope.account_sha,
        }
    )
    key = Ed25519PrivateKey.generate()
    j.activate_copy_mandate(
        sign(b.model_dump(mode="json"), key, "copy-mandate-v1"),
        key.public_key(),
        account_id=b.account_id,
        at_ms=BOUNDARY - 1,
    )

    def other(index, quantity, fail=False):
        boundary = BOUNDARY + index * GRID
        return j.append_checkpoint_sample(
            sp.epoch,
            sample(
                j,
                boundary,
                quantity,
                fail=fail,
                source_scope=other_scope,
                address=address,
            ),
            boundary + 101,
        )

    first_a = checkpoint(j, sp, 0)
    first_b = other(0, "2")
    assert not consume(j, a, first_a, p, BOUNDARY + 102)["coverage_complete"]
    assert consume(j, b, first_b, p, BOUNDARY + 102)["coverage_complete"]
    checkpoint(j, sp, 1, "2")
    b_change = other(1, "3")
    now = BOUNDARY + GRID + 102
    quote(j, now)
    assert consume(j, b, b_change, p, now + 2)["status"] == "COMMITTED_ONCE"
    residual = j.restore("p1")["account"]["pm_quantities"][b.owner]
    gap = other(2, "0", fail=True)
    healthy = checkpoint(j, sp, 2, "3")
    now = BOUNDARY + 2 * GRID + 102
    assert consume(j, b, gap, p, now)["status"] == "COVERAGE_GAP"
    quote(j, now)
    result = consume(j, a, healthy, p, now + 2)
    assert result["status"] == "COMMITTED_ONCE"
    assert result["coverage_complete"] is False
    assert j.restore("p1")["account"]["pm_quantities"][b.owner] == residual


def test_selected_campaign_rejects_missing_or_changed_mandates(tmp_path):
    from copytrade_pm.pm_forward_observed_paper import PaperPortfolioSpec
    from copytrade_pm.pm_v4_sixteen_scenarios import V4Campaign
    from test_pm_forward_ccxt_market import ccxt_market

    j = PaperJournal(tmp_path / "paper")
    profiles, accounts, requests = {}, {}, {}
    for name in IDENTITIES:
        _, sp, m, p = setup_paper(tmp_path, run=name, account="acct_" + name, journal=j)
        profiles[name] = PaperPortfolioSpec(
            name, (m.source_id,), (m.source_id,), ("0.025",), ("200",), "SYNTHETIC_TEST_ONLY", "200"
        )
        accounts[name] = {m.source_id: m.source_account_sha}
        requests[name] = {"owner": m.owner, "outcome_id": "", "policy": p}
    selected = V4Campaign(
        profiles,
        {},
        accounts,
        {name: {"definition_sha256": "a" * 64} for name in IDENTITIES},
        {name: () for name in IDENTITIES},
        "b" * 64,
    )
    baseline = checkpoint(j, sp, 0)
    for row in requests.values():
        row["outcome_id"] = baseline.outcome_id
    campaign = PaperCampaign(journal=j)
    result = campaign.record_selected_checkpoint_wave(
        selected,
        requests,
        at_ms=BOUNDARY + 102,
        catalog={"BTC/USDC:USDC": ccxt_market()},
    )
    assert {r["status"] for r in result["portfolios"].values()} == {"BASELINE"}
    missing = campaign.record_selected_checkpoint_wave(
        selected,
        {},
        at_ms=BOUNDARY + 103,
        catalog={},
    )
    assert len(missing["portfolios"]) == 16
    assert {r["status"] for r in missing["portfolios"].values()} == {"UNRESOLVED"}
    changed_name = next(iter(IDENTITIES))
    before = j.restore(changed_name)
    profiles[changed_name] = PaperPortfolioSpec(
        changed_name,
        (m.source_id,),
        (m.source_id,),
        ("0.05",),
        ("200",),
        "SYNTHETIC_TEST_ONLY",
        "200",
    )
    drift = campaign.record_selected_checkpoint_wave(
        selected,
        requests,
        at_ms=BOUNDARY + 104,
        catalog={"BTC/USDC:USDC": ccxt_market()},
    )
    assert drift["portfolios"][changed_name]["status"] == "UNRESOLVED"
    assert (
        drift["portfolios"][changed_name]["reason"] == "CHECKPOINT_SELECTED_MANDATE_OR_RISK_DRIFT"
    )
    assert j.restore(changed_name) == before
    assert sum(r["status"] == "BASELINE" for r in drift["portfolios"].values()) == 15
