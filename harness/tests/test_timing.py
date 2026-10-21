"""Timing tracker unit tests."""
import time

from answer_entry.timing import Tracker


def test_tracker_accumulates_and_reports():
    t = Tracker()
    with t.phase("a"):
        time.sleep(0.01)
    with t.phase("a"):
        pass
    with t.phase("b"):
        pass
    report = t.report()
    assert set(report["phases"]) == {"a", "b"}
    assert report["phases"]["a"] >= 0.01
    assert report["total_s"] >= report["phases"]["a"]
    summary = t.summary()
    assert "a=" in summary and "b=" in summary and "total=" in summary
