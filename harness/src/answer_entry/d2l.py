"""Deterministic D2L quiz read/enter (Playwright).

Follows the validated procedure in references/d2l.md: the quiz lives in a
frame full of shadow-DOM web components, so one JS traversal collects text
plus radio markers; radios are grouped by name in DOM order; entry is DOM
.click() (never .checked=); bulk clicks end with an exact-text "Save All
Responses" click; the driver NEVER submits — saved answers stand as the
attempt and submitting is the user's call.

Two constraints from the browser-extension days do NOT apply here: there is
no 1.5 KB result truncation and no cookie-text filter, so the dump comes
back whole and labels keep their whitespace.

Status: fixture-tested only. The group-n-is-question-n mapping still needs
its live confirmation (compare the dump's answered pattern against the
navigator's badges before trusting a full-quiz enter).
"""
from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

from .model import AnswerFile

if TYPE_CHECKING:
    from playwright.sync_api import Frame, Page

SAVE_ALL_TEXT = "Save All Responses"

FOOTER_RE = re.compile(r"(\d+)\s+of\s+(\d+)\s+questions?\s+saved",
                       re.IGNORECASE)

# Per-question "saved" markers sit between radios in the DOM walk; they are
# status chrome, never option labels. Heuristic, documented: a dump review
# before entering catches anything this misclassifies; index:N answers
# bypass labels entirely.
_STATUS_TEXT_RE = re.compile(r"^✓|saved\s*$", re.IGNORECASE)

_DUMP_JS = """() => {
  const events = [];
  const walk = (node) => {
    if (node.nodeType === 3) {
      if (node.data.trim()) events.push({t: 'text', s: node.data});
    } else if (node.nodeType === 1) {
      if (node.tagName === 'INPUT' && node.type === 'radio') {
        events.push({t: 'radio', name: node.name || '', checked: node.checked});
      }
      for (const c of node.childNodes) walk(c);
      if (node.shadowRoot) for (const c of node.shadowRoot.childNodes) walk(c);
    }
  };
  walk(document.body);
  return events;
}"""

_CLICK_JS = """({name, index}) => {
  const radios = [];
  const walk = (node) => {
    if (node.nodeType !== 1) return;
    if (node.tagName === 'INPUT' && node.type === 'radio' && node.name === name)
      radios.push(node);
    for (const c of node.childNodes) walk(c);
    if (node.shadowRoot) for (const c of node.shadowRoot.childNodes) walk(c);
  };
  walk(document.body);
  if (index < 0 || index >= radios.length) return {ok: false, found: radios.length};
  radios[index].click();  // .click(), never .checked= : D2L's save handler must run
  return {ok: true, checked: radios[index].checked};
}"""

_SAVE_ALL_JS = """(want) => {
  let target = null;
  const textOf = (el) => ((el.innerText || el.value || '').trim());
  const walk = (node) => {
    if (target || node.nodeType !== 1) return;
    if ((node.tagName === 'BUTTON' || (node.tagName === 'INPUT' &&
        (node.type === 'button' || node.type === 'submit'))) &&
        textOf(node) === want) {
      target = node;
      return;
    }
    for (const c of node.childNodes) walk(c);
    if (node.shadowRoot) for (const c of node.shadowRoot.childNodes) walk(c);
  };
  walk(document.body);
  if (target) { target.click(); return true; }
  return false;
}"""


