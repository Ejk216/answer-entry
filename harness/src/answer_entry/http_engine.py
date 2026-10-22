"""HTTP engine: WeBWorK without a browser.

Design: generic form replay. The engine never hardcodes WeBWorK field names —
it parses the problem page's form, overrides the answer blanks in order, and
POSTs everything back the way the page would. Preview/submit buttons are found
by label.

Status: validated live on WeBWorK 2.19 (Oct 2026, local 1:1): 8-problem set,
all first-try correct, plus mock-server coverage (tests/). Answer blanks are
text inputs named AnSwErNNNN; MaThQuIlL_/previous_ companions replay verbatim.
"""
from __future__ import annotations

import concurrent.futures
import re
import threading
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass
from html.parser import HTMLParser
from http.cookiejar import Cookie, MozillaCookieJar
from pathlib import Path
from typing import Any

from .browser import PROFILE_DIR
from .timing import Tracker
from .webwork import parse_score_text

COOKIE_JAR = PROFILE_DIR / "http_cookies.txt"
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"
)

# Validated on 2.19 (local 1:1, Oct 2026): answer blanks are text inputs named
# AnSwEr0001, AnSwEr0002, ... Hidden companions MaThQuIlL_AnSwEr0001 and
# previous_AnSwEr0001 are replayed verbatim, never filled.
ANSWER_PATTERN = r"^AnSwEr\d"
REPLAY_PREFIXES = ("MaThQuIlL_", "previous_")

PREVIEW_LABEL = re.compile(r"preview", re.IGNORECASE)
SUBMIT_LABEL = re.compile(r"submit|check answer", re.IGNORECASE)


