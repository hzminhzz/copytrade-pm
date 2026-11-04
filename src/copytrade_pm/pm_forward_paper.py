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
        }
