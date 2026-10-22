# Harness — scripted hands beneath the answer-entry skill

The skill (`SKILL.md` + `references/`) is the brain: modes, solving,
verification. This is the hands: deterministic, screenshot-free WeBWorK
read/enter through a persistent Chromium profile. One JS call fills a whole
problem; every widget is read back and compared before anything submits.

## Status

| Piece | State | Notes |
|---|---|---|
| Browser fill + read-back + submit + score | Validated live | 8-problem set, Oct 2026, first-try correct |
| HTTP engine (fetch/parse/replay/submit) | Validated live | Local 8/8 + school HW07-FS26 9/9, ~1 min mechanical |
| Set enumeration (HTTP) | Validated live | School set page, Oct 2026 |
| Unattended Okta+SMS login | Validated live | Full `--full` chain green, Oct 2026 |
| Cookie-only refresh | Live-tested (needs-you path) | `ok` path triggers on next SP-only expiry |
| Set status (HTTP) | Validated live | `http-status` on sim 2.19 set page, Oct 2026 |
| Offline `validate` | Tested | Counts, option labels, checkbox shape |
| Problem-text selectors (browser path) | **Unvalidated** | Candidate cascade; finalize via `probe` |
| D2L dump + enter | Fixture-tested | Shadow-DOM traversal, Save All; needs live mapping check |
| Top Hat read path (JWT API) | Validated live | Open-assignment fetch; closed items 403 (by design) |
| Top Hat submit | Shape-validated | POST shape from live traffic; driver run pending |
| Top Hat recon hygiene | Done | Auth bodies redacted; creds never logged |

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

# Validate offline (counts, option labels, checkbox shape), then canary
# problem 1, then the set (a scoreless submit response stops the run:
# that means the protocol drifted, e.g. a new WeBWorK version)
uv run harness validate answers.json --problems dumps/http-set/problems.json
uv run harness http-enter answers.json --dry-run --only 1
uv run harness http-enter answers.json --only 1
uv run harness http-enter answers.json

# Confirm per-problem scores on the set page
uv run harness http-status https://host/webwork2/Course/Set/
```

## Sessions (expiry, refresh, keep-alive)

School sessions die after a few hours (Incapsula + SSO). Three layers:

1. **Auto-refresh.** `http-fetch`/`http-enter`/`http-status` pre-flight
   the session and, on expiry, redo the SSO dance headlessly with
   profile cookies — no interaction while the school SSO session lives.
2. **Manual refresh.** `harness http-auth --refresh <url>` does the same
   on demand (retries visibly if headless hits the bot-wall).
3. **Keep-alive.** `harness keepalive <url>` prints `alive` / `expired
   (<kind>)` for a scheduler and notifies on repeated failure (log:
   `~/Library/Logs/answer-entry-keepalive.log`). The launchd job
   (`harness/keepalive.plist`, 30-minute tick) runs keepalive and
   refreshes on expiry:

```bash
cp harness/keepalive.plist ~/Library/LaunchAgents/edu.msu.webwork-keepalive.plist
launchctl bootstrap gui/$UID ~/Library/LaunchAgents/edu.msu.webwork-keepalive.plist
```

One user step makes refreshes reliable: at the next interactive
`http-auth`, check **"Keep me signed in"** on the school login. That
extends the SSO session for weeks, so the cookie-only dance heals
every SP expiry without you. Without it, refresh correctly reports
`needs-you` and you sign in again.

## Unattended Okta login (email + password + SMS code)

When the SSO session itself is dead, `http-auth --full` performs one
complete Okta pass: email, Keychain password, SMS authenticator, and
the code read from the Mac Messages database (iPhone texts land there
within seconds). Single attempt, no retries — SSO hammering risks
lockout, so anything unexpected aborts with a screen dump instead.

One-time setup (password never touches files or logs):

```bash
security add-generic-password -s answer-entry-msu -a '<msu-email>' -w
uv run harness http-auth --full 'https://SET-URL' --email '<msu-email>'
```

`fetch`/`enter`/`status` escalate to this automatically when set up
(email remembered, Keychain password present). `keepalive` deliberately
never does — a scheduler must not fire SMS logins on its own.

## Health and recovery

`harness smoke --ww-url <url> --th-code <code>` is the read-only
health check: sessions, Keychain, Messages access, Top Hat API. It
never submits or fires logins. Run it before homework when anything
has been idle, or weekly.

If this Mac dies, everything rebuilds from the repo plus logins:

1. Clone, `uv sync --extra dev`, `uv run playwright install chromium`.
2. `harness http-auth`, `harness th-auth`, Keychain password, Full Disk
   Access for the terminal (SMS codes), Friday class cron (lives in
   the agent session — recreate it).
3. `cp harness/keepalive.plist ~/Library/LaunchAgents/edu.msu.webwork-keepalive.plist`
   + `launchctl bootstrap gui/$UID ~/Library/LaunchAgents/...`.
4. Local sim: `webwork-test-env` is an upstream checkout (never push
   it); `docker compose up -d` + `provision_test_course.py`.

Machine-local state that does NOT survive (all re-created by the
steps above): `.profile/` (browser, jars, tokens), Keychain item,
launchd job, agent cron.

## Parallel solving

Solving is the bottleneck once mechanics take seconds. Split the fetched
dump, solve chunks simultaneously (parallel agents work well — each chunk
is self-contained), merge, enter:

```bash
uv run harness split dumps/http-set/problems.json --out dumps/chunks --chunks 3
# solve chunk-1.answers.json, chunk-2.answers.json, ... in parallel
uv run harness merge dumps/chunks/chunk-*.answers.json -o answers.json
uv run harness validate answers.json --problems dumps/http-set/problems.json
uv run harness http-enter answers.json --only 1   # canary, then the set
uv run harness http-enter answers.json
```

`merge` validates the combined file (shape, duplicates, types) before writing;
`validate` checks it against what was fetched (counts, option labels).

Every command prints per-phase timings (`fetch / parse / preview / submit`).

## D2L quizzes (Playwright)

Same safety shape as the WeBWorK path, following `references/d2l.md`: one
shadow-DOM traversal dumps the whole quiz, clicks land via DOM `.click()`,
bulk entry ends with an exact-text **Save All Responses**, and the driver
**never submits**.

```bash
# Sign in once (persistent profile), then dump the attempt page
uv run harness login https://brightspace.msu.edu/
uv run harness d2l-dump '<quiz-attempt-URL>'

