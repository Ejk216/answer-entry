"""Deterministic WeBWorK read/enter.

Status: page-shape selectors are UNVALIDATED (no live page seen yet) and live
behind the ``probe`` command for finalization. The fill/read-back/submit/score
logic is validated against local fixtures (see tests/).

Safety rule, mirroring the skill's canary: nothing is submitted unless every
filled widget reads back exactly what was intended.
"""
from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

from .model import AnswerFile, ProblemAnswers

if TYPE_CHECKING:
    from playwright.sync_api import BrowserContext, Page

# Candidate selectors for the rendered problem statement, best first.
# UNVALIDATED — finalize against a live page via `harness probe`.
PROBLEM_TEXT_SELECTORS = (
    ".problem-content",
    ".problem",
    "#problemMainForm",
    "main",
    "article",
)

SUBMIT_NAME = re.compile(r"submit answers|check answers|^submit$|submit", re.IGNORECASE)
PREVIEW_NAME = re.compile(r"preview", re.IGNORECASE)

SCORE_RE = re.compile(r"You received a score of\s+(\d+(?:\.\d+)?)\s*%")
UNANSWERED_RE = re.compile(r"(\d+)\s+of the questions remain unanswered")
ALL_CORRECT = "All of the answers are correct."

_INVENTORY_JS = """() => {
  const labelOf = (el) => {
    const lab = el.closest('label');
    if (lab) return lab.innerText.trim();
    if (el.id) {
      const l = document.querySelector(`label[for="${el.id}"]`);
      if (l) return l.innerText.trim();
    }
    return (el.getAttribute('aria-label') || el.value || '').trim();
  };
  const out = [];
  const counters = {mathquill: 0, select: 0, text: 0};
  const radioGroups = new Map();
  const checkGroups = new Map();
  const groupFor = (map, name) => {
    if (!map.has(name)) {
      const g = {options: []};
      map.set(name, g);
      out.push(g);
    }
    return map.get(name);
  };
  const els = document.querySelectorAll(
    '.mq-editable-field, select, input[type=radio], input[type=checkbox], input[type=text]');
  els.forEach((el) => {
    if (el.classList.contains('mq-editable-field')) {
      let current = null;
      try {
        current = MathQuill.getInterface(2).MathField(el).latex();
      } catch (e) { /* interface unavailable; fill step will report it */ }
      out.push({kind: 'mathquill', index: counters.mathquill++, current});
    } else if (el.tagName === 'SELECT') {
      out.push({kind: 'select', index: counters.select++,
        name: el.name || null,
        options: [...el.options].map(o => ({label: o.text.trim(), value: o.value}))});
    } else if (el.type === 'radio') {
      const g = groupFor(radioGroups, el.name || '(unnamed)');
      g.kind = 'radio'; g.name = el.name || null;
      g.options.push({label: labelOf(el), value: el.value, checked: el.checked});
    } else if (el.type === 'checkbox') {
      const g = groupFor(checkGroups, el.name || '(unnamed)');
      g.kind = 'checkbox'; g.name = el.name || null;
      g.options.push({label: labelOf(el), value: el.value, checked: el.checked});
    } else {
      out.push({kind: 'text', index: counters.text++,
        name: el.name || null, current: el.value});
    }
  });
  return out;
}"""

_MQ_FILL_JS = """({index, latex}) => {
  const els = document.querySelectorAll('.mq-editable-field');
  const el = els[index];
  if (!el) return {ok: false, error: `no MathQuill field at index ${index}`};
  if (typeof MathQuill === 'undefined')
    return {ok: false, error: 'MathQuill is undefined on this page'};
  const f = MathQuill.getInterface(2).MathField(el);
  try { f.select(); } catch (e) { /* no selection API; fields start empty on fresh load */ }
  f.write(latex);
  return {ok: true, readback: f.latex()};
}"""

_MQ_READ_JS = """(index) => {
  const els = document.querySelectorAll('.mq-editable-field');
  if (!els[index]) return null;
  return MathQuill.getInterface(2).MathField(els[index]).latex();
}"""


