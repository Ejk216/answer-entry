"""Top Hat HTTP driver: enumerate, fetch, answer, verify. No browser clicks.

Reverse-engineered Oct 2026 from live app traffic (`harness recon`):
- Auth: ES256 JWT in localStorage (`jwt/accessToken`), sent as
  `Authorization: Bearer`, plus a `Course-Id` header.
- Enumerate: `/api/v1/tree_data/` (folders + module_items, numeric ids).
- Bridge numeric id -> content id: `/api/content/course/<id>/id_mappings/`.
- Read: `/api/content-delivery/course/<id>/content/<cid>/` -> document
  tree (paragraphs, multiple_choice_question/option nodes).
- Answer: POST `/api/question/v3/review/questions/<cid>/responses/`
  `{"data": {"1": [<option-id>]}}` -> graded_response with per-part
  status plus points. The response IS the grade; no separate check.
- Status: `/api/v2/answered_items/<course>/` (answered numeric ids).

Scope: single-part multiple-choice only. Anything else raises instead of
guessing — new question types get added deliberately, one at a time.
"""
from __future__ import annotations

import base64
import json
import re
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from .browser import PROFILE_DIR

TOKEN_FILE = PROFILE_DIR / "tophat_tokens.json"
APP_BASE = "https://app.tophat.com"
PUBLIC_CODE_RE = re.compile(r"/e/(\d+)/")


def token_expiry(jwt: str) -> float:
    """exp claim of a JWT (0 if unreadable — treated as expired)."""
    try:
        payload = jwt.split(".")[1]
        payload += "=" * (-len(payload) % 4)
        return float(json.loads(base64.urlsafe_b64decode(payload))["exp"])
    except Exception:  # noqa: BLE001 — unreadable token must refresh, not crash
        return 0.0


def read_tokens_from_profile() -> dict[str, str]:
    """Fresh JWTs from the persistent browser profile's localStorage.

    The app refreshes its own access token when it runs, so opening the
    app headless and reading localStorage back is the refresh mechanism —
    no refresh-endpoint reverse engineering needed.
    """
    from .browser import HarnessBrowser
    with HarnessBrowser(headless=True) as b:
        page = b.new_page()
        page.goto(APP_BASE + "/")
        page.wait_for_timeout(4000)
        tokens = page.evaluate(
            "() => ({access: window.localStorage.getItem('jwt/accessToken'),"
            " refresh: window.localStorage.getItem('jwt/refreshToken')})")
    if not tokens.get("access"):
        raise ValueError("no Top Hat JWT in the browser profile; "
                         "run `harness th-auth` and sign in first")
    TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)
    TOKEN_FILE.write_text(json.dumps(tokens))
    return tokens


def file_token_provider() -> Callable[[], str]:
    """Bearer tokens from disk, refreshed via the profile when expiring."""
    def provide() -> str:
        try:
            tokens = json.loads(TOKEN_FILE.read_text())
        except (FileNotFoundError, ValueError):
            tokens = {}
        if (not tokens.get("access")
                or token_expiry(tokens["access"]) < time.time() + 120):
            tokens = read_tokens_from_profile()
        return tokens["access"]
    return provide


@dataclass
class Question:
    cid: str
    title: str
    stem: str
    part: str
    options: list[dict[str, Any]]  # [{id: int, label: str}]
    can_submit: bool
    profile: dict[str, Any]


def _text_of(node: dict[str, Any]) -> str:
    """Concatenated text values under a document node."""
    if node.get("type") == "text":
        return node.get("properties", {}).get("value", "")
    return "".join(_text_of(c) for c in
                   node.get("properties", {}).get("children", []))


