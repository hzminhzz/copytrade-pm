"""Offline, fixture-only source-to-PM04 paper worker (FP-09/11 partial).

Consumes already captured whole-book/market events under one shared private
journal. No websocket, provider request, service manager or broker dependency.
This module is NOT a live-source producer and cannot report PAPER_OBSERVED.
"""

from __future__ import annotations

from contextlib import closing
from decimal import Decimal
import json
import sqlite3

from .pm03_account import clock, digest, number
from .pm_forward_admission import admit_source_book
from .pm_forward_journal import PaperJournal
from .pm_forward_paper import PaperCampaign, PaperManifest
from .pm_forward_portfolios import FrozenPaperPortfolio


class FixturePaperWorker:
    """One frozen paper campaign driven by already captured fixture receipts."""

    def __init__(
        self,
        journal: PaperJournal,
        portfolio: FrozenPaperPortfolio,
        manifest: PaperManifest,
        frozen_policy: dict,
    ) -> None:
        if (
            manifest.portfolio_sha != portfolio.sha
            or manifest.policy_sha != digest(frozen_policy)
            or manifest.payload().get("order_route") != "NONE"
        ):
            raise ValueError("PAPER_WORKER_FROZEN_CONTRACT_MISMATCH")
        if set(frozen_policy.get("pods", {})) != set(portfolio.members) or set(
            frozen_policy.get("follower_allocations", {})
        ) != set(portfolio.members):
            raise ValueError("PAPER_WORKER_POD_CENSUS_MISMATCH")
        self.journal = journal
        self.portfolio = portfolio
        self.manifest = manifest
        self.policy = frozen_policy
        self.campaign = PaperCampaign(journal=journal)
        self.campaign.register(manifest)
        t0 = manifest.started_at
        self.campaign.record_event(
            manifest.run_id,
            "configure",
            {
                "kind": "PM04_CONFIG",
                "run_id": manifest.run_id,
                "event_at": t0,
                "source_event_at": t0,
                "first_known_at": t0,
                "hypothetical_fill_at": t0,
                "sealed_policy_sha": manifest.policy_sha,
                "evidence_class": "FORWARD_PAPER_SIMULATED_v1",
                "order_route": "NONE",
                "fixture_attested": True,
                "input": {"policy": frozen_policy},
            },
        )

    def _latest_source(self, alias: str) -> tuple[int, dict, dict] | None:
        # Verify the entire source chain before trusting the most recent row.
        state = self.journal.source_status(alias)
        if not state["cursor"]:
            return None
        uri = "file:" + str(self.journal.path.resolve()) + "?mode=ro"
        with closing(sqlite3.connect(uri, uri=True, timeout=0)) as db:
            db.execute("PRAGMA query_only=ON")
            row = db.execute(
                "SELECT seq,payload FROM source_receipts WHERE source_id=? "
                "ORDER BY seq DESC LIMIT 1",
                (alias,),
            ).fetchone()
        if row is None:
            return None
        receipt = json.loads(row[1])
        book = receipt.get("source_book")
        if not isinstance(book, dict) or receipt.get("payload_sha") != book.get("snapshot_sha"):
            raise ValueError("PAPER_SOURCE_CONTENT_NOT_AVAILABLE")
        return (row[0], receipt, book)

    def record_source_book(
        self, alias: str, sequence: int, receipt_id: str, book: dict, *, captured_at: str
    ) -> dict:
        if alias not in self.portfolio.members:
            raise ValueError("WALLET_NOT_IN_SEALED_PORTFOLIO")
        if book.get("wallet_id") != alias:
            raise ValueError("SOURCE_ALIAS_MISMATCH")
        admission = admit_source_book(book, decision_at=captured_at, fill_at=captured_at)
        if not admission.admitted:
            return {"status": "BLOCKED_SOURCE", "reasons": list(admission.reason_codes)}
        if clock(book["first_known_at"]) > clock(captured_at):
            raise ValueError("FUTURE_SOURCE_BOOK")
        receipt = {
            "schema": "paper_first_known_source_v1",
            "source_id": alias,
            "source_event_at": book["source_event_at"],
            "first_known_at": book["first_known_at"],
            "captured_at": captured_at,
            "payload_sha": book["snapshot_sha"],
            "source_book": book,
        }
        return self.journal.append_source_receipt(alias, sequence, receipt_id, receipt)

    def readiness(self, *, decision_at: str) -> dict:
        clock(decision_at)
        missing: list[str] = []
        stale: list[str] = []
        for alias in self.portfolio.members:
            captured = self._latest_source(alias)
            if captured is None:
                missing.append(alias)
            else:
                _, receipt, book = captured
                validated = admit_source_book(book, decision_at=decision_at, fill_at=decision_at)
                if (
                    not validated.admitted
                    or (clock(decision_at) - clock(receipt["captured_at"])).total_seconds()
                    > self.policy["max_signal_age_seconds"]
                ):
                    stale.append(alias)
        return {
            "status": "READY_SYNTHETIC" if not missing and not stale else "BLOCKED",
            "missing_wallets": missing,
            "stale_or_incomplete_wallets": stale,
            "evidence_class": "FORWARD_PAPER_SIMULATED_v1",
            "paper_observed": False,
            "order_route": "NONE",
        }

    def drive(
        self,
        *,
        decision_at: str,
        hypothetical_fill_at: str,
        observations: list[dict],
        shocks: list[dict],
        evidence: dict,
        costs: dict,
        market_contracts: dict,
    ) -> dict:
        """Process each independently captured wallet exactly once, then PM04 tick.

        With a missing member, do NOT paper-trade the remaining subset.
        A failed market/risk gate cannot silently advance any source cursor.
        """
        health = self.readiness(decision_at=decision_at)
        if health["status"] != "READY_SYNTHETIC":
            return health
        if not clock(decision_at) <= clock(hypothetical_fill_at):
            raise ValueError("PAPER_FILL_IN_PAST")
        event_input = {
            "observations": observations,
            "shocks": shocks,
            "evidence": evidence,
            "costs": costs,
        }
        for alias in self.portfolio.members:
            source = self._latest_source(alias)
            if source is None:
                raise ValueError("MISSING_FULL_SOURCE_BOOK")
            seq, receipt, book = source
            cursors = self.journal.restore(self.manifest.run_id)["source_cursors"]
            if cursors.get(alias, 0) >= seq:
                continue
            if cursors.get(alias, 0) + 1 != seq:
                raise ValueError("PAPER_SOURCE_SEQUENCE_BACKLOG_NOT_CONSUMED")
            admission = admit_source_book(
                book, decision_at=decision_at, fill_at=hypothetical_fill_at
            )
            if not admission.admitted or admission.source_equity is None:
                raise ValueError("PAPER_SOURCE_ADMISSION_LOST")
            scale = number(self.policy["follower_allocations"][alias]) / admission.source_equity
            quantities = {k.key: quantity * scale for k, quantity in admission.positions.items()}
            stored = self.journal.restore(self.manifest.run_id)["account"]["pm04"]
            prev_targets = stored["pod_targets"].get(alias, {})
            for key in prev_targets:
                quantities.setdefault(key, Decimal("0"))
            versions = stored["versions"].get(alias, {})
            targets = [
                {
                    "pod": alias,
                    "instrument": key,
                    "quantity": str(value),
                    "revision": versions.get(key, 0) + 1,
                    "source_event_at": book["source_event_at"],
                    "first_known_at": book["first_known_at"],
                    "source_sha": book["snapshot_sha"],
                    "budget_ref": self.policy["pods"][alias]["budget_ref"],
                }
                for key, value in sorted(quantities.items())
            ]
            event = {
                "kind": "PM04_SIGNAL",
                "run_id": self.manifest.run_id,
                "event_at": decision_at,
                "source_event_at": book["source_event_at"],
                "first_known_at": book["first_known_at"],
                "hypothetical_fill_at": hypothetical_fill_at,
                "sealed_policy_sha": self.manifest.policy_sha,
                "evidence_class": "FORWARD_PAPER_SIMULATED_v1",
                "fixture_attested": True,
                "order_route": "NONE",
                "source_book": book,
                "source_ref": {
                    "source_id": alias,
                    "sequence": seq,
                    "receipt_sha": digest(receipt),
                },
                "market_contracts": market_contracts,
                "input": {**event_input, "targets": targets},
            }
            self.campaign.record_source_decision(self.manifest.run_id, f"src_{alias}_{seq}", event)
        tick = {
            "kind": "PM04_TICK",
            "run_id": self.manifest.run_id,
            "event_at": decision_at,
            "source_event_at": decision_at,
            "first_known_at": decision_at,
            "hypothetical_fill_at": hypothetical_fill_at,
            "sealed_policy_sha": self.manifest.policy_sha,
            "evidence_class": "FORWARD_PAPER_SIMULATED_v1",
            "fixture_attested": True,
            "order_route": "NONE",
            "market_contracts": market_contracts,
            "input": event_input,
        }
        # Caller must supply a unique decision clock; duplicate replay is
        # idempotent only if the full tick input remains identical.
        self.campaign.record_event(self.manifest.run_id, "tick_" + digest(tick), tick)
        return {
            "status": "SYNTHETIC_EVENT_COMMITTED",
            "run_id": self.manifest.run_id,
            "state": self.campaign.status(self.manifest.run_id),
            "paper_observed": False,
        }
