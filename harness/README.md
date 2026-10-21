# Harness — scripted hands beneath the answer-entry skill

The skill (`SKILL.md` + `references/`) is the brain: modes, solving,
verification. This is the hands: deterministic, screenshot-free WeBWorK
read/enter through a persistent Chromium profile. One JS call fills a whole
problem; every widget is read back and compared before anything submits.

## Status

| Piece | State | Notes |
|---|---|---|
| Fill + read-back + submit + score | Validated | 13 tests green vs local fixtures |
| MathQuill `.latex('')` + `.write()` entry | Validated live | 8-problem set, Oct 2026, first-try correct; canary still governs new installs |
| Problem-text selectors | **Unvalidated** | Candidate cascade; finalize via `probe` |
| Set enumeration + status | **Unvalidated** | Confirm on a live set page |
| D2L / Top Hat | Not built | Procedures live in `references/`; roadmap |

Nothing here has touched a live page yet. The live-validation protocol below
is the gate before any real set.

## Setup

```bash
cd harness
uv sync --extra dev
uv run playwright install chromium   # large download; on this Mac route via heavy
```

## Workflow

```bash
# 1. Sign in once per site (headed window; sessions persist in .profile/)
uv run harness login https://your-webwork-host/

# 2. Claude solves from dumped text and writes answers.json (schema: answers.example.json)
uv run harness read-set answers.json --out dumps/set-3

# 3. Canary: dry-run problem 1, then live problem 1, confirm the score
uv run harness enter answers.json --dry-run --only 1
uv run harness enter answers.json --only 1

# 4. The rest, then confirm on the set page
uv run harness enter answers.json
uv run harness status https://.../<course>/<Set>/
```

`enter` stops at the first problem that isn't cleanly verified, and exits
nonzero unless every attempted problem scored or dry-ran clean. A read-back
that differs from intent vetoes that problem's submit — no exceptions.

## Live-validation protocol (do this once, on a safe set)

1. `uv run harness probe <problem-url> --save-html dumps/p1.html` — inspect the
   JSON: widget inventory, buttons, which text selector hit.
2. Fix `PROBLEM_TEXT_SELECTORS` / enumeration in `src/answer_entry/webwork.py`
   until `read-problem` returns clean text and the right widget count.
3. `--dry-run --only 1`, then live `--only 1`: fill must land, read-back must
   match, Preview must be clean, score must post.
4. Only then run a full set. Update the Status table above with what you proved.

A past-due set proves entry mechanics only (it often shows answers) — fine for
steps 1–3, useless for validating solving.

## Layout

- `src/answer_entry/browser.py` — persistent profile (`harness/.profile/`)
- `src/answer_entry/model.py` — answers.json schema + validation
- `src/answer_entry/webwork.py` — inventory, fill, read-back, submit, score
- `src/answer_entry/cli.py` — `login probe read-problem read-set enter status`
- `tests/` — schema tests + headless-Chromium fixture tests (`uv run pytest`)

## Roadmap

D2L (JS dump + click + Save All) and Top Hat drivers following the validated
procedures in `references/d2l.md` / `references/tophat.md`; an MCP wrapper so
desktop sessions can call the harness as tools.