def parse_content(cid: str, body: dict[str, Any]) -> Question:
    """Document tree -> stem + options. Single-part MC only."""
    try:
        item = body["learning_material_data"]["data"]["item_details"][
            "generic_item_data"]
    except KeyError as e:
        raise ValueError(f"{cid}: not a readable question body "
                         f"(missing {e})")
    config = item.get("configuration", {})
    if len(config) != 1:
        raise ValueError(f"{cid}: want 1 part, have {sorted(config)}")
    part, cfg = next(iter(config.items()))
    if cfg.get("type") != "multiple_choice_question":
        raise ValueError(f"{cid}: unsupported question type "
                         f"{cfg.get('type')!r}")
    stem_bits: list[str] = []
    options: list[dict[str, Any]] = []
    for child in item.get("document", {}).get("children", []):
        if child.get("type") == "paragraph":
            stem_bits.append(_text_of(child).strip())
        elif child.get("type") == "multiple_choice_question":
            for opt in child.get("properties", {}).get("children", []):
                if opt.get("type") != "multiple_choice_option":
                    continue
                label = _text_of(opt).strip()
                options.append({"id": opt["properties"]["id"],
                                "label": label})
    if not options:
        raise ValueError(f"{cid}: no multiple-choice options found")
    details = body["learning_material_data"]["data"]["item_details"]
    return Question(cid=cid, title=details.get("title", ""),
                    stem="\n".join(b for b in stem_bits if b), part=part,
                    options=options,
                    can_submit=bool(cfg.get("can_submit_question", True)),
                    profile=details.get("profile", {}))


def folders(tree: dict[str, Any]) -> dict[str, list[tuple[int, str]]]:
    """Every folder title -> [(numeric id, display name)] beneath it."""
    out: dict[str, list[tuple[int, str]]] = {}

    def walk(node: dict[str, Any], path: list[str]) -> None:
        if node.get("item_type") == "module_item_folder":
            path = path + [node.get("title", "")]
            out.setdefault(path[-1], [])
        elif (node.get("item_type") == "module_item"
                and str(node.get("id", "")).isdigit()):
            for title in path:
                out.setdefault(title, []).append(
                    (int(node["id"]),
                     node.get("display_name") or node.get("title") or ""))
        for child in node.get("children", []):
            walk(child, path)

    walk(tree, [])
    return out


def enumerate_folder(tree: dict[str, Any],
                     folder: str) -> list[tuple[int, str]]:
    """(numeric id, display name) for module_items under a folder title.

    Exact title match first, then case-insensitive substring; anything
    else errors with the available folder list.
    """
    found = folders(tree)
    if folder in found:
        return found[folder]
    sub = [t for t in found if folder.lower() in t.lower()]
    if len(sub) == 1:
        return found[sub[0]]
    raise ValueError(f"no folder {folder!r}" +
                     (f" (have {sorted(found)})" if found
                      else " (tree holds no folders)"))


def build_due_report(tree: dict[str, Any], dues: list[dict[str, Any]],
                     answered: set[int]) -> list[dict[str, Any]]:
    """Per-folder due rows: earliest due, totals, open item names.

    dues: student_available_due_dates rows ({module_item_id, date});
    answered: answered numeric ids. Folders without dated items are
    omitted (undated folders are lecture history, not homework).
    """
    by_id = {d["module_item_id"]: d["date"] for d in dues}
    report = []
    for title, items in folders(tree).items():
        dated = [(nid, name) for nid, name in items if nid in by_id]
        if not dated:
            continue
        open_items = [(nid, name) for nid, name in dated
                      if nid not in answered]
        report.append({"title": title,
                       "due": min(by_id[nid] for nid, _ in dated),
                       "total": len(dated),
                       "answered": len(dated) - len(open_items),
                       "open": [name for _, name in open_items],
                       "done": not open_items})
    return sorted(report, key=lambda r: r["due"])


