"""Parser arguments for official wallet-health capture."""

import argparse
from pathlib import Path

MAX_WALLETS = 512
DEFAULT_WEIGHT_PER_MIN = 240
HISTORY_DAYS = 90
DEFAULT_DATA_ROOT = Path("~/.local/share/copytrade")


def add_arguments(parser: argparse.ArgumentParser) -> argparse.ArgumentParser:
    parser.add_argument(
        "--roster-db",
        type=Path,
        default=DEFAULT_DATA_ROOT / "roster.sqlite",
        help="read-only roster.sqlite (active + draining + scored candidates)",
    )
    parser.add_argument(
        "--store", type=Path, default=DEFAULT_DATA_ROOT / "facts", help="fact store root"
    )
    parser.add_argument("--generation", type=Path, help="immutable raw archive generation dir")
    parser.add_argument("--no-raw-archive", action="store_true", help="write only normalised facts")
    parser.add_argument("--facts-root", type=Path, help="optional store for additional wallets")
    parser.add_argument("--publish-dir", type=Path, help="optional aggregate-only publish dir")
    parser.add_argument("--max-wallets", type=int, default=MAX_WALLETS)
    parser.add_argument("--deep-wallets", type=int, default=0)
    parser.add_argument("--weight-per-minute", type=int, default=DEFAULT_WEIGHT_PER_MIN)
    parser.add_argument("--history-days", type=int, default=HISTORY_DAYS)
    parser.add_argument(
        "--no-scored-candidates",
        action="store_true",
        help="observe only active and draining wallets",
    )
    parser.add_argument("--dry-run", action="store_true", help="preview a capture")
    return parser
