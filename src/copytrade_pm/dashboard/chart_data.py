"""Bounded, evidence-separated Polars/Altair presentation of owner-supplied series.

No source retrieval or contractual risk computation happens here. In the absence
of a trusted native historical read, callers must show UNAVAILABLE instead of
inventing chart points.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Any

import altair as alt
import polars as pl

from .adapter import parse_utc, safe_decimal, safe_text

EVIDENCE_CLASSES = frozenset({
    "HISTORICAL_SOURCE", "MODELED_FOLLOWER", "PAPER_SHADOW",
    "DEMO_OBSERVED", "BROKER_EXECUTED",
})
MAX_SOURCE_POINTS = 120_000


def prepare_series(
    points: list[dict[str, Any]],
    *,
    max_points: int = 1200,
    expected_interval_ms: int | None = None,
) -> list[dict[str, Any]]:
    """Reduce owner-supplied points without losing extrema, gaps or reset boundaries.

    Source/value evidence stays distinct. Decimal is used for exact extrema
    selection; float conversion occurs only after the surviving points are chosen.
    An oversized set of critical points fails closed rather than concealing gaps.
    """
    if (type(max_points) is not int or not 16 <= max_points <= 5000
            or type(expected_interval_ms) not in (int, type(None))
            or expected_interval_ms is not None and not 1 <= expected_interval_ms <= 86_400_000
            or not isinstance(points, list) or len(points) > MAX_SOURCE_POINTS):
        raise ValueError("UNBOUNDED_OR_INVALID_FINANCIAL_SERIES")
    if not points:
        return []
    seen_series: dict[str, tuple[str, str, str]] = {}
    groups: dict[str, list[dict[str, Any]]] = {}
    for point in points:
        if not isinstance(point, dict):
            raise ValueError("INVALID_FINANCIAL_ROW")
        ts = parse_utc(point.get("timestamp"))
        exact = safe_decimal(point.get("value"))
        series = safe_text(point.get("series"), 96)
        source = safe_text(point.get("source_id"), 96)
        metric = safe_text(point.get("metric"), 64)
        grade = point.get("evidence_class")
        if (ts is None or exact is None or not series or not source or not metric
                or grade not in EVIDENCE_CLASSES
                or type(point.get("gap_before", False)) is not bool
                or type(point.get("reset_boundary", False)) is not bool):
            raise ValueError("INVALID_OR_UNGRADED_FINANCIAL_ROW")
        identity = (source, grade, metric)
        if series in seen_series and seen_series[series] != identity:
            raise ValueError("CONTRADICTORY_SERIES_PROVENANCE")
        seen_series[series] = identity
        groups.setdefault(series, []).append({
            "timestamp": ts.isoformat(),
            "time_ms": int(ts.timestamp() * 1000),
            "value_exact": exact,
            "value": Decimal(exact),
            "source_id": source,
            "evidence_class": grade,
            "metric": metric,
            "series": series,
            "gap_before": point.get("gap_before", False),
            "reset_boundary": point.get("reset_boundary", False),
        })
    output: list[dict[str, Any]] = []
    per_series_budget = max(16, max_points // len(groups))
    if len(groups) > max_points // 16:
        raise ValueError("TOO_MANY_EVIDENCE_SERIES")
    for name, rows in sorted(groups.items()):
        rows.sort(key=lambda r: r["time_ms"])
        if any(rows[i]["time_ms"] == rows[i - 1]["time_ms"]
               for i in range(1, len(rows))):
            raise ValueError("DUPLICATE_FINANCIAL_TIMESTAMP")
        for i in range(1, len(rows)):
            if (expected_interval_ms is not None
                    and rows[i]["time_ms"] - rows[i - 1]["time_ms"] > expected_interval_ms):
                rows[i]["gap_before"] = True
        if len(rows) <= per_series_budget:
            indices = list(range(len(rows)))
        else:
            # Polars Decimal compares values exactly, including extrema.
            frame = pl.DataFrame({
                "index": list(range(len(rows))),
                "time_ms": [r["time_ms"] for r in rows],
                "value": [r["value_exact"] for r in rows],
            }).with_columns(pl.col("value").cast(pl.Decimal(38, 18)).alias("exact"))
            time_start = rows[0]["time_ms"]
            span = rows[-1]["time_ms"] - time_start
            bucket_width = max(1, (span + max(1, per_series_budget // 4) - 1)
                               // max(1, per_series_budget // 4))
            candidates = frame.with_columns(
                ((pl.col("time_ms") - time_start) // bucket_width).alias("bucket")
            ).group_by("bucket").agg(
                pl.col("index").first().alias("first"),
                pl.col("index").last().alias("last"),
                pl.col("index").sort_by("exact").first().alias("minimum"),
                pl.col("index").sort_by("exact").last().alias("maximum"),
            )
            wanted = {0, len(rows) - 1}
            for record in candidates.iter_rows(named=True):
                wanted.update(record[k] for k in ("first", "last", "minimum", "maximum"))
            critical = {0, len(rows) - 1}
            # Preserve the input's original resets/gaps plus both sides of breaks.
            for i, item in enumerate(rows):
                if item["gap_before"] or item["reset_boundary"]:
                    critical.add(i)
                    critical.add(max(0, i - 1))
            critical.add(min(range(len(rows)), key=lambda i: rows[i]["value"]))
            critical.add(max(range(len(rows)), key=lambda i: rows[i]["value"]))
            if len(critical) > per_series_budget:
                raise ValueError("CRITICAL_FINANCIAL_POINTS_EXCEED_DISPLAY_BUDGET")
            extras = sorted(wanted - critical)
            remaining = per_series_budget - len(critical)
            if len(extras) > remaining:
                extras = [extras[i * len(extras) // remaining] for i in range(remaining)
                          ] if remaining else []
            indices = sorted(critical | set(extras))
        segment = 0
        current_indices = set(indices)
        # Compute original break-segment membership, not just visible neighbors.
        for i, item in enumerate(rows):
            if item["gap_before"]:
                segment += 1
            if i not in current_indices:
                continue
            output.append({
                "timestamp": item["timestamp"], "value": float(item["value"]),
                "value_exact": item["value_exact"], "series": name,
                "trace": f"{name} · {item['evidence_class']}",
                "segment": f"{name}:{segment}",
                "source_id": item["source_id"],
                "evidence_class": item["evidence_class"],
                "metric": item["metric"],
                "gap_before": item["gap_before"],
                "reset_boundary": item["reset_boundary"],
            })
    if len(output) > max_points:
        raise ValueError("TOTAL_FINANCIAL_POINTS_EXCEED_DISPLAY_BUDGET")
    return output


def linked_chart(points: list[dict[str, Any]]) -> alt.VConcatChart:
    """A purely browser-side Vega-Lite brush; no callback or financial re-read."""
    if not points:
        raise ValueError("NO_AUTHORITATIVE_FINANCIAL_POINTS")
    if len(points) > 5000:
        raise ValueError("CHART_RENDER_BUDGET_EXCEEDED")
    data = pl.DataFrame(points).to_dicts()
    base = alt.Chart(alt.InlineData(values=data)).mark_line(point=True).encode(
        x=alt.X("timestamp:T", title="UTC", scale=alt.Scale(type="utc")),
        y=alt.Y("value:Q", title="Presentation-only value"),
        color=alt.Color("trace:N", title="Source / evidence class"),
        detail="segment:N",
        tooltip=["timestamp:T", "value_exact:N", "source_id:N",
                 "evidence_class:N", "metric:N", "gap_before:N", "reset_boundary:N"],
    )
    brush = alt.selection_interval(encodings=["x"], name="time_brush")
    focus = base.transform_filter(brush).properties(height=260, title="Evidence-qualified view")
    context = base.mark_line().add_params(brush).properties(height=80, title="Brush UTC scope")
    return alt.vconcat(focus, context).resolve_scale(x="shared")
