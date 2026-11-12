"""CWSA Chapter 2: Six clean SQLite-sealed paper portfolios with shared canonical source.

Runs six isolated PM-03/04 virtual paper ledgers under a new prospective epoch root.
First checkpoint is a nonactionable baseline. Zero initial virtual holdings,
zero fills, zero fees, zero realized P&L. Portfolios without approved copy
mandates stay in BLOCKED_EVIDENCE with order route NONE.

No broker route, live orders, or funded trading authorization.
"""

from __future__ import annotations

import argparse
from contextlib import closing
from datetime import datetime, timezone
from decimal import Decimal
import json
import os
from pathlib import Path
import signal
import sqlite3
import sys
import time

from .pm03_account import digest
from .pm03_rules import propr_rulebook
from .pm_cwsa_chapter2_waves import WaveReceipts, parse_outcome, publication_grace_ms
from .pm_cwsa_chapter2_release import FinanceScan, read_activation_bundle
from .pm_cwsa_chapter2_mirror import consume_canonical_paper
from .pm_forward_journal import PaperJournal
from .pm_forward_paper import PaperManifest

EPOCH_ID = "cwsa_chapter2_20261112"

PORTFOLIO_CONFIGS: dict[str, dict] = {
    "A": {
        "portfolio_id": "A",
        "folder": "A",
        "starting_balance": Decimal("10000"),
        "nominal_risk": Decimal("600"),
        "pod_risk": Decimal("200"),
        "members": ("W028", "W030", "W042"),
        "sizing_contract": "Q3_E0_ILLUSTRATIVE_10000_USD_NOT_LIVE",
    },
    "B": {
        "portfolio_id": "B",
        "folder": "B",
        "starting_balance": Decimal("10000"),
        "nominal_risk": Decimal("600"),
        "pod_risk": Decimal("200"),
        "members": ("CA-005", "W031", "W044"),
        "sizing_contract": "Q3_E0_ILLUSTRATIVE_10000_USD_NOT_LIVE",
    },
    "C": {
        "portfolio_id": "C",
        "folder": "C",
        "starting_balance": Decimal("10000"),
        "nominal_risk": Decimal("600"),
        "pod_risk": Decimal("200"),
        "members": ("CO-001", "VS066", "W015"),
        "sizing_contract": "Q3_E0_ILLUSTRATIVE_10000_USD_NOT_LIVE",
    },
    "Combo2": {
        "portfolio_id": "Combo2",
        "folder": "Combo2",
        "starting_balance": Decimal("5000"),
        "nominal_risk": Decimal("300"),
        "pod_risk": Decimal("100"),
        "members": ("CA-008", "W015", "W028"),
        "sizing_contract": "COMBO2_VIRTUAL_5000_USD_ACCOUNT_NOT_BROKER",
    },
    "regime.macro/TriadA": {
        "portfolio_id": "regime.macro/TriadA",
        "folder": "TriadA",
        "starting_balance": Decimal("10000"),
        "nominal_risk": Decimal("600"),
        "pod_risk": Decimal("200"),
        "members": ("ACT04", "ACT08", "ACT09"),
        "sizing_contract": "NON_EXECUTABLE_SIGNED_RESEARCH",
    },
    "regime.macro/TriadChop": {
        "portfolio_id": "regime.macro/TriadChop",
        "folder": "TriadChop",
        "starting_balance": Decimal("10000"),
        "nominal_risk": Decimal("600"),
        "pod_risk": Decimal("200"),
        "members": ("ACT04", "ACT09", "ACT10"),
        "sizing_contract": "NON_EXECUTABLE_SIGNED_RESEARCH",
    },
}

ALL_14_WALLETS = (
    "ACT04",
    "ACT08",
    "ACT09",
    "ACT10",
    "CA-005",
    "CA-008",
    "CO-001",
    "VS066",
    "W015",
    "W028",
    "W030",
    "W031",
    "W042",
    "W044",
)


