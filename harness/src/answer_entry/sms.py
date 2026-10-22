"""2FA SMS watcher: poll the Mac Messages database for a fresh code.

The school SSO sends one-time codes by SMS. Texts forwarded from the
iPhone land in ~/Library/Messages/chat.db within seconds, so an
unattended login can read the code straight from SQLite — no phone in
hand. Only SMS rows newer than the recorded marker are considered, so
stale codes never match.

Reads go through the sqlite3 module, falling back to the `sqlite3` CLI
(an Apple-signed binary, which macOS privacy controls treat better than
a venv Python). If both fail, the terminal app needs Full Disk Access:
System Settings -> Privacy & Security -> Full Disk Access.
"""
from __future__ import annotations

import re
import shutil
import sqlite3
import subprocess
import time
from pathlib import Path

CHAT_DB = Path.home() / "Library/Messages/chat.db"

# 6-digit runs, preferably near verification language. Senders vary
# (short codes rotate), so match content, not handles.
CODE_RE = re.compile(r"(\d{6})")
VERIFY_RE = re.compile(r"verif|code|okta|passcode|single-use|one-time",
                       re.IGNORECASE)


def _query(db_path: str | Path, sql: str,
           params: tuple = ()) -> list[tuple]:
    """One read-only query, module first, `sqlite3` CLI as fallback."""
    try:
        db = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        try:
            return db.execute(sql, params).fetchall()
        finally:
            db.close()
    except sqlite3.OperationalError:
        pass
    cli = shutil.which("sqlite3")
    if cli is None:
        raise _blocked()
    stmt = sql
    for p in params:  # our params are ints; no quoting games
        stmt = stmt.replace("?", str(int(p)), 1)
    try:
        out = subprocess.run([cli, "-separator", "\t", str(db_path), stmt],
                             capture_output=True, text=True, timeout=15)
    except (OSError, subprocess.TimeoutExpired):
        raise _blocked()
    if out.returncode != 0:
        raise _blocked()
    return [tuple(line.split("\t")) for line in out.stdout.splitlines()
            if line]


def _blocked() -> PermissionError:
    return PermissionError(
        "cannot read the Messages database: grant Full Disk Access to "
        "your terminal app (System Settings -> Privacy & Security -> "
        "Full Disk Access), restart the terminal, and retry")


def latest_rowid(db_path: str | Path = CHAT_DB) -> int:
    """Marker for 'now': poll only rows newer than this."""
    rows = _query(db_path, "select max(ROWID) from message")
    return int(rows[0][0]) if rows and rows[0][0] is not None else 0


def extract_code(text: str) -> str | None:
    """A 6-digit code from a verification-looking text, else None."""
    if not VERIFY_RE.search(text):
        return None
    m = CODE_RE.search(text)
    return m.group(1) if m else None


def wait_for_code(since_rowid: int, timeout_s: int = 150,
                  poll_s: float = 2.0,
                  db_path: str | Path = CHAT_DB) -> str:
    """Newest verification code in SMS rows after since_rowid.

    Raises TimeoutError when nothing arrives in time.
    """
    end = time.monotonic() + timeout_s
    while time.monotonic() < end:
        rows = _query(db_path,
                      "select text from message "
                      "where service='SMS' and ROWID > ? and is_from_me=0 "
                      "order by ROWID desc", (since_rowid,))
        for (text,) in rows:
            if text and (code := extract_code(text)):
                return code
        time.sleep(poll_s)
    raise TimeoutError(f"no SMS verification code in {timeout_s}s")
