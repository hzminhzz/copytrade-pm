"""PM-03 offline research CLI; consumes local JSON only, never submits orders."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .pm03_account import Rulebook, canonical, digest, number
from .pm03_memory import Event, _atomic_private
from .pm03_run import ShadowRun, _cost_model, _positions, _prices, _quotes
from .pm03_stress import ScenarioStep, compare_policies


def _write_report(root: Path, report: dict) -> Path:
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    if root.is_symlink():
        raise ValueError("SYMLINK_REPORT_DIRECTORY")
    root.chmod(0o700)
    sha = digest(report)
    destination = root / f"{sha}.json"
    _atomic_private(destination, canonical(report) + b"\n")
    return destination


def execute(spec: dict, output_dir: Path) -> dict:
    if spec.get("schema") != "pm03_cli_input_v1":
        raise ValueError("UNSUPPORTED_PM03_CLI_INPUT")
    book = Rulebook.from_dict(spec["rulebook"])
    if spec.get("action") == "compare":
        if spec.get("mode") != "RESEARCH_SYNTHETIC":
            raise ValueError("NO_REAL_ECONOMIC_POLICY_COMPARISON")
        steps = [
            ScenarioStep(
                as_of=s["as_of"],
                hypothetical_fill_at=s["hypothetical_fill_at"],
                proposed=_positions(s["proposed"]),
                observations=_quotes(s["observations"]),
                shocks=tuple(_prices(shock) for shock in s["shocks"]),
                trusted=s.get("trusted", True),
                capacity_known=s.get("capacity_known", True),
                hedge_break_loss=number(s.get("hedge_break_loss", "0")),
            )
            for s in spec["steps"]
        ]
        result = compare_policies(
            rulebook=book,
            started_at=spec["started_at"],
            steps=steps,
            cost_model=_cost_model(spec["costs"]),
            historical_scores={k: number(v) for k, v in spec["historical_scores"].items()},
        )
    elif spec.get("action") == "replay":
        run = ShadowRun(
            output_dir / "runs",
            run_id=spec["run_id"],
            rulebook=book,
            started_at=spec["started_at"],
            mode=spec["mode"],
            pm01_sha=spec["pm01_sha"],
            pm02_sha=spec["pm02_sha"],
            market_manifest_sha=spec["market_manifest_sha"],
        )
        for event in spec.get("events", []):
            run.record(Event(**event))
        state = run.state()
        checkpoint = run.checkpoint()
        run.verify_checkpoint(checkpoint)
        result = {
            "schema": "pm03_replay_result_v1",
            "state": state,
            "checkpoint_sha": checkpoint,
            "ledger_sha": run.ledger.read()[-1]["sha"] if run.ledger.read() else None,
            "no_live_order_path": True,
        }
    else:
        raise ValueError("UNKNOWN_PM03_ACTION")
    output = _write_report(output_dir / "reports", result)
    return {"path": str(output), "sha": digest(result), "mode": spec["mode"]}


def main() -> None:
    parser = argparse.ArgumentParser(description="PM-03 offline synthetic shadow simulator")
    parser.add_argument("--input", required=True, type=Path, help="Local immutable JSON fixture")
    parser.add_argument(
        "--output-dir", required=True, type=Path, help="Owner-private results directory"
    )
    args = parser.parse_args()
    spec = json.loads(args.input.read_text(encoding="utf-8"))
    print(json.dumps(execute(spec, args.output_dir), sort_keys=True))


if __name__ == "__main__":
    main()
