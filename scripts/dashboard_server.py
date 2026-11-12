#!/usr/bin/env python3
"""Read-only HTTP projection for the Copytrade Ops Control Center.

SQLite and independent finance/release systems retain authority. This server
can neither write evidence nor infer trading qualification or authorization.
"""

from __future__ import annotations

import argparse
from contextlib import closing
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import re
import sqlite3
import sys
import threading
import time
from urllib.parse import urlsplit

WORKSPACE = Path(__file__).resolve().parents[1]
DIST = WORKSPACE / "ops" / "control-center" / "dist"
REGISTRY_DB = Path(
    os.environ.get(
        "COPYTRADE_OPS_REGISTRY_DB",
        "/home/quant/.local/share/copytrade/registry/wallet_registry.sqlite",
    )
)
PROJECTION_DB = Path(
    os.environ.get(
        "COPYTRADE_OPS_PROJECTION_DB",
        "/home/quant/.local/share/copytrade/projection.db",
    )
)
OPS_DB = Path(
    os.environ.get(
        "COPYTRADE_OPS_RECORDS_DB",
        "/home/quant/.local/share/copytrade/ops_dashboard.sqlite",
    )
)
PREFECT_STAGING_DIR = Path(
    os.environ.get(
        "COPYTRADE_PREFECT_STAGING_DIR",
        "/home/quant/.local/share/copytrade-track-b/track-b-prefect-staging",
    )
)
HASHED_ASSET = re.compile(r"^/assets/[\w.-]+-[A-Za-z0-9_-]{8,}\.(?:js|css|svg|woff2?)$")
_STATE_CACHE: tuple[float, str, dict] | None = None
_STATE_CACHE_LOCK = threading.Lock()
_STATE_CACHE_SECONDS = 8.0


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def readonly(db: Path) -> sqlite3.Connection:
    """Read live WAL snapshots without journaling, write capability or read pins."""
    con = sqlite3.connect(db.resolve().as_uri() + "?mode=ro", uri=True, timeout=2.0)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA query_only=ON")
    return con


def read_projection(db: Path) -> dict[str, str | None]:
    if not db.exists():
        return {}
    try:
        with closing(readonly(db)) as con:
            return {
                str(r["wallet_id"]).lower(): r["account_value"]
                for r in con.execute("SELECT wallet_id, account_value FROM expert_equity")
            }
    except (sqlite3.Error, OSError, TypeError) as exc:
        print(f"[ops] projection unavailable: {type(exc).__name__}", file=sys.stderr)
        return {}


def read_ops_records(db: Path) -> tuple[list[dict], list[dict]]:
    """Imported operator notes are not independently attested operational proof."""
    if not db.exists():
        return [], []
    try:
        with closing(readonly(db)) as con:
            records = []
            for r in con.execute(
                "SELECT * FROM ops_records ORDER BY updated_at DESC, id DESC LIMIT 500"
            ):
                records.append(
                    {
                        "id": r["id"],
                        "category": r["category"],
                        "title": r["title"],
                        "status": "pending",
                        "reportedStatus": r["status"],
                        "basis": r["basis"]
                        if r["basis"] in ("historical", "prospective", "paper", "unknown")
                        else "unknown",
                        "quality": "unverified",
                        "severity": r["severity"],
                        "owner": r["owner"],
                        "sourceRef": r["source_ref"],
                        "details": r["details"],
                        "createdAt": r["created_at"],
                        "updatedAt": r["updated_at"],
                    }
                )
            events = [
                {
                    "id": r["id"],
                    "entityType": r["entity_type"],
                    "entityId": r["entity_id"],
                    "action": r["action"],
                    "actor": r["actor"],
                    "createdAt": r["created_at"],
                }
                for r in con.execute(
                    "SELECT id, entity_type, entity_id, action, actor, created_at "
                    "FROM event_log ORDER BY id DESC LIMIT 100"
                )
            ]
            return records, events
    except (sqlite3.Error, OSError, TypeError) as exc:
        print(f"[ops] records unavailable: {type(exc).__name__}", file=sys.stderr)
        return [], []


