"""Cross-branch FP PaperPortfolioView -> WAL -> WR registry read-only smoke.

Invoke from the WR worktree with an existing isolated FP worktree:
  uv run --group dev python scripts/verify_wr_fp_journal_contract.py \
    --fp-worktree /path/to/FP-worktree --portfolio P1

All generated accounts and financial events are SYNTHETIC in TemporaryDirectory.
No broker, service, tracker, owner-private FP state or live registry mutation.
"""

from __future__ import annotations

import argparse
from contextlib import closing
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import tempfile

from copytrade_pm import wallet_registry as reg
from copytrade_pm import wallet_registry_fp_journal as fp
from copytrade_pm import wallet_registry_portfolios as selections
from copytrade_pm import wallet_registry_runs as runs

FP_CHILD = """
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
import json, sys
from copytrade_pm.pm_forward_journal import PaperJournal
from copytrade_pm.pm_forward_paper import PaperCampaign, PaperManifest
from copytrade_pm.pm_forward_portfolios import P1, P14, PaperPortfolioView
from copytrade_pm.pm_forward_status import paper_operator_status
from copytrade_pm.pm03_rules import propr_rulebook

root, expected_sha, portfolio_name = Path(sys.argv[1]), sys.argv[2], sys.argv[3]
frozen = {"P1": P1, "P14": P14}[portfolio_name]
assert frozen.sha == expected_sha
at = datetime.now(timezone.utc).isoformat()
manifest = PaperManifest(
    run_id="wr_fp_cross_contract",
    account_id="wr_fp_virtual_account",
    portfolio_sha=frozen.sha,
    market_manifest_sha="b"*64,
    release_sha="c"*64,
    policy_sha="d"*64,
    selected_at=at,
    started_at=at,
    rulebook=propr_rulebook(
        "classic_1step", "evaluation", Decimal("10000"), observed_at=at
    ),
)
journal = PaperJournal(root)
campaign = PaperCampaign(journal=journal)
view = PaperPortfolioView(campaign)
view.register(frozen, manifest)
before = paper_operator_status(
    root/"paper-events.sqlite3", run_id="wr_fp_cross_contract", as_of=at
)
assert before["health"] == "NOT_RUNNING"
assert before["real_worker_evidence"] is False
assert before["paper_admitted"] is False
campaign.record_event(
    "wr_fp_cross_contract",
    "halt-only",
    {"kind": "HALT", "event_at": at, "reason": "isolated_contract_smoke"},
)
restored = journal.restore("wr_fp_cross_contract")
assert restored["cursor"] == 1 and restored["account"]["risk"] == "HALT"
assert view.status(portfolio_name)["worker_status"] == "NOT_RUNNING"
after = paper_operator_status(
    root/"paper-events.sqlite3", run_id="wr_fp_cross_contract",
    as_of=datetime.now(timezone.utc).isoformat()
)
assert after["health"] == "HALT" and after["real_worker_evidence"] is False
assert after["paper_admitted"] is False
print(json.dumps({
    "run_id": "wr_fp_cross_contract", "cursor": 1,
    "operator_before": before["health"], "operator_after": after["health"],
    "real_worker_evidence": after["real_worker_evidence"],
}))
"""


