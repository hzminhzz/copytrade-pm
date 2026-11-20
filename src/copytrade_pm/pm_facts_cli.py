"""``copytrade-pm-facts`` — FactStore migration, verification, coverage, benchmark.

Output discipline: only aggregate, non-identifying numbers are printed. Wallet
addresses, private paths inside batches, and row contents never reach stdout or
stderr. :func:`assert_aggregate_only` enforces that at the print boundary, so a
future edit that echoes a row fails closed instead of leaking.

Canonical invocations (from the repository root, Polars comes from the `market`
extra)::

    uv run --frozen --extra market python -m copytrade_pm.pm_facts_cli migrate \\
        --store  ~/.local/share/copytrade/facts \\
        --wallet-store ~/dev/copytrade-pm/data/private/wallet_store \\
        --reservoir full-history=~/.local/share/copytrade/research/reservoir-full-history-20261115 \\
        --reservoir monitored-plus-six=~/.local/share/copytrade/research/reservoir-monitored-plus-six-20260701-20261111 \\
        --reservoir roster-daily=~/.local/share/copytrade/research/reservoir-roster-daily-20261118 \\
        --reservoir liquid12-discovery=~/.local/share/copytrade/research/liquid12-discovery-20261117 \\
        --report /tmp/facts-migration-receipt.json \\
        --apply

    uv run --frozen --extra market python -m copytrade_pm.pm_facts_cli verify \\
        --store ~/.local/share/copytrade/facts

    uv run --frozen --extra market python -m copytrade_pm.pm_facts_cli benchmark \\
        --store ~/.local/share/copytrade/facts --wallets 250 --days 200

Drop ``--apply`` to run the same migration as a dry run (no file or manifest
write; the receipt still shows every batch id and row count).

There is no console-script alias in Slice 2: every ``[project.scripts]`` entry
must be classified in ``pm_capabilities_catalog`` and pass the capability
inventory's parser-construct rules, and Slice 3 replaces that list with five
domain subcommands. Use the ``python -m`` form above until then.
"""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
import json
from pathlib import Path
import re
import shutil
import sys
import tempfile
from typing import Any, Sequence

ADDRESS_PATTERN = re.compile(r"0x[0-9a-fA-F]{40}")


def redact(text: str) -> str:
    """Replace any wallet-shaped token with ``<wallet>`` before it is printed."""
    return ADDRESS_PATTERN.sub("<wallet>", text)


def assert_aggregate_only(text: str) -> str:
    """Fail closed if any wallet-shaped token reaches the output."""
    if ADDRESS_PATTERN.search(text):
        raise RuntimeError("FACTS_OUTPUT_WOULD_LEAK_WALLET_ADDRESS")
    return text


def emit(lines: Sequence[str]) -> None:
    for line in lines:
        print(assert_aggregate_only(redact(line)))


def _pairs(values: Sequence[str] | None) -> dict[str, str]:
    out: dict[str, str] = {}
    for value in values or ():
        if "=" not in value:
            raise SystemExit(f"--reservoir expects PREFIX=PATH, got {value!r}")
        name, path = value.split("=", 1)
        out[name.strip()] = path.strip()
    return out


def _kinds(value: str) -> tuple[str, ...]:
    kinds = tuple(part.strip() for part in value.split(",") if part.strip())
    if not kinds:
        raise SystemExit("--kinds must name at least one kind")
    return kinds