class _PageParser(HTMLParser):
    """Collects forms (fields in document order), text, and image URLs."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.forms: list[dict[str, Any]] = []
        self.page_text: list[str] = []
        self.page_images: list[str] = []
        self._form: dict[str, Any] | None = None
        self._select: dict[str, Any] | None = None
        self._option: dict[str, Any] | None = None
        self._label_inputs: list[dict[str, Any]] | None = None
        self._label_text: list[str] = []
        self._skip = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        a = {k: v or "" for k, v in attrs}
        if tag == "style":
            self._skip += 1
            return
        if tag == "script":
            # MathJax displayMode puts TeX in script tags: keep it, skip the rest.
            if a.get("type", "").startswith("math/tex"):
                self._math = True
            else:
                self._skip += 1
            return
        if tag == "form":
            self._form = {"action": a.get("action", ""),
                          "method": a.get("method", "get").lower(),
                          "fields": [], "text": [], "images": []}
            self.forms.append(self._form)
        elif tag == "input" and self._form is not None:
            field = {
                "tag": "input", "kind": a.get("type", "text").lower(),
                "name": a.get("name"), "value": a.get("value", ""),
                "checked": "checked" in a}
            self._form["fields"].append(field)
            if self._label_inputs is not None and field["kind"] in ("radio", "checkbox"):
                self._label_inputs.append(field)
        elif tag == "label" and self._form is not None:
            self._label_inputs = []
            self._label_text = []
        elif tag == "select" and self._form is not None:
            self._select = {"tag": "select", "kind": "select",
                            "name": a.get("name"), "options": []}
            self._form["fields"].append(self._select)
        elif tag == "option" and self._select is not None:
            self._option = {"value": a.get("value"), "label": "",
                            "selected": "selected" in a}
            self._select["options"].append(self._option)
        elif tag == "textarea" and self._form is not None:
            self._form["fields"].append({"tag": "textarea", "kind": "textarea",
                                         "name": a.get("name"), "value": ""})
        elif tag == "img":
            if a.get("src"):
                self.page_images.append(a["src"])
                if self._form is not None:
                    self._form["images"].append(a["src"])

    def handle_endtag(self, tag: str) -> None:
        if tag == "style":
            self._skip = max(0, self._skip - 1)
        elif tag == "label" and self._label_inputs is not None:
            text = " ".join(self._label_text).strip()
            for field in self._label_inputs:
                field["label_text"] = text
            self._label_inputs = None
            self._label_text = []
        elif tag == "script":
            if getattr(self, "_math", False):
                self._math = False
            else:
                self._skip = max(0, self._skip - 1)
        elif tag == "form":
            self._form = None
        elif tag == "select":
            self._select = None
        elif tag == "option":
            self._option = None

    def handle_data(self, data: str) -> None:
        if self._skip:
            return
        s = data.strip()
        if not s:
            return
        if getattr(self, "_math", False):
            s = f"$ {s} $"
        if self._label_inputs is not None:
            self._label_text.append(s)
        if self._option is not None:
            self._option["label"] += s
            if not self._option["value"]:
                self._option["value"] = s
        else:
            self.page_text.append(s)
            if self._form is not None:
                self._form["text"].append(s)


@dataclass
class ParsedProblem:
    url: str
    text: str
    images: list[str]
    form_action: str
    form_method: str
    replay_fields: list[tuple[str, str]]  # opaque round-trip fields (hidden etc.)
    blanks: list[dict[str, Any]]  # answer widgets in document order
    buttons: list[dict[str, Any]]  # submit/button inputs by label


def parse_problem(html: str, url: str, answer_pattern: str = ANSWER_PATTERN) -> ParsedProblem:
    parser = _PageParser()
    parser.feed(html)
    answerish = {"text", "select", "radio", "checkbox", "textarea"}
    form = next((f for f in parser.forms
                 if any(g["kind"] in answerish or
                        (g["kind"] == "hidden" and g["name"] and re.search(answer_pattern, g["name"]))
                        for g in f["fields"] if g.get("name"))), None)
    if form is None:
        raise ValueError(f"no answer form found at {url}")

    blanks: list[dict[str, Any]] = []
    replay: list[tuple[str, str]] = []
    buttons: list[dict[str, Any]] = []
    radio_groups: dict[str, dict[str, Any]] = {}
    check_groups: dict[str, dict[str, Any]] = {}

    def group(groups: dict[str, dict[str, Any]], name: str, kind: str) -> dict[str, Any]:
        if name not in groups:
            groups[name] = {"kind": kind, "name": name, "options": []}
            blanks.append(groups[name])
        return groups[name]

    for g in form["fields"]:
        name, kind = g.get("name"), g["kind"]
        if kind in ("submit", "button") or (g["tag"] == "input" and kind == "image"):
            buttons.append({"name": name, "value": g["value"], "label": g["value"]})
        elif kind == "select" and name:
            blanks.append({"kind": "select", "name": name, "options": g["options"]})
        elif kind == "radio" and name:
            group(radio_groups, name, "radio")["options"].append(
                {"label": g.get("label_text") or g["value"], "value": g["value"],
                 "checked": g["checked"]})
        elif kind == "checkbox" and name:
            group(check_groups, name, "checkbox")["options"].append(
                {"label": g.get("label_text") or g["value"], "value": g["value"],
                 "checked": g["checked"]})
        elif kind in ("text", "textarea") and name:
            # PG names every graded blank AnSwErNNNN; anything else is a
            # control or JS-widget scratch input: replay, never fill.
            if re.search(answer_pattern, name):
                blanks.append({"kind": "text", "name": name, "current": g["value"]})
            else:
                replay.append((name, g["value"]))
        elif kind == "hidden" and name:
            if name.startswith(REPLAY_PREFIXES):
                replay.append((name, g["value"]))
            elif re.search(answer_pattern, name):
                blanks.append({"kind": "mathquill", "name": name, "current": g["value"]})
            else:
                replay.append((name, g["value"]))
        elif name and kind not in ("password", "file"):
            replay.append((name, g["value"]))

    if not blanks:
        # A matched form with zero blanks is a diverted/bounce page (school
        # middleboxes do this transiently), not a problem. Raise so callers
        # retry instead of silently carrying an empty parse.
        raise ValueError(f"no answer blanks found at {url}")
    text = "\n".join(form["text"]) or "\n".join(parser.page_text)
    # Form images only: figures render inside the problem. Falling back to
    # page images picks up theme logos.
    images = [urllib.parse.urljoin(url, src) for src in form["images"]]
    return ParsedProblem(url=url, text=text, images=images,
                         form_action=urllib.parse.urljoin(url, form["action"] or url),
                         form_method=form["method"], replay_fields=replay,
                         blanks=blanks, buttons=buttons)


def _find_button(buttons: list[dict[str, Any]], pattern: re.Pattern[str], what: str) -> dict[str, Any]:
    for b in buttons:
        if b["name"] and pattern.search(b["label"]):
            return b
    raise ValueError(f"no {what} button found "
                     f"(have {[b['label'] for b in buttons]})")


def build_submission(parsed: ParsedProblem, answers: list[Any],
                     button: dict[str, Any]) -> list[tuple[str, str]]:
    """Field list for POST: replayed opaque fields + overridden blanks + button."""
    if len(answers) != len(parsed.blanks):
        raise ValueError(f"{len(answers)} answers but {len(parsed.blanks)} blanks at {parsed.url}")
    out: list[tuple[str, str]] = list(parsed.replay_fields)
    for blank, value in zip(parsed.blanks, answers):
        kind = blank["kind"]
        if kind in ("text", "mathquill"):
            assert isinstance(value, str), f"{blank['name']}: want str"
            out.append((blank["name"], value))
        elif kind == "select":
            assert isinstance(value, str), f"{blank['name']}: want str"
            out.append((blank["name"], _select_value(blank, value)))
        elif kind == "radio":
            assert isinstance(value, str), f"{blank['name']}: want str"
            out.append((blank["name"], _option_value(blank, value, "radio")))
        elif kind == "checkbox":
            assert isinstance(value, list), f"{blank['name']}: want list"
            for v in value:
                out.append((blank["name"], _option_value(blank, v, "checkbox")))
        else:
            raise ValueError(f"unknown blank kind {kind!r}")
    if button.get("name"):
        out.append((button["name"], button["value"]))
    return out


def _select_value(blank: dict[str, Any], value: str) -> str:
    if value.startswith("index:"):
        return blank["options"][int(value.removeprefix("index:"))]["value"]
    for o in blank["options"]:
        if o["label"] == value:
            return o["value"]
    raise ValueError(f"{blank['name']}: no option labelled {value!r}")


def _option_value(blank: dict[str, Any], value: str, what: str) -> str:
    if value.startswith("index:"):
        return blank["options"][int(value.removeprefix("index:"))]["value"]
    for o in blank["options"]:
        if o["label"] == value or o["value"] == value:
            return o["value"]
    raise ValueError(f"{blank['name']}: no {what} option {value!r}")


def get_problem_page(engine: "Engine", url: str, tries: int = 3,
                   delay: float = 3.0) -> tuple[ParsedProblem, str]:
    """GET + parse with serial retries. School servers intermittently bounce
    problem requests to the SSO authenticator; a bounce is transient, never
    a reason to give up (read-only, zero risk in retrying)."""
    last: ValueError | None = None
    for _ in range(tries):
        html = engine.get(url)
        try:
            return parse_problem(html, url), html
        except ValueError as e:
            last = e
            time.sleep(delay)
    assert last is not None
    raise last


def enumerate_set(engine: "Engine", set_url: str, tries: int = 3,
                  delay: float = 4.0) -> list[tuple[int, str]]:
    """Problem (n, url) pairs from a set page. Full hrefs are harvested
    verbatim — including query strings like ?effectiveUser= — since some
    problems refuse to serve without them. Retries: set pages bounce to
    SSO as transiently as problem pages do."""
    base_path = urllib.parse.urlparse(set_url).path.rstrip("/")
    for _ in range(tries):
        html = engine.get(set_url)
        found: dict[int, str] = {}
        for m in re.finditer(r'href="([^"]+)"', html):
            absolute = urllib.parse.urljoin(set_url, m.group(1))
            upath = urllib.parse.urlparse(absolute).path.rstrip("/")
            mm = re.match(re.escape(base_path) + r"/(\d+)$", upath)
            if mm:
                found[int(mm.group(1))] = absolute
        if found:
            return [(n, found[n]) for n in sorted(found)]
        time.sleep(delay)
    raise ValueError(f"no problem links found at {set_url}")


class _SetStatusParser(HTMLParser):
    """Per-problem percents from a set page. A row counts when it links to a
    problem (same base/N rule as enumerate_set); its first percent wins."""

    def __init__(self, base_path: str):
        super().__init__(convert_charrefs=True)
        self.base_path = base_path
        self.rows: list[dict[str, Any]] = []
        self._row: dict[str, Any] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "tr":
            self._row = {"n": None, "text": []}
            self.rows.append(self._row)
        elif tag == "a" and self._row is not None and self._row["n"] is None:
            href = dict(attrs).get("href") or ""
            upath = urllib.parse.urlparse(href).path.rstrip("/")
            m = re.match(re.escape(self.base_path) + r"/(\d+)$", upath)
            if m:
                self._row["n"] = int(m.group(1))

    def handle_endtag(self, tag: str) -> None:
        if tag == "tr":
            self._row = None

    def handle_data(self, data: str) -> None:
        if self._row is not None:
            s = data.strip()
            if s:
                self._row["text"].append(s)


PERCENT_RE = re.compile(r"(\d+(?:\.\d+)?)\s*%")


def parse_set_status(html: str, set_url: str) -> list[dict[str, Any]]:
    """Per-problem status rows from set-page HTML, sorted by n.

    Contract is mock-defined (tests/fixtures/mock_set.html) until a live
    set page confirms the row shape; rows with no percent parse as None
    rather than guessing.
    """
    base_path = urllib.parse.urlparse(set_url).path.rstrip("/")
    parser = _SetStatusParser(base_path)
    parser.feed(html)
    rows = []
    for row in parser.rows:
        if row["n"] is None:
            continue
        m = PERCENT_RE.search(" ".join(row["text"]))
        rows.append({"n": row["n"],
                     "percent": float(m.group(1)) if m else None})
    return sorted(rows, key=lambda r: r["n"])


def fetch_set_status(engine: "Engine", set_url: str, tries: int = 3,
                     delay: float = 4.0) -> list[dict[str, Any]]:
    """Set status with serial retries (set pages bounce like problem pages)."""
    for _ in range(tries):
        rows = parse_set_status(engine.get(set_url), set_url)
        if rows:
            return rows
        time.sleep(delay)
    raise ValueError(f"no problem status rows found at {set_url}")


def auth_failure_kind(html: str) -> str | None:
    """Why an HTTP fetch didn't yield app content, if auth is the reason.

    - "incapsula": bot-wall stub (JS challenge, no content).
    - "sso": diverted to the school's single-sign-on login.
    - "login": plain WeBWorK login form.
    None means no auth failure is visible (parse errors are something else).
    """
    if "_Incapsula_Resource" in html:
        return "incapsula"
    lowered = html.lower()
    if ("auth.msu.edu" in lowered or "login.msu.edu" in lowered
            or "okta" in lowered and "sign in" in lowered):
        return "sso"
    if 'id="login_form"' in html or 'name="passwd"' in html:
        return "login"
    return None


def classify_refresh_page(url: str, html: str) -> tuple[str, str]:
    """Refresh-dance state for a browser page: (state, reason).

    - "ready": app content is showing (problem form or set rows).
    - "needs-you": an interactive gate (SSO/Okta, password, 2FA, bot-wall).
    - "loading": mid-dance transit; keep polling.
    """
    lowered = html.lower()
    if "AnSwEr" in html or "Problem 1" in html:
        return "ready", "app content showing"
    if "_Incapsula_Resource" in html:
        return "needs-you", "Incapsula bot-wall in the browser"
    if 'type="password"' in lowered:
        return "needs-you", "password field showing"
    if "duosecurity" in lowered or "duo " in lowered and "push" in lowered:
        return "needs-you", "2FA prompt showing"
    if "auth.msu.edu" in url or "login.msu.edu" in url:
        if "sign in" in lowered or "email" in lowered:
            return "needs-you", "school SSO login showing"
        return "loading", "SSO dance in transit"
    if "sign in" in lowered and "okta" in lowered:
        return "needs-you", "Okta login showing"
    return "loading", "no app content yet"


def strip_to_text(html: str) -> str:
    no_script = re.sub(r"(?is)<(script|style).*?</\1>", " ", html)
    return re.sub(r"\s+", " ",
                  re.sub(r"<[^>]+>", " ", no_script)).strip()


class Engine:
    """Cookie-authenticated HTTP session with keep-alive and parallel fetch."""

    def __init__(self, jar_path: str | Path = COOKIE_JAR):
        self.jar_path = Path(jar_path)
        self.jar = MozillaCookieJar(self.jar_path)
        if self.jar_path.exists():
            # Session cookies come back with discard set; keep them too.
            self.jar.load(ignore_discard=True, ignore_expires=True)
        self._local = threading.local()

    def _opener(self) -> urllib.request.OpenerDirector:
        opener = getattr(self._local, "opener", None)
        if opener is None:
            opener = urllib.request.build_opener(
                urllib.request.HTTPCookieProcessor(self.jar))
            opener.addheaders = [("User-Agent", USER_AGENT)]
            self._local.opener = opener
        return opener

    def save(self) -> None:
        self.jar_path.parent.mkdir(parents=True, exist_ok=True)
        # Persist session cookies too: a saved login that evaporates is useless.
        self.jar.save(ignore_discard=True, ignore_expires=True)

    def get(self, url: str, timeout: int = 30) -> str:
        with self._opener().open(url, timeout=timeout) as r:
            return r.read().decode("utf-8", "replace")

    def get_bytes(self, url: str, timeout: int = 30) -> bytes:
        with self._opener().open(url, timeout=timeout) as r:
            return r.read()

    def post(self, url: str, fields: list[tuple[str, str]], timeout: int = 30) -> str:
        data = urllib.parse.urlencode(fields).encode()
        req = urllib.request.Request(url, data=data)
        with self._opener().open(req, timeout=timeout) as r:
            return r.read().decode("utf-8", "replace")

    def fetch_all(self, urls: list[str], workers: int = 2,
                  tracker: Tracker | None = None) -> dict[str, str]:
        """Parallel GET with one retry per URL. Workers stay low: bursts
        make school servers bounce requests to SSO re-auth."""
        out: dict[str, str] = {}
        errors: dict[str, str] = {}
        t0 = time.perf_counter()

        def one(url: str) -> tuple[str, str | None]:
            last: Exception | None = None
            for attempt in range(2):
                try:
                    return url, self.get(url)
                except Exception as e:  # noqa: BLE001 — retry once, then report
                    last = e
                    time.sleep(2 * (attempt + 1))
            errors[url] = f"{type(last).__name__}: {last}"
            return url, None

        with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
            for url, html in pool.map(one, urls):
                if html is not None:
                    out[url] = html
        if errors:
            raise RuntimeError("fetch failed for: " + ", ".join(
                f"{u} ({e})" for u, e in errors.items()))
        if tracker is not None:
            tracker.phases["fetch_all"] = tracker.phases.get("fetch_all", 0.0) \
                + (time.perf_counter() - t0)
            if "fetch_all" not in tracker._order:
                tracker._order.append("fetch_all")
        return out


def export_playwright_cookies(pw_cookies: list[dict[str, Any]],
                              jar_path: str | Path = COOKIE_JAR) -> Path:
    """Bridge: browser login → HTTP session. Overwrites the cookie jar."""
    jar_path = Path(jar_path)
    jar = MozillaCookieJar(jar_path)
    for c in pw_cookies:
        # Playwright marks session cookies expires=-1; Python would treat
        # that as already-expired and withhold them. Translate to a true
        # session cookie (expires=None), which request handling attaches.
        exp = c.get("expires", None)
        session = exp is None or exp == -1
        jar.set_cookie(Cookie(
            version=0, name=c["name"], value=c["value"],
            port=None, port_specified=False,
            domain=c.get("domain", ""), domain_specified=bool(c.get("domain")),
            domain_initial_dot=(c.get("domain", "") or "").startswith("."),
            path=c.get("path", "/"), path_specified=True,
            secure=bool(c.get("secure", False)),
            expires=None if session else exp,
            discard=session, comment=None, comment_url=None,
            rest={"HttpOnly": ""} if c.get("httpOnly") else {},
            rfc2109=False))
    jar_path.parent.mkdir(parents=True, exist_ok=True)
    jar.save(ignore_discard=True, ignore_expires=True)
    return jar_path


@dataclass
class EnterResult:
    n: int
    url: str
    status: str
    detail: str
    score: dict[str, Any] | None = None


def enter_problem(engine: Engine, n: int, url: str, answers: list[Any],
                  dry_run: bool = False,
                  tracker: Tracker | None = None) -> EnterResult:
    """GET → parse → count check → preview POST → submit POST → parse score.

    Validated live on WeBWorK 2.19 (Oct 2026): 8-problem set, all first-try
    correct. A submit response without a score message means the protocol
    drifted (new WeBWorK version?) and stops the run instead of guessing.
    """
    t = tracker or Tracker()
    try:
        with t.phase("fetch"):
            parsed, html = get_problem_page(engine, url)
    except ValueError:
        return EnterResult(n, url, "fetch_error",
                           "problem page bounced repeatedly; session may need "
                           "`harness http-auth`, or the server is throttling")
    if "Login" in html[:2000] and not parsed.blanks:
        return EnterResult(n, url, "login_required",
                           "page has no answer form; run `harness http-auth` first")
    if len(answers) != len(parsed.blanks):
        return EnterResult(n, url, "widget_shortage" if len(answers) > len(parsed.blanks)
                           else "answer_shortage",
                           f"{len(answers)} answers but {len(parsed.blanks)} blanks")
    try:
        preview_fields = build_submission(
            parsed, answers, _find_button(parsed.buttons, PREVIEW_LABEL, "preview"))
        submit_fields = build_submission(
            parsed, answers, _find_button(parsed.buttons, SUBMIT_LABEL, "submit"))
    except ValueError as e:
        return EnterResult(n, url, "form_error", str(e))

    with t.phase("preview"):
        engine.post(parsed.form_action, preview_fields)
    if dry_run:
        return EnterResult(n, url, "dry_run_ok",
                           f"{len(answers)} answers previewed, not submitted")
    with t.phase("submit"):
        result_html = engine.post(parsed.form_action, submit_fields)
    score = parse_score_text(strip_to_text(result_html))
    if score.get("percent") is None and score.get("unanswered") is None:
        return EnterResult(n, url, "protocol_drift",
                           "submit response had no score message; stopping",
                           score=score)
    status = "ok" if score.get("percent") == 100 else "submitted"
    return EnterResult(n, url, status, score["verdict"], score=score)
