"""Answer-file schema (answers.json). Pure logic — no browser needed.

Expected shape:

.. code-block:: json

    {
      "set_url": "https://webwork2.../<course>/<Set>/",
      "problems": [
        {"n": 1, "url": "https://webwork2.../<course>/<Set>/1/",
         "answers": [
           {"value": "-\\\\frac{1}{2},3"},
           {"value": "42", "type": "select"},
           {"value": ["A", "C"], "type": "checkbox"}
         ]}
      ]
    }

Answers map to the page's widgets in page order; widget type is auto-detected
unless overridden. ``set_url`` and per-problem ``url`` are optional as long as
one of them lets every problem URL be derived.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

WIDGET_TYPES = ("mathquill", "text", "select", "radio", "checkbox")


@dataclass
class Answer:
    value: object  # str, or list[str] for checkbox
    type: str | None = None  # override: checked against detection, never trusted blindly


@dataclass
class ProblemAnswers:
    n: int
    url: str | None
    answers: list[Answer]


@dataclass
class AnswerFile:
    set_url: str | None
    problems: list[ProblemAnswers]

    def problem_url(self, p: ProblemAnswers) -> str:
        if p.url:
            return p.url
        if self.set_url:
            return self.set_url.rstrip("/") + f"/{p.n}/"
        raise ValueError(f"problem {p.n}: no url and no set_url to derive it from")


def load_answers(path: str | Path) -> AnswerFile:
    return parse_answers_dict(json.loads(Path(path).read_text()))


def parse_answers_dict(raw: object) -> AnswerFile:
    if not isinstance(raw, dict):
        raise ValueError("answers file must be a JSON object")
    set_url = raw.get("set_url")
    problems_raw = raw.get("problems")
    if not isinstance(problems_raw, list) or not problems_raw:
        raise ValueError("'problems' must be a non-empty list")
    problems: list[ProblemAnswers] = []
    seen: set[int] = set()
    for i, pr in enumerate(problems_raw):
        if not isinstance(pr, dict):
            raise ValueError(f"problems[{i}] must be an object")
        n = pr.get("n")
        if not isinstance(n, int) or n < 1:
            raise ValueError(f"problems[{i}]: 'n' must be a positive int")
        if n in seen:
            raise ValueError(f"duplicate problem n={n}")
        seen.add(n)
        answers_raw = pr.get("answers")
        if not isinstance(answers_raw, list) or not answers_raw:
            raise ValueError(f"problem {n}: 'answers' must be a non-empty list")
        answers: list[Answer] = []
        for j, a in enumerate(answers_raw):
            if not isinstance(a, dict) or "value" not in a:
                raise ValueError(f"problem {n} answer[{j}]: must be an object with 'value'")
            t = a.get("type")
            if t is not None and t not in WIDGET_TYPES:
                raise ValueError(f"problem {n} answer[{j}]: unknown type {t!r}")
            v = a["value"]
            if t == "checkbox":
                if not isinstance(v, list) or not all(isinstance(x, str) for x in v):
                    raise ValueError(f"problem {n} answer[{j}]: checkbox value must be a list of strings")
            elif not isinstance(v, str):
                raise ValueError(f"problem {n} answer[{j}]: value must be a string")
            answers.append(Answer(value=v, type=t))
        problems.append(ProblemAnswers(n=n, url=pr.get("url"), answers=answers))
    problems.sort(key=lambda p: p.n)
    return AnswerFile(set_url=set_url, problems=problems)