def values_match(intended: str, actual: str | None) -> bool:
    """Read-back comparison. Strip-only: anything subtler is a mismatch the
    caller must report, not paper over."""
    return actual is not None and intended.strip() == actual.strip()


def extract_text(page: "Page") -> dict[str, Any]:
    """Best-effort problem statement plus which selector produced it."""
    for selector in PROBLEM_TEXT_SELECTORS:
        loc = page.locator(selector).first
        if loc.count() and (text := loc.inner_text().strip()):
            return {"text": text, "selector": selector,
                    "confidence": "high" if selector != "main" else "medium"}
    body = page.locator("body").inner_text().strip()
    return {"text": body, "selector": "body", "confidence": "low"}


def inventory_widgets(page: "Page") -> list[dict[str, Any]]:
    """Every answer widget in DOM order. One JS call, no screenshots."""
    return page.evaluate(_INVENTORY_JS)


def _option_position(options: list[dict[str, Any]], value: str, what: str) -> int:
    if value.startswith("index:"):
        pos = int(value.removeprefix("index:"))
        if not 0 <= pos < len(options):
            raise ValueError(f"{what}: index {pos} out of range ({len(options)} options)")
        return pos
    for i, opt in enumerate(options):
        if opt["label"] == value:
            return i
    labels = [o["label"] for o in options]
    raise ValueError(f"{what}: no option labelled {value!r} (have {labels})")


def fill_mathquill(page: "Page", index: int, latex: str) -> dict[str, Any]:
    return page.evaluate(_MQ_FILL_JS, {"index": index, "latex": latex})


def fill_select(page: "Page", index: int, value: str, options: list[dict[str, Any]]) -> str:
    pos = _option_position(options, value, "select")
    page.locator("select").nth(index).select_option(index=pos)
    return options[pos]["label"]


def fill_radio(page: "Page", name: str | None, value: str, options: list[dict[str, Any]]) -> str:
    pos = _option_position(options, value, "radio")
    if name:
        loc = page.get_by_role("radio", name=options[pos]["label"])
        if not loc.count():
            loc = page.locator(f'input[type=radio][name="{name}"]').nth(pos)
    else:
        loc = page.locator("input[type=radio]").nth(pos)
    loc.check()
    if not loc.is_checked():
        raise RuntimeError(f"radio option {value!r} did not stay checked")
    return options[pos]["label"]


def fill_checkbox(page: "Page", name: str | None, values: list[str],
                  options: list[dict[str, Any]]) -> list[str]:
    filled = []
    for value in values:
        pos = _option_position(options, value, "checkbox")
        if name:
            loc = page.locator(f'input[type=checkbox][name="{name}"]').nth(pos)
        else:
            loc = page.locator("input[type=checkbox]").nth(pos)
        loc.check()
        if not loc.is_checked():
            raise RuntimeError(f"checkbox option {value!r} did not stay checked")
        filled.append(options[pos]["label"])
    return filled


def fill_text(page: "Page", index: int, value: str) -> str:
    loc = page.locator("input[type=text]").nth(index)
    loc.fill(value)
    return loc.input_value()


def read_back(page: "Page", widgets: list[dict[str, Any]]) -> list[Any]:
    """Current value of every widget, in inventory order."""
    values: list[Any] = []
    for w in widgets:
        kind = w["kind"]
        if kind == "mathquill":
            values.append(page.evaluate(_MQ_READ_JS, w["index"]))
        elif kind == "select":
            values.append(page.locator("select").nth(w["index"]).input_value())
        elif kind == "text":
            values.append(page.locator("input[type=text]").nth(w["index"]).input_value())
        elif kind == "radio":
            checked = [o["label"] for o in w["options"] if o["checked"]]
            # re-read live state rather than trusting the earlier snapshot
            namesel = f'[name="{w["name"]}"]' if w["name"] else ""
            live = page.locator(f"input[type=radio]{namesel}").evaluate_all(
                "els => els.map(e => e.checked)")
            checked = [o["label"] for o, c in zip(w["options"], live) if c]
            values.append(checked[0] if checked else None)
        elif kind == "checkbox":
            namesel = f'[name="{w["name"]}"]' if w["name"] else ""
            live = page.locator(f'input[type=checkbox]{namesel}').evaluate_all(
                "els => els.map(e => e.checked)")
            values.append([o["label"] for o, c in zip(w["options"], live) if c])
    return values


