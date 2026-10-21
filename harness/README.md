# Harness — scripted hands beneath the answer-entry skill

The skill (`SKILL.md` + `references/`) is the brain: modes, solving,
verification. This is the hands: deterministic, screenshot-free WeBWorK
read/enter through a persistent Chromium profile. One JS call fills a whole
problem; every widget is read back and compared before anything submits.

## Status

| Piece | State | Notes |
|---|---|---|
| Browser fill + read-back + submit + score | Validated live | 8-problem set, Oct 2026, first-try correct |
| HTTP engine (fetch/parse/replay/submit) | Validated live | 8/8 first-try on local 2.19, ~10 s mechanical; mock-server tests green |
| Problem-text selectors (browser path) | **Unvalidated** | Candidate cascade; finalize via `probe` |
| Set enumeration + status | **Unvalidated** | Confirm on a live set page |
| D2L / Top Hat | Not built | Procedures live in `references/`; roadmap |

## HTTP engine (no browser)

The fast path: cookie-authenticated HTTP against WeBWorK directly. Generic
form replay — no hardcoded field names — with parallel fetch.

```bash
# One-time: sign in through the browser, export cookies to the engine
uv run harness http-auth http://localhost:8080/webwork2/testcourse/

# Fetch + parse every problem (parallel; saves HTML + problems.json).
# Pass a set URL directly (links harvested, effectiveUser included) or an
# answers file. --workers 2 suits school servers; raise for local.
uv run harness http-fetch https://host/webwork2/Course/Set/ --out dumps/http-set --figures

# Canary problem 1, then the set (a scoreless submit response stops the run:
# that means the protocol drifted, e.g. a new WeBWorK version)
uv run harness http-enter answers.json --dry-run --only 1
uv run harness http-enter answers.json --only 1
uv run harness http-enter answers.json
```

## Parallel solving

Solving is the bottleneck once mechanics take seconds. Split the fetched
dump, solve chunks simultaneously (parallel agents work well — each chunk
is self-contained), merge, enter:

```bash
uv run harness split dumps/http-set/problems.json --out dumps/chunks --chunks 3
# solve chunk-1.answers.json, chunk-2.answers.json, ... in parallel
uv run harness merge dumps/chunks/chunk-*.answers.json -o answers.json
uv run harness http-enter answers.json --only 1   # canary, then the set
uv run harness http-enter answers.json
```

`merge` validates the combined file (shape, duplicates, types) before writing.

Every command prints per-phase timings (`fetch / parse / preview / submit`).

## Local WeBWorK 2.19 (1:1 test environment)

Real server, same version as the school, running in Docker one directory over
(`Developer/webwork-test-env`). Free attempts, zero stakes — the proving
ground for the HTTP engine before it touches a live set.

```bash
cd ../webwork-test-env
docker compose up -d        # first boot clones the OPL; takes a while
uv run --project ../webwork-answer-entry/harness \
  python provision_test_course.py   # course `test`, set DemoTest, users prof1/student1
open http://localhost:8080/webwork2/
```

Test accounts: prof1 / testprofpass, student1 / teststudentpass (local only).
Courses live in `ww-courses/` (bind-mounted). The DemoTest set is the HTTP
engine's regression target: re-run `http-enter` against it after any engine
change. Stop with `docker compose stop`; `down` also stops the DB (course data
survives in `ww-courses/` + the `webwork2_mysql` volume).

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