def load_registry_seals(registry_db: Path) -> dict[str, dict]:
    """Read version 2 seals and memberships directly from SQLite authority."""
    if not registry_db.is_file():
        raise ValueError(f"REGISTRY_DB_NOT_FOUND: {registry_db}")
    seals: dict[str, dict] = {}
    with closing(sqlite3.connect(f"file:{registry_db.resolve()}?mode=ro", uri=True)) as con:
        con.row_factory = sqlite3.Row
        cur = con.cursor()
        for pid, cfg in PORTFOLIO_CONFIGS.items():
            row = cur.execute(
                "SELECT portfolio_id, version, definition_sha256, selection_known_at FROM portfolio_seals WHERE portfolio_id=? AND version=2",
                (pid,),
            ).fetchone()
            if not row:
                raise ValueError(f"SEAL_V2_MISSING: {pid}")
            members_rows = cur.execute(
                "SELECT member_alias FROM portfolio_memberships WHERE portfolio_id=? AND version=2 ORDER BY member_alias",
                (pid,),
            ).fetchall()
            actual_members = tuple(r["member_alias"] for r in members_rows)
            expected_members = tuple(sorted(cfg["members"]))
            if actual_members != expected_members:
                raise ValueError(
                    f"MEMBERSHIP_MISMATCH: {pid} expected {expected_members} got {actual_members}"
                )
            seals[pid] = {
                "portfolio_id": pid,
                "version": 2,
                "definition_sha256": row["definition_sha256"],
                "selection_known_at": row["selection_known_at"],
                "members": actual_members,
            }
    return seals


