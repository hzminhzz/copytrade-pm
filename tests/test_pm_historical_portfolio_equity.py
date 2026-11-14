"""Retrospective source-equity extraction: bounded, hashed, not first-known."""

import json

import pytest

from copytrade_pm import pm_historical_portfolio_equity as p

SHA = "a" * 64


def vendor_payload():
    return [
        ["allTime", {"accountValueHistory": [[p.START_MS, "11111"]]}],
        [
            "perpAllTime",
            {
                "accountValueHistory": [
                    [p.START_MS - 600_000, "120000"],
                    [p.START_MS + 3_600_000, "100000"],
                    [p.END_MS - 1_000, "101000"],
                    [p.END_MS + 5_000, "108000"],
                ],
                "pnlHistory": [],
            },
        ],
    ]


def test_reader_keeps_only_perp_scope_and_explicit_q3_sparse_history():
    report = p.inspect_portfolio(vendor_payload())
    assert report["period"] == "perpAllTime"
    assert report["q3_points"] == 2
    assert report["total_points"] == 4
    assert report["q3_hourly_equity_denominator_continuous"] is False
    assert report["account_dex_subaccount_scope_reconciled"] is False
    assert report["follower_first_known_in_q3"] is False


@pytest.mark.parametrize(
    "fault",
    [
        lambda d: d.pop(),
        lambda d: d[1][1]["accountValueHistory"].append(d[1][1]["accountValueHistory"][-1]),
        lambda d: d[1][1]["accountValueHistory"][0].__setitem__(1, "NaN"),
    ],
)
def test_reader_rejects_missing_perp_or_bad_data(fault):
    data = vendor_payload()
    fault(data)
    with pytest.raises(ValueError):
        p.inspect_portfolio(data)


def test_bounded_read_only_provider_stores_only_private_generation(tmp_path, monkeypatch):
    requests = []

    class Entry:
        def __init__(self, alias):
            self.alias = alias
            self.address = "0x" + "a" * 40
            self.address_sha256 = SHA

    monkeypatch.setattr(p, "load_cohort", lambda _root: ((Entry("W028"),), {"manifest": SHA}))

    def fake_info(query):
        requests.append(query["type"])
        content = json.dumps(vendor_payload()).encode()
        import hashlib

        return json.loads(content), content, hashlib.sha256(content).hexdigest()

    monkeypatch.setattr(p, "guarded_info", fake_info)
    generation = tmp_path / "g20261102privateequitytest"
    info = p.collect(tmp_path, generation, aliases=("W028",))
    assert info["queries"] == 1
    assert requests == ["portfolio"]
    assert info["wallet_point_counts"] == {"W028": 2}
    assert info["hourly_source_equity_validated"] is False
    assert (generation / "raw" / "W028" / "portfolio.json").exists()
    assert (generation / "metadata" / "W028" / "portfolio.json").exists()
    with pytest.raises(ValueError, match="E4_IMMUTABLE_GENERATION_ALREADY_EXISTS"):
        p.collect(tmp_path, generation, aliases=("W028",))


def test_provider_budget_and_whitelist_reject_unauthorized_wallet(tmp_path):
    with pytest.raises(ValueError, match="UNBOUNDED_EQUITY_PROVIDER_REQUEST"):
        p.collect(tmp_path, tmp_path / "g20261102privateequitybudget", aliases=("W019",))
    with pytest.raises(ValueError, match="UNBOUNDED_EQUITY_PROVIDER_REQUEST"):
        p.collect(
            tmp_path,
            tmp_path / "g20261102privateequitybudget",
            aliases=p.DEFAULT_ALIASES,
            min_interval_seconds=0,
        )
