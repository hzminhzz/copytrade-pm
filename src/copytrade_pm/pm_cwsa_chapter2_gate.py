"""CWSA Chapter 2 read-only acceptance: code, release, installed finance are distinct.

Never starts/restarts services, writes finance journals, signs mandates, or authorizes orders.
Machine-verifiable FAIL overrides BLOCKED_EVIDENCE, which overrides PASS.
"""

from __future__ import annotations

import argparse
from contextlib import closing
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from hashlib import sha256
import json
from pathlib import Path
import re
import shutil
import sqlite3
import subprocess
import time
from typing import Literal
from urllib.request import Request, urlopen
from urllib.error import HTTPError

from . import pm_runtime_readonly
from .pm03_account import digest
from .pm_forward_journal import PaperJournal
from .pm_cwsa_six_paper import ALL_14_WALLETS, PORTFOLIO_CONFIGS, load_registry_seals

Stage = Literal["premerge", "predeploy", "postdeploy"]
Verdict = Literal["PASS", "BLOCKED_EVIDENCE", "FAIL"]
EXPECTED_PORTFOLIOS = {
    name: tuple(sorted(value["members"])) for name, value in PORTFOLIO_CONFIGS.items()
}
EXPECTED_WALLETS = frozenset(ALL_14_WALLETS)
DEFAULT_REGISTRY = Path("/home/quant/.local/share/copytrade/registry/wallet_registry.sqlite")
DEFAULT_SOURCE = Path(
    "/home/quant/.local/share/copytrade/prospective/"
    "cwsa-5m-source-chapter2-20261112/paper-events.sqlite3"
)
DEFAULT_PAPER = Path(
    "/home/quant/.local/share/copytrade/prospective/cwsa-5m-paper-chapter2-20261112"
)
SOURCE_UNIT = "copytrade-cwsa-5m-source-chapter2.service"
PAPER_UNIT = "copytrade-cwsa-5m-paper-chapter2.service"
SHA_RE = re.compile(r"^[0-9a-f]{40}$")


@dataclass(frozen=True)
class GateCheck:
    name: str
    state: Verdict
    detail: str
    evidence: dict | None = None

    def __post_init__(self) -> None:
        if self.state not in ("PASS", "BLOCKED_EVIDENCE", "FAIL"):
            raise ValueError("CHAPTER2_INVALID_GATE_STATE")


def decide(stage: Stage, checks: list[GateCheck]) -> dict:
    """Typed non-green precedence; no empty set can pass."""
    if stage not in ("premerge", "predeploy", "postdeploy"):
        raise ValueError("CHAPTER2_UNKNOWN_STAGE")
    verdict: Verdict = (
        "FAIL"
        if any(c.state == "FAIL" for c in checks)
        else "BLOCKED_EVIDENCE"
        if not checks or any(c.state == "BLOCKED_EVIDENCE" for c in checks)
        else "PASS"
    )
    return {
        "schema": "cwsa_chapter2_gate_verdict_v1",
        "stage": stage,
        "verdict": verdict,
        "checked_at": datetime.now(UTC).isoformat(),
        "checks": [asdict(c) for c in checks],
        "order_route": "NONE",
        "trading_authorized": False,
        "scientifically_qualified": False,
    }


def assess_portfolio_roster(actual: dict[str, set[str]]) -> GateCheck:
    expected = {k: set(v) for k, v in EXPECTED_PORTFOLIOS.items()}
    if actual != expected or set().union(*actual.values()) != EXPECTED_WALLETS:
        return GateCheck(
            "six_sealed_portfolio_identities",
            "FAIL",
            "SEAL_MEMBERSHIP_OR_14_WALLET_UNION_DRIFT",
            {"expected_portfolios": sorted(expected), "expected_wallet_count": 14},
        )
    return GateCheck(
        "six_sealed_portfolio_identities",
        "PASS",
        "SQLITE_SEAL_AND_14_WALLET_UNION_MATCH",
        {"portfolios": sorted(actual), "wallet_count": 14},
    )


