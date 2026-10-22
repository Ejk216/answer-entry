"""Okta login helpers: the identifier must never carry whitespace (MSU-1)."""
import pathlib

import pytest
from playwright.sync_api import sync_playwright

from answer_entry import okta
from answer_entry.cli import known_email
from answer_entry.okta import _fill

FIX = pathlib.Path(__file__).parent / "fixtures" / "okta_fill_fake.html"


@pytest.fixture(scope="module")
def browser():
    pw = sync_playwright().start()
    b = pw.chromium.launch()
    yield b
    b.close()
    pw.stop()


def test_clean_email_collapses_interior_whitespace():
    assert okta.clean_email("kra\nme197@msu.edu") == "krame197@msu.edu"
    assert okta.clean_email("  kra\t me197@msu.edu\n") == "krame197@msu.edu"
    assert okta.clean_email("krame197@msu.edu") == "krame197@msu.edu"


def test_clean_email_blank_collapses_to_empty():
    assert okta.clean_email("  \n\t ") == ""


def test_known_email_heals_stored_newline(tmp_path, monkeypatch):
    monkeypatch.setattr(okta, "EMAIL_FILE", tmp_path / "okta_email")
    okta.EMAIL_FILE.write_text("kra\nme197@msu.edu")
    assert known_email(None) == "krame197@msu.edu"
    assert okta.EMAIL_FILE.read_text() == "krame197@msu.edu"


def test_known_email_sanitizes_explicit(tmp_path, monkeypatch):
    monkeypatch.setattr(okta, "EMAIL_FILE", tmp_path / "okta_email")
    assert known_email("kra\nme197@msu.edu") == "krame197@msu.edu"
    assert okta.EMAIL_FILE.read_text() == "krame197@msu.edu"


def test_human_fill_clears_stale_content(browser):
    page = browser.new_page()
    page.goto(FIX.as_uri())
    _fill(page, ['input[name="credentials.passcode"]'], "s3cret-pw",
          "password", human=True)
    assert page.locator("#pw").input_value() == "s3cret-pw"
    page.close()


def test_human_fill_refuses_mangled_landing(browser):
    page = browser.new_page()
    page.goto(FIX.as_uri())
    with pytest.raises(ValueError, match="not submitting"):
        _fill(page, ["#greedy"], "s3cret-pw", "password", human=True)
    page.close()


def test_plain_fill_replaces_content(browser):
    page = browser.new_page()
    page.goto(FIX.as_uri())
    _fill(page, ['input[name="credentials.passcode"]'], "a@b.c",
          "identifier")
    assert page.locator("#pw").input_value() == "a@b.c"
    page.close()
