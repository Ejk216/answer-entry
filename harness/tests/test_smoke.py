"""Smoke aggregator: pass/fail shaping, no live calls."""
from answer_entry.cli import run_smoke


def test_all_pass():
    out = run_smoke([("a", lambda: (True, "fine")),
                     ("b", lambda: (True, "fine"))])
    assert [(r["name"], r["ok"]) for r in out] == [("a", True), ("b", True)]


def test_failure_and_crash():
    def boom():
        raise RuntimeError("kaput")

    out = run_smoke([("a", lambda: (False, "expired (sso)")),
                     ("b", boom)])
    assert [r["ok"] for r in out] == [False, False]
    assert out[0]["detail"] == "expired (sso)"
    assert "RuntimeError: kaput" in out[1]["detail"]
