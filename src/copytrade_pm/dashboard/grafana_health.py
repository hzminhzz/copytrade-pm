"""Read-only Grafana liveness and authentic publication health; no finance authority."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
import math
import re
import subprocess
from typing import Literal

COMPONENTS = ("grafana", "projection", "ingress", "publisher")
MAX_PUBLICATION_AGE_SECONDS = 45
EXTERNAL_READ_ERRORS = (OSError, ValueError, subprocess.SubprocessError)


@dataclass(frozen=True)
class OperatorHealth:
    status: Literal["HEALTHY", "DEGRADED"]
    container_liveness: dict[str, bool]
    authentic_publication_fresh: bool
    source_evidence_complete: bool
    reasons: tuple[str, ...]
    scope: Literal["OBSERVABILITY_ONLY"] = "OBSERVABILITY_ONLY"
    trading_authorized: Literal[False] = False


def assess(projection: object, components: dict[str, bool]) -> OperatorHealth:
    data = projection if isinstance(projection, dict) else {}
    live = {name: components.get(name) is True for name in COMPONENTS}
    reasons = {name.upper() + "_NOT_RUNNING" for name, running in live.items() if not running}
    age = data.get("publication_age_seconds")
    generation = data.get("generation_sha256")
    fresh = (
        type(age) in (int, float)
        and math.isfinite(age)
        and 0 <= age <= MAX_PUBLICATION_AGE_SECONDS
        and isinstance(generation, str)
        and re.fullmatch(r"[0-9a-f]{64}", generation) is not None
        and data.get("synthetic") is False
    )
    if not fresh:
        reasons.add("AUTHENTIC_PUBLICATION_UNAVAILABLE_OR_STALE")
    # The existing reader validates source clocks, metrics and coverage.
    # This launch-time helper runs from an archive without a project virtualenv.
    complete = data.get("coverage") == "VERIFIED"
    if not complete:
        reasons.add("SOURCE_EVIDENCE_INCOMPLETE")
    return OperatorHealth(
        status="DEGRADED" if reasons else "HEALTHY",
        container_liveness=live,
        authentic_publication_fresh=fresh,
        source_evidence_complete=complete,
        reasons=tuple(sorted(reasons)),
    )


def inspect_running_stack() -> OperatorHealth:
    """Only docker inspect and a read of the existing sanitized evidence volume."""
    components = {}
    for name in COMPONENTS:
        try:
            result = subprocess.run(
                [
                    "docker",
                    "inspect",
                    f"copytrade-grafana-phase1-{name}-1",
                    "--format",
                    "{{.State.Running}}",
                ],
                check=True,
                capture_output=True,
                text=True,
                timeout=5,
            )
            components[name] = result.stdout.strip() == "true"
        except EXTERNAL_READ_ERRORS:
            components[name] = False
    projection = {}
    if components["projection"]:
        try:
            result = subprocess.run(
                [
                    "docker",
                    "exec",
                    "copytrade-grafana-phase1-projection-1",
                    "python",
                    "-c",
                    "import json; from pathlib import Path; "
                    "from copytrade_pm.dashboard.evidence_plane import read_generation; "
                    "print(json.dumps(read_generation(Path('/evidence'))))",
                ],
                check=True,
                capture_output=True,
                text=True,
                timeout=8,
            )
            if len(result.stdout) <= 2_000_000:
                projection = json.loads(result.stdout)
        except EXTERNAL_READ_ERRORS:
            pass
    return assess(projection, components)


def main() -> None:
    report = inspect_running_stack()
    print(json.dumps(asdict(report), sort_keys=True, allow_nan=False))
    raise SystemExit(0 if report.status == "HEALTHY" else 3)


if __name__ == "__main__":
    main()