def click_preview(page: "Page") -> bool:
    """Click Preview if present (unlocks multi-part problems). Free and unlimited."""
    btn = page.get_by_role("button", name=PREVIEW_NAME)
    if btn.count():
        btn.first.click()
        page.wait_for_timeout(1000)
        return True
    inp = page.locator("input[type=submit][value*=Preview], input[type=button][value*=Preview]")
    if inp.count():
        inp.first.click()
        page.wait_for_timeout(1000)
        return True
    return False


def click_submit(page: "Page") -> None:
    btn = page.get_by_role("button", name=SUBMIT_NAME)
    if btn.count():
        btn.first.click()
        return
    inp = page.locator("input[type=submit]")
    if inp.count():
        inp.first.click()
        return
    raise RuntimeError("no Submit button found")


def parse_score_text(text: str) -> dict[str, Any]:
    if m := UNANSWERED_RE.search(text):
        return {"percent": None, "unanswered": int(m.group(1)),
                "verdict": f"{m.group(1)} of the questions remain unanswered"}
    if m := SCORE_RE.search(text):
        return {"percent": float(m.group(1)), "unanswered": 0,
                "all_correct": ALL_CORRECT in text,
                "verdict": m.group(0)}
    return {"percent": None, "unanswered": None, "verdict": "no score message found"}


def read_score(page: "Page", timeout_ms: int = 15000) -> dict[str, Any]:
    try:
        page.get_by_text(SCORE_RE, exact=False).first.wait_for(timeout=timeout_ms)
    except Exception:
        pass  # fall through to parse whatever is there
    return parse_score_text(page.locator("body").inner_text())


def _fill_one(page: "Page", widget: dict[str, Any], value: object) -> Any:
    kind = widget["kind"]
    if kind == "mathquill":
        assert isinstance(value, str)
        result = fill_mathquill(page, widget["index"], value)
        if not result.get("ok"):
            raise RuntimeError(f"MathQuill fill failed: {result.get('error')}")
        return result["readback"]
    if kind == "select":
        assert isinstance(value, str)
        return fill_select(page, widget["index"], value, widget["options"])
    if kind == "radio":
        assert isinstance(value, str)
        return fill_radio(page, widget.get("name"), value, widget["options"])
    if kind == "checkbox":
        assert isinstance(value, list)
        return fill_checkbox(page, widget.get("name"), value, widget["options"])
    if kind == "text":
        assert isinstance(value, str)
        return fill_text(page, widget["index"], value)
    raise ValueError(f"unknown widget kind {kind!r}")


