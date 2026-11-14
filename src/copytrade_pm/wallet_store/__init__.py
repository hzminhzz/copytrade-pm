"""Canonical wallet-level trading data store for copytrade-pm."""

from .adapters import (
    from_hyperx_camel,
    from_hyperx_snake,
    from_vike,
)
from .catalog import (
    DEFAULT_REGISTRY_DB,
    DEFAULT_STORE_DIR,
    get_catalog_path,
    init_catalog,
    query_uncovered_registry_wallets,
)
from .schema import (
    DATASET_SCHEMAS,
    DATASET_SHA256,
    FILLS_POLARS_SCHEMA,
    POSITIONS_POLARS_SCHEMA,
    EQUITY_POLARS_SCHEMA,
    FUNDING_POLARS_SCHEMA,
    LEDGER_POLARS_SCHEMA,
    SCHEMA_VERSION,
    Equity,
    Fill,
    Funding,
    Ledger,
    Position,
)
from .store import (
    coverage,
    ingest,
    scan,
    verify,
)

__all__ = [
    "DATASET_SCHEMAS",
    "DATASET_SHA256",
    "DEFAULT_REGISTRY_DB",
    "DEFAULT_STORE_DIR",
    "EQUITY_POLARS_SCHEMA",
    "Equity",
    "FILLS_POLARS_SCHEMA",
    "Fill",
    "FUNDING_POLARS_SCHEMA",
    "Funding",
    "LEDGER_POLARS_SCHEMA",
    "Ledger",
    "POSITIONS_POLARS_SCHEMA",
    "Position",
    "SCHEMA_VERSION",
    "coverage",
    "from_hyperx_camel",
    "from_hyperx_snake",
    "from_vike",
    "get_catalog_path",
    "ingest",
    "init_catalog",
    "query_uncovered_registry_wallets",
    "scan",
    "verify",
]