class Chapter2PaperSupervisor:
    """Supervises the six independent paper journals fed by the canonical CWSA source."""

    def __init__(
        self,
        *,
        state_root: Path,
        source_db: Path,
        registry_db: Path,
        run_label: str = EPOCH_ID,
        release_sha: str | None = None,
        publication_grace_override_ms: int | None = None,
        approval_path: Path | None = None,
        approval_sha256: str | None = None,
        trusted_authority_hex: str | None = None,
        quote_db: Path | None = None,
        activation_now_ms: int | None = None,
    ) -> None:
        self._activation_now_ms = (
            time.time_ns() // 1_000_000 if activation_now_ms is None else activation_now_ms
        )
        if type(self._activation_now_ms) is not int or self._activation_now_ms <= 0:
            raise ValueError("CHAPTER2_ACTIVATION_CLOCK")
        self.state_root = Path(state_root).resolve()
        self.source_db = Path(source_db).resolve()
        self.registry_db = Path(registry_db).resolve()
        if (
            not isinstance(run_label, str)
            or not 1 <= len(run_label) <= 48
            or not all(c.isascii() and (c.isalnum() or c in "_-") for c in run_label)
        ):
            raise ValueError("CHAPTER2_EPOCH_ID_INVALID")
        self.run_label = run_label
        self.release_sha = release_sha or os.environ.get(
            "COPYTRADE_RELEASE_SHA", "cwsa_chapter2_20261112"
        )
        self.seals = load_registry_seals(self.registry_db)
        self.approved = read_activation_bundle(
            path=approval_path,
            expected_sha256=approval_sha256,
            trusted_authority_hex=trusted_authority_hex,
            seals=self.seals,
            configs=PORTFOLIO_CONFIGS,
            run_label=self.run_label,
            source_db=self.source_db,
        )
        self.quote_db = Path(quote_db).resolve() if quote_db is not None else None
        if self.approved and (self.quote_db is None or not self.quote_db.is_file()):
            raise ValueError("CHAPTER2_INDEPENDENT_QUOTES_REQUIRED")
        self._finance_attempts: dict[tuple[str, str, str], int] = {}
        self._finance_errors: dict[str, str] = {}
        self.journals: dict[str, PaperJournal] = {}
        self.wave_ledgers: dict[str, WaveReceipts] = {}
        self.finance_scans: dict[str, FinanceScan] = {}
        self.last_processed_checkpoint_ms: int = 0
        self._initialize_journals()
        self.last_processed_checkpoint_ms = min(
            ledger.last_checkpoint_ms for ledger in self.wave_ledgers.values()
        )
        self.publication_grace_ms = publication_grace_ms(
            self.source_db, override=publication_grace_override_ms
        )
        self._recover_status()

    def _recover_status(self) -> None:
        """Rebuild presentation state from immutable receipts after any crash.

        Status JSON is a replaceable projection, not a financial source of truth.
        Source waves and PM03 account events remain in their own SQLite journals.
        """
        results: dict[str, dict] = {}
        for pid, cfg in PORTFOLIO_CONFIGS.items():
            wave = self.wave_ledgers[pid].latest()
            if wave is None:
                continue
            checkpoint_ms = wave["checkpoint_ms"]
            status = {
                "portfolio_id": pid,
                "run_id": cfg["folder"],
                "folder": cfg["folder"],
                "checkpoint_ms": checkpoint_ms,
                "checkpoint_utc": datetime.fromtimestamp(
                    checkpoint_ms / 1000, timezone.utc
                ).isoformat(),
                "source_checkpoint_cursor_ms": checkpoint_ms,
                "source_receipt_sha": digest(wave),
                "starting_balance": str(cfg["starting_balance"]),
                "members": list(cfg["members"]),
                "missing_sources": wave["missing_sources"],
                "coverage_complete": wave["coverage_complete"],
                "source_wave_state": ("COMPLETE" if wave["coverage_complete"] else "COVERAGE_GAP"),
                "source_kinds": {member: item["kind"] for member, item in wave["outcomes"].items()},
                "order_route": "NONE",
                "trading_authorized": False,
            }
            status = self._refresh_portfolio_finance(pid, status)
            path = self.state_root / cfg["folder"] / "status.json"
            temporary = path.with_suffix(".json.tmp")
            with open(temporary, "w", encoding="utf-8") as out:
                json.dump(status, out, indent=2)
            temporary.replace(path)
            results[pid] = status
        if results:
            latest = max(item["checkpoint_ms"] for item in results.values())
            self._write_campaign_status(
                latest,
                datetime.fromtimestamp(latest / 1000, timezone.utc).isoformat(),
                results,
            )

    def _initialize_journals(self) -> None:
        """Create and initialize six isolated, verified clean paper journals."""
        self.state_root.mkdir(parents=True, exist_ok=True, mode=0o700)
        for pid, cfg in PORTFOLIO_CONFIGS.items():
            folder = cfg["folder"]
            journal_dir = self.state_root / folder
            journal_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
            journal = PaperJournal(journal_dir)
            self.journals[pid] = journal
            self.wave_ledgers[pid] = WaveReceipts(journal)
            if pid in self.approved:
                self.finance_scans[pid] = FinanceScan(journal)

            run_id = cfg["folder"]
            # Check if run is already registered
            with closing(sqlite3.connect(f"file:{journal.path}?mode=ro", uri=True)) as db:
                row = db.execute(
                    "SELECT manifest,cursor FROM runs WHERE run_id=?", (run_id,)
                ).fetchone()
            approved = self.approved.get(pid)
            expected_policy_sha = (
                digest(approved.policy) if approved else digest(["CHAPTER2_FINANCE_DISABLED", pid])
            )
            expected_market_sha = (
                digest(approved.catalog)
                if approved
                else digest(["CHAPTER2_MARKET_UNQUALIFIED", pid])
            )
            account_id = f"acct_{cfg['folder'].lower()}_{self.run_label}"
            if row is None:
                # Each new, real mandate release requires a *new* empty epoch.
                # A provisional run cannot be retrospectively upgraded.
                started_iso = datetime.fromtimestamp(
                    self._activation_now_ms / 1000, timezone.utc
                ).isoformat()
                rulebook = (
                    approved.rulebook
                    if approved
                    else propr_rulebook(
                        "classic_1step",
                        "evaluation",
                        cfg["starting_balance"],
                        observed_at=self.seals[pid]["selection_known_at"],
                    )
                )
                manifest = PaperManifest(
                    run_id=run_id,
                    account_id=account_id,
                    portfolio_sha=self.seals[pid]["definition_sha256"],
                    market_manifest_sha=expected_market_sha,
                    release_sha=digest(self.release_sha),
                    policy_sha=expected_policy_sha,
                    selected_at=self.seals[pid]["selection_known_at"],
                    started_at=started_iso,
                    rulebook=rulebook,
                )
                journal.register(manifest)
            else:
                current = json.loads(row[0])
                # The first Chapter 2 observer wrote six nonfinancial, empty
                # placeholder manifests with literal-zero pins. Retain those
                # bytes unchanged, strictly *only* as unsigned observation
                # ledgers. A real signed paper release requires a new epoch.
                legacy_placeholder = (
                    approved is None
                    and current["policy_sha"] == "0" * 64
                    and current["market_manifest_sha"] == "0" * 64
                    and row[1] == 0
                    and current["account_id"] == account_id
                    and current["portfolio_sha"] == self.seals[pid]["definition_sha256"]
                )
                if (
                    current["account_id"] != account_id
                    or current["portfolio_sha"] != self.seals[pid]["definition_sha256"]
                    or (
                        not legacy_placeholder
                        and (
                            current["market_manifest_sha"] != expected_market_sha
                            or current["policy_sha"] != expected_policy_sha
                        )
                    )
                    or (approved and current["rulebook"] != approved.rulebook.to_dict())
                ):
                    raise ValueError(f"CHAPTER2_FINANCIAL_RELEASE_DRIFT: {pid}")

            restored = journal.restore(run_id)
            if row is None:
                acct = restored["account"]
                if acct.get("quantities") or acct.get("fills") or Decimal(acct.get("costs", "0")):
                    raise ValueError(f"DIRTY_NEW_PAPER_ACCOUNT: {pid}")
                if Decimal(str(acct.get("cash", "0"))) != cfg["starting_balance"]:
                    raise ValueError(f"STARTING_CASH_MISMATCH: {pid}")
            if approved:
                for mandate, envelope in approved.mandates:
                    if row is None and mandate.effective_from_ms < self._activation_now_ms:
                        raise ValueError("CHAPTER2_APPROVAL_NOT_PROSPECTIVE")
                    journal.activate_copy_mandate(
                        envelope,
                        approved.trusted_authority,
                        account_id=account_id,
                        at_ms=self._activation_now_ms,
                    )
                    journal.copy_mandate_state(mandate.owner)

    def process_checkpoint(
        self, checkpoint_ms: int, outcomes_by_source: dict[str, dict], *, observed_ms: int
    ) -> dict:
        """Durably close one source wave; finance stays gated by real mandates.

        These receipts are *observations*, not modeled fills. In particular,
        a non-empty mandate_heads table cannot promote an account to ACTIVE.
        """
        dt_str = datetime.fromtimestamp(checkpoint_ms / 1000, timezone.utc).isoformat()
        wave_results: dict[str, dict] = {}

        for pid, cfg in PORTFOLIO_CONFIGS.items():
            run_id = cfg["folder"]
            journal = self.journals[pid]
            ledger = self.wave_ledgers[pid]
            member_outcomes = {
                m: outcomes_by_source[m] for m in cfg["members"] if m in outcomes_by_source
            }
            status_path = self.state_root / cfg["folder"] / "status.json"
            if checkpoint_ms > ledger.last_checkpoint_ms and (
                len(member_outcomes) < len(cfg["members"])
                and observed_ms < checkpoint_ms + self.publication_grace_ms
            ):
                restored = journal.restore(run_id)
                wave_results[pid] = {
                    "portfolio_id": pid,
                    "run_id": run_id,
                    "folder": cfg["folder"],
                    "checkpoint_ms": checkpoint_ms,
                    "checkpoint_utc": dt_str,
                    "source_checkpoint_cursor_ms": ledger.last_checkpoint_ms,
                    "members": list(cfg["members"]),
                    "missing_sources": sorted(set(cfg["members"]) - set(member_outcomes)),
                    "coverage_complete": False,
                    "source_wave_state": "WAITING_SOURCE_WAVE",
                    "source_kinds": {m: v["kind"] for m, v in member_outcomes.items()},
                    "financial_admission": "BLOCKED_EVIDENCE",
                    "admission_reason": "NO_APPROVED_CHECKPOINT_FINANCIAL_CONSUMER",
                    "order_route": "NONE",
                    "trading_authorized": False,
                }
                wave_results[pid] = self._refresh_portfolio_finance(pid, wave_results[pid])
                tmp_port = status_path.with_suffix(".json.tmp")
                with open(tmp_port, "w", encoding="utf-8") as pf:
                    json.dump(wave_results[pid], pf, indent=2)
                tmp_port.replace(status_path)
                continue
            if checkpoint_ms <= ledger.last_checkpoint_ms and status_path.is_file():
                wave_results[pid] = self._refresh_portfolio_finance(
                    pid, json.loads(status_path.read_text())
                )
                continue
            wave = ledger.record(
                checkpoint_ms,
                cfg["members"],
                member_outcomes,
                recorded_ms=observed_ms,
            )
            restored = journal.restore(run_id)
            port_result = {
                "portfolio_id": pid,
                "run_id": run_id,
                "folder": cfg["folder"],
                "checkpoint_ms": checkpoint_ms,
                "checkpoint_utc": dt_str,
                "source_checkpoint_cursor_ms": wave["checkpoint_ms"],
                "source_receipt_sha": digest(wave),
                "starting_balance": str(cfg["starting_balance"]),
                "current_equity": str(restored["account"].get("equity")),
                "positions_count": len(restored["account"].get("quantities", {})),
                "cursor": restored["cursor"],
                "journal_head_sha": restored["journal_head_sha"],
                "members": list(cfg["members"]),
                "missing_sources": wave["missing_sources"],
                "coverage_complete": wave["coverage_complete"],
                "source_wave_state": ("COMPLETE" if wave["coverage_complete"] else "COVERAGE_GAP"),
                "source_kinds": {m: r["kind"] for m, r in wave["outcomes"].items()},
                "financial_admission": "SIGNED_MODELED_PAPER"
                if pid in self.approved
                else "BLOCKED_EVIDENCE",
                "admission_reason": (
                    "AWAITING_AUTHENTIC_PROSPECTIVE_PAPER_EVIDENCE"
                    if pid in self.approved
                    else "NO_APPROVED_CHECKPOINT_FINANCIAL_CONSUMER"
                ),
                "order_route": "NONE",
                "trading_authorized": False,
            }
            port_result = self._refresh_portfolio_finance(pid, port_result)
            wave_results[pid] = port_result

            port_status_path = self.state_root / cfg["folder"] / "status.json"
            tmp_port = self.state_root / cfg["folder"] / "status.json.tmp"
            with open(tmp_port, "w", encoding="utf-8") as pf:
                json.dump(port_result, pf, indent=2)
            tmp_port.replace(port_status_path)

        self.last_processed_checkpoint_ms = min(
            ledger.last_checkpoint_ms for ledger in self.wave_ledgers.values()
        )
        self._write_campaign_status(checkpoint_ms, dt_str, wave_results)
        return wave_results

    def _refresh_portfolio_finance(self, pid: str, status: dict) -> dict:
        """Financial facts only from verified PM03 journal replay, never source status."""
        cfg = PORTFOLIO_CONFIGS[pid]
        account = self.journals[pid].restore(cfg["folder"])
        snapshot = account["account"]
        status.update(
            current_equity=snapshot["equity"],
            cash=snapshot["cash"],
            realized_pnl=snapshot["realized_pnl"],
            costs=snapshot["costs"],
            positions_count=len(snapshot["quantities"]),
            cursor=account["cursor"],
            journal_head_sha=account["journal_head_sha"],
        )
        if pid in self.approved:
            status["financial_admission"] = (
                "PROSPECTIVE_MODELED_PAPER" if account["cursor"] else "AWAITING_FIRST_PAPER_EFFECT"
            )
            status["admission_reason"] = (
                self._finance_errors[pid]
                if pid in self._finance_errors
                else "SIGNED_RESEARCH_MANDATES_NO_BROKER_ROUTE"
            )
            status["last_financial_result"] = account["last_event_result"]
        else:
            status["financial_admission"] = "BLOCKED_EVIDENCE"
            status["admission_reason"] = "NO_APPROVED_CHECKPOINT_FINANCIAL_CONSUMER"
        return status

    def process_finance_once(self, *, now_ms: int) -> int:
        """Act on each owner's causal result only after genuine signed admission.

        Uses the upstream PM03 one-shot consumer, not new executable-finance
        logic. Unchanged checkpoints advance a durable nonfinancial cursor.
        A blocked changed opportunity is retried only within its immutable
        deadline; crash after a financial commit replays idempotently.
        """
        if not self.approved:
            return 0
        from .pm_checkpoint_journal import CheckpointOutcome
        from .pm_checkpoint_paper import TERMINAL

        with closing(sqlite3.connect(f"file:{self.source_db}?mode=ro", uri=True)) as db:
            streams = {
                json.loads(scope)["source_id"]: stream
                for stream, scope in db.execute("SELECT stream,scope FROM cwsa_heads")
            }
        attempts = 0
        self._finance_errors.clear()
        for pid, approved in self.approved.items():
            journal = self.journals[pid]
            scanner = self.finance_scans[pid]
            for mandate, _ in approved.mandates:
                stream = streams.get(mandate.source_id)
                if stream is None:
                    self._finance_errors[pid] = "CWSA_SIGNED_SOURCE_STREAM_MISSING"
                    continue
                cursor_ms = scanner.current(
                    mandate.owner, effective_from_ms=mandate.effective_from_ms
                )
                with closing(sqlite3.connect(f"file:{self.source_db}?mode=ro", uri=True)) as db:
                    rows = db.execute(
                        "SELECT checkpoint_ms,outcome FROM cwsa_outcomes "
                        "WHERE stream=? AND checkpoint_ms>? AND checkpoint_ms<=? "
                        "ORDER BY checkpoint_ms LIMIT 32",
                        (stream, cursor_ms, now_ms),
                    ).fetchall()
                for cp, raw in rows:
                    outcome = CheckpointOutcome.model_validate_json(raw)
                    if (
                        outcome.checkpoint_ms != cp
                        or outcome.source_id != mandate.source_id
                        or outcome.published_ms > now_ms
                    ):
                        break
                    phase = journal.copy_mandate_state(mandate.owner).phase
                    if outcome.kind == "UNCHANGED" and phase == "ACTIVE":
                        scanner.advance(mandate.owner, cp, outcome.outcome_id)
                        continue
                    attempt_key = (pid, mandate.owner, outcome.outcome_id)
                    if now_ms - self._finance_attempts.get(attempt_key, -(10**18)) < 5000:
                        break
                    self._finance_attempts[attempt_key] = now_ms
                    try:
                        result = consume_canonical_paper(
                            journal=journal,
                            run_id=PORTFOLIO_CONFIGS[pid]["folder"],
                            owner=mandate.owner,
                            outcome_id=outcome.outcome_id,
                            source_db=self.source_db,
                            quote_db=self.quote_db,
                            policy=approved.policy,
                            catalog=approved.catalog,
                            at_ms=now_ms,
                        )
                    except (ValueError, sqlite3.DatabaseError) as exc:
                        self._finance_errors[pid] = "PAPER_REVIEW_BLOCKED:" + type(exc).__name__
                        break
                    attempts += 1
                    if result["status"] not in TERMINAL:
                        break
                    scanner.advance(mandate.owner, cp, outcome.outcome_id)
            status_path = self.state_root / PORTFOLIO_CONFIGS[pid]["folder"] / "status.json"
            if status_path.is_file():
                status = json.loads(status_path.read_text())
                status = self._refresh_portfolio_finance(pid, status)
                temporary = status_path.with_suffix(".json.tmp")
                with open(temporary, "w", encoding="utf-8") as out:
                    json.dump(status, out, indent=2)
                temporary.replace(status_path)
        status_path = self.state_root / "cwsa_chapter2_status.json"
        if status_path.is_file():
            previous = json.loads(status_path.read_text())
            portfolio_results = {}
            for pid, cfg in PORTFOLIO_CONFIGS.items():
                individual = self.state_root / cfg["folder"] / "status.json"
                if individual.is_file():
                    portfolio_results[pid] = self._refresh_portfolio_finance(
                        pid, json.loads(individual.read_text())
                    )
            self._write_campaign_status(
                previous["last_checkpoint_ms"],
                previous["last_checkpoint_utc"],
                portfolio_results,
            )
        return attempts

    def _write_campaign_status(self, checkpoint_ms: int, dt_str: str, wave_results: dict) -> None:
        """Persist a consolidated status snapshot under the state root."""
        status_payload = {
            "epoch_id": self.run_label,
            "state_root": str(self.state_root),
            "source_db": str(self.source_db),
            "last_checkpoint_ms": checkpoint_ms,
            "last_checkpoint_utc": dt_str,
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "portfolios_count": len(wave_results),
            "wallets_count": len(ALL_14_WALLETS),
            "portfolios": wave_results,
            "order_route": "NONE",
            "scientifically_qualified": False,
            "trading_authorized": False,
        }
        status_path = self.state_root / "cwsa_chapter2_status.json"
        tmp_path = self.state_root / "cwsa_chapter2_status.json.tmp"
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(status_payload, f, indent=2)
        tmp_path.replace(status_path)

    def poll_once(self, *, now_ms: int | None = None) -> int:
        """Consume complete source waves, never skipping late wallet results.

        The canonical source publishes per wallet. Do not advance the durable
        observation cursor until every wallet has an outcome, or until the
        original source policy's publication deadline makes it nonactionable.
        """
        if not self.source_db.is_file():
            return 0
        now_ms = time.time_ns() // 1_000_000 if now_ms is None else now_ms
        with closing(sqlite3.connect(f"file:{self.source_db}?mode=ro", uri=True)) as con:
            con.row_factory = sqlite3.Row
            rows = con.execute(
                "SELECT checkpoint_ms,stream,candidate_sha,outcome FROM cwsa_outcomes "
                "WHERE checkpoint_ms > ? AND checkpoint_ms <= ? ORDER BY checkpoint_ms,stream",
                (self.last_processed_checkpoint_ms, now_ms),
            ).fetchall()
        if not rows:
            self.process_finance_once(now_ms=now_ms)
            return 0
        by_cp: dict[int, dict[str, dict]] = {}
        for r in rows:
            cp = r["checkpoint_ms"]
            outcome = parse_outcome(r["stream"], cp, r["outcome"], r["candidate_sha"])
            source_id = outcome["source_id"]
            if source_id not in ALL_14_WALLETS or source_id in by_cp.setdefault(cp, {}):
                raise ValueError("CHAPTER2_UNKNOWN_OR_DUPLICATE_SOURCE")
            by_cp[cp][source_id] = outcome

        processed = 0
        for cp, outcomes in sorted(by_cp.items()):
            before = tuple(ledger.last_checkpoint_ms for ledger in self.wave_ledgers.values())
            self.process_checkpoint(cp, outcomes, observed_ms=now_ms)
            after = tuple(ledger.last_checkpoint_ms for ledger in self.wave_ledgers.values())
            if before != after:
                processed += 1
            if self.last_processed_checkpoint_ms < cp:
                break
        self.process_finance_once(now_ms=now_ms)
        return processed


