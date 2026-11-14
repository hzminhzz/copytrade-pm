"""Backward-compatibility re-export for the pinned sixteen-portfolio campaign roster."""

from __future__ import annotations

from .pm_source_campaign_roster import (
    ADDRESS,
    CAMPAIGN,
    CANONICAL,
    E2_CONSERVATIVE_100K,
    E9_CONSERVATIVE_100K,
    IDENTITIES,
    MANIFEST_SHA256,
    SHA,
    V4Campaign,
    _fixed_k,
    _fmt,
    _parse_pairs,
    _ro_database,
    load_campaign,
)

__all__ = [
    "ADDRESS",
    "CAMPAIGN",
    "CANONICAL",
    "E2_CONSERVATIVE_100K",
    "E9_CONSERVATIVE_100K",
    "IDENTITIES",
    "MANIFEST_SHA256",
    "SHA",
    "V4Campaign",
    "_fixed_k",
    "_fmt",
    "_parse_pairs",
    "_ro_database",
    "load_campaign",
]
