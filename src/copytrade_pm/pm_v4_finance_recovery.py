"""Independent PM03/PM04 SHADOW ledger backup and replay for V4 #292.

Must run only after explicit quiescence of the relevant source/paper workers.
This never opens a broker route or modifies the original financial ledgers.
"""

from __future__ import annotations

from decimal import Decimal
from hashlib import sha256
import json
from pathlib import Path
import shutil

from .pm03_account import Rulebook, digest
from .pm03_risk import RiskPolicy
from .pm03_run import ShadowRun


def _source_finance_manifests(roots: tuple[Path, ...]) -> list[Path]:
    if not roots or len(roots) != len(set(roots)):
        raise ValueError("V4_FINANCE_ROOTS_INVALID")
    manifests: list[Path] = []
    for root in roots:
        if root.is_symlink() or not root.is_dir():
            raise ValueError("V4_FINANCE_ROOT_INVALID")
        if root.stat().st_mode & 0o077:
            raise ValueError("V4_FINANCE_ROOT_NOT_PRIVATE")
        for path in sorted(root.rglob("manifest.json")):
            if path.is_symlink() or not path.is_file():
                raise ValueError("V4_FINANCE_MANIFEST_INVALID")
            if any(p.is_symlink() for p in path.parents if p.is_relative_to(root)):
                raise ValueError("V4_FINANCE_NESTED_SYMLINK")
            manifests.append(path)
    if not manifests:
        raise ValueError("V4_FINANCE_MANIFESTS_MISSING")
    return manifests


def replay_financial_roots(roots: tuple[Path, ...]) -> dict:
    """Read all immutable financial event chains and independently replay PM03.

    ShadowRun(root, ...) writes no new events and requires byte-identical
    manifest; callers use either an existing quiescent original or copied tree.
    """
    results = []
    for manifest_path in _source_finance_manifests(roots):
        manifest_bytes = manifest_path.read_bytes()
        manifest = json.loads(manifest_bytes)
        policy = RiskPolicy(
            **{key: Decimal(value) for key, value in manifest["risk_policy"].items()}
        )
        if manifest_path.parent.name != manifest.get("run_id"):
            raise ValueError("V4_FINANCE_RUN_ID_MISMATCH")
        run = ShadowRun(
            manifest_path.parent.parent,
            run_id=manifest["run_id"],
            rulebook=Rulebook.from_dict(manifest["rulebook"]),
            started_at=manifest["started_at"],
            mode=manifest["mode"],
            pm01_sha=manifest["pm01_sha"],
            pm02_sha=manifest["pm02_sha"],
            market_manifest_sha=manifest["market_manifest_sha"],
            policy=policy,
        )
        events = run.ledger.read()
        results.append(
            {
                "run_id": manifest["run_id"],
                "manifest_sha256": sha256(manifest_bytes).hexdigest(),
                "event_count": len(events),
                "ledger_sha": events[-1]["sha"] if events else "0" * 64,
                "state_sha": digest(run.state()),
                "account_sha": digest(run.account.snapshot()),
                "pending_intent_count": sum(
                    row["status"] == "PENDING_5M"
                    for row in run.account.pm04_state.get("paper_execution", {})
                    .get("history", {})
                    .values()
                ),
                "held_instrument_count": sum(bool(q) for q in run.account.quantities.values()),
                "unresolved_exposures": len(
                    run.account.pm04_state.get("paper_execution", {}).get(
                        "unresolved_exposures", {}
                    )
                ),
                "financial_replay": "VERIFIED",
            }
        )
    return {
        "schema": "v4_financial_ledger_replay_292_v1",
        "run_count": len(results),
        "runs": sorted(results, key=lambda x: x["run_id"]),
        "all_source_finance_halted": False,
        "broker_route": "NONE",
        "financial_status": "RESEARCH_SHADOW_ONLY",
    }


def backup_financial_roots(
    roots: tuple[Path, ...], destination: Path, *, quiescence_verified: bool
) -> dict:
    if not quiescence_verified:
        raise ValueError("V4_FINANCE_BACKUP_REQUIRES_QUIESCENCE")
    if destination.exists() or destination.is_symlink():
        raise FileExistsError("V4_FINANCE_BACKUP_EXISTS")
    before = replay_financial_roots(roots)
    destination.mkdir(mode=0o700, parents=True)
    restored_roots = []
    for n, root in enumerate(roots):
        target = destination / f"run-root-{n:02d}"
        shutil.copytree(root, target, symlinks=False)
        restored_roots.append(target)
    after = replay_financial_roots(tuple(restored_roots))
    # Compare logical identities not root paths.
    if before["runs"] != after["runs"]:
        raise ValueError("V4_FINANCE_BACKUP_REPLAY_DIVERGENCE")
    return {
        "status": "FINANCIAL_BACKUP_INDEPENDENT_REPLAY_VERIFIED",
        "run_count": after["run_count"],
        "run_head_sha": digest(after["runs"]),
        "runs": after["runs"],
        "original_roots": [str(x) for x in roots],
        "backup_roots": [str(x) for x in restored_roots],
        "broker_route": "NONE",
        "trading_authorized": False,
    }
