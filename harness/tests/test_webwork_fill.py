"""Browser tests against local fixtures (headless Chromium, no network).

These validate the fill / read-back / submit / score logic. Real-page
selectors (problem text, set enumeration) still need a live WeBWorK page.
"""
import pathlib

import pytest
from playwright.sync_api import sync_playwright

from answer_entry import webwork
from answer_entry.model import Answer, ProblemAnswers

FIX = pathlib.Path(__file__).parent / "fixtures"


@pytest.fixture(scope="module")
def browser():
    pw = sync_playwright().start()
    b = pw.chromium.launch()
    yield b
    b.close()
    pw.stop()


def test_mathquill_fill_and_readback(browser):
    page = browser.new_page()
    page.goto((FIX / "mathquill_fake.html").as_uri())
    inv = webwork.inventory_widgets(page)
    assert [w["kind"] for w in inv] == ["mathquill"] * 3

    r0 = webwork.fill_mathquill(page, 0, r"-\frac{1}{2},3")
    assert r0["ok"] and r0["readback"] == r"-\frac{1}{2},3"
    r1 = webwork.fill_mathquill(page, 1, "42")
    assert r1["ok"] and webwork.values_match("42", r1["readback"])
    # f2 mangles input; the mismatch must be detectable, never papered over
    r2 = webwork.fill_mathquill(page, 2, "abc")
    assert r2["ok"] and r2["readback"] == "ABC"
    assert not webwork.values_match("abc", r2["readback"])
    page.close()


def test_native_widgets_fill_submit_score(browser):
    page = browser.new_page()
    page.goto((FIX / "widgets.html").as_uri())
    inv = webwork.inventory_widgets(page)
    assert [w["kind"] for w in inv] == ["select", "radio", "checkbox"]

    assert webwork.fill_select(page, 0, "42", inv[0]["options"]) == "42"
    assert webwork.fill_radio(page, "color", "green", inv[1]["options"]) == "green"
    assert webwork.fill_checkbox(page, "opts", ["A", "C"], inv[2]["options"]) == ["A", "C"]

    assert webwork.read_back(page, inv) == ["v42", "green", ["A", "C"]]
    assert webwork.click_preview(page) is True  # fixture has a Preview button
    webwork.click_submit(page)
    score = webwork.read_score(page)
    assert score["percent"] == 100 and score["all_correct"] is True
    page.close()


def test_enter_problem_end_to_end(browser):
    page = browser.new_page()
    url = (FIX / "widgets.html").as_uri()
    problem = ProblemAnswers(n=1, url=url, answers=[
        Answer(value="42", type="select"),
        Answer(value="green", type="radio"),
        Answer(value=["A", "C"], type="checkbox"),
    ])
    dry = webwork.enter_problem(page, problem, url, dry_run=True)
    assert dry["status"] == "dry_run_ok", dry
    live = webwork.enter_problem(page, problem, url, dry_run=False)
    assert live["status"] == "ok", live
    assert live["score"]["percent"] == 100
    page.close()


def test_enter_refuses_type_mismatch(browser):
    page = browser.new_page()
    url = (FIX / "widgets.html").as_uri()
    problem = ProblemAnswers(n=1, url=url, answers=[
        Answer(value="42", type="radio"),  # actually a select
        Answer(value="green", type="radio"),
        Answer(value=["A", "C"], type="checkbox"),
    ])
    report = webwork.enter_problem(page, problem, url, dry_run=False)
    assert report["status"] == "type_mismatch", report
    # and nothing was submitted
    assert webwork.parse_score_text(page.locator("body").inner_text())["percent"] is None
    page.close()


def test_enter_refuses_answer_shortage(browser):
    page = browser.new_page()
    url = (FIX / "widgets.html").as_uri()
    problem = ProblemAnswers(n=1, url=url, answers=[Answer(value="42", type="select")])
    report = webwork.enter_problem(page, problem, url, dry_run=False)
    assert report["status"] == "answer_shortage", report
    page.close()


def test_parse_score_text():
    assert webwork.parse_score_text("You received a score of 85%.")["percent"] == 85
    r = webwork.parse_score_text("3 of the questions remain unanswered.")
    assert r["unanswered"] == 3 and r["percent"] is None
    assert webwork.parse_score_text("nothing here")["percent"] is None
