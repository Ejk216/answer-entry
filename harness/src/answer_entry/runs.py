"""Resumable homework runs: fetch -> answers -> canary -> enter -> verify.

One pipeline across platforms. Stage state lives in run.json inside the
run directory, so an interrupted run resumes instead of restarting —
problems already graded ok are never re-entered. The canary gates the
set: problem 1 must grade clean before anything else submits.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

# Problem statuses that stop a run (transport/protocol, not grades).
FATAL = {"fetch_error", "form_error", "protocol_drift", "login_required",
         "fill_error", "submit_error", "widget_shortage", "answer_shortage",
         "type_mismatch", "mismatch", "save_button_missing", "canary_failed",
         "no_quiz_frame"}


def slug(set_url: str) -> str:
    return "".join(c if c.isalnum() else "-" for c in
                   set_url.rstrip("/").rsplit("/", 1)[-1]).strip("-") or "set"


def new_state(platform: str, set_url: str) -> dict[str, Any]:
    return {"platform": platform, "set_url": set_url, "stage": "started",
            "problems": None, "answers": None, "entered": {},
            "canary": None, "verify": None, "error": None}


def load_state(run_dir: str | Path) -> dict[str, Any]:
    return json.loads((Path(run_dir) / "run.json").read_text())


def save_state(run_dir: str | Path, state: dict[str, Any]) -> None:
    path = Path(run_dir) / "run.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=1))


def start_run(run_dir: str | Path, platform: str, set_url: str,
              fetch: Callable[[str, Path], str]) -> dict[str, Any]:
    """Fetch stage: dump problems, wait for answers. Pure plumbing —
    the platform fetch does the real work."""
    run_dir = Path(run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)
    state = new_state(platform, set_url)
    try:
        state["problems"] = fetch(set_url, run_dir)
    except ValueError as e:
        state["stage"] = "failed"
        state["error"] = str(e)
    else:
        state["stage"] = "awaiting-answers"
    save_state(run_dir, state)
    return state


def advance_run(run_dir: str | Path, answers_path: str,
                io: Any, dry_run: bool = False) -> dict[str, Any]:
    """Validate -> canary -> enter -> verify. Skips problems already ok."""
    run_dir = Path(run_dir)
    state = load_state(run_dir)
    if state["stage"] not in ("awaiting-answers", "entering", "failed",
                              "validated"):
        return state
    state["answers"] = answers_path
    try:
        answers = io.load_answers(answers_path)
    except ValueError as e:
        return _fail(run_dir, state, f"answers file: {e}")
    problems = {p["n"]: p for p in io.load_problems(state["problems"])}
    validation = io.validate(answers_path, state["problems"])
    state["validation"] = {"errors": validation.errors,
                           "warnings": validation.warnings}
    if validation.errors:
        return _fail(run_dir, state,
                      "validate: " + "; ".join(validation.errors))
    if dry_run:
        state["stage"] = "validated"
        save_state(run_dir, state)
        return state
    order = sorted(a["n"] for a in answers if a["n"] in problems)
    if not order:
        return _fail(run_dir, state, "no answered problems match the fetch")
    state["stage"] = "entering"
    save_state(run_dir, state)

    def pending() -> list[int]:
        return [n for n in order if state["entered"].get(str(n)) != "ok"]

    # Canary: the first pending problem must grade clean. Re-gated
    # after a failed canary (fixed answers get a fresh bird).
    todo = pending()
    if todo and (state["canary"] is None
                 or state["canary"].get("status") != "ok"):
        n = todo[0]
        report = io.enter_one(n, problems[n], _values(answers, n))
        state["canary"] = {"n": n, **report}
        state["entered"][str(n)] = report["status"]
        save_state(run_dir, state)
        if report["status"] != "ok":
            return _fail(run_dir, state,
                         f"canary problem {n}: {report['status']} — "
                         f"{report.get('detail', '')}")
        todo = pending()
    for n in todo:
        report = io.enter_one(n, problems[n], _values(answers, n))
        state["entered"][str(n)] = report["status"]
        save_state(run_dir, state)
        if report["status"] in FATAL:
            return _fail(run_dir, state,
                         f"problem {n}: {report['status']} — "
                         f"{report.get('detail', '')}; stopping")
    try:
        state["verify"] = io.verify(state["set_url"])
    except ValueError as e:
        return _fail(run_dir, state, f"verify: {e}")
    bad = [n for n in order if state["entered"].get(str(n)) != "ok"]
    state["stage"] = "done" if not bad else "done-with-errors"
    if bad:
        state["error"] = f"non-clean problems: {bad}"
    save_state(run_dir, state)
    return state


def _values(answers: list[dict[str, Any]], n: int) -> list[Any]:
    return next(a["answers"] for a in answers if a["n"] == n)


def _fail(run_dir: Path, state: dict[str, Any],
          error: str) -> dict[str, Any]:
    state["stage"] = "failed"
    state["error"] = error
    save_state(run_dir, state)
    return state


class WWIO:
    """WeBWorK platform plug for the run machine (HTTP engine)."""

    def __init__(self, engine: Any, workers: int = 2):
        from . import http_engine
        self.engine = engine
        self.workers = workers
        self._http = http_engine

    def fetch(self, set_url: str, run_dir: Path) -> str:
        from . import http_engine
        stubs = [{"n": n, "url": u}
                 for n, u in http_engine.enumerate_set(self.engine, set_url)]
        pages = self.engine.fetch_all([s["url"] for s in stubs],
                                      workers=self.workers)
        dumps = []
        for s in stubs:
            n, url = s["n"], s["url"]
            try:
                parsed = http_engine.parse_problem(pages[url], url)
            except ValueError:
                parsed, _ = http_engine.get_problem_page(self.engine, url)
            (run_dir / f"problem-{n}.html").write_text(pages[url])
            dumps.append({"n": n, "url": url, "text": parsed.text,
                          "blanks": parsed.blanks, "images": parsed.images})
        out = run_dir / "problems.json"
        out.write_text(json.dumps(dumps, indent=2))
        return str(out)

    def load_problems(self, problems_path: str) -> list[dict[str, Any]]:
        return json.loads(Path(problems_path).read_text())

    def load_answers(self, answers_path: str) -> list[dict[str, Any]]:
        from .model import load_answers
        parsed = load_answers(answers_path)
        return [{"n": p.n, "answers": [a.value for a in p.answers]}
                for p in parsed.problems]

    def validate(self, answers_path: str, problems_path: str) -> Any:
        from .validate import validate_answers
        from .model import load_answers
        return validate_answers(json.loads(Path(problems_path).read_text()),
                                load_answers(answers_path))

    def enter_one(self, n: int, dump: dict[str, Any],
                  values: list[Any]) -> dict[str, Any]:
        import dataclasses
        r = self._http.enter_problem(self.engine, n, dump["url"], values)
        d = dataclasses.asdict(r)
        return {"status": d["status"], "detail": d["detail"]}

    def verify(self, set_url: str) -> list[dict[str, Any]]:
        return self._http.fetch_set_status(self.engine, set_url)
