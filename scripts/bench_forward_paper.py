"""Ext4-local, one-shot synthetic Forward-Paper full-account performance probe.

Not a 24h soak, not a prospective source/market capture, and not a broker
benchmark. Includes private SQLite WAL + PM-03 account, quote, fee and
funding events. All scratch bytes are deleted on exit.
"""

from __future__ import annotations

import argparse
from dataclasses import replace
from datetime import datetime, timedelta
from decimal import Decimal
import json
import math
from pathlib import Path
import resource
import statistics
import tempfile
from time import perf_counter

from copytrade_pm.pm03_account import Instrument, digest
from copytrade_pm.pm03_rules import propr_rulebook
from copytrade_pm.pm_forward_journal import PaperJournal
from copytrade_pm.pm_forward_paper import PaperCampaign, PaperManifest

BTC = Instrument("hyperliquid", "mainnet:perp:default", "BTC")
START = "2026-11-04T04:00:00+00:00"


def at(seconds: int) -> str:
    return (datetime.fromisoformat(START) + timedelta(seconds=seconds)).isoformat()


def measure(fn, samples: list[float]) -> None:
    started = perf_counter()
    fn()
    samples.append((perf_counter() - started) * 1000)


def _fixture() -> tuple[dict, dict, dict]:
    book = {
        "schema": "paper_source_book_v1",
        "wallet_id": "synthetic_benchmark_wallet",
        "account_id": "synthetic_benchmark_source",
        "snapshot_kind": "ATOMIC_WHOLE_ACCOUNT",
        "account_scope_complete": True,
        "hedges_complete": True,
        "spot_scope_known": True,
        "vault_scope_known": True,
        "margin_mode": "CROSS",
        "dex_census": [BTC.market],
        "observed_dexes": [BTC.market],
        "subaccounts": [],
        "observed_subaccounts": [],
        "source_event_at": START,
        "first_known_at": START,
        "source_equity": "20000",
        "collateral_denominator": "account_equity",
        "collateral_value": "10000",
        "positions": {BTC.key: "2"},
        "synthetic_fixture": True,
    }
    book["snapshot_sha"] = digest(book)
    receipt = {
        "schema": "paper_first_known_source_v1",
        "source_id": book["wallet_id"],
        "source_event_at": START,
        "first_known_at": START,
        "captured_at": START,
        "payload_sha": book["snapshot_sha"],
    }
    costs = {
        "fee_bps": "2",
        "full_spread_bps": "4",
        "slippage_bps": "1",
        "impact_bps_at_full_participation": "4",
        "max_participation": "0.1",
        "max_age_seconds": 300,
        "latency_seconds": 1,
    }
    market = {
        "schema": "paper_market_contract_v1",
        "instrument": BTC.key,
        "quality": "SYNTHETIC",
        "costs_sha": digest(costs),
        "session_open": True,
        "market_permitted": True,
        "first_known_at": START,
        "quantity_step": "0.01",
        "minimum_quantity": "0.01",
    }
    market["contract_sha"] = digest(market)
    effect = {
        "kind": "SIMULATED_DECISION",
        "event_at": START,
        "hypothetical_fill_at": at(2),
        "evidence_class": "FORWARD_PAPER_SIMULATED_v1",
        "order_route": "NONE",
        "fixture_attested": True,
        "source_book": book,
        "source_ref": {
            "source_id": book["wallet_id"],
            "sequence": 1,
            "receipt_sha": digest(receipt),
        },
        "proposed": {"PM_A": {BTC.key: "1"}},
        "shocks": [{BTC.key: "-0.05"}, {BTC.key: "0.05"}],
        "observations": [
            {
                "instrument": BTC.key,
                "source_at": START,
                "first_known_at": START,
                "mark": "100",
                "volume_base": "1000",
                "quality": "SYNTHETIC",
                "supported": True,
            }
        ],
        "costs": costs,
        "market_contracts": {BTC.key: market},
    }
    return book, receipt, effect