def cmd_migrate(args: argparse.Namespace) -> int:
    from .facts.migrate import Migration, new_receipt, now_iso
    from .facts.sources import build_catalogue
    from .facts.store import FactStore
    from .facts import manifest as mf

    kinds = _kinds(args.kinds)
    sources, not_supplied = build_catalogue(
        wallet_store=args.wallet_store,
        reservoir=_pairs(args.reservoir),
    )
    if args.require_all_sources and not_supplied:
        missing = ", ".join(not_supplied)
        raise SystemExit(f"MISSING_REQUIRED_SOURCES: {missing}")

    store = FactStore(args.store, create=args.apply)
    receipt = new_receipt(
        store_root=args.store,
        sources=sources,
        not_supplied=not_supplied,
        kinds=kinds,
        dry_run=not args.apply,
    )
    migration = Migration(
        store=store,
        sources=sources,
        kinds=kinds,
        dry_run=not args.apply,
        wallet_store_catalog=args.wallet_store_catalog,
        pattern=args.pattern,
    )
    started = datetime.now(tz=UTC).timestamp()
    if args.apply:
        con = store.connect()
        mf.start_run(con, run_id=receipt.run_id, started_at=receipt.started_at)
    result = migration.run(receipt)
    result.finished_at = now_iso()
    elapsed = round(datetime.now(tz=UTC).timestamp() - started, 2)

    payload = result.as_dict()
    payload["elapsed_seconds"] = elapsed
    payload["applied"] = bool(args.apply)
    if args.report:
        report_path = Path(args.report).expanduser()
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str))
    if args.apply:
        mf.finish_run(
            store.connect(),
            run_id=result.run_id,
            finished_at=result.finished_at,
            status="OK",
            totals=payload["totals"],
        )

    if args.json:
        emit([json.dumps(payload, sort_keys=True, default=str)])
    else:
        lines = [
            f"facts migrate: applied={bool(args.apply)} store={args.store} elapsed_s={elapsed}",
            "sources used=" + (",".join(result.sources_used) or "none"),
            "sources not_supplied=" + (",".join(result.sources_not_supplied) or "none"),
            "sources empty=" + (",".join(result.sources_empty) or "none"),
            "kinds="
            + ",".join(result.kinds)
            + (
                "  unmigrated_kinds=" + ",".join(result.unmigrated_kinds)
                if result.unmigrated_kinds
                else ""
            ),
            f"days total={payload['days_total']} created={payload['days_created']} "
            f"rebuilt={payload['days_rebuilt']} unchanged={payload['days_unchanged']} "
            f"dry_run={payload['days_dry_run']}",
        ]
        for kind, summary in sorted(result.reconciliation.items()):
            lines.append(
                f"{kind}: rows_read={summary['rows_read']} rows_written={summary['rows_written']} "
                f"rows_accounted={summary['rows_accounted']} "
                f"identity_holds={summary['identity_holds']} "
                f"quantized_to_zero={summary['rows_quantized_to_zero']} "
                f"repair_bursts={summary['repair_bursts']} "
                f"repair_bursts_repaired={summary['repair_bursts_repaired']} "
                f"repair_rows_moved={summary['repair_rows_moved']}"
            )
        for key, totals in sorted(result.totals.items()):
            lines.append(
                f"source {key}: files={totals.get('files_read', 0)} "
                f"read={totals.get('rows_read', 0)} kept={totals.get('rows_kept', 0)} "
                f"dup_within={totals.get('rows_duplicate_within', 0)} "
                f"dup_cross={totals.get('rows_duplicate_cross', 0)} "
                f"conflicting={totals.get('rows_conflicting_values', 0)} "
                f"null_key={totals.get('rows_null_key', 0)} "
                f"rejected={totals.get('rows_rejected', 0)}"
            )
        lines.append(f"receipt_sha256={payload['receipt_sha256']}")
        if args.report:
            lines.append(f"report={args.report}")
        emit(lines)
    store.close()
    for summary in result.reconciliation.values():
        if not summary["identity_holds"]:
            return 2
    return 0


def cmd_verify(args: argparse.Namespace) -> int:
    from .facts.store import FactStore

    store = FactStore(args.store)
    report = store.verify()
    payload = {
        "store": str(args.store),
        "batches_checked": report["batches_checked"],
        "problems": report["problems"],
        "orphan_files": report["orphan_files"],
        "ok": report["ok"],
    }
    if args.json:
        emit([json.dumps(payload, sort_keys=True)])
    else:
        emit(
            [
                f"facts verify: store={args.store} batches={report['batches_checked']} "
                f"problems={len(report['problems'])} "
                f"orphans={len(report['orphan_files'])} ok={report['ok']}",
                *[f"problem {problem}" for problem in report["problems"][:20]],
            ]
        )
    store.close()
    return 0 if report["ok"] else 1


def cmd_coverage(args: argparse.Namespace) -> int:
    from .facts.store import FactStore

    store = FactStore(args.store)
    payload: dict[str, Any] = {}
    for kind in _kinds(args.kinds):
        payload[kind] = store.coverage(kind).as_dict()
    if args.json:
        emit([json.dumps(payload, sort_keys=True)])
    else:
        lines = [f"facts coverage: store={args.store}"]
        for kind, summary in payload.items():
            lines.append(
                f"{kind}: days={summary['days_present']} rows={summary['rows']} "
                f"files={summary['files']} first={summary['first_day']} last={summary['last_day']} "
                f"observed_fetch_rows={summary['observed_fetch_rows']} "
                f"retrospective_rows={summary['retrospective_rows']}"
            )
        emit(lines)
    store.close()
    return 0