def _git(path: Path, *args: str) -> str:
    return subprocess.check_output(["git", "-C", str(path), *args], text=True).strip()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fp-worktree", type=Path, required=True)
    parser.add_argument("--registry-db", type=Path, default=reg.DB)
    parser.add_argument("--portfolio", choices=("P1", "P14"), default="P1")
    parser.add_argument(
        "--audit-native-source",
        action="store_true",
        help="also compare FP source identity census to actual WR sealed registry (read only)",
    )
    parser.add_argument("--primary-dir", type=Path)
    parser.add_argument("--secondary-dir", type=Path)
    args = parser.parse_args()
    fp_root = args.fp_worktree.resolve()
    if not (fp_root / "src/copytrade_pm/pm_forward_portfolios.py").is_file():
        raise SystemExit("FP frozen portfolio and journal modules unavailable")
    fp_head = _git(fp_root, "rev-parse", "HEAD")
    fp_dirty = bool(_git(fp_root, "status", "--porcelain"))
    contract_files = (
        "src/copytrade_pm/pm_forward_journal.py",
        "src/copytrade_pm/pm_forward_paper.py",
        "src/copytrade_pm/pm_forward_portfolios.py",
        "src/copytrade_pm/pm_forward_status.py",
        "src/copytrade_pm/pm03_rules.py",
        "src/copytrade_pm/pm03_account.py",
    )
    if _git(fp_root, "diff", "--name-only", "HEAD", "--", *contract_files):
        raise SystemExit("Selected FP journal/status contract modules have uncommitted changes")
    with closing(reg.connect(args.registry_db, False)) as con:
        selected = selections.select_asof(con, args.portfolio, "9999-12-31T23:59:59+00:00")
    if not selected.get("definition_sha256"):
        raise SystemExit("WR portfolio selection is not SHA-sealed")
    fp_sha = fp.fp_portfolio_sha(selected)
    if fp_sha is None:
        raise SystemExit("FP aliases/risk do not match the WR sealed decision")
    native_identity = None
    if args.audit_native_source:
        if args.primary_dir is None or args.secondary_dir is None:
            raise SystemExit("source census requires both private locator directories")
        before_registry = sha256(args.registry_db.read_bytes()).hexdigest()
        process = subprocess.run(
            [
                "uv",
                "run",
                "--frozen",
                "--offline",
                "--directory",
                str(fp_root),
                "--group",
                "dev",
                "copytrade-pm-paper-registry-audit",
                "--registry",
                str(args.registry_db),
                "--primary-dir",
                str(args.primary_dir),
                "--secondary-dir",
                str(args.secondary_dir),
                "--portfolio",
                args.portfolio,
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        native_identity = json.loads(process.stdout)
        if (
            native_identity.get("portfolio_id") != args.portfolio
            or native_identity.get("registry_version") != selected["version"]
            or native_identity.get("registry_definition_sha256") != selected["definition_sha256"]
            or native_identity.get("source_document_sha256") != selected["source_doc_sha256"]
            or native_identity.get("selection_known_at") != selected["selection_known_at"]
            or sorted(item["alias"] for item in native_identity.get("members", []))
            != sorted(selected["members"])
            or native_identity.get("source_wallet_equity_attested") is not False
            or native_identity.get("registry_mutated") is not False
            or native_identity.get("paper_admitted") is not False
            or native_identity.get("order_route") != "NONE"
            or sha256(args.registry_db.read_bytes()).hexdigest() != before_registry
        ):
            raise SystemExit("FP/WR native identity or sealed selection drift")

    with tempfile.TemporaryDirectory(prefix="wr-fp-contract-") as directory:
        fp_run_dir = Path(directory) / "fp-owned-state"
        output = subprocess.run(
            [
                "uv",
                "run",
                "--frozen",
                "--offline",
                "--directory",
                str(fp_root),
                "--group",
                "dev",
                "python",
                "-c",
                FP_CHILD,
                str(fp_run_dir),
                fp_sha,
                args.portfolio,
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        child = json.loads(output.stdout.strip().splitlines()[-1])
        source_db = fp_run_dir / "paper-events.sqlite3"
        before = sha256(source_db.read_bytes()).hexdigest()
        observed = runs.inspect_run(fp_run_dir, selected, run_id=child["run_id"])
        after = sha256(source_db.read_bytes()).hexdigest()
        if (
            observed.get("state") != "NOT_RUNNING"
            or observed.get("journal_seq_reported") != 1
            or observed.get("portfolio_definition_sha256") != selected["definition_sha256"]
            or observed.get("fp_portfolio_sha256") != fp_sha
            or observed.get("order_route") != "NONE"
            or observed.get("scientifically_qualified") is not False
            or child.get("operator_before") != "NOT_RUNNING"
            or child.get("operator_after") != "HALT"
            or child.get("real_worker_evidence") is not False
            or before != after
        ):
            raise SystemExit("FP/WR dual-SHA contract smoke failed")
        print(
            json.dumps(
                {
                    "smoke": "PASS",
                    "fp_head": fp_head,
                    "fp_dirty_worktree": fp_dirty,
                    "fp_contract_modules_clean": True,
                    "portfolio": args.portfolio,
                    "fp_portfolio_sha256": fp_sha,
                    "registry_definition_sha256": selected["definition_sha256"],
                    "journal_cursor": observed["journal_seq_reported"],
                    "read_only_source_unchanged": True,
                    "registry_mutated": False,
                    "worker_state": observed["state"],
                    "native_source_identity_checked": native_identity is not None,
                    "native_source_aliases_reconciled": (
                        len(native_identity["members"]) if native_identity else None
                    ),
                    "native_source_aliases_unresolved": (
                        len(native_identity["unresolved_aliases"]) if native_identity else None
                    ),
                    "native_source_wallet_equity_attested": False,
                    "fp_operator_before": child["operator_before"],
                    "fp_operator_after": child["operator_after"],
                    "financial_replay_verified": False,
                    "source_identity_proven": False,
                    "scientifically_qualified": False,
                    "trading_authorized": False,
                },
                sort_keys=True,
            )
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
