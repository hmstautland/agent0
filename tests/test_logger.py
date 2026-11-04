import json
from datetime import datetime, timedelta

import pytest

import core.logger as logger


@pytest.fixture
def log_file(tmp_path, monkeypatch):
    path = tmp_path / "logs.txt"
    monkeypatch.setattr(logger, "LOG_FILE", str(path))
    return path


def entry(days_ago, n=0):
    return json.dumps({"timestamp": (datetime.now() - timedelta(days=days_ago)).isoformat(), "n": n}) + "\n"


def numbers(path):
    return [json.loads(line).get("n") for line in path.read_text().splitlines()]


def test_prune_drops_entries_older_than_the_cutoff(log_file):
    log_file.write_text(entry(30, 1) + entry(20, 2) + "not json\n" + entry(1, 3))

    assert logger.prune_logs(keep_days=14) == 2
    assert log_file.read_text().splitlines()[0] == "not json"
    assert json.loads(log_file.read_text().splitlines()[1])["n"] == 3


def test_prune_drops_the_oldest_until_the_log_fits(log_file):
    log_file.write_text("".join(entry(0, n) for n in range(10)))
    one = len(entry(0, 0).encode())

    logger.prune_logs(keep_days=14, max_bytes=one * 3)

    assert numbers(log_file) == [7, 8, 9]


def test_the_log_prunes_itself_when_it_passes_the_limit(log_file, monkeypatch):
    log_file.write_text(entry(30, 1) + entry(0, 2))
    # Room for two entries, so after pruning (to half) only the newest fits
    monkeypatch.setattr(logger, "MAX_LOG_BYTES", 2 * len(entry(0, 3).encode()) + 10)

    logger.log_event({"n": 3})

    assert numbers(log_file) == [3]  # old by age; then oldest until under half the limit


def test_prune_without_a_log_does_nothing(log_file):
    assert logger.prune_logs() == 0
    assert not log_file.exists()


def test_a_write_failure_does_not_break_the_request_being_logged(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(logger, "LOG_FILE", str(tmp_path))  # a directory: opening it for append fails

    logger.log_event({"type": "x"})

    assert "could not write" in capsys.readouterr().err


def test_a_failed_prune_does_not_break_the_request_being_logged(log_file, monkeypatch, capsys):
    monkeypatch.setattr(logger, "MAX_LOG_BYTES", 10)
    monkeypatch.setattr(logger, "_prune", lambda *a: (_ for _ in ()).throw(OSError("disk full")))

    logger.log_event({"type": "x"})

    assert "disk full" in capsys.readouterr().err and log_file.exists()


CHILD_SCRIPT = """
import sys
import core.logger as logger

logger.LOG_FILE = sys.argv[1]
for i in range(int(sys.argv[2])):
    logger.log_event({"who": sys.argv[3], "i": i})
"""


def test_lines_logged_by_other_processes_survive_a_prune_running_alongside(log_file):
    import os
    import subprocess
    import sys
    from pathlib import Path

    root = str(Path(logger.__file__).resolve().parent.parent)
    env = {**os.environ, "PYTHONPATH": root}
    log_file.write_text("")
    kids = [
        subprocess.Popen([sys.executable, "-c", CHILD_SCRIPT, str(log_file), "300", name], env=env)
        for name in ("a", "b")
    ]
    # The rewrite in a third process of the same file: drops nothing, but replaces the whole file
    while any(kid.poll() is None for kid in kids):
        logger.prune_logs(keep_days=14, max_bytes=10**9)
    for kid in kids:
        kid.wait()

    seen = [json.loads(line) for line in log_file.read_text().splitlines() if line.strip()]
    assert sorted((e["who"], e["i"]) for e in seen) == sorted((who, i) for who in "ab" for i in range(300))


def test_logging_still_happens_when_the_lock_cannot_be_taken(log_file, monkeypatch, capsys):
    def no_lock(handle):
        raise OSError("locking unavailable")

    monkeypatch.setattr(logger, "_lock_file", no_lock)

    logger.log_event({"type": "x"})

    assert "could not lock" in capsys.readouterr().err
    assert json.loads(log_file.read_text())["type"] == "x"