def assess_financial_runtime(
    *,
    service_active: bool | None,
    signed_portfolios: set[str],
    finance_scans: dict[str, dict],
    source_changes: dict[str, int],
    journal_cursors: dict[str, int],
    latest_source_checkpoint_ms: int,
    modeled_effects: dict[str, int] | None = None,
) -> GateCheck:
    """An OS process and six empty journals NEVER pass financial admission.

    A signed consumer without due changed-event processing is a broken worker.
    A quiet source with no eligible change is explicitly inconclusive, not PASS.
    """
    if service_active is False:
        return GateCheck("financial_consumer", "FAIL", "PAPER_SERVICE_NOT_RUNNING")
    if not signed_portfolios:
        return GateCheck("financial_consumer", "BLOCKED_EVIDENCE", "NO_SIGNED_FINANCIAL_MANDATES")
    if not signed_portfolios <= set(EXPECTED_PORTFOLIOS):
        return GateCheck("financial_consumer", "FAIL", "UNKNOWN_SIGNED_PORTFOLIO")
    if any(pid not in journal_cursors for pid in signed_portfolios):
        return GateCheck("financial_consumer", "FAIL", "MISSING_FINANCIAL_JOURNAL")
    if any(journal_cursors[pid] < 0 for pid in signed_portfolios):
        return GateCheck("financial_consumer", "FAIL", "INVALID_FINANCIAL_CURSOR")
    for pid in sorted(signed_portfolios):
        change = source_changes.get(pid)
        scanned = finance_scans.get(pid, {}).get("last_checkpoint_ms", 0)
        if change and change <= latest_source_checkpoint_ms - 300_000 and scanned < change:
            return GateCheck(
                "financial_consumer",
                "FAIL",
                "FINANCIAL_CONSUMER_DID_NOT_PROCESS_DUE_CHANGE",
                {"portfolio": pid, "source_change_ms": change, "financial_scan_ms": scanned},
            )
    if service_active is None:
        return GateCheck(
            "financial_consumer", "BLOCKED_EVIDENCE", "PAPER_PROCESS_LIVENESS_UNVERIFIED"
        )
    if not source_changes:
        return GateCheck("financial_consumer", "BLOCKED_EVIDENCE", "NO_ELIGIBLE_SOURCE_CHANGES")
    # A baseline writes PM03 events; that is not a modeled fill. Only
    # actual replayed effects (not observations/cursors) can prove activity.
    effects = modeled_effects or {}
    if not any(effects.get(pid, 0) > 0 for pid in signed_portfolios):
        return GateCheck(
            "financial_consumer", "BLOCKED_EVIDENCE", "NO_PROVEN_MODELED_FINANCIAL_EFFECT"
        )
    return GateCheck(
        "financial_consumer",
        "PASS",
        "SIGNED_CONSUMER_JOURNAL_PROGRESS_VERIFIED",
        {"signed_portfolios": sorted(signed_portfolios)},
    )


def _git(path: Path, expression: str) -> str:
    return subprocess.run(
        ["git", "-C", str(path), "rev-parse", "--verify", expression],
        check=True,
        capture_output=True,
        text=True,
        timeout=10,
    ).stdout.strip()


def _ro(db: Path) -> sqlite3.Connection:
    if db.is_symlink() or not db.is_file():
        raise ValueError("CHAPTER2_MISSING_OR_SYMLINKED_SQLITE")
    return sqlite3.connect(f"file:{db.resolve()}?mode=ro", uri=True, timeout=3)


