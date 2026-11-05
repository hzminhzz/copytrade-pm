"""Check canonical wallet-registry documentation and source-status truth.

This is read-only. It does not remove historical artifacts or rewrite docs.
Run: uv run --group dev python scripts/audit_wallet_registry_docs.py
"""

from __future__ import annotations

import json
from pathlib import Path
import re
from urllib.parse import unquote

from copytrade_pm import wallet_registry as registry

DOCS = (
    "AGENTS.md",
    "docs/INDEX.md",
    "docs/ARCHITECTURE.md",
    "docs/DATA-ACQUISITION.md",
    "docs/RUNBOOK.md",
    "docs/WALLET-STATUS.md",
    "docs/WALLET-REGISTRY-AGENT-WORKFLOW.md",
    "docs/SQLITE-NATIVE-LEGACY-LOCK-20261105.md",
    "docs/WALLET-REGISTRY-STATUS-20261104.md",
    "docs/WALLET-REGISTRY-ACCEPTANCE-20261104.md",
    "docs/WALLET-REGISTRY-PAPER-CONTRACT-20261104.md",
    "docs/WALLET-REGISTRY-SQLITE-ADOPTION-PLAN-20261104.md",
    "docs/WALLET-REGISTRY-RELEASE-RUNBOOK.md",
    "docs/WALLET-REGISTRY-SIGNED-NEGATIVE-EVIDENCE-20261104.md",
)
REQUIRED_LINKS = (
    "docs/WALLET-REGISTRY-AGENT-WORKFLOW.md",
    "docs/SQLITE-NATIVE-LEGACY-LOCK-20261105.md",
    "docs/WALLET-STATUS.md",
    "docs/WALLET-REGISTRY-STATUS-20261104.md",
    "docs/WALLET-REGISTRY-ACCEPTANCE-20261104.md",
    "docs/WALLET-REGISTRY-PAPER-CONTRACT-20261104.md",
    "docs/WALLET-REGISTRY-RELEASE-RUNBOOK.md",
    "docs/WALLET-REGISTRY-SIGNED-NEGATIVE-EVIDENCE-20261104.md",
)
MD_LINK = re.compile(r"(?<!!)\[[^\]]+\]\(([^)]+)\)")


def check(repo: Path, *, current: dict | None = None) -> dict:
    if not all((repo / relative).is_file() for relative in DOCS):
        raise ValueError("required wallet registry document missing")
    broken = []
    found = {}
    for relative in DOCS:
        src = repo / relative
        content = src.read_text(encoding="utf-8")
        for raw in MD_LINK.findall(content):
            dest = raw.split(" ", 1)[0].strip(" <>")
            if not dest or dest.startswith(("http:", "https:", "mailto:", "#", "app:")):
                continue
            target = unquote(dest.split("#", 1)[0])
            if not target:
                continue
            linked = (src.parent / target).resolve()
            if not linked.is_relative_to(repo.resolve()) or not linked.is_file():
                broken.append((relative, target))
            else:
                found[relative, target] = str(linked.relative_to(repo))
    if broken:
        raise ValueError("canonical local Markdown links broken (redacted paths)")
    index = (repo / "docs/INDEX.md").read_text(encoding="utf-8")
    agents = (repo / "AGENTS.md").read_text(encoding="utf-8")
    if not all(Path(relative).name in index for relative in REQUIRED_LINKS):
        raise ValueError("current wallet registry documents missing from INDEX")
    if "WALLET-STATUS.md" not in agents:
        raise ValueError("AGENTS.md omits canonical wallet status")
    if "WALLET-REGISTRY-AGENT-WORKFLOW.md" not in agents:
        raise ValueError("AGENTS.md omits mandatory registry-first workflow")
    if "MANDATORY REGISTRY-FIRST" not in agents:
        raise ValueError("AGENTS.md must require registry-first discovery")
    status = (repo / "docs/WALLET-STATUS.md").read_text(encoding="utf-8")
    if (
        "RUNTIME_ADMITTED" not in status
        or "UNKNOWN" not in status
        or "SCIENTIFICALLY_QUALIFIED" not in status
        or "NOT ESTABLISHED" not in status
        or "TRADING_AUTHORIZED" not in status
    ):
        raise ValueError("canonical status conflates research and authorization")
    published_sha = re.search(r"manifest hash at this cut: `([0-9a-f]{64})`", status)
    if not published_sha:
        raise ValueError("status has no declared dated manifest SHA")
    db = current if current is not None else registry.db_status(registry.DB)
    db_sha = db["generation"].get("manifest_sha256")
    matches = db_sha == published_sha.group(1)
    # Historical status remains dated on a changed source; never silently
    # publish it as current or treat it as an authorization decision.
    return {
        "canonical_files_checked": len(DOCS),
        "local_links_verified": len(found),
        "broken_links": 0,
        "dated_status_source_match": matches,
        "dated_status_requires_refresh": not matches,
        "unsafe_historical_archives_removed": 0,
        "authorization": "NOT_ESTABLISHED",
        "admission": "UNKNOWN",
        "paper_running": "UNKNOWN",
    }


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    print(json.dumps(check(root), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
