"""PM03 consumes the canonical kernel contract instead of re-deriving it."""

from decimal import Decimal

import pytest

from copytrade_kernel import RulebookCatalog

from copytrade_pm.pm03_account import digest
from copytrade_pm.pm03_rules import PUBLIC_RULES, propr_rulebook
from copytrade_pm.pm_mandate import SignedMandate

BTC = "hyperliquid/mainnet:perp:default/BTC"


def mandate():
    return SignedMandate.from_fields(
        mandate_id="parity-copy",
        generation=1,
        source_id="parity-leader",
        source_scope_generation="a" * 64,
        source_account_sha="b" * 64,
        account_id="fixture-account",
        pod_id="pod-a",
        k="0.025",
        allowed_markets=("hyperliquid/mainnet:perp:default/BTC",),
        policy_epoch="c" * 64,
        risk_policy_sha="d" * 64,
        rulebook_sha="e" * 64,
        effective_from_ms=0,
        effective_until_ms=3_600_000,
    )


def test_kernel_owns_mandate_fields_and_pm_only_adds_evidence_digests():
    m = mandate()
    assert m.data["k"] == "0.025" and m.data["pod_id"] == "pod-a"
    assert m.sha == digest(m.data)
    assert m.owner == digest(["fixture-account", "parity-copy", 1])
    assert m.k == Decimal("0.025")
    # The kernel rejects field tampering; PM adds no second validator of its own.
    for broken in (
        m.data | {"k": "10.5"},
        m.data | {"allowed_markets": ["hyperliquid/mainnet:perp:default/BTC", "bad"]},
        m.data | {"pod_id": ""},
        {key: value for key, value in m.data.items() if key != "risk_policy_sha"},
    ):
        with pytest.raises(ValueError):
            SignedMandate.parse(broken)


OBSERVED = "2026-10-31T00:00:00+00:00"
CATALOG_KEYS = {
    ("classic_1step", "evaluation"): "propr:classic_1step:phase_1",
    ("turbo_1step", "evaluation"): "propr:turbo_1step:phase_1",
    ("classic_2step", "step1"): "propr:classic_2step:phase_1",
    ("classic_2step", "step2"): "propr:classic_2step:phase_2",
    ("classic_2step", "funded"): "propr:classic_2step:funded",
}


def test_propr_rulebook_terms_are_reconciled_against_the_kernel_catalog():
    for (program, stage), key in CATALOG_KEYS.items():
        spec = RulebookCatalog.get(key)
        book = propr_rulebook(program, stage, Decimal("10000"), observed_at=OBSERVED)
        base = Decimal(spec.initial)
        assert book.daily_loss_rate == Decimal(spec.daily_loss) / base
        if book.profit_target is not None:
            assert book.profit_target == Decimal(spec.target) * Decimal("10000") / base
        if book.static_loss is not None:
            assert book.static_loss == Decimal(spec.trailing_loss) * Decimal("10000") / base
        if book.trailing_loss is not None:
            assert book.trailing_loss == Decimal(spec.trailing_loss) * Decimal("10000") / base
        assert book.snapshot_sha and not book.confirmed and not book.account_terms_confirmed


def test_rulebook_quotes_drift_from_the_catalog_fails_closed():
    from copy import deepcopy

    from copytrade_pm import pm03_rules

    quoted = deepcopy(PUBLIC_RULES)
    quoted["classic_1step"]["daily"] = "0.04"
    pm03_rules.PUBLIC_RULES = quoted
    try:
        with pytest.raises(ValueError, match="PROPR_RULEBOOK_CATALOG_DRIFT"):
            pm03_rules.propr_rulebook(
                "classic_1step", "evaluation", Decimal("10000"), observed_at=OBSERVED
            )
    finally:
        pm03_rules.PUBLIC_RULES = PUBLIC_RULES


def test_pm03_checkpoint_proposal_delegates_the_fixed_k_request_to_the_kernel(
    tmp_path, monkeypatch
):
    """The paper shell must call ``copytrade_kernel.step_checkpoint``, not re-derive it."""
    from copytrade_pm import pm_checkpoint_paper
    from copytrade_pm.pm_checkpoint_journal import CheckpointOutcome
    from test_checkpoint_paper import GRID, checkpoint, consume, quote, setup_paper
    from test_checkpoint_source import BOUNDARY

    calls = []
    kernel_step = pm_checkpoint_paper.step_checkpoint

    def spy(*, state, frame, inputs=None):
        calls.append((state, frame, inputs))
        return kernel_step(state=state, frame=frame, inputs=inputs)

    monkeypatch.setattr(pm_checkpoint_paper, "step_checkpoint", spy)
    j, source_policy, m, p = setup_paper(tmp_path)
    baseline = checkpoint(j, source_policy, 0)
    assert consume(j, m, baseline, p, BOUNDARY + 102)["status"] == "BASELINE"
    changed = checkpoint(j, source_policy, 1, "3")
    assert isinstance(changed, CheckpointOutcome)
    now = BOUNDARY + GRID + 102
    consume(j, m, changed, p, now)
    quote(j, now + 1)
    result = consume(j, m, changed, p, now + 3)
    assert result["status"] == "COMMITTED_ONCE"
    state, frame, inputs = calls[-1]
    assert state.owner_books[0].owner == m.owner
    assert frame.outcomes[0].owner == m.owner
    assert frame.outcomes[0].sizing.k == m.k
    assert frame.checkpoint_ms.value == changed.checkpoint_ms
    # The kernel receives real normalized decision inputs, not an empty shell.
    assert inputs is not None
    assert inputs.now_ms.value == now + 3
    assert inputs.market.quotes.data()[BTC] == {
        "bid": "9999",
        "ask": "10001",
        "known_at_ms": now + 2,  # first_known_at of the appended L2 quote
    }
    assert inputs.market.markets.data()[BTC]["qty_step"] == "0.00001"
    assert inputs.market.markets.data()[BTC]["min_notional"] == "10"
    assert inputs.account.positions.data() == {}
    # Flat owner book: the kernel sizes this first entry from no inventory.
    assert inputs.account.owner_positions.data() == {}
    assert inputs.account.finance.data()["headroom"] == "300.00"
    policy = inputs.policy.fields.data()
    assert policy["schema"] == "risk_policy_v1" and policy["scale_steps"] == 4
    assert [cap.market for cap in inputs.market.capabilities] == [BTC]
    # PM03 consumes the kernel's net intent instead of re-deriving the order.
    assert result["net_intents"] == [
        {
            "market": BTC,
            "net_delta_qty": "0.07499",
            "reduce_only": False,
            "owner_allocations": [[m.owner, "0.07499"]],
        }
    ]
    assert result["kernel_decision"]["scale"] == "1"
    assert result["order_route"] == "NONE"
