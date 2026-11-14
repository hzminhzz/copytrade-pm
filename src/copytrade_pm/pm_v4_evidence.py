"""Backward-compatibility re-export for the shared content-addressed wire store."""

from __future__ import annotations

from .pm_wire_evidence import (
    MAX_ORIGINAL_WIRE,
    SHA,
    compact_official_receipt,
    evidence_path,
    publish_wire,
    read_wire,
)

__all__ = [
    "MAX_ORIGINAL_WIRE",
    "SHA",
    "compact_official_receipt",
    "evidence_path",
    "publish_wire",
    "read_wire",
]
