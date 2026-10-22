"""2FA SMS watcher: poll the Mac Messages database for a fresh code.

The school SSO sends one-time codes by SMS. Texts forwarded from the
iPhone land in ~/Library/Messages/chat.db within seconds, so an
unattended login can read the code straight from SQLite — no phone in
hand. Only SMS rows newer than the recorded marker are considered, so
stale codes never match.
"""
from __future__ import annotations

import re
import sqlite3
import time
from pathlib import Path

CHAT_DB = Path.home() / "Library/Messages/chat.db"

# 6-digit runs, preferably near verification language. Senders vary
# (short codes rotate), so match content, not handles.
CODE_RE = re.compile(r"(\d{6})")
VERIFY_RE = re.compile(r"verif|code|okta|passcode|single-use|one-time",
                       re.IGNORECASE)


def latest_rowid(db_path: str | Path = CHAT_DB) -> int:
    """Marker for 'now': poll only rows newer than this."""
    db = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        row = db.execute("select max(ROWID) from message").fetchone()
        return row[0] or 0
    finally:
        db.close()


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
        db = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        try:
            rows = db.execute(
                "select text from message "
                "where service='SMS' and ROWID > ? and is_from_me=0 "
                "order by ROWID desc", (since_rowid,)).fetchall()
        finally:
            db.close()
        for (text,) in rows:
            if text and (code := extract_code(text)):
                return code
        time.sleep(poll_s)
    raise TimeoutError(f"no SMS verification code in {timeout_s}s")