def _source_facts(db_path: Path) -> dict:
    from .pm_checkpoint_journal import CheckpointOutcome, CwsaPolicy, history, stream_key
    from .pm_checkpoint_source import CheckpointScope

    with closing(_ro(db_path)) as db:
        if db.execute("PRAGMA quick_check").fetchone() != ("ok",):
            raise ValueError("CHAPTER2_SOURCE_SQLITE_CORRUPT")
        streams = db.execute("SELECT stream,scope,policy,head FROM cwsa_heads").fetchall()
        if not streams:
            raise ValueError("CHAPTER2_SOURCE_UNREGISTERED")
        scopes = {}
        graces = set()
        heads = []
        heads_by_wallet = {}
        policy_epochs_by_wallet = {}
        scope_generations_by_wallet = {}
        validated_outcomes = {}
        for stream, raw_scope, raw_policy, head in streams:
            scope = CheckpointScope.model_validate_json(raw_scope)
            policy = CwsaPolicy.model_validate_json(raw_policy)
            if scope.source_id in scopes:
                raise ValueError("CHAPTER2_DUPLICATE_SOURCE_SCOPE")
            if stream != stream_key(scope, policy.epoch):
                raise ValueError("CHAPTER2_SOURCE_STREAM_IDENTITY_DRIFT")
            for transition in history(db, scope, policy.epoch):
                if transition.effect is not None:
                    key = (stream, transition.effect.checkpoint_ms)
                    if key in validated_outcomes:
                        raise ValueError("CHAPTER2_DUPLICATE_NATIVE_SOURCE_EFFECT")
                    # The outcome table is a projection, not an authority. Bind
                    # its complete recorded payload to the journal transition,
                    # including original receipt clocks and position completeness.
                    validated_outcomes[key] = digest(transition.effect.model_dump(mode="json"))
            scopes[scope.source_id] = stream
            heads_by_wallet[scope.source_id] = head
            policy_epochs_by_wallet[scope.source_id] = policy.epoch
            scope_generations_by_wallet[scope.source_id] = scope.generation
            graces.add(policy.limits.publication_grace_ms)
            heads.append((stream, head))
        if set(scopes) != EXPECTED_WALLETS or len(graces) != 1:
            raise ValueError("CHAPTER2_SOURCE_SCOPE_OR_POLICY_MISMATCH")
        rows = db.execute(
            "SELECT stream,checkpoint_ms,outcome FROM cwsa_outcomes ORDER BY checkpoint_ms DESC"
        ).fetchall()
    if len(rows) != len(validated_outcomes):
        raise ValueError("CHAPTER2_SOURCE_EFFECT_ROWS_DRIFT")
    latest = max((cp for _, cp, _ in rows), default=0)
    changes: dict[str, int] = {}
    kinds: dict[str, str] = {}
    wallet_checkpoints: dict[str, int] = {}
    publication_ms_by_wallet: dict[str, int] = {}
    receipt_first_known_ms_by_wallet: dict[str, int | None] = {}
    complete_position_proof_by_wallet: dict[str, bool] = {}
    for stream, cp, raw in rows:
        outcome = CheckpointOutcome.model_validate_json(raw)
        if (
            outcome.checkpoint_ms != cp
            or outcome.source_id not in EXPECTED_WALLETS
            or scopes.get(outcome.source_id) != stream
            or validated_outcomes.get((stream, cp)) != digest(outcome.model_dump(mode="json"))
            or outcome.policy_epoch != policy_epochs_by_wallet.get(outcome.source_id)
            or outcome.scope_generation != scope_generations_by_wallet.get(outcome.source_id)
        ):
            raise ValueError("CHAPTER2_SOURCE_OUTCOME_DRIFT")
        kinds.setdefault(outcome.source_id, outcome.kind)
        if outcome.source_id not in wallet_checkpoints:
            wallet_checkpoints[outcome.source_id] = cp
            publication_ms_by_wallet[outcome.source_id] = outcome.published_ms
            receipt_first_known_ms_by_wallet[outcome.source_id] = (
                outcome.sample.received_ms if outcome.sample is not None else None
            )
            complete_position_proof_by_wallet[outcome.source_id] = (
                outcome.kind in ("BASELINE", "UNCHANGED", "CHANGED", "RECOVERY_BASELINE")
                and outcome.sample is not None
                and outcome.sample.kind == "COMPLETE"
            )
        if outcome.kind == "CHANGED":
            changes.setdefault(outcome.source_id, cp)
    return {
        "latest_checkpoint_ms": latest,
        "policy_grace_ms": next(iter(graces)),
        "source_count": len(scopes),
        "head_sha256": digest(["cwsa_source_head_set_v1", sorted(heads)]),
        "latest_kinds": kinds,
        "checkpoint_ms_by_wallet": wallet_checkpoints,
        "published_ms_by_wallet": publication_ms_by_wallet,
        "receipt_first_known_ms_by_wallet": receipt_first_known_ms_by_wallet,
        "complete_position_proof_by_wallet": complete_position_proof_by_wallet,
        "source_heads_by_wallet": heads_by_wallet,
        "policy_epochs_by_wallet": policy_epochs_by_wallet,
        "scope_generations_by_wallet": scope_generations_by_wallet,
        "changed_sources": changes,
    }


def _verified_finance_scan(db: sqlite3.Connection, pid: str) -> tuple[int, int]:
    if not db.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='chapter2_finance_scan'"
    ).fetchone():
        return 0, 0
    scans = db.execute(
        "SELECT owner,checkpoint_ms,outcome_id,receipt_sha FROM chapter2_finance_scan"
    ).fetchall()
    for owner, cp, outcome_id, receipt_sha in scans:
        if receipt_sha != digest(["chapter2_finance_scan_v1", owner, cp, outcome_id]):
            raise ValueError(f"CHAPTER2_FINANCE_SCAN_TAMPERED:{pid}")
    return len(scans), max((cp for _, cp, _, _ in scans), default=0)


def _paper_facts(root: Path, *, portfolios: tuple[str, ...] | None = None) -> dict:
    from .pm_cwsa_chapter2_waves import SCHEMA as _wave_schema

    # Schema name is referenced to guarantee the native owner is imported.
    assert "chapter2_wave_receipts" in _wave_schema
    results = {}
    selected = portfolios if portfolios is not None else tuple(PORTFOLIO_CONFIGS)
    if not selected or any(pid not in PORTFOLIO_CONFIGS for pid in selected):
        raise ValueError("UNKNOWN_CHAPTER2_PORTFOLIO")
    for pid in selected:
        cfg = PORTFOLIO_CONFIGS[pid]
        db_path = root / cfg["folder"] / "paper-events.sqlite3"
        with closing(_ro(db_path)) as db:
            if db.execute("PRAGMA quick_check").fetchone() != ("ok",):
                raise ValueError(f"CHAPTER2_FINANCIAL_JOURNAL_CORRUPT:{pid}")
            replay = PaperJournal._verify(db, cfg["folder"])
            prior = "0" * 64
            last = 0
            count = 0
            for cp, raw, receipt_sha in db.execute(
                "SELECT checkpoint_ms,payload,receipt_sha FROM chapter2_wave_receipts ORDER BY checkpoint_ms"
            ):
                body = json.loads(raw)
                if (
                    digest(body) != receipt_sha
                    or body.get("prior_sha") != prior
                    or body.get("checkpoint_ms") != cp
                    or cp <= last
                ):
                    raise ValueError(f"CHAPTER2_WAVE_CHAIN_TAMPERED:{pid}")
                last, prior, count = cp, receipt_sha, count + 1
            signed_count = db.execute("SELECT count(*) FROM copy_mandate_heads").fetchone()[0]
            scan_count, scan_ms = _verified_finance_scan(db, pid)
            results[pid] = {
                "cursor": replay["cursor"],
                "journal_head_sha": replay["journal_head_sha"],
                "wave_count": count,
                "wave_checkpoint_ms": last,
                "wave_head_sha": prior,
                "signed_mandates": signed_count,
                "finance_scan_count": scan_count,
                "finance_scan_checkpoint_ms": scan_ms,
                "current_equity": replay["account"]["equity"],
                "realized_pnl": replay["account"]["realized_pnl"],
                "costs": replay["account"]["costs"],
                "positions_count": len(replay["account"]["quantities"]),
                "modeled_effects": len(replay["account"].get("fills", [])),
            }
    return results


