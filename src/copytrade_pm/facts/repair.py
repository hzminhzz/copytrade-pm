"""Intake-only repair of same-millisecond fill ordering.

``trade_id`` is not monotonic inside a same-millisecond burst on Hyperliquid:
sorting by it breaks position chains (trading-ops measured 59,584 of 68,744
chain links broken in a 30-day window versus raw arrival order). The only
in-band evidence of true order is ``start_position`` continuity — the next
fill's ``start_position`` must equal the previous fill's ``start_position`` plus
its signed size.

This module repairs only *inverted* bursts, using the same algorithm and search
budget as ``trading-ops``'s study-side helper, so a chain that already matches
arrival order is returned untouched. It runs once, at ingest; downstream readers
order by ``(wallet, coin, event_ts_ms, arrival_seq)`` and never re-derive order.

Values are exact ``Decimal``. A ``tolerance`` (default ``1e-6``, the legacy
epsilon) absorbs the already-lossy ``Float64`` provenance of archive sources;
it is a comparison slack, never a rewrite of a stored value.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Sequence

DEFAULT_TOLERANCE = Decimal("1e-6")


@dataclass(frozen=True, slots=True)
class FillLink:
    """The only fields ordering repair needs from a fill row."""

    ts_ms: int
    start_position: Decimal | None
    sign: int  # +1 buy, -1 sell, 0 unknown
    size: Decimal | None

    @property
    def usable(self) -> bool:
        return self.start_position is not None and self.size is not None and self.sign != 0

    @property
    def post_position(self) -> Decimal | None:
        if not self.usable:
            return None
        assert self.start_position is not None and self.size is not None
        return self.start_position + (Decimal(self.sign) * self.size)


@dataclass(frozen=True, slots=True)
class RepairStats:
    bursts: int = 0
    bursts_repaired: int = 0
    bursts_left_broken: int = 0
    bursts_skipped_missing_start_position: int = 0
    rows_moved: int = 0

    def as_dict(self) -> dict[str, int]:
        return {
            "bursts": self.bursts,
            "bursts_repaired": self.bursts_repaired,
            "bursts_left_broken": self.bursts_left_broken,
            "bursts_skipped_missing_start_position": self.bursts_skipped_missing_start_position,
            "rows_moved": self.rows_moved,
        }


@dataclass(frozen=True, slots=True)
class RepairResult:
    order: tuple[int, ...]
    stats: RepairStats


def _count_breaks(
    seq: Sequence[int],
    pre: Sequence[Decimal],
    post: Sequence[Decimal],
    prev_post: Decimal | None,
    next_pre: Decimal | None,
    tolerance: Decimal,
) -> int:
    breaks = 0
    if prev_post is not None and abs(pre[seq[0]] - prev_post) > tolerance:
        breaks += 1
    for left, right in zip(seq, seq[1:], strict=False):
        if abs(pre[right] - post[left]) > tolerance:
            breaks += 1
    if next_pre is not None and abs(next_pre - post[seq[-1]]) > tolerance:
        breaks += 1
    return breaks


def _greedy_order(
    candidates: list[int],
    start: int,
    pre: Sequence[Decimal],
    post: Sequence[Decimal],
    tolerance: Decimal,
) -> list[int]:
    used = {start}
    path = [start]
    while len(path) < len(candidates):
        current_post = post[path[-1]]
        nxt = next(
            (
                idx
                for idx in candidates
                if idx not in used and abs(pre[idx] - current_post) <= tolerance
            ),
            None,
        )
        if nxt is None:
            nxt = next(idx for idx in candidates if idx not in used)
        used.add(nxt)
        path.append(nxt)
    return path


def _solve_burst(
    pre: Sequence[Decimal],
    post: Sequence[Decimal],
    prev_post: Decimal | None,
    next_pre: Decimal | None,
    tolerance: Decimal,
) -> list[int]:
    """Return the best local order for one same-ms burst (indices 0..n-1)."""
    size = len(pre)
    original = list(range(size))
    original_breaks = _count_breaks(original, pre, post, prev_post, next_pre, tolerance)
    if original_breaks == 0:
        return original

    in_degree = [
        sum(1 for other in original if other != idx and abs(post[other] - pre[idx]) <= tolerance)
        for idx in original
    ]
    starts = sorted(
        original,
        key=lambda idx: (
            0 if (prev_post is not None and abs(pre[idx] - prev_post) <= tolerance) else 1,
            0 if in_degree[idx] == 0 else 1,
            idx,
        ),
    )

    best_order = original
    best_breaks = original_breaks

    if size > 6:
        for start in starts[:12]:
            candidate = _greedy_order(original, start, pre, post, tolerance)
            breaks = _count_breaks(candidate, pre, post, prev_post, next_pre, tolerance)
            if breaks < best_breaks:
                best_breaks = breaks
                best_order = candidate
                if best_breaks == 0:
                    break
        return best_order

    used = [False] * size
    path: list[int] = []

    def dfs() -> None:
        nonlocal best_order, best_breaks
        if len(path) == size:
            breaks = _count_breaks(path, pre, post, prev_post, next_pre, tolerance)
            if breaks < best_breaks:
                best_breaks = breaks
                best_order = path.copy()
            return
        current_post = post[path[-1]]
        matches = [
            idx for idx in original if not used[idx] and abs(pre[idx] - current_post) <= tolerance
        ]
        candidates = matches if matches else [idx for idx in original if not used[idx]]
        for nxt in candidates:
            used[nxt] = True
            path.append(nxt)
            dfs()
            path.pop()
            used[nxt] = False
            if best_breaks == 0:
                return

    for start in starts:
        used[start] = True
        path.append(start)
        dfs()
        path.pop()
        used[start] = False
        if best_breaks == 0:
            break

    return best_order


def repair_same_ms_order(
    links: Sequence[FillLink],
    *,
    tolerance: Decimal = DEFAULT_TOLERANCE,
) -> RepairResult:
    """Return the canonical order of one ``(wallet, coin)`` chain.

    ``links`` must already be sorted by ``(event_ts_ms, source_rank, raw_order)``.
    A burst whose continuity cannot be evaluated (missing ``start_position``,
    unknown side) is left in arrival order and counted, never guessed.
    """
    count = len(links)
    order = list(range(count))
    bursts = repaired = left_broken = skipped = moved = 0

    index = 0
    while index < count:
        end = index + 1
        while end < count and links[end].ts_ms == links[index].ts_ms:
            end += 1
        if end - index > 1:
            bursts += 1
            burst = links[index:end]
            usable = all(link.usable for link in burst) and (index == 0 or links[index - 1].usable)
            if not usable:
                skipped += 1
            else:
                pre: list[Decimal] = []
                post: list[Decimal] = []
                for link in burst:
                    assert link.start_position is not None
                    assert link.post_position is not None
                    pre.append(link.start_position)
                    post.append(link.post_position)
                previous = links[index - 1].post_position if index > 0 else None
                following = links[end].start_position if end < count else None
                local = _solve_burst(pre, post, previous, following, tolerance)
                if len(local) != len(burst):
                    raise AssertionError("REPAIR_BURST_LENGTH_MISMATCH")
                breaks = _count_breaks(local, pre, post, previous, following, tolerance)
                if local != list(range(len(burst))):
                    moved += sum(
                        1
                        for local_idx, original_idx in enumerate(local)
                        if local_idx != original_idx
                    )
                    order[index:end] = [index + offset for offset in local]
                    repaired += 1
                if breaks:
                    left_broken += 1
        index = end

    return RepairResult(
        order=tuple(order),
        stats=RepairStats(
            bursts=bursts,
            bursts_repaired=repaired,
            bursts_left_broken=left_broken,
            bursts_skipped_missing_start_position=skipped,
            rows_moved=moved,
        ),
    )