def benchmark(*, accounts: int, marks: int, burst_multiplier: int) -> dict:
    if not 1 <= accounts <= 50 or not 1 <= marks <= 200 or burst_multiplier not in (1, 2):
        raise ValueError("UNSUPPORTED_BENCHMARK_SCOPE")
    start_cpu = resource.getrusage(resource.RUSAGE_SELF)
    timings: list[float] = []
    wallet, receipt, effect = _fixture()
    before = perf_counter()
    with tempfile.TemporaryDirectory(prefix="copytrade-paper-bench-") as scratch:
        journal = PaperJournal(Path(scratch) / "paper")
        campaign = PaperCampaign(journal=journal)
        rulebook = replace(
            propr_rulebook("classic_1step", "evaluation", Decimal("10000"), observed_at=START),
            confirmed=True,
            permitted=(BTC,),
        )
        journal.append_source_receipt(wallet["wallet_id"], 1, "shared_fixture", receipt)
        names = []
        for i in range(accounts):
            run = f"paper_{i:02d}"
            account = f"paper_account_{i:02d}"
            row = PaperManifest(
                run_id=run,
                account_id=account,
                portfolio_sha=digest(["benchmark", i]),
                market_manifest_sha=digest("synthetic_markets"),
                release_sha=digest("synthetic_benchmark_release"),
                selected_at=START,
                started_at=START,
                rulebook=rulebook,
                policy_sha=digest("benchmark_policy"),
            )
            campaign.register(row)
            names.append(run)
        for run in names:
            measure(
                lambda run=run: campaign.record_source_decision(run, "source_1", effect),
                timings,
            )
        for minute in range(1, marks + 1):
            tick = at(minute * 60)
            market_price = str(Decimal("100") + Decimal(minute % 7) / Decimal("10"))
            event = {
                "kind": "MARK",
                "event_at": tick,
                "state_known": True,
                "prices": {BTC.key: market_price},
            }
            for run in names:
                measure(
                    lambda run=run, event=event, minute=minute: campaign.record_event(
                        run, f"mark_{minute}", event
                    ),
                    timings,
                )
            if burst_multiplier == 2:
                for run in names:
                    measure(
                        lambda run=run, event=event, minute=minute: campaign.record_event(
                            run, f"burst_mark_{minute}", event
                        ),
                        timings,
                    )
        funded_at = at((marks + 1) * 60)
        margin = {
            "schema": "paper_margin_contract_v1",
            "synthetic_fixture": True,
            "margin_mode": "CROSS",
            "first_known_at": funded_at,
            "initial_margin_fraction": "0.1",
            "maintenance_margin_fraction": "0.05",
        }
        funding = {
            "kind": "FUNDING",
            "event_at": funded_at,
            "source_event_at": funded_at,
            "first_known_at": funded_at,
            "fixture_attested": True,
            "instrument": BTC.key,
            "interval_id": "funding_synthetic_1",
            "amount": "-0.01",
            "allocated": {"PM_A": "-0.01"},
            "marks": {BTC.key: market_price},
            "margin_contract": {**margin, "contract_sha": digest(margin)},
        }
        for run in names:
            measure(
                lambda run=run: campaign.record_event(run, "funding_1", funding),
                timings,
            )
        expected_count = 2 + marks * burst_multiplier
        for run in names:
            final = journal.restore(run)
            if (
                final["cursor"] != expected_count
                or final["source_cursors"] != {wallet["wallet_id"]: 1}
                or Decimal(final["account"]["funding"]) != Decimal("-0.01")
                or final["account"]["quantities"][BTC.key] != "1"
            ):
                raise ValueError("BENCHMARK_FINANCIAL_OR_CURSOR_MISMATCH")
        disk_bytes = sum(file.stat().st_size for file in journal.root.glob("paper-events.sqlite3*"))
        elapsed = perf_counter() - before
    ordered = sorted(timings)
    usage = resource.getrusage(resource.RUSAGE_SELF)
    return {
        "schema": "forward_paper_synthetic_benchmark_v1",
        "account_count": accounts,
        "mark_events_per_account": marks * burst_multiplier,
        "event_count": len(timings),
        "expected_event_count": accounts * (marks * burst_multiplier + 2),
        "all_accounts_financially_reconciled": True,
        "source_cursors_atomic": True,
        "first_known_source_kind": "SYNTHETIC_FIXTURE_ONLY",
        "market_kind": "SYNTHETIC_QUOTE",
        "broker_order_route": "NONE",
        "local_filesystem_path": "TEMPORARY_LOCAL",
        "elapsed_wall_seconds": round(elapsed, 3),
        "event_processing_ms_p50": round(statistics.median(timings), 3),
        "event_processing_ms_p99": round(ordered[math.ceil(0.99 * len(ordered)) - 1], 3),
        "event_processing_ms_max": round(max(ordered), 3),
        "final_sqlite_disk_bytes": disk_bytes,
        "process_cpu_user_seconds_delta": round(usage.ru_utime - start_cpu.ru_utime, 3),
        "process_cpu_system_seconds_delta": round(usage.ru_stime - start_cpu.ru_stime, 3),
        "process_max_rss_kib": usage.ru_maxrss,
        "synthetic_2x_sequential_burst": burst_multiplier == 2,
        "unattended_24h_soak_verified": False,
        "real_source_or_market_freshness_verified": False,
        "p99_eligible_due_lag_5s_slo_verified": False,
        "scientifically_qualified": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Temporary synthetic private paper benchmark")
    parser.add_argument("--accounts", type=int, default=50)
    parser.add_argument("--marks", type=int, default=20)
    parser.add_argument("--burst-multiplier", type=int, default=2)
    args = parser.parse_args()
    result = benchmark(
        accounts=args.accounts,
        marks=args.marks,
        burst_multiplier=args.burst_multiplier,
    )
    print(json.dumps(result, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