def _unit(name: str, expected_sha: str | None) -> GateCheck:
    """Translate T05 launch proof into the Chapter 2 gate's three valid states."""
    try:
        report = pm_runtime_readonly.verify_unit_release(
            name, expected_sha=expected_sha, manager="user"
        )
    except (OSError, ValueError, TypeError, subprocess.SubprocessError) as exc:
        return GateCheck(
            name, "BLOCKED_EVIDENCE", "SYSTEMD_RELEASE_PROOF_UNAVAILABLE:" + type(exc).__name__
        )
    verdict: Verdict = {
        "VERIFIED": "PASS",
        "NOT_RUNNING": "FAIL",
        "MISMATCH": "FAIL",
        "UNKNOWN": "BLOCKED_EVIDENCE",
    }.get(report.get("state"), "BLOCKED_EVIDENCE")
    return GateCheck(
        name,
        verdict,
        report.get("reason") or "PROCESS_RELEASE_PROOF_UNAVAILABLE",
        {"process_release_binding": report},
    )


def _paper_process_liveness(paper_unit: GateCheck) -> GateCheck:
    """Read OS liveness separately; a release-verification failure is not a stop."""
    try:
        observed = pm_runtime_readonly.observe_unit_liveness(PAPER_UNIT, manager="user")
    except OSError, ValueError, TypeError, subprocess.SubprocessError:
        observed = {"state": "UNKNOWN", "reason": "PROCESS_LIVENESS_UNAVAILABLE"}
    evidence = {"os_liveness": observed}
    state = observed.get("state")
    if state == "RUNNING":
        # Two independently timed inspections must identify the same birth
        # when claiming both a verified release and a running paper process.
        if paper_unit.state == "PASS":
            bound = (
                (paper_unit.evidence or {}).get("process_release_binding", {}).get("observed", {})
            )
            if (
                observed.get("pid") != bound.get("pid")
                or observed.get("process_start_ticks") != bound.get("process_start_ticks")
                or observed.get("pid") is None
                or observed.get("process_start_ticks") is None
            ):
                return GateCheck(
                    "paper_process_liveness",
                    "BLOCKED_EVIDENCE",
                    "PROCESS_RELEASE_AND_LIVENESS_SNAPSHOTS_DISAGREE",
                    evidence,
                )
        return GateCheck("paper_process_liveness", "PASS", observed["reason"], evidence)
    if state in ("NOT_RUNNING", "MISMATCH"):
        return GateCheck(
            "paper_process_liveness",
            "FAIL",
            observed.get("reason", "PROCESS_NOT_RUNNING"),
            evidence,
        )
    return GateCheck(
        "paper_process_liveness",
        "BLOCKED_EVIDENCE",
        observed.get("reason", "PROCESS_LIVENESS_UNAVAILABLE"),
        evidence,
    )


def _resources() -> GateCheck:
    disk = shutil.disk_usage("/home/quant")
    try:
        mem = Path("/proc/meminfo").read_text()
        available_kib = int(re.search(r"^MemAvailable:\s+(\d+) kB$", mem, re.M).group(1))
    except OSError, AttributeError, ValueError:
        return GateCheck("resources", "BLOCKED_EVIDENCE", "MEMORY_HEADROOM_UNVERIFIED")
    evidence = {"free_disk_bytes": disk.free, "mem_available_bytes": available_kib * 1024}
    if disk.free < 15 * 1024**3 or available_kib < 2 * 1024**2:
        return GateCheck("resources", "FAIL", "RESOURCE_HEADROOM_UNSAFE", evidence)
    return GateCheck("resources", "PASS", "DISK_AND_MEMORY_HEADROOM", evidence)


