"""SMS watcher tests against a scratch SQLite db (real chat.db untouched)."""
import shutil
import sqlite3
import time

import pytest

from answer_entry import sms


@pytest.fixture()
def db(tmp_path):
    path = tmp_path / "chat.db"
    conn = sqlite3.connect(path)
    conn.execute("create table message (text TEXT, service TEXT, "
                 "date INTEGER, is_from_me INTEGER, handle_id INTEGER)")
    conn.execute("insert into message values "
                 "('Your verification code is 111111', 'SMS', 1, 0, 7),"
                 "('dinner at 7?', 'iMessage', 2, 0, 8)")
    conn.commit()
    conn.close()
    return path


def add(db, text, service="SMS"):
    conn = sqlite3.connect(db)
    conn.execute("insert into message values (?, ?, 3, 0, 9)",
                 (text, service))
    conn.commit()
    conn.close()


def test_extract_code_shapes():
    assert sms.extract_code("Your MSU verification code is 482916") == "482916"
    assert sms.extract_code("Okta: 038211 is your one-time passcode") == "038211"
    assert sms.extract_code("call me at 5551234 tomorrow") is None  # 7 digits
    assert sms.extract_code("no digits here") is None
    assert sms.extract_code("game score 42 to 17, rematch?") is None


def test_wait_skips_old_and_nonsms(db):
    mark = sms.latest_rowid(db)
    add(db, "Your verification code is 222222", "iMessage")  # wrong service
    add(db, "Your verification code is 333333")  # fresh SMS
    assert sms.wait_for_code(mark, timeout_s=5, poll_s=0.1,
                             db_path=db) == "333333"


def test_wait_times_out(db):
    mark = sms.latest_rowid(db)
    t0 = time.monotonic()
    with pytest.raises(TimeoutError, match="no SMS verification code"):
        sms.wait_for_code(mark, timeout_s=1, poll_s=0.1, db_path=db)
    assert time.monotonic() - t0 < 5


@pytest.mark.skipif(shutil.which("sqlite3") is None, reason="no sqlite3 CLI")
def test_cli_fallback_when_module_blocked(db, monkeypatch):
    import sqlite3 as _sqlite3

    def blocked(*a, **k):
        raise _sqlite3.OperationalError("unable to open database file")

    monkeypatch.setattr(_sqlite3, "connect", blocked)
    import subprocess
    mark = sms.latest_rowid(db_path=db)
    subprocess.run(["sqlite3", str(db), "insert into message values "
                    "('Your verification code is 444444', 'SMS', 3, 0, 9)"],
                   check=True)
    assert sms.wait_for_code(mark, timeout_s=5, poll_s=0.1,
                             db_path=db) == "444444"


def test_clear_error_when_fully_blocked(db, monkeypatch):
    import sqlite3 as _sqlite3

    def blocked(*a, **k):
        raise _sqlite3.OperationalError("unable to open database file")

    monkeypatch.setattr(_sqlite3, "connect", blocked)
    monkeypatch.setattr(sms.shutil, "which", lambda _: None)
    with pytest.raises(PermissionError, match="Full Disk Access"):
        sms.latest_rowid(db_path=db)