# Confirm the dump's answered pattern against the navigator's badges
# (group n = question n), write answers.json (set_url = attempt URL,
# one label-or-index:N answer per question), then:
uv run harness d2l-enter answers.json --dry-run
uv run harness d2l-enter answers.json
```

Fixture-tested only: the first live run must confirm the group→question
mapping (compare already-answered groups against the navigator) before a
full-quiz enter.

## Top Hat (JWT API, no browser)

Reverse-engineered from live app traffic (`harness recon`, Oct 2026).
Bearer JWT + `Course-Id` header; the JWT lives in the profile's
localStorage and is re-read (self-refreshing) whenever it nears expiry.
Submit responses carry the grade (`graded_response` status + points).

```bash
uv run harness th-auth 'https://app.tophat.com/e/<code>/'   # headed sign-in, export JWT
uv run harness th-fetch '<item-URL>' --folder '<folder>' --out dumps/th-set
uv run harness validate answers.json --problems dumps/th-set/problems.json
uv run harness th-enter answers.json --problems dumps/th-set/problems.json --only 1
uv run harness th-enter answers.json --problems dumps/th-set/problems.json
uv run harness th-status '<item-URL>' --folder '<folder>'
```

Scope: single-part multiple-choice; anything else raises. Only items in
an **open** assignment fetch — closed items 403, which the driver
reports plainly. `recon` redacts auth-endpoint bodies: credentials are
never written to its log.

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
- `src/answer_entry/http_engine.py` — fetch/parse/replay/submit/status, no browser
- `src/answer_entry/d2l.py` — quiz dump/enter, Save All, never submits
- `src/answer_entry/tophat.py` — JWT API client: tree, fetch, submit, status
- `src/answer_entry/okta.py` + `sms.py` — unattended Okta+SMS login
- `src/answer_entry/validate.py` — offline answers-vs-fetch check
- `src/answer_entry/chunks.py` + `timing.py` — split/merge, phase timings
- `src/answer_entry/cli.py` — all commands (see `harness -h`)
- `tests/` — schema, mock-server, fixture, timing tests (`uv run pytest`)

## Roadmap

Top Hat: first live `th-enter` run; non-MC question types as their API
shapes get captured; live-question watcher (needs in-class recon of the
launch flow). D2L's group→question mapping still needs its live
confirmation. No MCP wrapper planned — the workflow lives on web Claude,
which MCP can't reach.
