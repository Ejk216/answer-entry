"""SMS watcher tests against a scratch SQLite db (real chat.db untouched)."""
import sqlite3
import time

import pytest

from answer_entry import sms


@pytest.fixture()
def db(tmp_path):
    path = tmp_path / "chat.db"
    conn = sqlite3.connect(path)
    conn.execute("create table message (text TEXT, service TEXT, "
                 "date INTEGER, is_from_me INTEGER)")
    conn.execute("insert into message values "
                 "('Your verification code is 111111', 'SMS', 1, 0),"
                 "('dinner at 7?', 'iMessage', 2, 0)")
    conn.commit()
    conn.close()
    return path


def add(db, text, service="SMS"):
    conn = sqlite3.connect(db)
    conn.execute("insert into message values (?, ?, 3, 0)", (text, service))
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
