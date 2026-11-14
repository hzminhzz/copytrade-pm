"""Selected official parent-only streaming deployment and wire SHA regressions."""

from contextlib import closing
from hashlib import sha256
import json
import sqlite3

import pytest

from copytrade_pm.pm_forward_journal import PaperJournal
from copytrade_pm.pm_forward_observed_paper import _read_source, _readonly
from copytrade_pm.pm_forward_stream_journal import (
    verify_official_position_transition,
    verify_streams,
)
from copytrade_pm.pm_source_selection import official_accounts, selected_parents
from test_pm_forward_multi_portfolio import full_registry, pin_reviewed_registry
from test_pm_forward_observed_paper import at
from test_pm_vike_paper_integration import official_frame


def test_selected_service_uses_exact_verified_p1_p14_p16_parent_union(tmp_path, monkeypatch):
    pin_reviewed_registry(monkeypatch)
    db = full_registry(tmp_path)
    # This synthetic registry fixture predates the P1 seal table.
    with closing(sqlite3.connect(db)) as conn:
        conn.execute("CREATE TABLE portfolio_seals (id INTEGER PRIMARY KEY)")
        conn.commit()
    parents = selected_parents(
        db,
        portfolios=("P1", "P14", "P16"),
        as_of=at(0),
    )
    assert set(parents) == {"S035", "S051", "S053", "S064", "Whale_0x5f94"}
    assert len(set(parents.values())) == 5
    with pytest.raises(ValueError, match="DUPLICATE_ACCOUNTS|PORTFOLIOS_INVALID"):
        selected_parents(db, portfolios=("P14", "P14"), as_of=at(0))
    with pytest.raises(ValueError, match="PORTFOLIO_UNAPPROVED"):
        selected_parents(db, portfolios=("unknown",), as_of=at(0))


def test_official_wire_sha_and_signed_positions_verify_without_fill_rebuild(tmp_path):
    journal = PaperJournal(tmp_path / "position")
    address = official_frame(1, 0)["data"]["user"]

    def info(req):
        assert req == {"type": "perpDexs"}
        catalog = [None]
        raw = json.dumps(catalog, sort_keys=True).encode()
        return catalog, raw, sha256(raw).hexdigest()

    source = official_accounts(journal, {"S035": address}, info=info)["S035"]
    source.begin(at(0))
    for at_seconds, qty, expected in (
        (1, 0, "BASELINE"),
        (12, 20, "OBSERVED_STATE_CHANGE"),
    ):
        frame = official_frame(at_seconds, qty)
        wire = json.dumps(frame, separators=(",", ":"))
        result = source.observe(
            frame,
            at(at_seconds + 1),
            raw_sha=sha256(wire.encode()).hexdigest(),
            raw_text=wire,
        )
        assert result["classification"] == expected

    with closing(_readonly(journal.path)) as db:
        receipt = _read_source(db, "S035", 2)
        assert receipt is not None
        assert verify_official_position_transition(
            db,
            alias="S035",
            receipt_id=receipt["receipt_id"],
            receipt_sha=receipt["sha"],
            receipt=receipt["receipt"],
            require_current_positions=True,
        )
    assert verify_streams(journal.path)["streams"]["account:S035"]["observation_count"] == 1
    # A malformed frame may GAP without changing the socket epoch. Rebaseline
    # must not revive an older, unconsumed T+300 source opportunity.
    source.gap(at(20), "SIMULATED_FRAME_FAULT")
    source.observe(official_frame(21, 0), at(22))
    with closing(_readonly(journal.path)) as db:
        receipt = _read_source(db, "S035", 2)
        assert not verify_official_position_transition(
            db,
            alias="S035",
            receipt_id=receipt["receipt_id"],
            receipt_sha=receipt["sha"],
            receipt=receipt["receipt"],
        )


def test_official_catalog_does_not_trust_tampered_wire_or_metadata(tmp_path):
    journal = PaperJournal(tmp_path / "position")
    address = official_frame(1, 0)["data"]["user"]

    def corrupt(_):
        raw = b"[null]"
        return [None], raw, "0" * 64

    with pytest.raises(ValueError, match="CATALOG_PROVENANCE_INVALID"):
        official_accounts(journal, {"S035": address}, info=corrupt)
