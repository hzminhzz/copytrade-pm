""":mod:`copytrade_pm.facts` — the unified bi-temporal fact store.

Public surface (three deep operations plus read-only reporting)::

    from copytrade_pm.facts import FactStore, ProvenanceTier

    store = FactStore("~/.local/share/copytrade/facts").expanduser()
    slice_ = store.scan("fills", wallets=[...], as_of_ms=..., tiers=(ProvenanceTier.OBSERVED_FETCH,))

This package owns raw facts only. It never imports ``roster``, scoring, paper
risk, or broker code, and it never invents a clock, a price, or a flat.

Layering:

* :mod:`copytrade_pm.facts.schemas` — canonical ``Decimal(38, 12)`` schemas.
* :mod:`copytrade_pm.facts.manifest` — stdlib-only SQLite manifest (importable
  by read-only clients that have no Polars).
* :mod:`copytrade_pm.facts.repair` — intake-only same-ms order repair.
* :mod:`copytrade_pm.facts.sources` — named source catalogue + adapters.
* :mod:`copytrade_pm.facts.store` — :class:`FactStore` writer/reader.
* :mod:`copytrade_pm.facts.migrate` — idempotent, reconciling migration.
"""

from __future__ import annotations

from .manifest import (
    MANIFEST_NAME,
    MANIFEST_SCHEMA_VERSION,
    DayBatch,
    InputRecord,
    connect,
    day_batches,
    day_coverage,
    manifest_path,
)
from .migrate import (
    Migration,
    MigrationError,
    MigrationReceipt,
    new_receipt,
)
from .repair import DEFAULT_TOLERANCE, FillLink, RepairResult, RepairStats, repair_same_ms_order
from .ingest import FactIngestor, IngestReceipt, frame_from_rows
from .schemas import (
    BARS_1M_COLUMNS,
    EQUITY_COLUMNS,
    FILLS_COLUMNS,
    FUNDING_COLUMNS,
    IDENTITY_COLUMNS,
    KIND_COLUMNS,
    LEDGER_COLUMNS,
    MONEY_SCALE,
    POSITIONS_COLUMNS,
    SCHEMA_VERSION,
    ProvenanceTier,
    column_names,
    schema_for,
    schema_sha,
)
from .sources import (
    RESERVOIR_FULL_HISTORY,
    RESERVOIR_LIQUID12_DISCOVERY,
    RESERVOIR_MONITORED_PLUS_SIX,
    RESERVOIR_ROSTER_DAILY,
    SOURCE_CATALOGUE,
    WALLET_STORE_SOURCE,
    SourceLayer,
    SourceSpec,
    build_catalogue,
    discover_inputs,
    file_sha256,
)
from .store import (
    CoverageReport,
    FactSlice,
    FactStore,
    FactStoreError,
    PreparedDay,
    WriteReceipt,
)

__all__ = [
    "BARS_1M_COLUMNS",
    "CoverageReport",
    "DEFAULT_TOLERANCE",
    "DayBatch",
    "EQUITY_COLUMNS",
    "FILLS_COLUMNS",
    "FUNDING_COLUMNS",
    "FactIngestor",
    "FactSlice",
    "FactStore",
    "FactStoreError",
    "FillLink",
    "IDENTITY_COLUMNS",
    "IngestReceipt",
    "InputRecord",
    "KIND_COLUMNS",
    "LEDGER_COLUMNS",
    "MANIFEST_NAME",
    "MANIFEST_SCHEMA_VERSION",
    "MONEY_SCALE",
    "Migration",
    "MigrationError",
    "MigrationReceipt",
    "POSITIONS_COLUMNS",
    "PreparedDay",
    "ProvenanceTier",
    "RESERVOIR_FULL_HISTORY",
    "RESERVOIR_LIQUID12_DISCOVERY",
    "RESERVOIR_MONITORED_PLUS_SIX",
    "RESERVOIR_ROSTER_DAILY",
    "RepairResult",
    "RepairStats",
    "SCHEMA_VERSION",
    "SOURCE_CATALOGUE",
    "SourceLayer",
    "SourceSpec",
    "WALLET_STORE_SOURCE",
    "WriteReceipt",
    "build_catalogue",
    "column_names",
    "connect",
    "day_batches",
    "day_coverage",
    "discover_inputs",
    "file_sha256",
    "frame_from_rows",
    "manifest_path",
    "new_receipt",
    "repair_same_ms_order",
    "schema_for",
    "schema_sha",
]