def _market_evidence(quote_db: Path | None, source_db: Path) -> GateCheck:
    """Read-only full native chain/L2 audit; a populated table alone is not proof."""
    if quote_db is None:
        return GateCheck(
            "independent_executable_quotes",
            "BLOCKED_EVIDENCE",
            "PINNED_INDEPENDENT_L2_QUOTE_JOURNAL_REQUIRED",
        )
    try:
        if quote_db.resolve() == source_db.resolve():
            return GateCheck("independent_executable_quotes", "FAIL", "L2_NOT_INDEPENDENT")
        with closing(_ro(quote_db)) as quotes:
            if quotes.execute("PRAGMA quick_check").fetchone() != ("ok",):
                raise ValueError("QUOTE_INTEGRITY")
            instruments = [
                row[0] for row in quotes.execute("SELECT instrument FROM market_quote_heads")
            ]
        if not instruments:
            return GateCheck(
                "independent_executable_quotes", "BLOCKED_EVIDENCE", "NO_L2_QUOTE_HEADS"
            )
        count = 0
        latest = 0
        heads = []
        for instrument in instruments:
            status = PaperJournal.market_quote_file_status(quote_db, instrument)
            if status["cursor"] < 1 or not status["last_quote_known_at"]:
                raise ValueError("EMPTY_OR_UNTIMED_L2_CHAIN")
            count += status["cursor"]
            heads.append((instrument, status["cursor"], status["journal_head_sha"]))
            known = int(datetime.fromisoformat(status["last_quote_known_at"]).timestamp() * 1000)
            latest = max(latest, known)
        evidence = {
            "instrument_count": len(instruments),
            "quote_count": count,
            "quote_heads_sha256": digest(["cwsa_quote_head_set_v1", sorted(heads)]),
            "original_latest_quote_known_ms": latest,
        }
        age = int(time.time() * 1000) - latest
        evidence["latest_age_ms"] = age
        if not 0 <= age <= 900_000:
            return GateCheck(
                "independent_executable_quotes",
                "BLOCKED_EVIDENCE",
                "NATIVE_L2_CHAINS_VERIFIED_BUT_STALE",
                evidence,
            )
        return GateCheck(
            "independent_executable_quotes",
            "PASS",
            "NATIVE_L2_PAYLOAD_CLOCK_AND_COMPLETE_CHAINS_VERIFIED",
            evidence,
        )
    except (ValueError, OSError, sqlite3.Error, KeyError, TypeError) as exc:
        return GateCheck(
            "independent_executable_quotes",
            "FAIL",
            "L2_NATIVE_VERIFICATION_FAILED:" + type(exc).__name__,
        )


def _dashboard(url: str | None, expected_sha: str | None, token_path: Path | None) -> GateCheck:
    if not url or not expected_sha:
        return GateCheck(
            "dashboard", "BLOCKED_EVIDENCE", "DEPLOYED_ENDPOINT_OR_REVISION_NOT_PINNED"
        )
    if not url.startswith("https://"):
        return GateCheck("dashboard", "FAIL", "DASHBOARD_REQUIRES_HTTPS")
    if token_path is None:
        return GateCheck(
            "dashboard", "BLOCKED_EVIDENCE", "INDEPENDENT_AUTHENTICATED_SMOKE_TOKEN_REQUIRED"
        )
    try:
        if token_path.is_symlink() or token_path.stat().st_mode & 0o077:
            return GateCheck("dashboard", "FAIL", "DASHBOARD_TOKEN_NOT_PRIVATE")
        headers = {"Accept": "application/json"}
        headers["Authorization"] = "Bearer " + token_path.read_text().strip()
        with urlopen(Request(url, headers=headers), timeout=8) as resp:
            if resp.status != 200:
                raise ValueError("DASHBOARD_HTTP_NOT_OK")
            raw = resp.read(2_000_001)
        if len(raw) > 2_000_000:
            raise ValueError("DASHBOARD_OVERSIZED")
        # A valid bearer response is insufficient: prove anonymous access is denied.
        try:
            with urlopen(Request(url, headers={"Accept": "application/json"}), timeout=8):
                return GateCheck("dashboard", "FAIL", "DASHBOARD_PUBLIC_UNAUTHENTICATED_ACCESS")
        except HTTPError as denied:
            denied.close()
            if denied.code not in (401, 403):
                return GateCheck(
                    "dashboard", "BLOCKED_EVIDENCE", "DASHBOARD_ANONYMOUS_AUTH_RESPONSE_UNEXPECTED"
                )
        data = json.loads(raw)
        if (
            data.get("schema") != "cwsa_chapter2_evidence_projection_v1"
            or data.get("release_sha") != expected_sha
            or set(data.get("portfolios", {})) != set(EXPECTED_PORTFOLIOS)
            or not data.get("source_heads_sha256")
            or data.get("trading_authorized") is not False
        ):
            return GateCheck("dashboard", "FAIL", "DEPLOYED_DASHBOARD_DATA_LINEAGE_MISMATCH")
        at = datetime.fromisoformat(data["generated_at"].replace("Z", "+00:00"))
        if abs((datetime.now(UTC) - at).total_seconds()) > 900:
            return GateCheck("dashboard", "FAIL", "DEPLOYED_DASHBOARD_DATA_STALE")
        return GateCheck(
            "dashboard",
            "PASS",
            "AUTHENTICATED_CURRENT_PROVENANCE_AND_REVISION",
            {"evidence_sha256": sha256(raw).hexdigest()},
        )
    except (OSError, ValueError, KeyError, TypeError, TimeoutError, json.JSONDecodeError) as exc:
        return GateCheck(
            "dashboard",
            "BLOCKED_EVIDENCE",
            "DASHBOARD_ENDPOINT_PROOF_MISSING:" + type(exc).__name__,
        )


