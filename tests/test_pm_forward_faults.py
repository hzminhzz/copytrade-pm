"""FP-02 isolated real-process SQLite crash and bounded-disk fault tests.

These tests kill only subprocesses they spawn; they never touch services.
"""

from pathlib import Path
import signal
import subprocess
import sys

from copytrade_pm.pm_forward_journal import PaperJournal
from test_pm_forward_journal import LATER, manifest


def _kill_child(script: str, db_path: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-c", script, str(db_path)],
        check=False,
        capture_output=True,
        text=True,
        timeout=20,
    )


def test_sigkill_before_commit_rolls_back_entire_sqlite_transaction(tmp_path) -> None:
    journal = PaperJournal(tmp_path / "paper")
    journal.register(manifest("run_1", "acct_1"))
    child = _kill_child(
        """
import os, signal, sqlite3, sys
db = sqlite3.connect(sys.argv[1], isolation_level=None, timeout=1)
db.execute("BEGIN IMMEDIATE")
db.execute("UPDATE runs SET cursor=999 WHERE run_id='run_1'")
os.kill(os.getpid(), signal.SIGKILL)
""",
        journal.path,
    )
    assert child.returncode == -signal.SIGKILL
    recovered = PaperJournal(journal.root).restore("run_1")
    assert recovered["cursor"] == 0
    assert recovered["account"]["cash"] == "10000"
    assert recovered["source_cursors"] == {}
    journal.append("run_1", "after_crash", {"kind": "HALT", "event_at": LATER})
    assert journal.restore("run_1")["cursor"] == 1


def test_sigkill_after_commit_reopens_exactly_once(tmp_path) -> None:
    journal = PaperJournal(tmp_path / "paper")
    journal.register(manifest("run_1", "acct_1"))
    child = _kill_child(
        """
import os, signal, sys
from pathlib import Path
from copytrade_pm.pm_forward_journal import PaperJournal
j = PaperJournal(Path(sys.argv[1]).parent)
j.append("run_1", "committed", {"kind":"HALT", "event_at":"2026-11-04T04:01:00+00:00"})
os.kill(os.getpid(), signal.SIGKILL)
""",
        journal.path,
    )
    assert child.returncode == -signal.SIGKILL
    recovered = PaperJournal(journal.root)
    state = recovered.restore("run_1")
    assert state["cursor"] == 1
    assert state["account"]["risk"] == "HALT"
    assert recovered.append("run_1", "committed", {"kind": "HALT", "event_at": LATER}) == state


def test_os_file_size_limit_rolls_back_without_account_mutation(tmp_path) -> None:
    journal = PaperJournal(tmp_path / "paper")
    journal.register(manifest("run_1", "acct_1"))
    # Only the child is restricted. This is a real OS file-size fault on the
    # SQLite WAL path, not a raised mock exception.
    child = _kill_child(
        """
import os, resource, signal, sqlite3, sys
from pathlib import Path
from copytrade_pm.pm_forward_journal import PaperJournal
signal.signal(signal.SIGXFSZ, signal.SIG_IGN)
resource.setrlimit(resource.RLIMIT_FSIZE, (8192, 8192))
try:
    PaperJournal(Path(sys.argv[1]).parent).append(
        "run_1", "large_halt",
        {"kind":"HALT","event_at":"2026-11-04T04:01:00+00:00","reason":"X"*200000},
    )
except (ValueError, sqlite3.OperationalError, OSError):
    sys.exit(0)
sys.exit(9)
""",
        journal.path,
    )
    assert child.returncode == 0, child.stderr
    assert journal.restore("run_1")["cursor"] == 0
    journal.append("run_1", "good_halt", {"kind": "HALT", "event_at": LATER})
    assert journal.restore("run_1")["cursor"] == 1
