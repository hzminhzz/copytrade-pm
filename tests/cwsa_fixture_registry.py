"""Synthetic committed roster books for the Chapter 2 campaign tests.

The legacy wallet registry is retired. Each campaign portfolio is one roster
account whose seat ids are the campaign's canonical member labels and whose
wallets are deterministic fictitious addresses.
"""

from hashlib import sha256
from pathlib import Path

from decimal import Decimal
from copytrade_pm.roster import RosterStore
from roster_fixture import add_account


PORTFOLIO_CONFIGS: dict[str, dict] = {
    "A": {
        "folder": "A",
        "starting_balance": Decimal("10000"),
        "members": ("W028", "W030", "W042"),
    },
    "B": {
        "folder": "B",
        "starting_balance": Decimal("10000"),
        "members": ("CA-005", "W031", "W044"),
    },
    "C": {
        "folder": "C",
        "starting_balance": Decimal("10000"),
        "members": ("CO-001", "VS066", "W015"),
    },
    "Combo2": {
        "folder": "Combo2",
        "starting_balance": Decimal("5000"),
        "members": ("CA-008", "W015", "W028"),
    },
    "regime.macro/TriadA": {
        "folder": "TriadA",
        "starting_balance": Decimal("10000"),
        "members": ("ACT04", "ACT08", "ACT09"),
    },
    "regime.macro/TriadChop": {
        "folder": "TriadChop",
        "starting_balance": Decimal("10000"),
        "members": ("ACT04", "ACT09", "ACT10"),
    },
}


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
            add_account(store, pid.replace("/", ":"), members)
    return path
