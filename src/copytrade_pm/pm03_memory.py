"""Append-only content-addressed PM-03 shadow event storage.

One run per owner-private directory. Files are created exclusively, never rewritten.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path

from .pm03_account import canonical, clock, digest


@dataclass(frozen=True)
class Event:
    event_id: str
    source_event_at: str
    first_known_at: str
    decision_at: str
    hypothetical_fill_at: str
    kind: str
    payload: dict
    source_sha: str
    revision: int = 1

    def validate(self) -> None:
        times = [
            clock(x)
            for x in (
                self.source_event_at,
                self.first_known_at,
                self.decision_at,
                self.hypothetical_fill_at,
            )
        ]
        if times != sorted(times) or not self.event_id or not self.source_sha:
            raise ValueError("INVALID_CAUSAL_EVENT")
        if self.revision < 1:
            raise ValueError("INVALID_REVISION")

    def to_dict(self) -> dict:
        return vars(self).copy()


class Ledger:
    def __init__(self, path: Path):
        self.path = path
        self.path.mkdir(mode=0o700, parents=True, exist_ok=True)
        os.chmod(self.path, 0o700)
        self.events_path = self.path / "events.jsonl"

    def read(self) -> list[dict]:
        if not self.events_path.exists():
            return []
        rows = [json.loads(line) for line in self.events_path.read_text().splitlines()]
        previous = "0" * 64
        ids = set()
        last_time = None
        for item in rows:
            event = Event(**item["event"])
            event.validate()
            if (
                item["previous"] != previous
                or digest({"previous": previous, "event": event.to_dict()}) != item["sha"]
            ):
                raise ValueError("LEDGER_CHAIN_CORRUPT")
            if event.event_id in ids:
                raise ValueError("CONFLICTING_DUPLICATE")
            if last_time is not None and clock(event.decision_at) < last_time:
                raise ValueError("REORDERED_EVENT")
            ids.add(event.event_id)
            previous = item["sha"]
            last_time = clock(event.decision_at)
        return rows

    def append(self, event: Event) -> str:
        event.validate()
        rows = self.read()
        for item in rows:
            if item["event"]["event_id"] == event.event_id:
                if item["event"] == event.to_dict():
                    return item["sha"]
                raise ValueError("CONFLICTING_EVENT_REVISION")
        if rows and clock(event.decision_at) < clock(rows[-1]["event"]["decision_at"]):
            raise ValueError("OUT_OF_ORDER_EVENT")
        prev = rows[-1]["sha"] if rows else "0" * 64
        item = {"previous": prev, "event": event.to_dict()}
        item["sha"] = digest(item)
        data = canonical(item) + b"\n"
        fd = os.open(self.events_path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
        try:
            os.write(fd, data)
            os.fsync(fd)
        finally:
            os.close(fd)
        return item["sha"]

    def checkpoint(self, state: dict, *, schema: str = "pm03_checkpoint_v1") -> str:
        rows = self.read()
        obj = {
            "schema": schema,
            "head": rows[-1]["sha"] if rows else "0" * 64,
            "event_count": len(rows),
            "state": state,
        }
        sha = digest(obj)
        target = self.path / f"{sha}.checkpoint.json"
        blob = canonical({"payload": obj, "sha": sha})
        fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            os.write(fd, blob)
            os.fsync(fd)
        finally:
            os.close(fd)
        return sha

    def load_checkpoint(self, sha: str) -> dict:
        obj = json.loads((self.path / f"{sha}.checkpoint.json").read_bytes())
        if obj["sha"] != sha or digest(obj["payload"]) != sha:
            raise ValueError("CHECKPOINT_HASH_MISMATCH")
        rows = self.read()
        expected = rows[-1]["sha"] if rows else "0" * 64
        if obj["payload"]["schema"] != "pm03_checkpoint_v1":
            raise ValueError("CHECKPOINT_SCHEMA_MISMATCH")
        if obj["payload"]["head"] != expected or obj["payload"]["event_count"] != len(rows):
            raise ValueError("CHECKPOINT_LEDGER_MISMATCH")
        return obj["payload"]["state"]
