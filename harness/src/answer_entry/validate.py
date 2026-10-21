"""Offline validation: answers.json against a fetched problems.json.

Catches transcription errors — wrong counts, mistyped option labels, str/list
mixups — before anything touches the server. Pure logic, no network.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .model import AnswerFile

# HTTP entry treats text and mathquill identically (both POST a string),
# so a declared type may use either spelling for either blank.
STR_BLANK_KINDS = ("text", "mathquill")


@dataclass
class Validation:
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors


def _check_option(blank: dict[str, Any], value: str, where: str,
                  out: Validation) -> None:
    options = blank.get("options", [])
    if value.startswith("index:"):
        try:
            pos = int(value.removeprefix("index:"))
        except ValueError:
            out.errors.append(f"{where}: bad index {value!r}")
            return
        if not 0 <= pos < len(options):
            out.errors.append(
                f"{where}: index {pos} out of range ({len(options)} options)")
        return
    labels = [o.get("label", "") for o in options]
    values = [o.get("value", "") for o in options]
    if value not in labels and value not in values:
        out.errors.append(
            f"{where}: {value!r} matches no option label "
            f"(have {labels})")


def validate_answers(problems: list[dict[str, Any]],
                     answers: AnswerFile) -> Validation:
    """Compare an answer file against fetched problem dumps (by problem n)."""
    out = Validation()
    by_n = {p["n"]: p for p in problems}
    seen = set()
    for p in answers.problems:
        seen.add(p.n)
        dump = by_n.get(p.n)
        if dump is None:
            out.errors.append(f"problem {p.n}: no fetch dump; "
                              f"re-run http-fetch covering problem {p.n}")
            continue
        blanks = dump.get("blanks", [])
        if len(p.answers) != len(blanks):
            out.errors.append(
                f"problem {p.n}: {len(p.answers)} answers but "
                f"{len(blanks)} blanks")
            continue
        for i, (answer, blank) in enumerate(zip(p.answers, blanks)):
            where = f"problem {p.n} answer[{i}] ({blank.get('kind')})"
            kind = blank.get("kind")
            value = answer.value
            if isinstance(value, list):
                if kind != "checkbox":
                    out.errors.append(f"{where}: list value needs a "
                                      f"checkbox blank, not {kind!r}")
                    continue
                for v in value:
                    _check_option(blank, v, where, out)
                continue
            if not isinstance(value, str):
                out.errors.append(f"{where}: value must be a string or list")
                continue
            if kind == "checkbox":
                out.errors.append(
                    f"{where}: checkbox blank needs a list value "
                    f"(add \"type\": \"checkbox\")")
                continue
            if answer.type is not None and answer.type != kind and not (
                    answer.type in STR_BLANK_KINDS
                    and kind in STR_BLANK_KINDS):
                out.errors.append(
                    f"{where}: declares type {answer.type!r} "
                    f"but blank is {kind!r}")
                continue
            if value == "":
                out.warnings.append(f"{where}: empty string counts as "
                                    f"unanswered")
            if kind in ("select", "radio"):
                _check_option(blank, value, where, out)
    for n in sorted(by_n):
        if n not in seen:
            out.warnings.append(f"problem {n}: fetched but not in answers "
                                f"file; will not be entered")
    return out
