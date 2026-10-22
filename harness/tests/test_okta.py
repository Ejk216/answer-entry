"""Okta login helpers: the identifier must never carry whitespace (MSU-1)."""
from answer_entry import okta
from answer_entry.cli import known_email


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