def enter_problem(page: "Page", problem: ProblemAnswers, url: str,
                  dry_run: bool = False) -> dict[str, Any]:
    """Fill one problem, verify every read-back, Preview, submit unless dry-run.

    Multi-part problems unlock later parts on Preview, so filling runs in
    passes: fill what's visible, Preview, fill what appeared, until every
    answer is placed or no new widget appears.
    """
    page.goto(url)
    try:
        page.get_by_text("Login").first.wait_for(timeout=2000)
        return {"n": problem.n, "url": url, "status": "login_required",
                "detail": "page looks like a login screen; run `harness login` first"}
    except Exception:
        pass

    filled: list[Any] = []
    widgets = inventory_widgets(page)
    for _ in range(3):  # fill passes; 3 is plenty for unveil-on-Preview parts
        while len(filled) < len(widgets) and len(filled) < len(problem.answers):
            i = len(filled)
            widget, answer = widgets[i], problem.answers[i]
            if answer.type is not None and answer.type != widget["kind"]:
                return {"n": problem.n, "url": url, "status": "type_mismatch",
                        "detail": f"answer[{i}] declares {answer.type!r} "
                                  f"but widget is {widget['kind']!r}; not submitted"}
            try:
                filled.append(_fill_one(page, widget, answer.value))
            except Exception as e:  # noqa: BLE001 — report, never submit blind
                return {"n": problem.n, "url": url, "status": "fill_error",
                        "detail": f"answer[{i}] ({widget['kind']}): {e}"}
        if len(filled) == len(problem.answers):
            break
        click_preview(page)
        new_widgets = inventory_widgets(page)
        if len(new_widgets) <= len(widgets):
            break
        widgets = new_widgets

    if len(filled) < len(problem.answers):
        return {"n": problem.n, "url": url, "status": "widget_shortage",
                "detail": f"{len(problem.answers)} answers but only {len(widgets)} "
                          f"widgets found; not submitted"}
    if len(problem.answers) < len(widgets):
        return {"n": problem.n, "url": url, "status": "answer_shortage",
                "detail": f"{len(widgets)} widgets but only {len(problem.answers)} "
                          f"answers supplied; not submitted"}

    # Read every widget back and compare against intent. Any mismatch vetoes submit.
    actual = read_back(page, widgets)
    mismatches = []
    for i, (answer, got) in enumerate(zip(problem.answers, actual)):
        want = answer.value
        ok = (sorted(want) == sorted(got) if isinstance(want, list)
              else values_match(want, got if isinstance(got, str) else None)
              or (widgets[i]["kind"] == "select" and _select_matches(want, got, widgets[i])))
        if not ok:
            mismatches.append({"answer": i, "kind": widgets[i]["kind"],
                               "intended": want, "read_back": got})
    if mismatches:
        return {"n": problem.n, "url": url, "status": "mismatch",
                "detail": "read-back differs from intent; not submitted",
                "mismatches": mismatches}

    click_preview(page)  # free; validates syntax server-side
    if dry_run:
        return {"n": problem.n, "url": url, "status": "dry_run_ok",
                "detail": f"{len(filled)} answers filled and verified, not submitted"}
    click_submit(page)
    score = read_score(page)
    status = "ok" if score.get("percent") == 100 else "submitted"
    return {"n": problem.n, "url": url, "status": status,
            "score": score, "detail": score["verdict"]}


def _select_matches(want: str, got: str | None, widget: dict[str, Any]) -> bool:
    """Select read-back is the option *value*; the answer names the *label*."""
    if want.startswith("index:"):
        return got == widget["options"][int(want.removeprefix("index:"))]["value"]
    return any(o["label"] == want and o["value"] == got for o in widget["options"])


def read_problem(page: "Page", url: str) -> dict[str, Any]:
    page.goto(url)
    text = extract_text(page)
    widgets = inventory_widgets(page)
    return {"url": url, "text": text["text"], "text_via": text["selector"],
            "text_confidence": text["confidence"], "widgets": widgets}


def enumerate_set(page: "Page", set_url: str) -> list[str]:
    """Problem URLs from a set page. UNVALIDATED — confirm against a live set."""
    page.goto(set_url)
    base = set_url.rstrip("/")
    hrefs = page.locator("a[href]").evaluate_all("els => els.map(e => e.href)")
    found: dict[int, str] = {}
    for href in hrefs:
        m = re.match(re.escape(base) + r"/(\d+)/?$", href)
        if m:
            found[int(m.group(1))] = href
    return [found[n] for n in sorted(found)]


def read_set(context: "BrowserContext", answers: AnswerFile) -> list[dict[str, Any]]:
    """Read every problem in an answer file's set (URLs from the file)."""
    page = context.new_page()
    try:
        return [read_problem(page, answers.problem_url(p)) for p in answers.problems]
    finally:
        page.close()


def set_status(page: "Page", set_url: str) -> dict[str, Any]:
    """Best-effort per-problem status from the set page. UNVALIDATED."""
    page.goto(set_url)
    text = page.locator("body").inner_text()
    rows = re.findall(r"(\d+)\s+(\d+(?:\.\d+)?)\s*%", text)
    return {"url": set_url, "status_rows": [{"n": int(n), "percent": float(p)} for n, p in rows],
            "raw_confidence": "low — confirm against a live set page"}
