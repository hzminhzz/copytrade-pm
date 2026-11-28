"""The appliance's private configuration, with paths confined to one state root."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from hashlib import sha256
import json
from pathlib import Path
import re
from typing import Any

SAFE_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,47}")
SHA = re.compile(r"[0-9a-f]{64}")


@dataclass(frozen=True)
class ApplianceConfig:
    root: Path
    sha256: str
    sources: dict[str, dict[str, Any]]
    papers: dict[str, dict[str, Any]]
    quotes: dict[str, Any]
    health: dict[str, Any]

    @property
    def roster(self) -> Path:
        return self.root / "roster.sqlite"

    def path(self, relative: str) -> Path:
        if not isinstance(relative, str) or not relative or Path(relative).is_absolute():
            raise ValueError("APPLIANCE_RELATIVE_STATE_PATH")
        if any(part in (".", "..") for part in relative.split("/")):
            raise ValueError("APPLIANCE_STATE_TRAVERSAL")
        candidate = self.root / relative
        if not candidate.resolve().is_relative_to(self.root) or any(
            item.is_symlink()
            for item in (candidate, *candidate.parents)
            if item != self.root.parent
        ):
            raise ValueError("APPLIANCE_STATE_SYMLINK")
        return candidate


def load_config(root: Path) -> ApplianceConfig:
    root = root.expanduser().absolute()
    path = root / "appliance.json"
    if root.is_symlink() or path.is_symlink() or not path.is_file():
        raise ValueError("APPLIANCE_CONFIG_REQUIRED")
    if root.stat().st_mode & 0o077 or path.stat().st_mode & 0o077:
        raise ValueError("APPLIANCE_PRIVATE_STATE_REQUIRED")
    raw = path.read_bytes()
    if len(raw) > 1024 * 1024:
        raise ValueError("APPLIANCE_CONFIG_TOO_LARGE")
    obj = json.loads(raw)
    if not isinstance(obj, dict) or set(obj) != {"schema", "sources", "papers", "quotes", "health"}:
        raise ValueError("APPLIANCE_CONFIG_SCHEMA")
    if obj["schema"] != "copytrade_appliance_v1":
        raise ValueError("APPLIANCE_CONFIG_SCHEMA")
    for kind in ("sources", "papers"):
        if not isinstance(obj[kind], dict) or not 1 <= len(obj[kind]) <= 32:
            raise ValueError("APPLIANCE_OWNER_COUNT")
        if any(not SAFE_ID.fullmatch(name) for name in obj[kind]):
            raise ValueError("APPLIANCE_OWNER_ID")
    config = ApplianceConfig(
        root,
        sha256(raw).hexdigest(),
        **{k: obj[k] for k in ("sources", "papers", "quotes", "health")},
    )
    paths: set[Path] = set()

    def add_writer(state: Path) -> None:
        if any(state.is_relative_to(other) or other.is_relative_to(state) for other in paths):
            raise ValueError("APPLIANCE_OVERLAPPING_WRITERS")
        paths.add(state)

    for item in config.sources.values():
        if set(item) != {"state", "portfolios", "checkpoint_config", "checkpoint_sha256"}:
            raise ValueError("APPLIANCE_SOURCE_SCHEMA")
        state = config.path(item["state"])
        add_writer(state)
        file = config.path(item["checkpoint_config"])
        if (
            not SHA.fullmatch(item["checkpoint_sha256"])
            or sha256(file.read_bytes()).hexdigest() != item["checkpoint_sha256"]
        ):
            raise ValueError("APPLIANCE_CHECKPOINT_PIN")
        members = item["portfolios"]
        if not isinstance(members, list) or not members or len(set(members)) != len(members):
            raise ValueError("APPLIANCE_SOURCE_PORTFOLIOS")
    from .pm_cwsa_paper import validate_portfolios

    for item in config.papers.values():
        if set(item) != {"state", "source", "run_label", "portfolios", "approval"}:
            raise ValueError("APPLIANCE_PAPER_SCHEMA")
        state = config.path(item["state"])
        add_writer(state)
        if item["source"] not in config.sources or not SAFE_ID.fullmatch(item["run_label"]):
            raise ValueError("APPLIANCE_PAPER_SOURCE_OR_EPOCH")
        validate_portfolios(item["portfolios"])
        if item["approval"] is not None:
            approval = item["approval"]
            if set(approval) != {"path", "sha256", "public_key"}:
                raise ValueError("APPLIANCE_APPROVAL_SCHEMA")
            for key in ("sha256", "public_key"):
                if not SHA.fullmatch(approval[key]):
                    raise ValueError("APPLIANCE_APPROVAL_PIN")
            if sha256(config.path(approval["path"]).read_bytes()).hexdigest() != approval["sha256"]:
                raise ValueError("APPLIANCE_APPROVAL_PIN")
    quote = config.quotes
    if not isinstance(quote, dict) or set(quote) != {"state", "instruments", "poll_seconds"}:
        raise ValueError("APPLIANCE_QUOTES_SCHEMA")
    add_writer(config.path(quote["state"]))
    if not isinstance(quote["instruments"], list) or not 1 <= len(quote["instruments"]) <= 5:
        raise ValueError("APPLIANCE_QUOTE_SCOPE")
    if len(set(quote["instruments"])) != len(quote["instruments"]):
        raise ValueError("APPLIANCE_QUOTE_SCOPE")
    if not Decimal("0.5") <= Decimal(str(quote["poll_seconds"])) <= 60:
        raise ValueError("APPLIANCE_QUOTE_POLL")
    from .pm03_account import Instrument

    for instrument in quote["instruments"]:
        Instrument.parse(instrument)
    health = config.health
    if not isinstance(health, dict) or set(health) != {
        "max_wallets",
        "deep_wallets",
        "weight_per_minute",
        "calendar",
    }:
        raise ValueError("APPLIANCE_HEALTH_SCHEMA")
    for name, low, high in (
        ("max_wallets", 1, 512),
        ("deep_wallets", 0, 64),
        ("weight_per_minute", 1, 600),
    ):
        if type(health[name]) is not int or not low <= health[name] <= high:
            raise ValueError("APPLIANCE_HEALTH_BUDGET")
    if not isinstance(health["calendar"], str) or not re.fullmatch(
        r"\*-\*-\* (?:[01][0-9]|2[0-3]):[0-5][0-9]:[0-5][0-9] UTC", health["calendar"]
    ):
        raise ValueError("APPLIANCE_HEALTH_CALENDAR")
    return config


def verify_config(config: ApplianceConfig) -> dict[str, Any]:
    from datetime import UTC, datetime

    from .pm_cwsa_source_observer import load_checkpoint_configuration
    from .pm_source_selection import selected_parents
    from .pm_cwsa_paper import load_selections, validate_portfolios
    from .pm_cwsa_chapter2_release import read_activation_bundle
    from .roster.store import RosterStore

    if RosterStore.authority_health(config.roster)["database_integrity"] != "VERIFIED":
        raise ValueError("APPLIANCE_ROSTER_INTEGRITY")
    source_counts = {}
    for name, item in config.sources.items():
        parents = selected_parents(
            config.roster, portfolios=tuple(item["portfolios"]), as_of=datetime.now(UTC).isoformat()
        )
        load_checkpoint_configuration(
            config.path(item["checkpoint_config"]), item["checkpoint_sha256"], parents
        )
        source_counts[name] = len(parents)
    paper_counts = {}
    for name, item in config.papers.items():
        portfolios = validate_portfolios(item["portfolios"])
        seals = load_selections(config.roster, configs=portfolios)
        approval = item["approval"]
        approved = read_activation_bundle(
            path=config.path(approval["path"]) if approval else None,
            expected_sha256=approval["sha256"] if approval else None,
            trusted_authority_hex=approval["public_key"] if approval else None,
            seals=seals,
            configs=portfolios,
            run_label=item["run_label"],
            source_db=config.path(config.sources[item["source"]]["state"]) / "paper-events.sqlite3",
        )
        paper_counts[name] = {"portfolios": len(portfolios), "signed": len(approved)}
    return {
        "state": "VERIFIED",
        "config_sha256": config.sha256,
        "sources": source_counts,
        "paper": paper_counts,
    }