def verify(args: argparse.Namespace) -> dict:
    checks: list[GateCheck] = []
    try:
        sha = _git(args.root, "HEAD")
        tree = _git(args.root, "HEAD^{tree}")
        if args.expected_sha and args.expected_sha != sha:
            checks.append(GateCheck("candidate", "FAIL", "CANDIDATE_SHA_DRIFT", {"actual": sha}))
        else:
            checks.append(
                GateCheck("candidate", "PASS", "EXACT_GIT_HEAD", {"sha": sha, "tree_sha": tree})
            )
    except OSError, subprocess.SubprocessError:
        checks.append(GateCheck("candidate", "FAIL", "GIT_PROVENANCE_UNAVAILABLE"))
        sha = ""
    if args.stage in ("premerge", "predeploy"):
        from .pm_ci_receipt import check_receipt

        checks.append(check_receipt(args.receipt, repo_root=args.root, expected_sha=sha))
    if args.stage == "premerge":
        if not args.root.joinpath("tests/test_cwsa_chapter2_ingestion.py").exists():
            checks.append(GateCheck("adversarial_contracts", "FAIL", "REQUIRED_TESTS_MISSING"))
    else:
        try:
            seals = load_registry_seals(args.registry_db)
            checks.append(
                assess_portfolio_roster({pid: set(s["members"]) for pid, s in seals.items()})
            )
        except (ValueError, OSError, sqlite3.Error) as exc:
            checks.append(GateCheck("six_sealed_portfolio_identities", "FAIL", type(exc).__name__))
        try:
            source = _source_facts(args.source_db)
            epochs = source.get("policy_epochs_by_wallet") or {}
            checkpoints = source.get("checkpoint_ms_by_wallet") or {}
            complete = source.get("complete_position_proof_by_wallet") or {}
            latest_cp = source["latest_checkpoint_ms"]
            grace = source["policy_grace_ms"]
            consistent = set(epochs) == EXPECTED_WALLETS and len(set(epochs.values())) == 1
            covered = all(
                complete.get(member) is True
                and isinstance(checkpoints.get(member), int)
                and latest_cp - grace <= checkpoints[member] <= latest_cp
                for member in EXPECTED_WALLETS
            )
            checks.append(
                GateCheck(
                    "canonical_source",
                    "PASS" if consistent and covered else "BLOCKED_EVIDENCE",
                    "NATIVE_14_SOURCE_POLICY_REGISTERED"
                    if consistent and covered
                    else "SOURCE_POLICY_GENERATIONS_OR_COMPLETE_POSITION_PROOF_UNVERIFIED",
                    {
                        "source_count": source["source_count"],
                        "grace_ms": grace,
                        "source_heads_sha256": source["head_sha256"],
                        "policy_epochs_by_wallet": epochs,
                        "unproved_wallets": sorted(
                            member
                            for member in EXPECTED_WALLETS
                            if complete.get(member) is not True
                            or not isinstance(checkpoints.get(member), int)
                            or checkpoints[member] < latest_cp - grace
                            or checkpoints[member] > latest_cp
                        ),
                    },
                )
            )
            age = int(time.time() * 1000) - source["latest_checkpoint_ms"]
            checks.append(
                GateCheck(
                    "source_freshness",
                    "PASS"
                    if source["latest_checkpoint_ms"] and 0 <= age <= 900_000
                    else "BLOCKED_EVIDENCE",
                    "SOURCE_CURRENT" if 0 <= age <= 900_000 else "SOURCE_LATEST_CHECKPOINT_STALE",
                    {"latest_checkpoint_ms": source["latest_checkpoint_ms"], "age_ms": age},
                )
            )
        except (OSError, ValueError, sqlite3.Error) as exc:
            source = None
            checks.append(
                GateCheck(
                    "canonical_source", "FAIL", "INVALID_SOURCE_JOURNAL:" + type(exc).__name__
                )
            )
        checks.append(_resources())
        if args.stage == "predeploy":
            if not args.rollback_sha or not args.rollback_path:
                checks.append(
                    GateCheck("rollback", "BLOCKED_EVIDENCE", "EXECUTABLE_ROLLBACK_PIN_REQUIRED")
                )
            else:
                try:
                    if (
                        not SHA_RE.fullmatch(args.rollback_sha)
                        or _git(args.rollback_path, "HEAD") != args.rollback_sha
                    ):
                        raise ValueError("ROLLBACK_COMMIT_DRIFT")
                    checks.append(
                        GateCheck(
                            "rollback",
                            "PASS",
                            "ROLLBACK_RELEASE_SHA_VERIFIED",
                            {"sha": args.rollback_sha, "path": str(args.rollback_path)},
                        )
                    )
                except (OSError, ValueError, subprocess.SubprocessError) as exc:
                    checks.append(
                        GateCheck(
                            "rollback",
                            "FAIL",
                            "ROLLBACK_NOT_EXECUTABLE_OR_PINNED:" + type(exc).__name__,
                        )
                    )
            from .pm_cwsa_paper_qualification import inspect_qualification

            checks.append(_market_evidence(args.quote_db, args.source_db))
            checks.append(
                inspect_qualification(
                    args.qualification,
                    args.research_public_key,
                    seals if "seals" in locals() else {},
                    args.source_db,
                )
            )
            if not (
                args.approved_paper_bundle
                and args.approved_paper_sha256
                and args.trusted_paper_public_key
            ):
                checks.append(
                    GateCheck(
                        "mandates",
                        "BLOCKED_EVIDENCE",
                        "SIGNED_PAPER_BUNDLE_AND_TRUST_ROOT_REQUIRED",
                    )
                )
            else:
                from .pm_cwsa_chapter2_release import read_activation_bundle

                try:
                    approved = read_activation_bundle(
                        path=args.approved_paper_bundle,
                        expected_sha256=args.approved_paper_sha256,
                        trusted_authority_hex=args.trusted_paper_public_key,
                        seals=seals,
                        configs=PORTFOLIO_CONFIGS,
                        run_label=args.epoch,
                        source_db=args.source_db,
                    )
                    if args.qualification and args.research_public_key:
                        from .pm_cwsa_paper_qualification import (
                            read_qualification,
                            mandate_k_blockers,
                        )

                        qualified_body = read_qualification(
                            args.qualification,
                            args.research_public_key,
                            seals,
                            args.source_db,
                        )
                        k_errors = mandate_k_blockers(approved, qualified_body)
                        if k_errors:
                            raise ValueError("CHAPTER2_SIGNED_K_MISMATCH:" + ",".join(k_errors))
                    checks.append(
                        GateCheck(
                            "mandates",
                            "PASS" if len(approved) == 6 else "BLOCKED_EVIDENCE",
                            "ALL_SIX_SIGNED" if len(approved) == 6 else "PARTIAL_FINANCIAL_RELEASE",
                            {"approved": sorted(approved)},
                        )
                    )
                except (ValueError, OSError, sqlite3.Error) as exc:
                    checks.append(
                        GateCheck(
                            "mandates", "FAIL", "INVALID_SIGNED_MANDATE:" + type(exc).__name__
                        )
                    )
            if args.paper_root.exists() and any(
                (args.paper_root / cfg["folder"] / "paper-events.sqlite3").exists()
                for cfg in PORTFOLIO_CONFIGS.values()
            ):
                checks.append(
                    GateCheck(
                        "new_epoch",
                        "BLOCKED_EVIDENCE",
                        "PAPER_EPOCH_ALREADY_EXISTS_NEW_EMPTY_ROOT_REQUIRED",
                    )
                )
            else:
                checks.append(GateCheck("new_epoch", "PASS", "NEW_EMPTY_FINANCIAL_EPOCH_ROOT"))
        else:
            paper_unit = _unit(PAPER_UNIT, args.expected_paper_sha)
            checks.append(_unit(SOURCE_UNIT, args.expected_source_sha))
            checks.append(paper_unit)
            paper_liveness = _paper_process_liveness(paper_unit)
            checks.append(paper_liveness)
            try:
                paper = _paper_facts(args.paper_root)
                checks.append(
                    GateCheck(
                        "six_paper_journals",
                        "PASS",
                        "ALL_PM03_REPLAYS_AND_WAVE_CHAINS",
                        {
                            "portfolios": {
                                pid: {
                                    k: v
                                    for k, v in info.items()
                                    if k not in ("current_equity", "realized_pnl", "costs")
                                }
                                for pid, info in paper.items()
                            }
                        },
                    )
                )
                source_changes = (
                    {
                        pid: max(
                            (
                                source["changed_sources"][member]
                                for member in cfg["members"]
                                if member in source["changed_sources"]
                            ),
                            default=0,
                        )
                        for pid, cfg in PORTFOLIO_CONFIGS.items()
                    }
                    if source
                    else {}
                )
                signed = set()
                if (
                    args.approved_paper_bundle
                    and args.approved_paper_sha256
                    and args.trusted_paper_public_key
                ):
                    from .pm_cwsa_chapter2_release import read_activation_bundle
                    from .pm_cwsa_paper_qualification import (
                        inspect_qualification,
                        read_qualification,
                        mandate_k_blockers,
                    )

                    qualified = inspect_qualification(
                        args.qualification,
                        args.research_public_key,
                        load_registry_seals(args.registry_db),
                        args.source_db,
                    )
                    checks.append(qualified)
                    if qualified.state == "PASS":
                        approved = read_activation_bundle(
                            path=args.approved_paper_bundle,
                            expected_sha256=args.approved_paper_sha256,
                            trusted_authority_hex=args.trusted_paper_public_key,
                            seals=load_registry_seals(args.registry_db),
                            configs=PORTFOLIO_CONFIGS,
                            run_label=args.epoch,
                            source_db=args.source_db,
                        )
                        qualified_body = read_qualification(
                            args.qualification,
                            args.research_public_key,
                            load_registry_seals(args.registry_db),
                            args.source_db,
                        )
                        k_errors = mandate_k_blockers(approved, qualified_body)
                        if k_errors:
                            raise ValueError("CHAPTER2_SIGNED_K_MISMATCH:" + ",".join(k_errors))
                        signed = {
                            pid
                            for pid, value in paper.items()
                            if pid in approved
                            and value["signed_mandates"] == len(EXPECTED_PORTFOLIOS[pid])
                        }
                else:
                    checks.append(
                        GateCheck(
                            "independent_financial_release",
                            "BLOCKED_EVIDENCE",
                            "TRUSTED_SIGNED_MANDATES_AND_K_QUALIFICATION_REQUIRED",
                        )
                    )
                checks.append(
                    assess_financial_runtime(
                        service_active=(
                            True
                            if paper_liveness.state == "PASS"
                            else False
                            if paper_liveness.state == "FAIL"
                            else None
                        ),
                        signed_portfolios=signed,
                        finance_scans={
                            pid: {"last_checkpoint_ms": x["finance_scan_checkpoint_ms"]}
                            for pid, x in paper.items()
                            if x["finance_scan_count"]
                        },
                        source_changes={
                            k: v for k, v in source_changes.items() if v and k in signed
                        },
                        journal_cursors={pid: x["cursor"] for pid, x in paper.items()},
                        latest_source_checkpoint_ms=source["latest_checkpoint_ms"] if source else 0,
                        modeled_effects={pid: x["modeled_effects"] for pid, x in paper.items()},
                    )
                )
            except (OSError, ValueError, sqlite3.Error, KeyError) as exc:
                checks.append(
                    GateCheck(
                        "six_paper_journals",
                        "FAIL",
                        "PM03_REPLAY_OR_WAVE_FAILED:" + type(exc).__name__,
                    )
                )
            checks.append(_market_evidence(getattr(args, "quote_db", None), args.source_db))
            checks.append(
                _dashboard(args.dashboard_url, args.dashboard_revision, args.dashboard_token_file)
            )
    result = decide(args.stage, checks)
    result["candidate_sha"] = sha
    result["financially_active"] = (
        args.stage == "postdeploy"
        and result["verdict"] == "PASS"
        and next((x.state for x in checks if x.name == "financial_consumer"), None) == "PASS"
    )
    return result


