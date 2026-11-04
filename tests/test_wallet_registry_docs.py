"""Canonical registry docs are self-consistent, dated and non-destructive."""

from __future__ import annotations

from copy import deepcopy
import importlib.util
from pathlib import Path
import re

import pytest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "wallet_registry_documentation_audit", ROOT / "scripts/audit_wallet_registry_docs.py"
)
assert SPEC is not None and SPEC.loader is not None
audit = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(audit)


def _dated_snapshot() -> dict:
    content = (ROOT / "docs/WALLET-STATUS.md").read_text(encoding="utf-8")
    known = re.search(r"manifest hash at this cut: `([0-9a-f]{64})`", content)
    assert known is not None
    return {"generation": {"manifest_sha256": known.group(1)}}


def test_canonical_docs_links_and_frozen_evidence_date() -> None:
    status = _dated_snapshot()
    result = audit.check(ROOT, current=status)
    assert result["canonical_files_checked"] >= 10
    assert result["broken_links"] == 0
    assert result["local_links_verified"] >= 40
    assert result["dated_status_source_match"]
    assert result["paper_running"] == "UNKNOWN"
    assert result["admission"] == "UNKNOWN"
    assert result["authorization"] == "NOT_ESTABLISHED"


def test_changed_source_marks_dated_status_stale_not_positive() -> None:
    status = deepcopy(_dated_snapshot())
    status["generation"]["manifest_sha256"] = "f" * 64
    result = audit.check(ROOT, current=status)
    assert result["dated_status_requires_refresh"]
    assert not result["dated_status_source_match"]
    assert result["authorization"] == "NOT_ESTABLISHED"
    assert result["paper_running"] == "UNKNOWN"


def test_registry_first_agent_instructions_are_required() -> None:
    """Future agents must not rediscover wallets from stale prose or memory."""
    agents = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
    guide = (ROOT / "docs/WALLET-REGISTRY-AGENT-WORKFLOW.md").read_text(encoding="utf-8")
    index = (ROOT / "docs/INDEX.md").read_text(encoding="utf-8")
    runbook = (ROOT / "docs/RUNBOOK.md").read_text(encoding="utf-8")
    for command in (
        "copytrade-wallet-registry doctor",
        "copytrade-wallet-registry status",
        "copytrade-wallet-registry portfolio --current",
        "copytrade-wallet-registry wallet --alias",
        "scripts/registry_release.py verify",
    ):
        assert command in guide
    for invariant in (
        "MANDATORY REGISTRY-FIRST",
        "source generation",
        "OptMem",
        "SCIENTIFICALLY_QUALIFIED",
        "TRADING_AUTHORIZED",
    ):
        assert invariant in agents + guide
    for entry in (agents, index, runbook):
        assert "WALLET-REGISTRY-AGENT-WORKFLOW.md" in entry
    assert "gemini.phase5/B" in guide and "q3/B" in guide
    assert "post-seal" in guide
    assert "PAPER_RUNNING" in guide


def test_missing_document_fails_closed(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="required wallet registry document missing"):
        audit.check(tmp_path, current={})
