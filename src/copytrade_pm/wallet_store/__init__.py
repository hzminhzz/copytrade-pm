"""Canonical wallet-level trading data store.

The public package remains importable without the optional market extra.
Accessing a store model or operation loads its actual implementation, which
requires Polars; ordinary copytrade-pm core imports do not.
"""

from __future__ import annotations

from importlib import import_module

_EXPORT_GROUPS = {
    "adapters": (
        "from_hyperx_camel",
        "from_hyperx_snake",
        "from_vike",
    ),
    "catalog": (
        "DEFAULT_REGISTRY_DB",
        "DEFAULT_STORE_DIR",
        "get_catalog_path",
        "init_catalog",
        "query_uncovered_registry_wallets",
    ),
    "schema": (
        "DATASET_SCHEMAS",
        "DATASET_SHA256",
        "FILLS_POLARS_SCHEMA",
        "POSITIONS_POLARS_SCHEMA",
        "EQUITY_POLARS_SCHEMA",
        "FUNDING_POLARS_SCHEMA",
        "LEDGER_POLARS_SCHEMA",
        "SCHEMA_VERSION",
        "Equity",
        "Fill",
        "Funding",
        "Ledger",
        "Position",
    ),
    "store": (
        "coverage",
        "ingest",
        "scan",
        "verify",
    ),
}
_EXPORT_MODULES = {name: module for module, names in _EXPORT_GROUPS.items() for name in names}

__all__ = sorted(_EXPORT_MODULES)


def __getattr__(name: str):
    module = _EXPORT_MODULES.get(name)
    if module is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    return getattr(import_module(f".{module}", __name__), name)


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(__all__))
