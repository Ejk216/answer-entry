"""HTTP engine tests against an in-process mock WeBWorK server. No network."""
import threading
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from answer_entry import http_engine
from answer_entry.http_engine import Engine, export_playwright_cookies, parse_problem

FIX = Path(__file__).parent / "fixtures"
PROBLEM_HTML = (FIX / "mock_problem.html").read_text()
SCORE_HTML = (FIX / "mock_score.html").read_text()


class Handler(BaseHTTPRequestHandler):
    posts: list = []

    def log_message(self, *args):
        pass

    def _send(self, body: bytes, ctype: str, cookie: str | None = None):
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        if cookie:
            self.send_header("Set-Cookie", cookie)
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/fig1.png":
            self._send(b"\x89PNG\r\n\x1a" + b"\0" * 64, "image/png")
        elif self.path in ("/course/set", "/course/set/"):
            links = "".join(
                f'<a href="/course/set/{n}/?effectiveUser=x">Problem {n}</a>'
                for n in (2, 1, 3))
            self._send(f"<html><body>{links}</body></html>".encode(), "text/html")
        elif self.path.startswith("/course/set/"):
            html = PROBLEM_HTML
            if self.path == "/course/set/99/":
                html = html.replace('action="/submit"', 'action="/submit-junk"')
            self._send(html.encode(), "text/html",
                       cookie="session=abc; Path=/")
        else:
            self.send_error(404)

    def do_POST(self):
        length = int(self.headers["Content-Length"])
        fields = urllib.parse.parse_qsl(self.rfile.read(length).decode())
        Handler.posts.append(fields)
        if self.path == "/submit-junk":
            self._send(b"<html><body>weird new version</body></html>", "text/html")
            return
        names = [k for k, _ in fields]
        if "submitAnswers" in names:
            self._send(SCORE_HTML.encode(), "text/html")
        elif "previewAnswers" in names:
            self._send(f"<html><body>Preview rendered: {fields}</body></html>".encode(),
                       "text/html")
        else:
            self.send_error(400, "no button field")


@pytest.fixture(scope="module")
def server():
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{httpd.server_port}"
    httpd.shutdown()
    thread.join()
    httpd.server_close()


@pytest.fixture()
def engine(tmp_path):
    return Engine(jar_path=tmp_path / "cookies.txt")


ANSWERS = ["14", "x^2", "42", "green", ["A", "B"]]


def test_fetch_all_parallel(server, engine):
    urls = [f"{server}/course/set/{n}/" for n in range(1, 5)]
    pages = engine.fetch_all(urls, workers=4)
    assert set(pages) == set(urls)
    assert all("f(x)" in html for html in pages.values())
    engine.save()
    reloaded = Engine(jar_path=engine.jar_path)
    assert any(c.name == "session" and c.value == "abc" for c in reloaded.jar)


def test_parse_problem(server, engine):
    parsed = parse_problem(engine.get(f"{server}/course/set/1/"),
                           f"{server}/course/set/1/")
    assert [b["kind"] for b in parsed.blanks] == [
        "text", "mathquill", "select", "radio", "checkbox"]
    assert ("session_key", "sess-1") in parsed.replay_fields
    assert ("user", "student") in parsed.replay_fields
    assert ("Input1", "1") in parsed.replay_fields  # non-answer control: replayed
    radio = next(b for b in parsed.blanks if b["kind"] == "radio")
    assert [(o["label"], o["value"]) for o in radio["options"]] == [
        ("red", "r"), ("green", "g")]  # labels captured from <label> text
    assert sorted(b["label"] for b in parsed.buttons) == [
        "Preview Answers", "Submit Answers"]
    assert parsed.images == [f"{server}/fig1.png"]
    assert "f(x)" in parsed.text
    assert "$ f(x) = 3x + 2 $" in parsed.text  # math/tex kept
    assert "noise" not in parsed.text  # plain script dropped
    assert parsed.form_action == f"{server}/submit"


def test_build_submission(server, engine):
    parsed = parse_problem(engine.get(f"{server}/course/set/1/"),
                           f"{server}/course/set/1/")
    submit = next(b for b in parsed.buttons if b["label"] == "Submit Answers")
    fields = dict_repeated(http_engine.build_submission(parsed, ANSWERS, submit))
    assert fields["AnSwEr0001"] == ["14"]
    assert fields["AnSwEr2"] == ["x^2"]
    assert fields["choice1"] == ["1"]  # label 42 -> option value
    assert fields["color"] == ["g"]  # label green -> option value
    assert fields["opts"] == ["A", "B"]
    assert fields["session_key"] == ["sess-1"]  # replayed opaque field
    assert fields["submitAnswers"] == ["Submit Answers"]
    with pytest.raises(ValueError, match="answers but"):
        http_engine.build_submission(parsed, ANSWERS[:2], submit)


def dict_repeated(pairs):
    out: dict = {}
    for k, v in pairs:
        out.setdefault(k, []).append(v)
    return out


def test_enter_stops_on_protocol_drift(server, engine):
    Handler.posts.clear()
    result = http_engine.enter_problem(engine, 99, f"{server}/course/set/99/",
                                       ANSWERS)
    assert result.status == "protocol_drift", result.detail


def test_enter_live_posts_preview_then_submit(server, engine):
    Handler.posts.clear()
    result = http_engine.enter_problem(engine, 1, f"{server}/course/set/1/",
                                       ANSWERS)
    assert result.status == "ok", result.detail
    assert result.score and result.score["percent"] == 100
    assert len(Handler.posts) == 2
    first = [k for k, _ in Handler.posts[0]]
    second = [k for k, _ in Handler.posts[1]]
    assert "previewAnswers" in first and "submitAnswers" not in first
    assert "submitAnswers" in second
    sent = dict_repeated(Handler.posts[1])
    assert sent["AnSwEr0001"] == ["14"] and sent["session_key"] == ["sess-1"]


def test_enter_dry_run_previews_only(server, engine):
    Handler.posts.clear()
    result = http_engine.enter_problem(engine, 1, f"{server}/course/set/1/",
                                       ANSWERS, dry_run=True)
    assert result.status == "dry_run_ok", result.detail
    assert len(Handler.posts) == 1
    assert "previewAnswers" in [k for k, _ in Handler.posts[0]]


def test_cookie_export_roundtrip(tmp_path):
    from urllib.request import Request
    jar_path = tmp_path / "jar.txt"
    export_playwright_cookies(
        [{"name": "session", "value": "abc", "domain": "127.0.0.1",
          "path": "/", "secure": False, "httpOnly": True, "expires": -1}],
        jar_path)
    engine = Engine(jar_path=jar_path)
    assert any(c.name == "session" and c.value == "abc" for c in engine.jar)
    # Playwright's expires=-1 must become an attachable session cookie,
    # not a permanently-expired one (school Incapsula lesson).
    req = Request("http://127.0.0.1/course/")
    engine.jar.add_cookie_header(req)
    assert "session=abc" in (req.get_header("Cookie") or "")


def test_enumerate_set(server, engine):
    pairs = http_engine.enumerate_set(engine, f"{server}/course/set/")
    assert pairs == [(n, f"{server}/course/set/{n}/?effectiveUser=x")
                     for n in (1, 2, 3)]
    with pytest.raises(ValueError, match="no problem links"):
        http_engine.enumerate_set(engine, f"{server}/fig1.png")


def test_strip_to_text():
    text = http_engine.strip_to_text(SCORE_HTML)
    assert http_engine.parse_score_text(text)["percent"] == 100
