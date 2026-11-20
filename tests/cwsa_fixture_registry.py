"""Synthetic committed roster books for the Chapter 2 campaign tests.

The legacy wallet registry is retired. Each campaign portfolio is one roster
account whose seat ids are the campaign's canonical member labels and whose
wallets are deterministic fictitious addresses.
"""

from hashlib import sha256
from pathlib import Path

from copytrade_pm.pm_cwsa_six_paper import PORTFOLIO_CONFIGS, roster_account_id
from copytrade_pm.roster import RosterStore
from roster_fixture import add_account


def _wallet(alias: str) -> str:
    """Deterministic fictitious address per member label; never a real wallet."""
    return "0x" + sha256(alias.encode("utf-8")).hexdigest()[:40]


def make_registry(tmp_path: Path) -> Path:
    path = tmp_path / "roster.sqlite"
    if path.is_file():
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    with RosterStore(path, create=True, writable=True) as store:
        for pid, config in PORTFOLIO_CONFIGS.items():
            members = {member: _wallet(f"{pid}{member}") for member in sorted(config["members"])}
            add_account(store, roster_account_id(pid), members)
    return path