def add_arguments(p: argparse.ArgumentParser) -> None:
    p.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[2])
    p.add_argument("--expected-sha")
    p.add_argument("--receipt", type=Path)
    p.add_argument("--registry-db", type=Path, default=DEFAULT_REGISTRY)
    p.add_argument("--source-db", type=Path, default=DEFAULT_SOURCE)
    p.add_argument("--paper-root", type=Path, default=DEFAULT_PAPER)
    p.add_argument("--rollback-sha")
    p.add_argument("--rollback-path", type=Path)
    p.add_argument("--quote-db", type=Path)
    p.add_argument("--epoch", default="cwsa_chapter2_20261112")
    p.add_argument("--approved-paper-bundle", type=Path)
    p.add_argument("--approved-paper-sha256")
    p.add_argument("--trusted-paper-public-key")
    p.add_argument("--qualification", type=Path)
    p.add_argument("--research-public-key")
    p.add_argument("--expected-paper-sha")
    p.add_argument("--expected-source-sha")
    p.add_argument("--dashboard-url")
    p.add_argument("--dashboard-revision")
    p.add_argument("--dashboard-token-file", type=Path)


def cli(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="copytrade-pm cwsa chapter2 verify")
    p.add_argument("--stage", required=True, choices=("premerge", "predeploy", "postdeploy"))
    add_arguments(p)
    args = p.parse_args(argv)
    response = verify(args)
    print(json.dumps(response, sort_keys=True, indent=2))
    return {"PASS": 0, "FAIL": 1, "BLOCKED_EVIDENCE": 2}[response["verdict"]]


if __name__ == "__main__":
    raise SystemExit(cli())