def run_supervisor(
    *,
    state_root: Path,
    source_db: Path,
    registry_db: Path,
    poll_seconds: float = 5.0,
    once: bool = False,
    run_label: str = EPOCH_ID,
    approved_paper_bundle: Path | None = None,
    approved_paper_sha256: str | None = None,
    trusted_paper_authority_public: str | None = None,
    quote_db: Path | None = None,
) -> None:
    supervisor = Chapter2PaperSupervisor(
        state_root=state_root,
        source_db=source_db,
        registry_db=registry_db,
        run_label=run_label,
        approval_path=approved_paper_bundle,
        approval_sha256=approved_paper_sha256,
        trusted_authority_hex=trusted_paper_authority_public,
        quote_db=quote_db,
    )
    print(f"[{datetime.now(timezone.utc).isoformat()}] Chapter 2 paper supervisor initialized.")
    print(f"  State root: {supervisor.state_root}")
    print(f"  Portfolios: {list(PORTFOLIO_CONFIGS.keys())}")
    print("  Initial catch-up check...")
    processed = supervisor.poll_once()
    print(
        f"  Processed {processed} historical checkpoint waves. Last ms: {supervisor.last_processed_checkpoint_ms}"
    )

    if once:
        return

    running = True

    def _sig_handler(signum, frame):
        nonlocal running
        print(f"\nCaught signal {signum}, shutting down cleanly...")
        running = False

    signal.signal(signal.SIGTERM, _sig_handler)
    signal.signal(signal.SIGINT, _sig_handler)

    while running:
        try:
            time.sleep(poll_seconds)
            new_waves = supervisor.poll_once()
            if new_waves > 0:
                print(
                    f"[{datetime.now(timezone.utc).isoformat()}] Processed {new_waves} new wave(s). Head at {supervisor.last_processed_checkpoint_ms}"
                )
        except Exception as exc:
            print(f"[ERROR] Supervisor loop error: {exc}", file=sys.stderr)
            time.sleep(poll_seconds)

    print(f"[{datetime.now(timezone.utc).isoformat()}] Supervisor exited cleanly.")


