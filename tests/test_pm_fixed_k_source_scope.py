"""Source NAV is not needed for parent-only, all-DEX perpetual position scope."""

from contextlib import closing
import json
import sqlite3

from copytrade_pm.pm03_account import digest
from copytrade_pm.pm_fixed_k_source_scope import assess_selected_parent_perp_scope
from test_pm_forward_readiness import _setup


def _book(tmp_path):
    roots = _setup(tmp_path)
    source = roots[3]
    with closing(sqlite3.connect(source.path)) as con:
        raw = con.execute("SELECT payload FROM source_receipts LIMIT 1").fetchone()[0]
    return json.loads(raw)["source_book"]


def _change(book, **changes):
    body = {key: value for key, value in book.items() if key != "snapshot_sha"}
    body.update(changes)
    return {**body, "snapshot_sha": digest(body)}


def test_official_parent_perp_scope_observed_without_any_nav(tmp_path):
    book = _book(tmp_path)
    assert book["source_equity"] is None
    assert book["account_scope_complete"] is False  # whole wallet, not parent
    report = assess_selected_parent_perp_scope(book, decision_at=book["first_known_at"])
    assert report["status"] == "SELECTED_SCOPE_OBSERVED_RESEARCH_ONLY"
    assert report["position_scope_observed"] is True
    assert report["source_nav_required"] is False
    assert report["trading_authorized"] is False
    assert report["order_route"] == "NONE"


def test_tamper_missing_dex_and_unknown_pos_fail_closed(tmp_path):
    book = _book(tmp_path)
    bad_hash = {**book, "positions": {}}
    assert (
        "SELECTED_SOURCE_SHA_OR_SCHEMA_INVALID"
        in assess_selected_parent_perp_scope(bad_hash, decision_at=book["first_known_at"])[
            "reasons"
        ]
    )
    bad_census = _change(book, observed_dexes=[])
    assert (
        "SELECTED_SOURCE_DEX_CENSUS_INCOMPLETE"
        in assess_selected_parent_perp_scope(bad_census, decision_at=book["first_known_at"])[
            "reasons"
        ]
    )
    bad_pos = _change(book, positions={"ETH": "1"})
    assert (
        "SELECTED_SOURCE_POSITION_INVALID"
        in assess_selected_parent_perp_scope(bad_pos, decision_at=book["first_known_at"])["reasons"]
    )


def test_unknown_local_first_known_not_replaced_with_event_time(tmp_path):
    book = _book(tmp_path)
    moved = _change(book, first_known_at="2026-10-28T00:00:00+00:00")
    assert (
        "SELECTED_SOURCE_CLOCK_STALE_OR_INVALID"
        in assess_selected_parent_perp_scope(moved, decision_at=book["first_known_at"])["reasons"]
    )
