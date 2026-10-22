"""Smoke aggregator: pass/fail shaping, no live calls."""
from answer_entry.cli import run_smoke


def test_all_pass():
    out = run_smoke([("a", lambda: (True, "fine")),
                     ("b", lambda: (True, "fine"))])
    assert [(r["name"], r["ok"]) for r in out] == [("a", True), ("b", True)]


def test_sso_spacing(tmp_path):
    from answer_entry.cli import sso_clear
    stamp = tmp_path / "sso"
    assert sso_clear(stamp_path=stamp) is None
    msg = sso_clear(stamp_path=stamp)
    assert msg is not None and "wait" in msg
    assert sso_clear(True, stamp_path=stamp) is None
    stamp.write_text("0")
    assert sso_clear(stamp_path=stamp) is None


def test_failure_and_crash():
    def boom():
        raise RuntimeError("kaput")

    out = run_smoke([("a", lambda: (False, "expired (sso)")),
                     ("b", boom)])
    assert [r["ok"] for r in out] == [False, False]
    assert out[0]["detail"] == "expired (sso)"
    assert "RuntimeError: kaput" in out[1]["detail"]