def main() -> None:
    parser = argparse.ArgumentParser(description="CWSA Chapter 2 Six-Portfolio Paper Supervisor")
    parser.add_argument(
        "--state-root",
        type=Path,
        default=Path(
            "/home/quant/.local/share/copytrade/prospective/cwsa-5m-paper-chapter2-20261112"
        ),
        help="Root directory for the six isolated paper journals",
    )
    parser.add_argument(
        "--source-db",
        type=Path,
        default=Path(
            "/home/quant/.local/share/copytrade/prospective/cwsa-5m-source-chapter2-20261112/paper-events.sqlite3"
        ),
        help="Path to the canonical CWSA source database",
    )
    parser.add_argument(
        "--registry-db",
        type=Path,
        default=Path("/home/quant/.local/share/copytrade/registry/wallet_registry.sqlite"),
        help="Path to the SQLite wallet registry",
    )
    parser.add_argument(
        "--poll-seconds",
        type=float,
        default=5.0,
        help="Seconds between source database polling checks",
    )
    parser.add_argument(
        "--run-label",
        default=EPOCH_ID,
        help="Immutable paper research epoch; a new signed finance release needs a fresh epoch",
    )
    parser.add_argument(
        "--approved-paper-bundle",
        type=Path,
        help="Original owner-approved signed Copy Mandates, sealed to this paper epoch",
    )
    parser.add_argument(
        "--approved-paper-sha256",
        help="Independent SHA-256 pin of the exact approval bundle",
    )
    parser.add_argument(
        "--trusted-paper-authority-public",
        help="Independently trusted Ed25519 signer public key (hex, never a private key)",
    )
    parser.add_argument(
        "--quote-db",
        type=Path,
        help="Original verified, independently known L2 quote journal",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Process current checkpoints once and exit",
    )
    args = parser.parse_args()

    run_supervisor(
        state_root=args.state_root,
        source_db=args.source_db,
        registry_db=args.registry_db,
        poll_seconds=args.poll_seconds,
        once=args.once,
        run_label=args.run_label,
        approved_paper_bundle=args.approved_paper_bundle,
        approved_paper_sha256=args.approved_paper_sha256,
        trusted_paper_authority_public=args.trusted_paper_authority_public,
        quote_db=args.quote_db,
    )


if __name__ == "__main__":
    main()
