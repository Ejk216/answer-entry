"""Course sets parsing + due scan (stub engine, no network)."""
from datetime import datetime
from pathlib import Path

from answer_entry import course

FIX = Path(__file__).parent / "fixtures"
SETS_HTML = (FIX / "ww_sets.html").read_text()
SET_HTML = (FIX / "mock_set.html").read_text()


def test_parse_sets_page():
    sets = course.parse_sets_page(SETS_HTML, "http://x/webwork2/c/")
    assert [(s["name"], s["status"]) for s in sets] == [
        ("HW01", "open"), ("EC01", "open"), ("OLD", "closed")]
    assert sets[0]["url"] == "http://x/webwork2/c/HW01?effectiveUser=s"
    assert sets[0]["due"] == datetime(2026, 11, 4, 23, 59, 0)
    assert sets[2]["due"] is None


class StubEngine:
    def __init__(self, pages):
        self.pages = pages

    def get(self, url):
        return self.pages[url]


def test_due_scan_skips_closed_and_scores_open():
    engine = StubEngine({
        "http://x/webwork2/c/": SETS_HTML,
        "http://x/webwork2/c/HW01?effectiveUser=s": SET_HTML.replace(
            "/course/set", "http://x/webwork2/c/HW01"),
        "http://x/webwork2/c/EC01?effectiveUser=s": "<html></html>",
    })
    report = course.due_scan(engine, "http://x/webwork2/c/")
    assert [s["name"] for s in report] == ["HW01", "EC01"]
    hw = report[0]
    assert (hw["total"], hw["at_100"], hw["done"]) == (3, 1, False)
    assert report[1]["total"] == 0  # unscorable page, not a crash
