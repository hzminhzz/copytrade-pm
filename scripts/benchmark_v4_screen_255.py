"""Verified 90-day same-input single/triple comparison, no source mutations."""

from __future__ import annotations

import json
import resource
from pathlib import Path
from statistics import median
from time import perf_counter
from copytrade_pm.pm_v4_fast_screen import run_v4_screen

root = Path("docs")
job = json.loads((root / "V4-FAST-SCREEN-HL94-ORACLE-20261110.json").read_text())
kw = dict(
    input_root=root,
    source_root=Path("/home/quant/dev/copytrade-pm/data"),
    market_root=Path("/home/quant/dev/quant/ml4t-data/.data/store"),
    cache_root=Path("/home/quant/.cache/copytrade-v4screen-255"),
)
results = {}
for label, scenarios in (("single", ("BASE",)), ("triple", ("BASE", "DELAYED", "ADVERSE"))):
    values = []
    for i in range(4):
        started = perf_counter()
        item = run_v4_screen(job, scenarios=scenarios, **kw)
        values.append(round(perf_counter() - started, 6))
    results[label] = dict(
        seconds=values,
        median_s=median(values),
        p95_nearest_rank_s=sorted(values)[3],
        report_sha256=item["report_sha256"],
        cache=item["report_cache_status"],
        estimated_episode_results=item["estimated_episode_results"],
    )
results["overhead_pct"] = round(
    100 * (results["triple"]["median_s"] / results["single"]["median_s"] - 1), 2
)
results["peak_rss_kib"] = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
results["source_accounts"] = item["source_accounts"]
results["episodes_supported"] = item["supported_episodes"]
results["economic_outcomes"] = item["economic_outcomes"]
print(json.dumps(results, sort_keys=True))
