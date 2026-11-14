"""A full final-timestamp page never proves a complete historical ledger."""

import asyncio
from hashlib import sha256
import json
from types import SimpleNamespace

from copytrade_pm import pm_e4_backfill as module


def test_saturated_final_timestamp_remains_unproven(tmp_path, monkeypatch):
    monkeypatch.setattr(
        module,
        "load_cohort",
        lambda root: (
            [
                SimpleNamespace(alias=p, address="0x" + "1" * 40, address_sha256="a" * 64)
                for p in module.PODS
            ],
            {"synthetic": "b" * 64},
        ),
    )

    def provider(request):
        rows = [{"time": request["endTime"], "id": i} for i in range(500)]
        raw = json.dumps(rows).encode()
        return rows, raw, sha256(raw).hexdigest()

    monkeypatch.setattr(module, "guarded_info", provider)

    async def no_sleep(_):
        return None

    monkeypatch.setattr(module.asyncio, "sleep", no_sleep)
    result = asyncio.run(
        module.collect_historical(
            tmp_path,
            tmp_path / "gsynthetic12345",
            pages_per_series=1,
            interval_seconds=3,
        )
    )
    assert result["requests"] == 6
    assert all(
        not row[k]["source_interval_complete"]
        for row in result["wallets"]
        for k in ("funding", "collateral")
    )