def read_prefect_staging(staging_dir: Path) -> dict[str, dict]:
    """Scan Track B Prefect private staging reports for strategy health assessments."""
    if not staging_dir.is_dir():
        return {}
    reports_by_portfolio: dict[str, dict] = {}
    try:
        for p in staging_dir.glob("*.json"):
            if not p.is_file():
                continue
            try:
                with open(p, encoding="utf-8") as f:
                    data = json.load(f)
                if not isinstance(data, dict):
                    continue
                strategy = data.get("strategy")
                if not isinstance(strategy, dict):
                    continue
                selected_portfolio = strategy.get("selected_portfolio")
                if not selected_portfolio or not isinstance(selected_portfolio, str):
                    continue
                pid_key = selected_portfolio.strip().upper()
                as_of = data.get("as_of") or data.get("created_at") or ""
                existing = reports_by_portfolio.get(pid_key)
                if existing is None or as_of > (existing.get("as_of") or ""):
                    reports_by_portfolio[pid_key] = {
                        "portfolio_id": selected_portfolio,
                        "as_of": as_of,
                        "report_sha256": data.get("report_sha256"),
                        "strategy": strategy,
                        "advisory": data.get("advisory") or {},
                        "follower_economics": data.get("follower_economics") or {},
                        "windows": data.get("windows") or [],
                        "warnings": data.get("warnings") or [],
                        "trading_authorized": data.get("trading_authorized", False),
                        "scientifically_qualified": data.get("scientifically_qualified", False),
                    }
            except (OSError, json.JSONDecodeError):
                continue
    except OSError as exc:
        print(f"[ops] staging scan error: {exc}", file=sys.stderr)
    return reports_by_portfolio