def dedupe_label(s: str) -> str:
    """Collapse D2L's triplicated labels ('3125''3125''3125' -> '3125').

    Exact repetition only, whitespace preserved: whitespace-sensitive
    questions have options differing solely by leading/trailing spaces.
    """
    if s and len(s) % 3 == 0 and s == s[:len(s) // 3] * 3:
        return s[:len(s) // 3]
    if s and len(s) % 2 == 0 and s == s[:len(s) // 2] * 2:
        return s[:len(s) // 2]
    return s


def find_quiz_frame(page: "Page") -> "Frame | None":
    """First frame holding quiz radios (the content frame, not the chrome)."""
    for frame in page.frames:
        try:
            if frame.locator("input[type=radio]").count():
                return frame
        except Exception:  # noqa: BLE001 — a dead frame is just not the quiz
            continue
    return None


def dump_quiz(frame: "Frame") -> dict[str, Any]:
    """Whole quiz in one traversal: questions in group order with stems,
    deduped labels, checked states, and the footer counter."""
    events: list[dict[str, Any]] = frame.evaluate(_DUMP_JS)
    questions: list[dict[str, Any]] = []
    by_group: dict[str, dict[str, Any]] = {}
    pending: list[str] = []
    for ev in events:
        if ev["t"] == "text":
            if not _STATUS_TEXT_RE.search(ev["s"].strip()):
                pending.append(ev["s"])
            continue
        label = dedupe_label(pending[-1]) if pending else ""
        group = by_group.get(ev["name"])
        if group is None:
            group = {"n": len(questions) + 1, "group": ev["name"],
                     "stem": " ".join(s.strip() for s in pending[:-1]).strip(),
                     "options": []}
            by_group[ev["name"]] = group
            questions.append(group)
        group["options"].append({"label": label, "checked": ev["checked"]})
        pending = []
    for q in questions:
        q["answered"] = any(o["checked"] for o in q["options"])
    try:
        footer_text = frame.locator("body").inner_text()
    except Exception:  # noqa: BLE001 — footer is a cross-check, not the quiz
        footer_text = ""
    m = FOOTER_RE.search(footer_text)
    footer = {"saved": int(m.group(1)), "total": int(m.group(2)),
              "raw": m.group(0)} if m else None
    return {"questions": questions, "footer": footer,
            "answered_pattern": [q["answered"] for q in questions]}


def option_index(options: list[dict[str, Any]], value: str, what: str) -> int:
    """Label (verbatim — whitespace counts) or index:N to option position."""
    if value.startswith("index:"):
        pos = int(value.removeprefix("index:"))
        if not 0 <= pos < len(options):
            raise ValueError(f"{what}: index {pos} out of range "
                             f"({len(options)} options)")
        return pos
    for i, o in enumerate(options):
        if o["label"] == value:
            return i
    raise ValueError(f"{what}: no option labelled {value!r} "
                     f"(have {[o['label'] for o in options]})")


def resolve_plan(dump: dict[str, Any],
                 answers: AnswerFile) -> list[dict[str, Any]]:
    """Every answer to a (question, option) click. All-or-nothing: any
    unresolvable answer aborts before the first click lands."""
    questions = dump["questions"]
    plan = []
    for p in answers.problems:
        if p.n < 1 or p.n > len(questions):
            raise ValueError(f"question {p.n}: quiz has {len(questions)} "
                             f"questions")
        if len(p.answers) != 1:
            raise ValueError(f"question {p.n}: want exactly 1 answer, "
                             f"have {len(p.answers)}")
        a = p.answers[0]
        if a.type is not None and a.type != "radio":
            raise ValueError(f"question {p.n}: D2L answers are radio, "
                             f"not {a.type!r}")
        if not isinstance(a.value, str):
            raise ValueError(f"question {p.n}: value must be a string")
        q = questions[p.n - 1]
        plan.append({"n": p.n, "group": q["group"],
                     "index": option_index(q["options"], a.value,
                                           f"question {p.n}"),
                     "label": a.value})
    return plan


def diff_checked(plan: list[dict[str, Any]],
                 dump: dict[str, Any]) -> list[dict[str, Any]]:
    """Expected option index vs actually-checked index per planned question."""
    by_n = {q["n"]: q for q in dump["questions"]}
    diffs = []
    for item in plan:
        q = by_n[item["n"]]
        checked = [i for i, o in enumerate(q["options"]) if o["checked"]]
        got = checked[0] if len(checked) == 1 else None
        if got != item["index"]:
            diffs.append({"n": item["n"], "expected": item["index"],
                          "checked": got})
    return diffs


def click_radio(frame: "Frame", group: str, index: int) -> dict[str, Any]:
    return frame.evaluate(_CLICK_JS, {"name": group, "index": index})


def click_save_all(page: "Page", frame: "Frame") -> bool:
    """Exact-text Save All Responses click. Never by index: Submit Quiz
    sits next to it."""
    for scope in (page, frame):
        try:
            if scope.evaluate(_SAVE_ALL_JS, SAVE_ALL_TEXT):
                return True
        except Exception:  # noqa: BLE001 — try the next scope
            continue
    return False


def footer_counter(page: "Page", frame: "Frame") -> dict[str, Any] | None:
    for scope in (frame, page):
        try:
            m = FOOTER_RE.search(scope.locator("body").inner_text())
        except Exception:  # noqa: BLE001 — try the next scope
            continue
        if m:
            return {"saved": int(m.group(1)), "total": int(m.group(2)),
                    "raw": m.group(0)}
    return None


def enter_quiz(page: "Page", url: str, answers: AnswerFile,
               dry_run: bool = False) -> dict[str, Any]:
    """Canary the first click, bulk-click the rest, Save All, verify by
    re-dump diff plus the footer counter. Never submits."""
    page.goto(url)
    frame = find_quiz_frame(page)
    if frame is None:
        return {"url": url, "status": "no_quiz_frame",
                "detail": "no frame holds quiz radios; sign in first?"}
    dump = dump_quiz(frame)
    try:
        plan = resolve_plan(dump, answers)
    except ValueError as e:
        return {"url": url, "status": "fill_error", "detail": str(e),
                "answered_pattern": dump["answered_pattern"]}
    if dry_run:
        return {"url": url, "status": "dry_run_ok", "plan": plan,
                "answered_pattern": dump["answered_pattern"],
                "detail": f"{len(plan)} clicks planned, none made"}
    if not plan:
        return {"url": url, "status": "fill_error",
                "detail": "no answers to enter"}

    first = plan[0]
    r = click_radio(frame, first["group"], first["index"])
    if not r.get("ok") or not r.get("checked"):
        return {"url": url, "status": "canary_failed",
                "detail": f"question {first['n']}: click did not check "
                          f"(found {r.get('found')} radios in group)"}
    page.wait_for_timeout(700)  # let autosave prove itself on the canary
    if diff_checked([first], dump_quiz(frame)):
        return {"url": url, "status": "canary_failed",
                "detail": f"question {first['n']}: re-dump disagrees "
                          f"with the click; stopping before bulk entry"}
    for item in plan[1:]:
        r = click_radio(frame, item["group"], item["index"])
        if not r.get("ok"):
            return {"url": url, "status": "fill_error",
                    "detail": f"question {item['n']}: group has "
                              f"{r.get('found')} radios, want "
                              f"index {item['index']}"}
    if not click_save_all(page, frame):
        return {"url": url, "status": "save_button_missing",
                "detail": f'no button with exact text {SAVE_ALL_TEXT!r}; '
                          f'clicks landed but bulk save is unconfirmed'}
    page.wait_for_timeout(2000)
    final = dump_quiz(frame)
    footer = footer_counter(page, frame)
    diffs = diff_checked(plan, final)
    if diffs:
        return {"url": url, "status": "mismatch",
                "detail": "re-dump differs from intent; answers saved, "
                          "not submitted", "diffs": diffs, "footer": footer}
    return {"url": url, "status": "ok", "plan": plan, "footer": footer,
            "detail": f"{len(plan)} saved "
                      f"({footer['raw'] if footer else 'no footer counter'}); "
                      f"not submitted"}
