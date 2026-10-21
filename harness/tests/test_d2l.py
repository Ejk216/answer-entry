"""D2L driver tests against a shadow-DOM fixture (headless Chromium).

The fixture mirrors the validated procedure: quiz radios inside a content
frame's shadow roots, triplicated labels, a footer counter that stalls
under rapid clicks until Save All, and a Submit button the driver must
never touch.
"""
import pathlib

import pytest
from playwright.sync_api import sync_playwright

from answer_entry import d2l
from answer_entry.d2l import (
    click_radio,
    click_save_all,
    dedupe_label,
    diff_checked,
    dump_quiz,
    enter_quiz,
    find_quiz_frame,
    footer_counter,
    resolve_plan,
)
from answer_entry.model import Answer, AnswerFile, ProblemAnswers

FIX = pathlib.Path(__file__).parent / "fixtures"
QUIZ_URL = (FIX / "d2l_quiz_fake.html").as_uri()


@pytest.fixture(scope="module")
def browser():
    pw = sync_playwright().start()
    b = pw.chromium.launch()
    yield b
    b.close()
    pw.stop()


@pytest.fixture()
def page(browser):
    p = browser.new_page()
    yield p
    p.close()


def quiz_frame(page):
    page.goto(QUIZ_URL)
    frame = find_quiz_frame(page)
    assert frame is not None
    return frame


def test_dedupe_label():
    assert dedupe_label("312531253125") == "3125"
    assert dedupe_label("abab") == "ab"
    assert dedupe_label("abc") == "abc"
    assert dedupe_label("") == ""
    # whitespace-sensitive options survive verbatim
    assert dedupe_label("  7  7  7") == "  7"
    assert dedupe_label("7") == "7"


def test_find_frame_skips_chrome_and_decoy(page):
    frame = quiz_frame(page)
    assert frame.url.endswith("d2l_quiz_frame.html")


def test_dump_whole_quiz(page):
    dump = dump_quiz(quiz_frame(page))
    assert [q["group"] for q in dump["questions"]] == ["q1", "q2", "q3"]
    assert [q["n"] for q in dump["questions"]] == [1, 2, 3]
    assert "pick green" in dump["questions"][0]["stem"]
    assert [o["label"] for o in dump["questions"][0]["options"]] == [
        "red", "green", "blue"]  # triplication collapsed
    assert [o["checked"] for o in dump["questions"][0]["options"]] == [
        True, False, False]  # pre-answered pattern
    assert [o["label"] for o in dump["questions"][2]["options"]] == [
        "  7", "7  ", "7"]  # spacing intact
    assert dump["answered_pattern"] == [True, False, False]
    assert dump["footer"] == {"saved": 1, "total": 3,
                              "raw": "1 of 3 questions saved"}


def answers_file(*values):
    return AnswerFile(
        set_url=QUIZ_URL,
        problems=[ProblemAnswers(n=i + 1, url=None, answers=[Answer(value=v)])
                  for i, v in enumerate(values)])


def test_enter_dry_run_plans_without_clicking(page):
    page.goto(QUIZ_URL)
    report = enter_quiz(page, QUIZ_URL,
                        answers_file("green", "index:1", "7  "),
                        dry_run=True)
    assert report["status"] == "dry_run_ok", report
    assert [(p["n"], p["index"]) for p in report["plan"]] == [
        (1, 1), (2, 1), (3, 1)]
    assert report["answered_pattern"] == [True, False, False]
    fresh = dump_quiz(find_quiz_frame(page))
    assert fresh["answered_pattern"] == [True, False, False]  # untouched
    assert fresh["footer"]["saved"] == 1


def test_enter_live_canary_bulk_save_verify(page):
    page.goto(QUIZ_URL)
    report = enter_quiz(page, QUIZ_URL,
                        answers_file("green", "index:1", "7  "))
    assert report["status"] == "ok", report
    assert report["footer"] == {"saved": 3, "total": 3,
                                "raw": "3 of 3 questions saved"}
    assert "not submitted" in report["detail"]
    assert find_quiz_frame(page).evaluate("!!window.__submitted") is False
    final = dump_quiz(find_quiz_frame(page))
    assert [next(i for i, o in enumerate(q["options"]) if o["checked"])
            for q in final["questions"]] == [1, 1, 1]


def test_bad_label_aborts_before_first_click(page):
    page.goto(QUIZ_URL)
    report = enter_quiz(page, QUIZ_URL, answers_file("green", "gren"))
    assert report["status"] == "fill_error", report
    assert "gren" in report["detail"] and "42" in report["detail"]
    fresh = dump_quiz(find_quiz_frame(page))
    # Q1's valid click never landed either: plan-all-then-click.
    assert [o["checked"] for o in fresh["questions"][0]["options"]] == [
        True, False, False]


def test_rapid_clicks_stall_until_save_all(page):
    frame = quiz_frame(page)
    assert footer_counter(page, frame)["saved"] == 1
    assert click_radio(frame, "q2", 0)["checked"] is True
    assert click_radio(frame, "q3", 0)["checked"] is True
    page.wait_for_timeout(100)  # inside the autosave window: stalled
    assert footer_counter(page, frame)["saved"] == 1
    assert click_save_all(page, frame) is True  # exact-text match
    page.wait_for_timeout(200)
    assert footer_counter(page, frame) == {"saved": 3, "total": 3,
                                           "raw": "3 of 3 questions saved"}
    assert frame.evaluate("!!window.__submitted") is False


def test_diff_checked():
    plan = [{"n": 1, "index": 1}, {"n": 2, "index": 0}]
    dump = {"questions": [
        {"n": 1, "options": [{"checked": False}, {"checked": True}]},
        {"n": 2, "options": [{"checked": True}, {"checked": False}]},
    ]}
    assert diff_checked(plan, dump) == []
    dump["questions"][1]["options"][0]["checked"] = False
    assert diff_checked(plan, dump) == [{"n": 2, "expected": 0,
                                        "checked": None}]


def test_resolve_plan_rejects():
    dump = {"questions": [{"n": 1, "group": "q1",
                           "options": [{"label": "a"}]}]}
    base = {"url": None}
    with pytest.raises(ValueError, match="quiz has 1"):
        resolve_plan(dump, AnswerFile(set_url=None, problems=[
            ProblemAnswers(n=2, answers=[Answer(value="a")], **base)]))
    with pytest.raises(ValueError, match="exactly 1 answer"):
        resolve_plan(dump, AnswerFile(set_url=None, problems=[
            ProblemAnswers(n=1, answers=[Answer(value="a")] * 2, **base)]))
    with pytest.raises(ValueError, match="are radio"):
        resolve_plan(dump, AnswerFile(set_url=None, problems=[
            ProblemAnswers(n=1, answers=[Answer(value="a", type="text")],
                           **base)]))


def test_enter_without_quiz_frame(page):
    report = enter_quiz(page, "about:blank",
                        answers_file("green"))
    assert report["status"] == "no_quiz_frame", report
