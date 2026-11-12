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
    ) -> None:
        self.state_root = Path(state_root).resolve()
        self.source_db = Path(source_db).resolve()
        self.registry_db = Path(registry_db).resolve()
        self.run_label = run_label
        self.release_sha = release_sha or os.environ.get(
            "COPYTRADE_RELEASE_SHA", "cwsa_chapter2_20261112"
        )
        self.seals = load_registry_seals(self.registry_db)
        self.journals: dict[str, PaperJournal] = {}
        self.last_processed_checkpoint_ms: int = 0
        self._initialize_journals()

    def _initialize_journals(self) -> None:
        """Create and initialize six isolated, verified clean paper journals."""
        self.state_root.mkdir(parents=True, exist_ok=True, mode=0o700)
        for pid, cfg in PORTFOLIO_CONFIGS.items():
            folder = cfg["folder"]
            journal_dir = self.state_root / folder
            journal_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
            journal = PaperJournal(journal_dir)
            self.journals[pid] = journal

            run_id = cfg["folder"]
            # Check if run is already registered
            with closing(sqlite3.connect(f"file:{journal.path}?mode=ro", uri=True)) as db:
                row = db.execute("SELECT manifest FROM runs WHERE run_id=?", (run_id,)).fetchone()
            if row is None:
                # Register clean fresh starting state before the first checkpoint
                started_iso = "2026-11-12T05:00:00+00:00"
                rulebook = propr_rulebook(
                    "classic_1step",
                    "evaluation",
                    cfg["starting_balance"],
                    observed_at=self.seals[pid]["selection_known_at"],
                )
                account_id = f"acct_{cfg['folder'].lower()}_{self.run_label}"
                manifest = PaperManifest(
                    run_id=run_id,
                    account_id=account_id,
                    portfolio_sha=self.seals[pid]["definition_sha256"],
                    market_manifest_sha="0" * 64,
                    release_sha=digest(self.release_sha),
                    policy_sha="0" * 64,
                    selected_at=self.seals[pid]["selection_known_at"],
                    started_at=started_iso,
                    rulebook=rulebook,
                )
                journal.register(manifest)

            # Reverify restored state has 0 positions, 0 fills, 0 fees, fresh cash
            restored = journal.restore(run_id)
            acct = restored["account"]
            if acct.get("quantities") or acct.get("fills") or Decimal(acct.get("fees", "0")) != 0:
                raise ValueError(f"DIRTY_PAPER_ACCOUNT_DETECTED: {pid}")
            expected_cash = cfg["starting_balance"]
            if Decimal(str(acct.get("cash", "0"))) != expected_cash:
                raise ValueError(
                    f"STARTING_CASH_MISMATCH: {pid} expected {expected_cash} got {acct.get('cash')}"
                )

    def process_checkpoint(self, checkpoint_ms: int, outcomes_by_source: dict[str, dict]) -> dict:
        """Evaluate one 5-minute checkpoint wave across all six paper journals."""
        dt_str = datetime.fromtimestamp(checkpoint_ms / 1000, timezone.utc).isoformat()
        wave_results: dict[str, dict] = {}

        for pid, cfg in PORTFOLIO_CONFIGS.items():
            run_id = cfg["folder"]
            journal = self.journals[pid]
            members = cfg["members"]
            member_outcomes = {m: outcomes_by_source.get(m) for m in members}
            all_present = all(v is not None for v in member_outcomes.values())
            kinds = {m: v["kind"] for m, v in member_outcomes.items() if v is not None}

            # Check if signed copy mandates exist in this journal
            with closing(sqlite3.connect(f"file:{journal.path}?mode=ro", uri=True)) as db:
                mandates_count = db.execute("SELECT COUNT(*) FROM copy_mandate_heads").fetchone()[0]

            if mandates_count == 0:
                admission_status = "BLOCKED_EVIDENCE"
                admission_reason = "CHECKPOINT_SIGNED_MANDATES_OR_RUN_MISSING"
            else:
                admission_status = "ACTIVE"
                admission_reason = "MANDATES_ACTIVE"

            restored = journal.restore(run_id)
            port_result = {
                "portfolio_id": pid,
                "run_id": run_id,
                "folder": cfg["folder"],
                "checkpoint_ms": checkpoint_ms,
                "checkpoint_utc": dt_str,
                "starting_balance": str(cfg["starting_balance"]),
                "current_equity": str(restored["account"].get("cash")),
                "positions_count": len(restored["account"].get("quantities", {})),
                "cursor": restored["cursor"],
                "journal_head_sha": restored["journal_head_sha"],
                "members": list(members),
                "coverage_complete": all_present,
                "source_kinds": kinds,
                "financial_admission": admission_status,
                "admission_reason": admission_reason,
                "order_route": "NONE",
                "trading_authorized": False,
            }
            wave_results[pid] = port_result

            # Write portfolio local status
            port_status_path = self.state_root / cfg["folder"] / "status.json"
            tmp_port = self.state_root / cfg["folder"] / "status.json.tmp"
            with open(tmp_port, "w", encoding="utf-8") as pf:
                json.dump(port_result, pf, indent=2)
            tmp_port.replace(port_status_path)
            wave_results[pid] = {
                "portfolio_id": pid,
                "folder": cfg["folder"],
                "starting_balance": str(cfg["starting_balance"]),
                "current_equity": str(restored["account"].get("cash")),
                "positions_count": len(restored["account"].get("quantities", {})),
                "cursor": restored["cursor"],
                "journal_head_sha": restored["journal_head_sha"],
                "coverage_complete": all_present,
                "financial_admission": "BLOCKED_EVIDENCE",
                "admission_reason": "CHECKPOINT_SIGNED_MANDATES_OR_RUN_MISSING",
                "order_route": "NONE",
                "trading_authorized": False,
            }

        self.last_processed_checkpoint_ms = max(self.last_processed_checkpoint_ms, checkpoint_ms)
        self._write_campaign_status(checkpoint_ms, dt_str, wave_results)
        return wave_results

    def _write_campaign_status(self, checkpoint_ms: int, dt_str: str, wave_results: dict) -> None:
        """Persist a consolidated status snapshot under the state root."""
        status_payload = {
            "epoch_id": EPOCH_ID,
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

    def poll_once(self) -> int:
        """Poll the source database for newly recorded checkpoints."""
        if not self.source_db.is_file():
            return 0

        with closing(sqlite3.connect(f"file:{self.source_db}?mode=ro", uri=True)) as con:
            con.row_factory = sqlite3.Row
            cur = con.cursor()
            cur.execute(
                "SELECT checkpoint_ms, stream, outcome FROM cwsa_outcomes WHERE checkpoint_ms > ? ORDER BY checkpoint_ms ASC",
                (self.last_processed_checkpoint_ms,),
            )
            rows = cur.fetchall()

        if not rows:
            return 0

        by_cp: dict[int, dict[str, dict]] = {}
        for r in rows:
            cp = r["checkpoint_ms"]
            outcome = json.loads(r["outcome"])
            source_id = outcome.get("source_id")
            if source_id:
                by_cp.setdefault(cp, {})[source_id] = outcome

        for cp in sorted(by_cp.keys()):
            self.process_checkpoint(cp, by_cp[cp])

        return len(by_cp)


def run_supervisor(
    *,
    state_root: Path,
    source_db: Path,
    registry_db: Path,
    poll_seconds: float = 5.0,
    once: bool = False,
) -> None:
    supervisor = Chapter2PaperSupervisor(
        state_root=state_root,
        source_db=source_db,
        registry_db=registry_db,
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
    )


if __name__ == "__main__":
    main()
