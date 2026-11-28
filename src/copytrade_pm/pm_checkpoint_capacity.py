"""One process-wide weight budget for public checkpoint acquisition."""

from threading import Lock
from time import monotonic, sleep
from typing import Any

from .pm_e4_prospective import guarded_info


class CaptureTransport:
    def __init__(self, weight_per_second: int) -> None:
        if not 0 < weight_per_second <= 8:
            raise ValueError("CAPACITY_PACING_OUTSIDE_EXPERIMENT_BUDGET")
        self.rate = weight_per_second
        self.lock = Lock()
        self.next = monotonic()

    def __call__(self, request: dict[str, Any]) -> tuple[Any, bytes, str]:
        weight = 2 if request["type"] == "clearinghouseState" else 20
        with self.lock:
            due = self.next
            self.next = max(monotonic(), due) + weight / self.rate
        sleep(max(0, due - monotonic()))
        return guarded_info(request)
