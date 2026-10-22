"""Top Hat driver tests against an in-process mock API. No network.

Endpoint shapes mirror app.tophat.com traffic captured Oct 2026 (see
`harness recon`); the question fixture is sanitized sample content.
"""
import json
import threading
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from answer_entry import tophat
from answer_entry.tophat import Client, enumerate_folder, parse_content

FIX = Path(__file__).parent / "fixtures"
QUESTION = json.loads((FIX / "tophat_question.json").read_text())

TREE = {"children": [
    {"item_type": "module_item_folder", "title": "Top Hat 6",
     "children": [
         {"item_type": "module_item", "id": "111",
          "display_name": "Sample Arithmetic"},
         {"item_type": "module_item", "id": "222",
          "display_name": "Second Question"}]},
    {"item_type": "module_item_folder", "title": "Other",
     "children": [{"item_type": "module_item", "id": "333",
                   "display_name": "Elsewhere"}]},
]}

TOKEN = "test-token"


class Handler(BaseHTTPRequestHandler):
    posts: list = []
    authed_paths = ("/api/content-delivery/", "/api/question/")

    def log_message(self, *args):
        pass

    def _send(self, obj, status=200):
        body = json.dumps(obj).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _guard(self):
        if self.headers.get("Authorization") != f"Bearer {TOKEN}":
            self._send({"Detail": "Not authorized"}, status=401)
            return False
        if self.path.startswith(self.authed_paths[0]) and \
                self.headers.get("Course-Id") != "1157914":
            self._send({"HTTP_COURSE_ID": "This header is required."},
                       status=400)
            return False
        return True

    def do_GET(self):
        if self.path.startswith("/index_metadata/"):
            self._send({"COURSE_ID": 1157914})
        elif self.path.startswith("/api/v1/tree_data/"):
            self._send({"objects": [{"data": json.dumps(TREE)}]})
        elif self.path.startswith("/api/content/course/"):
            self._send({"mappings": {"1": {"111": "1490555::aaa",
                                           "222": "1490555::bbb"},
                                      "3": {"8befd969-09c7-4cbb-a311-24651bdee88e":
                                            "1490555::zzz"}}})
        elif "/content/1490555::aaa/" in self.path:
            if self._guard():
                self._send(QUESTION)
        elif "/content/1490555::closed/" in self.path:
            if self._guard():
                self._send({"detail": "Forbidden"}, status=403)
        elif self.path.startswith("/api/v2/answered_items/"):
            self._send({"question": [111], "generic": []})
        else:
            self.send_error(404)

    def do_POST(self):
        if not self._guard():
            return
        length = int(self.headers["Content-Length"])
        body = json.loads(self.rfile.read(length).decode())
        Handler.posts.append((self.path, body))
        # option id 2 ("4") is correct in the fixture
        ids = body["data"]["1"]
        ok = ids == [2]
        self._send({"graded_response": {
            "1": {"status": "correct" if ok else "incorrect",
                  "weighted_correctness": 1 if ok else 0,
                  "answers": {str(i): True for i in ids}}},
            "points": 1.0 if ok else 0.0})


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
def client(server):
    return Client(base=server, token_provider=lambda: TOKEN)


def test_public_code():
    assert tophat.public_code(
        "https://app.tophat.com/e/904581/content/x") == "904581"
    with pytest.raises(ValueError, match="public-code"):
        tophat.public_code("https://app.tophat.com/nope")


def test_course_id_and_tree(client):
    assert client.course_id("904581") == "1157914"
    tree = client.tree("1157914")
    assert tree["children"][0]["title"] == "Top Hat 6"


def test_enumerate_folder():
    assert enumerate_folder(TREE, "Top Hat 6") == [
        (111, "Sample Arithmetic"), (222, "Second Question")]
    assert enumerate_folder(TREE, "top hat") == [
        (111, "Sample Arithmetic"), (222, "Second Question")]
    with pytest.raises(ValueError, match="Other"):
        enumerate_folder(TREE, "Missing")


