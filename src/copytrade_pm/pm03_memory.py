"""Owner-private append-only, content-addressed PM-03 event memory.

The event chain, not checkpoints or an LLM transcript, is authoritative.
An incomplete/corrupt append is a BLOCKER; it is never silently truncated.
"""

from __future__ import annotations

from dataclasses import dataclass
import fcntl
import json
import os
from pathlib import Path
import stat
from tempfile import NamedTemporaryFile

from .pm03_account import canonical, clock, digest

SENSITIVE_FIELDS = {
    "api_key",
    "apikey",
    "secret",
    "private_key",
    "privatekey",
    "authorization_header",
    "access_token",
    "refresh_token",
    "password",
    "credential",
    "credentials",
    "wallet_address_map",
    "private_wallet_map",
}


def _reject_sensitive_fields(value: object) -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            if str(key).lower().replace("-", "_") in SENSITIVE_FIELDS:
                raise ValueError("SENSITIVE_FIELD_IN_RESEARCH_LEDGER")
            _reject_sensitive_fields(item)
    elif isinstance(value, (tuple, list)):
        for item in value:
            _reject_sensitive_fields(item)


def _atomic_private(path: Path, blob: bytes) -> None:
    if path.exists():
        if path.read_bytes() != blob:
            raise ValueError("IMMUTABLE_FILE_CONFLICT")
        return
    with NamedTemporaryFile(dir=path.parent, prefix=".pm03-", delete=False) as handle:
        tmp = Path(handle.name)
        os.fchmod(handle.fileno(), 0o600)
        try:
            handle.write(blob)
            handle.flush()
            os.fsync(handle.fileno())
        except BaseException:
            tmp.unlink(missing_ok=True)
            raise
    try:
        os.link(tmp, path)  # no overwrite; atomic publication
    except FileExistsError:
        if path.read_bytes() != blob:
            raise ValueError("IMMUTABLE_FILE_CONFLICT") from None
    finally:
        tmp.unlink(missing_ok=True)
    directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(directory)
    finally:
        os.close(directory)


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
        if not isinstance(self.payload, dict) or not self.kind:
            raise ValueError("INVALID_EVENT_PAYLOAD")
        _reject_sensitive_fields(self.payload)

    def to_dict(self) -> dict:
        return vars(self).copy()


class Ledger:
    def __init__(self, path: Path):
        if path.is_symlink():
            raise ValueError("SYMLINK_LEDGER_DIRECTORY")
        self.path = path
        self.path.mkdir(mode=0o700, parents=True, exist_ok=True)
        if self.path.stat().st_mode & 0o077:
            os.chmod(self.path, 0o700)
        self.events_path = self.path / "events.jsonl"
        self.lock_path = self.path / ".writer.lock"

    def _secure_file(self, path: Path) -> None:
        if path.is_symlink():
            raise ValueError("SYMLINK_LEDGER_FILE")
        if path.exists() and (not stat.S_ISREG(path.stat().st_mode) or path.stat().st_mode & 0o077):
            raise ValueError("INSECURE_LEDGER_FILE")

    def read(self) -> list[dict]:
        self._secure_file(self.events_path)
        if not self.events_path.exists():
            return []
        raw = self.events_path.read_bytes()
        if raw and not raw.endswith(b"\n"):
            raise ValueError("TRUNCATED_EVENT_TAIL")
        try:
            rows = [json.loads(line) for line in raw.splitlines()]
        except (ValueError, UnicodeError) as exc:
            raise ValueError("MALFORMED_EVENT_LEDGER") from exc
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

    def append(self, event: Event, *, expected_head: str | None = None) -> str:
        event.validate()
        self._secure_file(self.events_path)
        self._secure_file(self.lock_path)
        lockfd = os.open(self.lock_path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        try:
            fcntl.flock(lockfd, fcntl.LOCK_EX)
            rows = self.read()
            for item in rows:
                if item["event"]["event_id"] == event.event_id:
                    if item["event"] == event.to_dict():
                        return item["sha"]
                    raise ValueError("CONFLICTING_EVENT_REVISION")
            if rows and clock(event.decision_at) < clock(rows[-1]["event"]["decision_at"]):
                raise ValueError("OUT_OF_ORDER_EVENT")
            previous = rows[-1]["sha"] if rows else "0" * 64
            if expected_head is not None and previous != expected_head:
                raise ValueError("CONCURRENT_LEDGER_ADVANCE")
            item = {"previous": previous, "event": event.to_dict()}
            item["sha"] = digest(item)
            blob = canonical(item) + b"\n"
            fd = os.open(
                self.events_path, os.O_WRONLY | os.O_CREAT | os.O_APPEND | os.O_NOFOLLOW, 0o600
            )
            try:
                with os.fdopen(fd, "ab", buffering=0) as stream:
                    stream.write(blob)
                    os.fsync(stream.fileno())
            finally:
                pass
            directory = os.open(self.path, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
            return item["sha"]
        finally:
            fcntl.flock(lockfd, fcntl.LOCK_UN)
            os.close(lockfd)

    def checkpoint(self, state: dict, *, schema: str = "pm03_checkpoint_v1") -> str:
        rows = self.read()
        obj = {
            "schema": schema,
            "head": rows[-1]["sha"] if rows else "0" * 64,
            "event_count": len(rows),
            "state": state,
        }
        sha = digest(obj)
        self._secure_file(self.path / f"{sha}.checkpoint.json")
        _atomic_private(
            self.path / f"{sha}.checkpoint.json", canonical({"payload": obj, "sha": sha})
        )
        return sha

    def load_checkpoint(self, sha: str) -> dict:
        if len(sha) != 64 or any(c not in "0123456789abcdef" for c in sha):
            raise ValueError("INVALID_CHECKPOINT_SHA")
        path = self.path / f"{sha}.checkpoint.json"
        self._secure_file(path)
        obj = json.loads(path.read_bytes())
        if obj["sha"] != sha or digest(obj["payload"]) != sha:
            raise ValueError("CHECKPOINT_HASH_MISMATCH")
        rows = self.read()
        expected = rows[-1]["sha"] if rows else "0" * 64
        if obj["payload"]["schema"] != "pm03_checkpoint_v1":
            raise ValueError("CHECKPOINT_SCHEMA_MISMATCH")
        if obj["payload"]["head"] != expected or obj["payload"]["event_count"] != len(rows):
            raise ValueError("CHECKPOINT_LEDGER_MISMATCH")
        return obj["payload"]["state"]
