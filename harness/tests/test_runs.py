"""Run machine: stages, canary gate, resume. Scripted fake IO, no network."""
import json

import pytest

from answer_entry import runs


class FakeIO:
    def __init__(self, tmp_path, grades, problems=(1, 2, 3)):
        self.tmp_path = tmp_path
        self.grades = dict(grades)  # n -> status
        self.problems = list(problems)
        self.enters = []
        self.fail_validate = False

    def fetch(self, set_url, run_dir):
        dumps = [{"n": n, "url": f"{set_url}/{n}/"} for n in self.problems]
        out = run_dir / "problems.json"
        out.write_text(json.dumps(dumps))
        return str(out)

    def load_problems(self, problems_path):
        import pathlib
        return json.loads(pathlib.Path(problems_path).read_text())

    def load_answers(self, answers_path):
        import pathlib
        return json.loads(pathlib.Path(answers_path).read_text())["problems"]

    def validate(self, answers_path, problems_path):
        import types
        if self.fail_validate:
            return types.SimpleNamespace(errors=["bad"], warnings=[])
        return types.SimpleNamespace(errors=[], warnings=[])

    def enter_one(self, n, dump, values):
        self.enters.append(n)
        status = self.grades.get(n, "ok")
        return {"status": status, "detail": f"{status} p{n}"}

    def verify(self, set_url):
        return [{"n": n, "percent": 100.0} for n in self.problems]


@pytest.fixture()
def rundir(tmp_path):
    return tmp_path / "run"


def answers_file(tmp_path, ns=(1, 2, 3)):
    p = tmp_path / "answers.json"
    p.write_text(json.dumps(
        {"problems": [{"n": n, "answers": ["x"]} for n in ns]}))
    return str(p)


def test_happy_path(rundir, tmp_path):
    io = FakeIO(tmp_path, {})
    st = runs.start_run(rundir, "webwork", "http://x/Set/", io.fetch)
    assert st["stage"] == "awaiting-answers"
    st = runs.advance_run(rundir, answers_file(tmp_path), io)
    assert st["stage"] == "done", st
    assert io.enters == [1, 2, 3]  # canary first, then the rest
    assert st["canary"]["n"] == 1 and st["verify"][0]["percent"] == 100.0


def test_validate_errors_enter_nothing(rundir, tmp_path):
    io = FakeIO(tmp_path, {})
    io.fail_validate = True
    runs.start_run(rundir, "webwork", "http://x/Set/", io.fetch)
    st = runs.advance_run(rundir, answers_file(tmp_path), io)
    assert st["stage"] == "failed" and io.enters == []


def test_canary_wrong_stops_set(rundir, tmp_path):
    io = FakeIO(tmp_path, {1: "submitted"})
    runs.start_run(rundir, "webwork", "http://x/Set/", io.fetch)
    st = runs.advance_run(rundir, answers_file(tmp_path), io)
    assert st["stage"] == "failed" and "canary" in st["error"]
    assert io.enters == [1]
    # fixed answers re-gate a fresh canary, then finish
    io.grades[1] = "ok"
    st = runs.advance_run(rundir, answers_file(tmp_path), io)
    assert st["stage"] == "done", st
    assert io.enters == [1, 1, 2, 3]


def test_transport_error_resumes_without_repeats(rundir, tmp_path):
    io = FakeIO(tmp_path, {2: "fetch_error"})
    runs.start_run(rundir, "webwork", "http://x/Set/", io.fetch)
    st = runs.advance_run(rundir, answers_file(tmp_path), io)
    assert st["stage"] == "failed" and io.enters == [1, 2]
    io.grades[2] = "ok"  # transient clears
    st = runs.advance_run(rundir, answers_file(tmp_path), io)
    assert st["stage"] == "done", st
    assert io.enters == [1, 2, 2, 3]  # p1 never re-entered


def test_dry_run_validates_only(rundir, tmp_path):
    io = FakeIO(tmp_path, {})
    runs.start_run(rundir, "webwork", "http://x/Set/", io.fetch)
    st = runs.advance_run(rundir, answers_file(tmp_path), io, dry_run=True)
    assert st["stage"] == "validated" and io.enters == []
    st = runs.advance_run(rundir, answers_file(tmp_path), io)
    assert st["stage"] == "done"


def test_slug():
    assert runs.slug("https://h/webwork2/c/HW07-FS26/") == "HW07-FS26"
    assert runs.slug("https://app.tophat.com/e/904581/x") == "x"