def test_build_due_report():
    dues = [{"module_item_id": 111, "date": "2026-10-22T03:59:00"},
            {"module_item_id": 222, "date": "2026-10-29T03:59:00"}]
    rows = tophat.build_due_report(TREE, dues, {111})
    assert rows == [{"title": "Top Hat 6", "due": "2026-10-22T03:59:00",
                     "total": 2, "answered": 1,
                     "open": ["Second Question"], "done": False}]
    assert tophat.build_due_report(TREE, [], set()) == []
    full = tophat.build_due_report(TREE, dues, {111, 222})
    assert full[0]["done"] is True and full[0]["open"] == []


def test_id_mappings(client):
    assert client.id_mappings("1157914") == {111: "1490555::aaa",
                                             222: "1490555::bbb"}


def test_parse_mc():
    q = parse_content("1490555::aaa", QUESTION)
    assert q.stem == "What is 2 + 2?"
    assert [(o["id"], o["label"]) for o in q.options] == [
        (1, "3"), (2, "4"), (3, "5")]
    assert q.part == "1" and q.title == "Sample Arithmetic"
    assert q.can_submit is True


def test_parse_rejects_non_mc():
    bad = json.loads(json.dumps(QUESTION))
    cfg = bad["learning_material_data"]["data"]["item_details"][
        "generic_item_data"]["configuration"]
    cfg["2"] = dict(cfg["1"])
    with pytest.raises(ValueError, match="1 part"):
        parse_content("x", bad)
    del cfg["2"]
    cfg["1"]["type"] = "numeric_question"
    with pytest.raises(ValueError, match="unsupported"):
        parse_content("x", bad)


def test_fetch_item(client):
    q = client.fetch_item("1157914", "1490555::aaa")
    assert q.stem == "What is 2 + 2?" and len(q.options) == 3


def test_option_id():
    q = parse_content("1490555::aaa", QUESTION)
    assert tophat.option_id(q, "4", "q") == 2
    assert tophat.option_id(q, "index:0", "q") == 1
    with pytest.raises(ValueError, match="no option labelled"):
        tophat.option_id(q, "6", "q")


def test_enter_grades_via_response(client):
    Handler.posts.clear()
    good = tophat.enter_question(client, "1157914", 1, "1490555::aaa",
                                 "4")
    assert good.status == "ok", good.detail
    assert "correct" in good.detail and good.grade["points"] == 1.0
    assert Handler.posts == [
        ("/api/question/v3/review/questions/1490555::aaa/responses/",
         {"data": {"1": [2]}})]
    bad = tophat.enter_question(client, "1157914", 1, "1490555::aaa",
                                "3")
    assert bad.status == "submitted", bad.detail
    assert "incorrect" in bad.detail


def test_enter_dry_run_posts_nothing(client):
    Handler.posts.clear()
    r = tophat.enter_question(client, "1157914", 1, "1490555::aaa",
                              "index:1", dry_run=True)
    assert r.status == "dry_run_ok" and Handler.posts == []


def test_enter_bad_label_is_fill_error(client):
    Handler.posts.clear()
    r = tophat.enter_question(client, "1157914", 1, "1490555::aaa", "6")
    assert r.status == "fill_error" and Handler.posts == []


def test_401_refreshes_token_and_retries(server):
    calls = []

    def provider():
        calls.append(1)
        return "stale" if len(calls) == 1 else TOKEN

    c = Client(base=server, token_provider=provider)
    q = c.fetch_item("1157914", "1490555::aaa")
    assert q.stem == "What is 2 + 2?"
    assert len(calls) == 2  # stale, then refreshed


def test_answered(client):
    assert client.answered("1157914") == {111}


def test_fetch_closed_item_explains_403(client):
    with pytest.raises(ValueError, match="not in an open assignment"):
        client.fetch_item("1157914", "1490555::closed")


def test_token_expiry():
    import base64
    import time
    payload = base64.urlsafe_b64encode(
        json.dumps({"exp": int(time.time()) + 600}).encode()).decode()
    assert tophat.token_expiry(f"h.{payload}.s") > time.time()
    assert tophat.token_expiry("junk") == 0.0
