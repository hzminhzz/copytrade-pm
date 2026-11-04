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
campaign.record_event(
    "wr_fp_cross_contract",
    "halt-only",
    {"kind": "HALT", "event_at": at, "reason": "isolated_contract_smoke"},
)
restored = journal.restore("wr_fp_cross_contract")
assert restored["cursor"] == 1 and restored["account"]["risk"] == "HALT"
assert view.status(portfolio_name)["worker_status"] == "NOT_RUNNING"
print(json.dumps({"run_id": "wr_fp_cross_contract", "cursor": 1}))
"""


def _git(path: Path, *args: str) -> str:
    return subprocess.check_output(["git", "-C", str(path), *args], text=True).strip()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fp-worktree", type=Path, required=True)
    parser.add_argument("--registry-db", type=Path, default=reg.DB)
    parser.add_argument("--portfolio", choices=("P1", "P14"), default="P1")
    args = parser.parse_args()
    fp_root = args.fp_worktree.resolve()
    if not (fp_root / "src/copytrade_pm/pm_forward_portfolios.py").is_file():
        raise SystemExit("FP frozen portfolio and journal modules unavailable")
    fp_head = _git(fp_root, "rev-parse", "HEAD")
    fp_dirty = bool(_git(fp_root, "status", "--porcelain"))
    with closing(reg.connect(args.registry_db, False)) as con:
        selected = selections.select_asof(con, args.portfolio, "9999-12-31T23:59:59+00:00")
    if not selected.get("definition_sha256"):
        raise SystemExit("WR portfolio selection is not SHA-sealed")
    fp_sha = fp.fp_portfolio_sha(selected)
    if fp_sha is None:
        raise SystemExit("FP aliases/risk do not match the WR sealed decision")

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
            or before != after
        ):
            raise SystemExit("FP/WR dual-SHA contract smoke failed")
        print(
            json.dumps(
                {
                    "smoke": "PASS",
                    "fp_head": fp_head,
                    "fp_dirty_worktree": fp_dirty,
                    "portfolio": args.portfolio,
                    "fp_portfolio_sha256": fp_sha,
                    "registry_definition_sha256": selected["definition_sha256"],
                    "journal_cursor": observed["journal_seq_reported"],
                    "read_only_source_unchanged": True,
                    "registry_mutated": False,
                    "worker_state": observed["state"],
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