def cmd_benchmark(args: argparse.Namespace) -> int:
    from .facts.bench import SyntheticPlan, build_synthetic_store, run_benchmark
    from .facts.store import FactStore

    temporary: Path | None = None
    if args.store:
        store = FactStore(args.store)
    else:
        target = (
            Path(args.workdir).expanduser()
            if args.workdir
            else Path(tempfile.mkdtemp(prefix="facts-bench-"))
        )
        if args.workdir:
            if target.exists():
                shutil.rmtree(target)
        temporary = target
        plan = SyntheticPlan(
            wallets=args.wallets,
            days=args.days,
            rows_per_wallet_day=args.rows_per_wallet_day,
        )
        store = build_synthetic_store(target, plan)
    try:
        stats = run_benchmark(
            store,
            wallets=args.wallets,
            days=args.days,
            repeats=args.repeats,
            day_end=args.end_day,
        )
    finally:
        store.close()
        if temporary is not None and not args.keep:
            shutil.rmtree(temporary, ignore_errors=True)
    payload = {"store": str(args.store or temporary), **stats}
    if args.json:
        emit([json.dumps(payload, sort_keys=True)])
    else:
        emit(
            [
                f"facts benchmark: wallets={stats['wallets']} days={stats['days']} "
                f"window={stats['window'][0]}..{stats['window'][1]}",
                f"rows_returned={stats['rows_returned']} files_scanned={stats['files_scanned']} "
                f"parquet_mb={round(stats['parquet_bytes'] / 1e6, 1)}",
                f"seconds p50={stats['seconds_p50']} p95={stats['seconds_p95']} "
                f"min={stats['seconds_min']} max={stats['seconds_max']}",
                f"rows_per_second={stats['rows_per_second']} "
                f"mb_per_second={stats['mb_per_second']} columns={stats['schema_columns']}",
                f"pit_pass: rows={stats['pit_rows_returned']} "
                f"seconds={stats['pit_seconds']} "
                f"(archive rows without a recorded clock are excluded by design)",
            ]
        )
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m copytrade_pm.pm_facts_cli",
        description="Day-partitioned Decimal(38,12) fact store: migrate, verify, coverage, benchmark.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    migrate = sub.add_parser("migrate", help="idempotent migration from named sources")
    migrate.add_argument("--store", required=True, help="fact store root (created with --apply)")
    migrate.add_argument("--wallet-store", default=None, help="legacy wallet_store root")
    migrate.add_argument(
        "--reservoir",
        action="append",
        default=[],
        metavar="PREFIX=PATH",
        help="reservoir source; PREFIX in full-history, monitored-plus-six, roster-daily, liquid12-discovery",
    )
    migrate.add_argument("--wallet-store-catalog", default=None, help="legacy catalog.sqlite path")
    migrate.add_argument("--kinds", default="fills,positions", help="comma separated kinds")
    migrate.add_argument("--pattern", default="**/*.parquet", help="glob under each root")
    migrate.add_argument(
        "--require-all-sources",
        action="store_true",
        help="fail closed unless all five catalogue sources are supplied",
    )
    migrate.add_argument("--report", default=None, help="write the full JSON receipt here")
    migrate.add_argument(
        "--apply", action="store_true", help="write batches and manifest (default: dry run)"
    )
    migrate.add_argument("--json", action="store_true", help="print the receipt as one JSON object")
    migrate.set_defaults(func=cmd_migrate)

    verify = sub.add_parser("verify", help="re-hash every batch against the manifest")
    verify.add_argument("--store", required=True)
    verify.add_argument("--json", action="store_true")
    verify.set_defaults(func=cmd_verify)

    coverage = sub.add_parser("coverage", help="day and row coverage per kind")
    coverage.add_argument("--store", required=True)
    coverage.add_argument("--kinds", default="fills,positions")
    coverage.add_argument("--json", action="store_true")
    coverage.set_defaults(func=cmd_coverage)

    benchmark = sub.add_parser(
        "benchmark",
        help="250-wallet x 200-day cross-sectional scan (synthetic store unless --store)",
    )
    benchmark.add_argument("--store", default=None, help="existing store root")
    benchmark.add_argument("--workdir", default=None, help="where to build the synthetic store")
    benchmark.add_argument("--wallets", type=int, default=250)
    benchmark.add_argument("--days", type=int, default=200)
    benchmark.add_argument("--rows-per-wallet-day", type=int, default=20)
    benchmark.add_argument("--repeats", type=int, default=3)
    benchmark.add_argument("--end-day", default=None)
    benchmark.add_argument("--keep", action="store_true", help="keep the synthetic store")
    benchmark.add_argument("--json", action="store_true")
    benchmark.set_defaults(func=cmd_benchmark)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except (RuntimeError, ValueError, FileNotFoundError) as exc:
        print(redact(f"facts {args.command} failed: {type(exc).__name__}: {exc}"), file=sys.stderr)
        return 2


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
