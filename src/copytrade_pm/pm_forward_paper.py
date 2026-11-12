"""Sealed, paper-only campaign admission facade (FP-01).

No transport, service activation, or real/virtual fill methods exist here.
The existing PM-03 Account is the only financial state owner.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .pm_forward_journal import PaperJournal

from .pm03_account import Account, Rulebook, clock, digest

SCHEMA = "paper_run_manifest_v1"
STATUS_SCHEMA = "paper_run_status_v1"
EVIDENCE_CLASS = "FORWARD_PAPER_SIMULATED_v1"
ORDER_ROUTE = "NONE"


@dataclass(frozen=True)
class PaperManifest:
    run_id: str
    account_id: str
    portfolio_sha: str
    market_manifest_sha: str
    release_sha: str
    selected_at: str
    started_at: str
    rulebook: Rulebook
    policy_sha: str

    def __post_init__(self) -> None:
        for value in (self.run_id, self.account_id):
            if (
                not value
                or value in {".", ".."}
                or any(
                    c not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-"
                    for c in value
                )
            ):
                raise ValueError("UNSAFE_PAPER_IDENTIFIER")
        for value in (
            self.portfolio_sha,
            self.market_manifest_sha,
            self.release_sha,
            self.policy_sha,
        ):
            if len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
                raise ValueError("INVALID_MANIFEST_SHA")
        if clock(self.selected_at) > clock(self.started_at):
            raise ValueError("FUTURE_KNOWN_PORTFOLIO")
        if clock(self.rulebook.observed_at) > clock(self.started_at):
            raise ValueError("FUTURE_KNOWN_RULEBOOK")
        if self.rulebook.initial_balance != Decimal("10000"):
            raise ValueError("PAPER_STARTING_BALANCE_MUST_BE_10000")

    def payload(self) -> dict[str, Any]:
        return {
            "schema": SCHEMA,
            "run_id": self.run_id,
            "account_id": self.account_id,
            "portfolio_sha": self.portfolio_sha,
            "market_manifest_sha": self.market_manifest_sha,
            "release_sha": self.release_sha,
            "selected_at": self.selected_at,
            "started_at": self.started_at,
            "rulebook": self.rulebook.to_dict(),
            "policy_sha": self.policy_sha,
            "order_route": ORDER_ROUTE,
            "evidence_class": EVIDENCE_CLASS,
        }

    @property
    def sha(self) -> str:
        return digest(self.payload())


class PaperCampaign:
    """In-memory FP-01 interface; FP-02 adds a durable separate journal."""

    def __init__(self, *, journal: PaperJournal | None = None) -> None:
        self._runs: dict[str, tuple[PaperManifest, Account]] = {}
        self._accounts: set[str] = set()
        self._journal = journal

    def register(self, manifest: PaperManifest) -> dict:
        previous = self._runs.get(manifest.run_id)
        if previous is not None:
            if previous[0].sha != manifest.sha:
                raise ValueError("CONFLICTING_PAPER_RUN_MANIFEST")
            return self.status(manifest.run_id)
        if manifest.account_id in self._accounts:
            raise ValueError("PAPER_ACCOUNT_ALREADY_REGISTERED")
        account = Account.start(manifest.rulebook, manifest.started_at)
        account.verify()
        if self._journal is not None:
            self._journal.register(manifest)
        self._runs[manifest.run_id] = (manifest, account)
        self._accounts.add(manifest.account_id)
        return self.status(manifest.run_id)

    def record_event(self, run_id: str, event_id: str, event: dict) -> dict:
        if self._journal is None:
            raise ValueError("PAPER_JOURNAL_REQUIRED")
        if run_id not in self._runs:
            raise ValueError("UNKNOWN_PAPER_RUN")
        self._journal.append(run_id, event_id, event)
        return self.status(run_id)

    def record_source_decision(self, run_id: str, event_id: str, event: dict) -> dict:
        """Public causal source-to-account seam with one SQLite transaction."""
        if self._journal is None:
            raise ValueError("PAPER_JOURNAL_REQUIRED")
        if run_id not in self._runs:
            raise ValueError("UNKNOWN_PAPER_RUN")
        self._journal.consume_source_effect(run_id, event_id, event)
        return self.status(run_id)

    def record_selected_checkpoint_wave(
        self, selected, requests: dict, *, at_ms: int, catalog: dict
    ) -> dict:
        """Bind the existing SQLite-selected campaign to independently approved runs."""
        from contextlib import closing
        import json
        import sqlite3

        from .pm_copy_mandate import CopyMandate
        from .pm_v4_sixteen_scenarios import IDENTITIES

        if self._journal is None:
            raise ValueError("PAPER_JOURNAL_REQUIRED")
        if set(selected.profiles) != set(IDENTITIES) or set(requests) - set(IDENTITIES):
            raise ValueError("CHECKPOINT_SELECTED_CAMPAIGN_ROSTER")
        ready, blocked = {}, {}
        with closing(sqlite3.connect(f"file:{self._journal.path}?mode=ro", uri=True)) as db:
            for name, profile in selected.profiles.items():
                try:
                    request = requests.get(name)
                    manifest_row = db.execute(
                        "SELECT manifest FROM runs WHERE run_id=?", (name,)
                    ).fetchone()
                    if not request or manifest_row is None:
                        raise ValueError("CHECKPOINT_SIGNED_MANDATES_OR_RUN_MISSING")
                    manifest = json.loads(manifest_row[0])
                    if manifest["portfolio_sha"] != selected.seals[name]["definition_sha256"]:
                        raise ValueError("CHECKPOINT_SELECTED_DEFINITION_DRIFT")
                    rows = request if isinstance(request, list) else [request]
                    sources = []
                    for row in rows:
                        saved = db.execute(
                            "SELECT mandate FROM copy_mandate_heads WHERE owner=?", (row["owner"],)
                        ).fetchone()
                        if saved is None:
                            raise ValueError("CHECKPOINT_SIGNED_MANDATE_MISSING")
                        mandate = CopyMandate.model_validate_json(saved[0])
                        source = mandate.source_id
                        sources.append(source)
                        if (
                            mandate.account_id != manifest["account_id"]
                            or source not in profile.source_ids
                            or mandate.source_account_sha != selected.account_hashes[name][source]
                            or mandate.k != Decimal(profile.k[source])
                            or Decimal(row["policy"]["pod_loss_limit"])
                            > Decimal(profile.risk[source])
                        ):
                            raise ValueError("CHECKPOINT_SELECTED_MANDATE_OR_RISK_DRIFT")
                    if len(sources) != len(set(sources)) or set(sources) != set(profile.source_ids):
                        raise ValueError("CHECKPOINT_SELECTED_MANDATE_COVERAGE")
                    ready[name] = request
                except ValueError as exc:
                    blocked[name] = {
                        "status": "UNRESOLVED",
                        "reason": str(exc),
                        "order_route": "NONE",
                    }
        result = self.record_checkpoint_wave(ready, at_ms=at_ms, catalog=catalog)
        result["portfolios"].update(blocked)
        return result

    def record_checkpoint_wave(self, requests: dict, *, at_ms: int, catalog: dict) -> dict:
        """Consume a caller-scheduled canonical wave with independent account commits."""
        if self._journal is None:
            raise ValueError("PAPER_JOURNAL_REQUIRED")
        portfolios = {}
        for run_id, request in sorted(requests.items()):
            rows = request if isinstance(request, list) else [request]
            results = []
            for row in rows:
                try:
                    result = self._journal.consume_checkpoint(
                        run_id,
                        row["owner"],
                        row["outcome_id"],
                        at_ms=at_ms,
                        policy=row["policy"],
                        catalog=catalog,
                    )
                except ValueError as exc:
                    result = {
                        "status": "UNRESOLVED",
                        "reason": str(exc),
                        "outcome_id": row["outcome_id"],
                        "order_route": "NONE",
                    }
                results.append(result)
            portfolios[run_id] = results[0] if len(results) == 1 else {"consumers": results}
        return {
            "schema": "checkpoint_paper_wave_v3",
            "portfolios": portfolios,
            "order_route": "NONE",
            "trading_authorized": False,
        }

    def checkpoint_status(self, run_id: str) -> dict:
        if self._journal is None:
            raise ValueError("PAPER_JOURNAL_REQUIRED")
        saved = self._journal.restore(run_id)
        state = saved["account"].get("pm04", {}).get("checkpoint_v3", {})
        outcomes = state.get("outcomes", {})
        counts: dict[str, int] = {}
        for row in outcomes.values():
            counts[row["status"]] = counts.get(row["status"], 0) + 1
        coverage = state.get("coverage", {})
        return {
            "schema": "checkpoint_paper_status_v3",
            "run_id": run_id,
            "coverage": coverage,
            "coverage_complete": bool(coverage) and all(coverage.values()),
            "dispositions": counts,
            "outcomes": outcomes,
            "account": saved["account"],
            "journal_head_sha": saved["journal_head_sha"],
            "cursor": saved["cursor"],
            "order_route": "NONE",
            "scientifically_qualified": False,
            "trading_authorized": False,
        }

    def status(self, run_id: str) -> dict:
        manifest, account = self._runs[run_id]
        persisted = self._journal.restore(run_id) if self._journal is not None else None
        return {
            "schema": STATUS_SCHEMA,
            "run_id": run_id,
            "account_id": manifest.account_id,
            "manifest_sha": manifest.sha,
            "release_sha": manifest.release_sha,
            "portfolio_sha": manifest.portfolio_sha,
            "policy_sha": manifest.policy_sha,
            "order_route": ORDER_ROUTE,
            "evidence_class": EVIDENCE_CLASS,
            "worker_status": "NOT_RUNNING",
            "admission": "BLOCKED",
            "blockers": [
                "NO_PROSPECTIVE_SOURCE_ADMISSION",
                "NO_MARKET_ADMISSION",
                "WORKER_NOT_STARTED",
            ],
            "account": persisted["account"] if persisted is not None else account.snapshot(),
            "cursor": persisted["cursor"] if persisted is not None else 0,
            "journal_head_sha": persisted["journal_head_sha"] if persisted is not None else None,
            "source_cursors": persisted["source_cursors"] if persisted is not None else {},
        }