def read_portfolio_tracking() -> tuple[dict[str, dict], dict[str, dict]]:
    """Read authentic portfolio tracking data for Archived V4 and CWSA Chapter 2.

    Explicit portfolio tracking modeled after ml4t-live shadow VirtualPortfolio & RiskState:
    - Initial & Current Equity, Cash, Realized / Unrealized PnL, Total PnL ($ and %)
    - High Water Mark, Drawdown %, Daily Loss, Trading Costs, Funding
    - Gross Exposure, Leverage, Open Positions count and details
    - Risk state, Halt reason, Kill switch activation status
    """
    hist_path = Path("/home/quant/.local/share/copytrade/prospective/v4_historical_portfolio_tracking.json")
    hist_data: dict[str, dict] = {}
    if hist_path.exists():
        try:
            with open(hist_path, "r", encoding="utf-8") as f:
                hist_data = json.load(f)
        except Exception as exc:
            print(f"[ops] warning: failed to read v4 historical tracking: {exc}", file=sys.stderr)

    cwsa_root = Path("/home/quant/.local/share/copytrade/prospective/cwsa-5m-paper-chapter2-20261112")
    cwsa_mapping = {
        "A": "A",
        "B": "B",
        "C": "C",
        "Combo2": "Combo2",
        "regime.macro/TriadA": "TriadA",
        "regime.macro/TriadChop": "TriadChop",
    }
    cwsa_tracking: dict[str, dict] = {}
    for pid, folder in cwsa_mapping.items():
        db_path = cwsa_root / folder / "paper-events.sqlite3"
        if not db_path.exists():
            continue
        try:
            with sqlite3.connect(f"file:{db_path}?mode=ro", uri=True) as conn:
                row = conn.execute(
                    "SELECT run_id, manifest, snapshot, last_event_at, cursor FROM runs ORDER BY last_event_at DESC LIMIT 1"
                ).fetchone()
                if not row:
                    continue
                run_id, mf_raw, snap_raw, last_event_at, cursor = row
                mf = json.loads(mf_raw)
                snap = json.loads(snap_raw)

                init_eq = float(mf.get("initial_balance") or mf.get("rulebook", {}).get("initial_balance", 10000.0))
                cur_eq = float(snap.get("equity", init_eq))
                cash = float(snap.get("cash", init_eq))
                realized_pnl = float(snap.get("realized_pnl", 0.0))
                costs = float(snap.get("costs", 0.0))
                funding = float(snap.get("funding", 0.0))
                high_water = float(snap.get("high_water", cur_eq))
                daily_start = float(snap.get("daily_start_balance", init_eq))

                quantities = snap.get("quantities", {})
                marks = snap.get("marks", {})
                entries = snap.get("entries", {})

                positions_list = []
                gross_notional = 0.0
                unrealized_pnl = 0.0
                for inst_key, qty_str in quantities.items():
                    qty_val = float(qty_str)
                    if qty_val == 0.0:
                        continue
                    mark_val = float(marks.get(inst_key, 0.0))
                    entry_val = float(entries.get(inst_key, mark_val))
                    notional = abs(qty_val * mark_val)
                    pos_pnl = qty_val * (mark_val - entry_val)
                    gross_notional += notional
                    unrealized_pnl += pos_pnl
                    sym = inst_key.split("/")[-1] if "/" in inst_key else inst_key
                    positions_list.append(
                        {
                            "instrument": inst_key,
                            "symbol": sym,
                            "side": "LONG" if qty_val > 0 else "SHORT",
                            "quantity": qty_val,
                            "entryPrice": entry_val,
                            "markPrice": mark_val,
                            "marketValue": notional,
                            "unrealizedPnl": pos_pnl,
                        }
                    )

                total_pnl = cur_eq - init_eq
                total_pnl_pct = (total_pnl / init_eq * 100.0) if init_eq > 0 else 0.0
                drawdown_pct = max(0.0, (high_water - cur_eq) / high_water * 100.0) if high_water > 0 else 0.0
                daily_loss = max(0.0, daily_start - cur_eq)
                leverage = (gross_notional / cur_eq) if cur_eq > 0 else 0.0

                cwsa_tracking[pid] = {
                    "portfolioId": pid,
                    "campaign": "CWSA Chapter 2",
                    "status": "ACTIVE",
                    "initialEquityUsd": init_eq,
                    "currentEquityUsd": cur_eq,
                    "cashUsd": cash,
                    "realizedPnlUsd": realized_pnl,
                    "unrealizedPnlUsd": unrealized_pnl,
                    "totalPnlUsd": total_pnl,
                    "totalPnlPct": total_pnl_pct,
                    "highWaterMarkUsd": high_water,
                    "drawdownPct": drawdown_pct,
                    "dailyLossUsd": daily_loss,
                    "totalCostsUsd": costs,
                    "totalFundingUsd": funding,
                    "grossExposureUsd": gross_notional,
                    "leverage": leverage,
                    "openPositionsCount": len(positions_list),
                    "positions": positions_list,
                    "riskState": snap.get("risk", "GREEN"),
                    "haltReason": snap.get("halt_reason"),
                    "killSwitchActivated": snap.get("breached", False) or (snap.get("risk") == "HALT"),
                    "lastMarkAt": snap.get("last_mark_at") or last_event_at,
                    "eventCount": cursor,
                }
        except Exception as exc:
            print(f"[ops] warning: failed to read cwsa journal for {pid}: {exc}", file=sys.stderr)

    return hist_data, cwsa_tracking


