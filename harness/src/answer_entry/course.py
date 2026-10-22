"""Course sets list: what's open, what's due, what's done.

The WeBWorK course page renders every set as a list item carrying its
status plus a due line; per-set completion comes from the set page
(`parse_set_status`). Read-only throughout — the watcher's eyes.
"""
from __future__ import annotations

import re
import urllib.parse
from datetime import datetime
from html.parser import HTMLParser
from typing import Any

from .http_engine import parse_set_status

DUE_RE = re.compile(
    r"Due\s+([A-Z][a-z]+\s+\d{1,2},\s+\d{4},\s+\d{1,2}:\d{2}:\d{2}\s+[AP]M)")


class _SetsParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.sets: list[dict[str, Any]] = []
        self._item: dict[str, Any] | None = None
        self._in_link = False
        self._in_due = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        a = {k: v or "" for k, v in attrs}
        if tag == "li" and "data-set-status" in a:
            self._item = {"status": a["data-set-status"], "name": "",
                          "href": "", "due_raw": ""}
        elif tag == "a" and self._item is not None and "set-id-tooltip" in a.get("class", ""):
            self._item["href"] = a.get("href", "")
            self._in_link = True
        elif tag == "div" and self._item is not None and "font-sm" in a.get("class", ""):
            if not self._item["due_raw"]:
                self._in_due = True

    def handle_endtag(self, tag: str) -> None:
        if tag == "li" and self._item is not None:
            if self._item["name"]:
                self.sets.append(self._item)
            self._item = None
        elif tag == "a":
            self._in_link = False
        elif tag == "div":
            self._in_due = False

    def handle_data(self, data: str) -> None:
        if self._item is None:
            return
        s = data.strip()
        if not s:
            return
        if self._in_link:
            self._item["name"] += s
        elif self._in_due:
            self._item["due_raw"] += s + " "


def parse_due(due_raw: str) -> datetime | None:
    """'Due November 4, 2026, 11:59:00 PM EST' -> naive school-local time."""
    m = DUE_RE.search(due_raw.replace("\u202f", " "))
    if not m:
        return None
    try:
        return datetime.strptime(m.group(1), "%B %d, %Y, %I:%M:%S %p")
    except ValueError:
        return None


def parse_sets_page(html: str, course_url: str) -> list[dict[str, Any]]:
    """Every set on the course page with status + due info."""
    parser = _SetsParser()
    parser.feed(html)
    out = []
    for s in parser.sets:
        due_raw = s["due_raw"].strip()
        out.append({"name": s["name"],
                    "url": urllib.parse.urljoin(course_url, s["href"]),
                    "status": s["status"], "due_raw": due_raw,
                    "due": parse_due(due_raw)})
    return out


def due_scan(engine: Any, course_url: str) -> list[dict[str, Any]]:
    """Open sets with completion: serial, polite, read-only."""
    report = []
    for s in parse_sets_page(engine.get(course_url), course_url):
        if s["status"] != "open":
            continue
        try:
            rows = parse_set_status(engine.get(s["url"]), s["url"])
        except ValueError:
            rows = []
        full = sum(1 for r in rows if r["percent"] == 100)
        s["total"] = len(rows)
        s["at_100"] = full
        s["done"] = bool(rows) and full == len(rows)
        report.append(s)
    return report