class Client:
    """Bearer-authenticated Top Hat API session over plain HTTP."""

    def __init__(self, base: str = APP_BASE,
                 token_provider: Callable[[], str] | None = None):
        self.base = base.rstrip("/")
        self._provide = token_provider or file_token_provider()
        self._token: str | None = None

    def _request(self, method: str, path: str, course: str | None,
                 body: dict[str, Any] | None = None) -> Any:
        data = json.dumps(body).encode() if body is not None else None
        for attempt in range(2):
            if self._token is None or attempt:
                self._token = self._provide()
            req = urllib.request.Request(self.base + path, data=data,
                                         method=method)
            req.add_header("Authorization", f"Bearer {self._token}")
            if course is not None:
                req.add_header("Course-Id", course)
            if data is not None:
                req.add_header("Content-Type", "application/json")
            try:
                with urllib.request.urlopen(req, timeout=30) as r:
                    raw = r.read().decode("utf-8", "replace")
                    return json.loads(raw) if raw.strip() else None
            except urllib.error.HTTPError as e:
                if e.code == 401 and not attempt:
                    continue  # token died mid-run: refresh once, retry
                try:
                    detail = e.read().decode("utf-8", "replace")[:120]
                except Exception:  # noqa: BLE001 — the code alone suffices
                    detail = ""
                hint = (" (item not in an open assignment: past-due, "
                        "unreleased, or review-closed)"
                        if e.code == 403 and "/content-delivery/" in path
                        else "")
                raise ValueError(
                    f"{method} {path}: HTTP {e.code} {detail}{hint}") from e
        raise AssertionError("unreachable")

    def course_id(self, public_code: str) -> str:
        meta = self._request(
            "GET", f"/index_metadata/frontend_v2/{public_code}", None)
        return str(meta["COURSE_ID"])

    def tree(self, course: str) -> dict[str, Any]:
        body = self._request(
            "GET",
            f"/api/v1/tree_data/?module_id=unitree&course_id={course}&limit=0",
            course)
        return json.loads(body["objects"][0]["data"])

    def id_mappings(self, course: str) -> dict[int, str]:
        body = self._request(
            "GET", f"/api/content/course/{course}/id_mappings/", course)
        out: dict[int, str] = {}
        for group in body["mappings"].values():
            for numeric, cid in group.items():
                # Group 3 keys are UUIDs (a different id space); only the
                # numeric module-item ids bridge tree/answered to content.
                if str(numeric).isdigit():
                    out[int(numeric)] = cid
        return out

    def fetch_item(self, course: str, cid: str) -> Question:
        body = self._request(
            "GET",
            f"/api/content-delivery/course/{course}/content/{cid}/"
            f"?exclude_mappings=true", course)
        return parse_content(cid, body)

    def submit(self, cid: str, part: str,
               option_ids: list[int]) -> dict[str, Any]:
        return self._request(
            "POST", f"/api/question/v3/review/questions/{cid}/responses/",
            None, {"data": {part: option_ids}})

    def answered(self, course: str) -> set[int]:
        body = self._request(
            "GET", f"/api/v2/answered_items/{course}/", course)
        return set(body.get("question", [])) | set(body.get("generic", []))

    def due_dates(self, course: str) -> list[dict[str, Any]]:
        body = self._request(
            "GET", f"/api/v3/course/{course}/student_available_due_dates/",
            course)
        return body if isinstance(body, list) else []


def public_code(public_url: str) -> str:
    if m := PUBLIC_CODE_RE.search(public_url):
        return m.group(1)
    raise ValueError(f"no /e/<public-code>/ in {public_url!r}")


def option_id(question: Question, value: str, what: str) -> int:
    """Option label (exact) or index:N to the numeric option id."""
    if value.startswith("index:"):
        pos = int(value.removeprefix("index:"))
        if not 0 <= pos < len(question.options):
            raise ValueError(f"{what}: index {pos} out of range "
                             f"({len(question.options)} options)")
        return question.options[pos]["id"]
    for o in question.options:
        if o["label"] == value:
            return o["id"]
    raise ValueError(f"{what}: no option labelled {value!r} "
                     f"(have {[o['label'] for o in question.options]})")


@dataclass
class EnterResult:
    n: int
    cid: str
    status: str
    detail: str
    grade: dict[str, Any] | None = None


def enter_question(client: Client, course: str, n: int, cid: str,
                   value: str, dry_run: bool = False) -> EnterResult:
    """Fetch -> resolve label -> submit -> parse grade. The submit response
    IS the verification: per-part status plus points come back together."""
    try:
        question = client.fetch_item(course, cid)
    except ValueError as e:
        return EnterResult(n, cid, "fetch_error", str(e))
    try:
        oid = option_id(question, value, f"question {n}")
    except ValueError as e:
        return EnterResult(n, cid, "fill_error", str(e))
    if dry_run:
        label = next(o["label"] for o in question.options
                     if o["id"] == oid)
        return EnterResult(n, cid, "dry_run_ok",
                           f"would submit {label!r} (id {oid})")
    try:
        grade = client.submit(cid, question.part, [oid])
    except ValueError as e:
        return EnterResult(n, cid, "submit_error", str(e))
    parts = grade.get("graded_response", {})
    states = [p.get("status") for p in parts.values()]
    pts = grade.get("points")
    if not states:
        return EnterResult(n, cid, "protocol_drift",
                           "submit response had no graded_response",
                           grade=grade)
    ok = all(s == "correct" for s in states)
    return EnterResult(n, cid, "ok" if ok else "submitted",
                       f"{'/'.join(states)}, {pts} pts", grade=grade)