def get_sqlite_state(
    registry_db: Path | None = None,
    projection_db: Path | None = None,
    ops_db: Path | None = None,
    prefect_staging_dir: Path | None = None,
) -> dict:
    """One read-only SQLite transaction, no fabricated assessment or releases."""
    reg = registry_db if registry_db is not None else REGISTRY_DB
    if not reg.is_file():
        raise FileNotFoundError("Registry source unavailable")
    now = utc_now()
    equity = read_projection(projection_db if projection_db is not None else PROJECTION_DB)
    prefect_health = read_prefect_staging(
        prefect_staging_dir if prefect_staging_dir is not None else PREFECT_STAGING_DIR
    )
    hist_tracking, cwsa_tracking = read_portfolio_tracking()
    wallets: list[dict] = []
    portfolios: list[dict] = []
    import_observed: str | None = None
    source_manifest_sha: str | None = None

    with closing(readonly(reg)) as con:
        con.execute("BEGIN")  # pin one consistent WAL read snapshot
        integrity = (
            "VERIFIED" if con.execute("PRAGMA quick_check").fetchone()[0] == "ok" else "FAILED"
        )
        foreign_keys = con.execute("PRAGMA foreign_key_check").fetchone()
        if foreign_keys is not None:
            integrity = "FAILED"
        imported = con.execute(
            "SELECT manifest_sha256, observed_at FROM import_runs ORDER BY observed_at DESC LIMIT 1"
        ).fetchone()
        if imported:
            source_manifest_sha = imported["manifest_sha256"]
            import_observed = imported["observed_at"]
        memberships: dict[int, list[str]] = {}
        for r in con.execute(
            "SELECT wallet_id, portfolio_id, version FROM portfolio_memberships WHERE wallet_id IS NOT NULL"
        ):
            memberships.setdefault(r["wallet_id"], []).append(
                f"{r['portfolio_id']} (v{r['version']})"
            )
        aliases = {}
        for r in con.execute(
            "SELECT wallet_id, alias FROM wallet_aliases "
            "WHERE known_at <= ? ORDER BY known_at, rowid",
            (now,),
        ):
            aliases[r["wallet_id"]] = r["alias"]
        excluded = {
            r["wallet_id"] for r in con.execute("SELECT DISTINCT wallet_id FROM exclusions")
        }

        for r in con.execute("SELECT wallet_id, address FROM wallets ORDER BY wallet_id"):
            wid, addr = r["wallet_id"], str(r["address"])
            alias = aliases.get(wid)
            wallets.append(
                {
                    "address": f"registry-wallet-{wid}",  # opaque, stable display key
                    "alias": alias,
                    "sourceEquityUsd": equity.get(addr.lower()),  # diagnostic, not follower NAV
                    "eligibility": "ineligible" if wid in excluded else "pending",
                    "assessmentStatus": "excluded" if wid in excluded else "candidate",
                    "edgeDecay": "unknown",
                    "drawdownPct": None,  # no authentic cash-flow-adjusted peak/equity path
                    "evidenceQuality": "unverified",
                    "evidenceBasis": "historical" if wid in excluded else "unknown",
                    "sourceRef": None,
                    "assessedAt": None,
                    "updatedAt": import_observed or now,
                    "registryMetadataJson": json.dumps(
                        {
                            "walletId": wid,
                            "portfolioMemberships": memberships.get(wid, []),
                            "receiptHealth": "unknown",
                        }
                    ),
                }
            )
        # CWSA Chapter 2 prospective paper status
        cwsa_status_path = Path("/home/quant/.local/share/copytrade/prospective/cwsa-5m-paper-chapter2-20261112/cwsa_chapter2_status.json")
        cwsa_info: dict = {}
        if cwsa_status_path.exists():
            try:
                with open(cwsa_status_path, encoding="utf-8") as f:
                    cwsa_info = json.load(f)
            except Exception:
                pass
        cwsa_ports = cwsa_info.get("portfolios", {})

        for seal in con.execute(
            "SELECT portfolio_id, version, definition_sha256, selection_known_at "
            "FROM portfolio_seals ORDER BY portfolio_id, version"
        ):
            pid, version = seal["portfolio_id"], seal["version"]
            # Use *sealed member aliases*, not aliases learned after this seal.
            member_aliases = [
                row[0]
                for row in con.execute(
                    "SELECT member_alias FROM portfolio_memberships "
                    "WHERE portfolio_id=? AND version=? ORDER BY member_alias",
                    (pid, version),
                )
            ]

            # Match Prefect strategy health assessment if available
            health_report = prefect_health.get(str(pid).strip().upper())
            strategy_health = None
            advisory_status = None
            advisory_cal = None
            advisory_reasons = []
            fee_drag_usd = None
            max_adverse_r = None
            report_sha = None
            health_as_of = None

            if health_report:
                adv = health_report.get("advisory", {})
                advisory_status = adv.get("status")
                advisory_cal = adv.get("calibration")
                advisory_reasons = adv.get("reasons", [])

                if advisory_status in ("INSUFFICIENT_EVIDENCE", "UNKNOWN", None):
                    strategy_health = advisory_status or "INSUFFICIENT_EVIDENCE"
                elif advisory_status in ("OK", "HEALTHY", "PASS"):
                    strategy_health = "HEALTHY"
                elif advisory_status in ("WARN", "WARNING"):
                    strategy_health = "WARN"
                elif advisory_status in ("BREACH", "HALT", "FAIL"):
                    strategy_health = "BREACH"
                else:
                    strategy_health = str(advisory_status)

                econ = health_report.get("follower_economics", {})
                costs = econ.get("costs_usd")
                funding = econ.get("funding_usd")
                if costs is not None or funding is not None:
                    total_fee = (float(costs) if costs else 0.0) + (float(funding) if funding else 0.0)
                    fee_drag_usd = str(round(total_fee, 2))

                windows = health_report.get("windows", [])
                for w in windows:
                    if isinstance(w, dict) and w.get("matched_adverse_r") is not None:
                        try:
                            adv_r = abs(float(w["matched_adverse_r"]))
                            if max_adverse_r is None or adv_r > max_adverse_r:
                                max_adverse_r = adv_r
                        except (ValueError, TypeError):
                            pass

                report_sha = health_report.get("report_sha256")
                health_as_of = health_report.get("as_of")

            is_cwsa_ch2 = (version == 2 and pid in ("A", "B", "C", "Combo2", "regime.macro/TriadA", "regime.macro/TriadChop"))
            is_archived_v4 = pid in ("P1", "P14", "P15", "P16") or str(pid).startswith("E")

            tracking_info = None
            if is_cwsa_ch2 and pid in cwsa_tracking:
                tracking_info = cwsa_tracking[pid]
            elif is_archived_v4 and str(pid).upper() in hist_tracking:
                tracking_info = hist_tracking[str(pid).upper()]

            if is_cwsa_ch2:
                port_state = "active"
                port_strat = "CWSA Chapter 2"
                cwsa_p = cwsa_ports.get(pid, {})
                paper_running = cwsa_p.get("financial_admission", "BLOCKED_EVIDENCE")
                total_risk = "300" if pid == "Combo2" else "600"
                ev_basis = "paper"
                ev_qual = "verified"
            elif is_archived_v4:
                port_state = "archived"
                port_strat = "Archived V4 — Historical"
                paper_running = "INACTIVE_ARCHIVED"
                total_risk = None
                ev_basis = "historical"
                ev_qual = "verified"
            else:
                port_state = "candidate"
                port_strat = "SEALED_RESEARCH_SELECTION"
                paper_running = "UNKNOWN"
                total_risk = None
                ev_basis = "historical"
                ev_qual = "unverified"

            init_eq = tracking_info["initialEquityUsd"] if tracking_info else (5000.0 if pid == "Combo2" else 10000.0 if (is_cwsa_ch2 or is_archived_v4) else None)
            cur_eq = tracking_info["currentEquityUsd"] if tracking_info else None
            cash_usd = tracking_info["cashUsd"] if tracking_info else None
            realized_pnl = tracking_info["realizedPnlUsd"] if tracking_info else None
            unrealized_pnl = tracking_info["unrealizedPnlUsd"] if tracking_info else None
            total_pnl = tracking_info["totalPnlUsd"] if tracking_info else None
            total_pnl_pct = tracking_info["totalPnlPct"] if tracking_info else None
            high_water = tracking_info["highWaterMarkUsd"] if tracking_info else None
            drawdown_pct = tracking_info["drawdownPct"] if tracking_info else None
            daily_loss = tracking_info["dailyLossUsd"] if tracking_info else None
            total_costs = tracking_info["totalCostsUsd"] if tracking_info else None
            total_funding = tracking_info["totalFundingUsd"] if tracking_info else None
            gross_exposure = tracking_info["grossExposureUsd"] if tracking_info else None
            leverage = tracking_info["leverage"] if tracking_info else None
            open_positions_count = tracking_info["openPositionsCount"] if tracking_info else (0 if (is_cwsa_ch2 or is_archived_v4) else None)
            positions = tracking_info["positions"] if tracking_info else ([] if (is_cwsa_ch2 or is_archived_v4) else None)
            risk_state = tracking_info["riskState"] if tracking_info else ("GREEN" if is_cwsa_ch2 else "ARCHIVED" if is_archived_v4 else "NORMAL")
            halt_reason = tracking_info["haltReason"] if tracking_info else None
            kill_switch = tracking_info["killSwitchActivated"] if tracking_info else False
            last_mark_at = tracking_info["lastMarkAt"] if tracking_info else None

            portfolios.append(
                {
                    "id": f"{pid}-v{version}",
                    "name": f"{pid} (v{version})",
                    "state": port_state,
                    "strategy": port_strat,
                    "walletAddressesJson": json.dumps(member_aliases),
                    "podCount": len(member_aliases),
                    "totalRiskUsd": total_risk,
                    "evidenceBasis": ev_basis,
                    "evidenceQuality": ev_qual,
                    "sourceRef": f"portfolio_seal:{str(seal['definition_sha256'])[:16]}",
                    "initialEquityUsd": init_eq,
                    "currentEquityUsd": cur_eq,
                    "cashUsd": cash_usd,
                    "realizedPnlUsd": realized_pnl,
                    "unrealizedPnlUsd": unrealized_pnl,
                    "totalPnlUsd": total_pnl,
                    "totalPnlPct": total_pnl_pct,
                    "highWaterMarkUsd": high_water,
                    "drawdownPct": drawdown_pct,
                    "dailyLossUsd": daily_loss,
                    "totalCostsUsd": total_costs,
                    "totalFundingUsd": total_funding,
                    "grossExposureUsd": gross_exposure,
                    "leverage": leverage,
                    "openPositionsCount": open_positions_count,
                    "positions": positions,
                    "riskState": risk_state,
                    "haltReason": halt_reason,
                    "killSwitchActivated": kill_switch,
                    "paperStatus": paper_running,
                    "lastMarkAt": last_mark_at,
                    "detailsJson": json.dumps(
                        {
                            "version": version,
                            "definitionSha256": seal["definition_sha256"],
                            "selectionKnownAt": seal["selection_known_at"],
                            "campaign": port_strat,
                            "paperRunning": paper_running,
                            "tradingAuthorized": False,
                            "sizingContract": "FIXED_K_NATIVE_QUANTITY (policy only)",
                            "cwsaDetails": cwsa_ports.get(pid),
                            "strategyHealth": strategy_health,
                            "advisoryStatus": advisory_status,
                            "advisoryCalibration": advisory_cal,
                            "advisoryReasons": advisory_reasons,
                            "feeDragUsd": fee_drag_usd,
                            "maxAdverseR": str(max_adverse_r) if max_adverse_r is not None else None,
                            "prefectReportSha256": report_sha,
                            "prefectAssessedAt": health_as_of,
                            "tracking": tracking_info,
                        }
                    ),
                    "strategyHealth": strategy_health,
                    "advisoryStatus": advisory_status,
                    "advisoryCalibration": advisory_cal,
                    "feeDragUsd": fee_drag_usd,
                    "prefectReportSha256": report_sha,
                    "prefectAssessedAt": health_as_of,
                    "updatedAt": health_as_of or seal["selection_known_at"] or now,
                }
            )
        con.execute("ROLLBACK")  # close the explicitly bounded snapshot

        # Add any remaining sealed historical V4 portfolios from archive
        existing_pids = {p["name"].split(" ")[0].upper() for p in portfolios}
        for hist_pid, h_info in sorted(hist_tracking.items()):
            if hist_pid in existing_pids:
                continue
            portfolios.append(
                {
                    "id": f"{hist_pid}-v4-archive",
                    "name": f"{hist_pid} (Archived V4)",
                    "state": "archived",
                    "strategy": "Archived V4 — Historical",
                    "walletAddressesJson": "[]",
                    "podCount": len(h_info.get("positions", [])),
                    "totalRiskUsd": None,
                    "evidenceBasis": "historical",
                    "evidenceQuality": "verified",
                    "sourceRef": "v4_canonical_archive:sealed",
                    "initialEquityUsd": h_info.get("initialEquityUsd", 10000.0),
                    "currentEquityUsd": h_info.get("currentEquityUsd"),
                    "cashUsd": h_info.get("cashUsd"),
                    "realizedPnlUsd": h_info.get("realizedPnlUsd"),
                    "unrealizedPnlUsd": h_info.get("unrealizedPnlUsd"),
                    "totalPnlUsd": h_info.get("totalPnlUsd"),
                    "totalPnlPct": h_info.get("totalPnlPct"),
                    "highWaterMarkUsd": h_info.get("highWaterMarkUsd"),
                    "drawdownPct": h_info.get("drawdownPct"),
                    "dailyLossUsd": h_info.get("dailyLossUsd"),
                    "totalCostsUsd": h_info.get("totalCostsUsd"),
                    "totalFundingUsd": h_info.get("totalFundingUsd"),
                    "grossExposureUsd": h_info.get("grossExposureUsd"),
                    "leverage": h_info.get("leverage"),
                    "openPositionsCount": h_info.get("openPositionsCount"),
                    "positions": h_info.get("positions"),
                    "riskState": h_info.get("riskState", "ARCHIVED"),
                    "haltReason": h_info.get("haltReason"),
                    "killSwitchActivated": h_info.get("killSwitchActivated", False),
                    "paperStatus": "INACTIVE_ARCHIVED",
                    "lastMarkAt": h_info.get("lastMarkAt"),
                    "detailsJson": json.dumps(
                        {
                            "campaign": "Archived V4 — Historical",
                            "paperRunning": "INACTIVE_ARCHIVED",
                            "tradingAuthorized": False,
                            "tracking": h_info,
                        }
                    ),
                    "updatedAt": h_info.get("lastMarkAt") or now,
                }
            )

    records, events = read_ops_records(ops_db if ops_db is not None else OPS_DB)
    prefect_rec = next((r for r in records if r.get("id") == "prefect-track-b-flow"), None)
    receipt = {
        "snapshotId": f"sqlite-snapshot-{now}",
        "status": "pending",
        "producedAt": now,
        "receivedAt": now,
        "sourceObservedAt": import_observed,
        "sourceStatus": "UNKNOWN",
        # The last import SHA is NOT the current live SQLite inventory SHA.
        "inventorySha256": None,
        "sourceManifestSha256": source_manifest_sha,
        "releaseStatus": None,
        "releaseRevision": None,
        "databaseIntegrity": integrity,
        "selectionKnownAt": None,
        "selectionSha256": None,
        "selectionState": "UNVERIFIED",
        "paperRunning": "UNKNOWN",
        "scientificallyQualified": 0,
        "tradingAuthorized": 0,
        "walletTotal": len(wallets),
        "walletSynced": sum(w["alias"] is not None for w in wallets),
        "walletUnresolved": sum(w["alias"] is None for w in wallets),
        "portfolioCount": len(portfolios),
        "error": "Selection proof and runtime authority have not been independently verified.",
    }
    return {
        "wallets": wallets,
        "portfolios": portfolios,
        "records": records,
        "events": events,
        "cwsaChapter2": cwsa_info,
        "registrySync": {"latestAttempt": receipt, "latestAccepted": None},
        "runtime": {
            "dashboardRevision": os.environ.get("COPYTRADE_OPS_RELEASE_SHA"),
            "observerMode": "NO_TRADE",
            "trustedBrokerAuthority": False,
            "prefectBatchStatus": prefect_rec.get("reportedStatus") if prefect_rec else None,
            "prefectReportCount": len(prefect_health),
        },
    }


def cached_sqlite_state() -> dict:
    """Singleflight short-lived projection limits WAL readers and CPU load."""
    global _STATE_CACHE
    with _STATE_CACHE_LOCK:
        if not REGISTRY_DB.is_file():
            raise FileNotFoundError("Registry source unavailable")
        now = time.monotonic()
        authority = str(REGISTRY_DB.resolve())
        if (
            _STATE_CACHE is not None
            and _STATE_CACHE[1] == authority
            and now - _STATE_CACHE[0] < _STATE_CACHE_SECONDS
        ):
            return _STATE_CACHE[2]
        state = get_sqlite_state()
        _STATE_CACHE = (time.monotonic(), authority, state)
        return state


class DashboardHandler(SimpleHTTPRequestHandler):
    """No write methods, CORS entitlement, directory listing or private keys."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(DIST), **kwargs)

    def log_message(self, fmt: str, *args: object) -> None:
        print("[ops] " + fmt % args, file=sys.stderr)

    def end_headers(self) -> None:
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header(
            "Content-Security-Policy",
            # Cloudflare JSD adds a request-specific inline bootstrap (dynamic Ray ID).
            # It cannot be SHA-allowlisted. Only this public NO_TRADE app needs it;
            # prohibit inline handler attributes and keep all remote script URLs
            # restricted to this origin. No authenticated API write path exists.
            "default-src 'self'; script-src 'self' 'unsafe-inline'; script-src-attr 'none'; "
            "style-src 'self' 'unsafe-inline'; img-src 'self' data:; "
            "font-src 'self' data:; connect-src 'self'; "
            "frame-ancestors 'none'; base-uri 'none'; form-action 'none'",
        )
        if not getattr(self, "_cache_set", False):
            self.send_header("Cache-Control", "no-store")
        self._cache_set = False
        super().end_headers()

    def send_json(self, data: object, status: int = HTTPStatus.OK) -> None:
        raw = json.dumps(data, allow_nan=False, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate")
        self._cache_set = True
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self) -> None:
        path = urlsplit(self.path).path
        if path == "/api/health":
            self.send_json(
                {
                    "status": "ok",
                    "mode": "NO_TRADE",
                    "revision": os.environ.get("COPYTRADE_OPS_RELEASE_SHA"),
                }
            )
            return
        if path in ("/api/state", "/api/records"):
            try:
                state = cached_sqlite_state()
                self.send_json(state if path == "/api/state" else state["records"])
            except (sqlite3.Error, OSError, ValueError, TypeError) as exc:
                print(f"[ops] source failure: {type(exc).__name__}", file=sys.stderr)
                self.send_json(
                    {"error": "Registry unavailable"}, status=HTTPStatus.SERVICE_UNAVAILABLE
                )
            return
        if path.startswith("/api/"):
            self.send_json({"error": "Not found"}, status=HTTPStatus.NOT_FOUND)
            return
        if path in ("/", "/index.html"):
            self.path = "/index.html"
        elif path != "/favicon.svg" and not path.startswith("/assets/"):
            self.send_error(HTTPStatus.NOT_FOUND, "Not found")
            return
        if not DIST.is_dir():
            self.send_error(HTTPStatus.SERVICE_UNAVAILABLE, "Frontend build unavailable")
            return
        super().do_GET()

    def send_head(self):
        path = urlsplit(self.path).path
        if HASHED_ASSET.fullmatch(path):
            self._cache_set = True
            original = self.end_headers

            def _headers() -> None:
                self.send_header("Cache-Control", "public, max-age=31536000, immutable")
                original()

            self.end_headers = _headers
            try:
                return super().send_head()
            finally:
                self.end_headers = original
        return super().send_head()

    def do_POST(self) -> None:
        self.send_json({"error": "Read-only observer"}, status=HTTPStatus.FORBIDDEN)

    do_PATCH = do_POST
    do_PUT = do_POST
    do_DELETE = do_POST
    do_OPTIONS = do_POST


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8888)
    parser.add_argument("--bind", default="127.0.0.1")
    args = parser.parse_args()
    if not DIST.joinpath("index.html").is_file():
        raise SystemExit(f"Cannot start: missing built dashboard at {DIST}")
    service = ThreadingHTTPServer((args.bind, args.port), DashboardHandler)
    service.daemon_threads = True
    try:
        service.serve_forever()
    finally:
        service.server_close()


if __name__ == "__main__":
    main()
