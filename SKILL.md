---
name: answer-entry
description: "Solve and enter answers for online homework in WeBWorK, Top Hat, or d2L (math, statistics, physics, coding). Use whenever the user points at a platform and wants problems worked, answers entered, and submitted."
---

# Online Problem Sets (WeBWorK, Top Hat, d2L Quiz)

Version: 2026-10-21 r2. This skill is five files: this router plus
`references/webwork.md`, `references/tophat.md`, `references/d2l.md` (entry
mechanics per platform) and `references/solving.md` (verification and solution
procedures, needed only in Solve/Check modes). Read the reference for the
platform you're on before touching a problem. On any change, bump the version
date and reinstall from the repo — a stale installed copy missing whole
sections is a known failure mode.

**Identify the platform first** from the open tab: a webwork2 URL → WeBWorK,
entry mechanics in **references/webwork.md**. `app.tophat.com` → Top Hat
(**references/tophat.md**). A `d2l.*` URL — especially
`/d2l/le/enhancedSequenceViewer/` or `/d2l/lms/quizzing/` — → D2L Quiz
(**references/d2l.md**). The shared sections below (setup, modes, stakes,
pipeline, speed, recovery, tool notes) apply to all three.

For WeBWorK, two facts drive everything:

1. Typed answer boxes are **MathQuill live-math editors**, not text inputs. They rewrite input as it is typed and silently ignore programmatic fill.
2. Submissions are **metered** (often 3–12 attempts; extra-credit sets may be unlimited). A blank or wrong submission burns one. **Preview is free and unlimited.**

Because attempts can be the scarce resource: **a timed-out or failed tool call may still have executed.** Screenshot and check page state before retrying anything that submits — a blind retry can burn a second attempt or double-submit.

## Before you start

Setup, before any problem is touched.

### A browser is required

This skill drives a real browser: it reads problems off the rendered page and
types into live widgets, and on D2L it runs JavaScript inside the quiz frame.
There is no text-only path. Either browser works — measured no speed
difference, and they keep **separate logins**:

- **Claude in Chrome** — the extension, driving your own Chrome. Existing D2L,
  Top Hat or WeBWorK sessions are already live in it.
- **The Claude desktop app's built-in browser** — a pane inside the app,
  nothing to install; keeps its own profile across sessions.

If neither is available, say so and stop rather than working the set blind.

### Tool bootstrap (Claude in Chrome)

Tool names below use the suffix only (`navigate`, not
`mcp__claude-in-chrome__navigate`); use whichever prefix the session carries.
If the only Claude in Chrome tool present is `enable__mcp__claude-in-chrome`,
call it first. If the tools are deferred, load everything this skill needs in
ONE ToolSearch call — each extra ToolSearch costs a full round trip:

```
select:mcp__claude-in-chrome__tabs_context_mcp,mcp__claude-in-chrome__tabs_create_mcp,mcp__claude-in-chrome__tabs_close_mcp,mcp__claude-in-chrome__navigate,mcp__claude-in-chrome__computer,mcp__claude-in-chrome__read_page,mcp__claude-in-chrome__get_page_text,mcp__claude-in-chrome__find,mcp__claude-in-chrome__form_input,mcp__claude-in-chrome__javascript_tool,mcp__claude-in-chrome__read_network_requests
```

Then call `tabs_context_mcp` and open a **new tab** for the work — never drive
the user's own tabs: the user may click or type mid-run and corrupt an entry.
(If the user points at an already-open tab — "this set" — work there instead.)
Close tabs you created when done. "One batch" in this skill means independent
calls issued together in one block.

### Site permission is the first thing that will stop you (Chrome)

Claude in Chrome gates access per site. The first `navigate` to a new LMS,
Top Hat or WeBWorK host returns a permission stop, not a page. This is normal
and one-time per site: tell the user to allow the site in the extension, wait,
and retry. Do not treat it as a broken tool or work around it.

### Getting to the work

Claude cannot guess a course's address. Ask for either:

- **a direct link** — paste the URL of the set, quiz or problem page (fastest)
- **the LMS and course** (D2L, Canvas, Blackboard) and navigate through

WeBWorK problem pages have predictable URLs once you have one:
`/<course>/<Set>/<n>/`, set page `/<course>/<Set>/`.

### Signing in is the user's job

Claude has no credentials and will not ask for them. A page that comes back as
a login screen is the signal to hand the browser back: the user signs in, then
says continue. SSO redirect chains and 2FA prompts belong to the user.

If the session also carries the Codex-login MCP tools, use
`session_status(domain)` to check a sign-in without prompting anyone, and
`open_page` for read-only pages (quiz lists, set pages). They cannot click or
submit, so entry still goes through the browser — and they may be absent (e.g.
web sessions), in which case this paragraph doesn't apply.

### Name the mode

"Enter these answers," "check my work," or "do the whole set." Solve mode
submits work the user has not reviewed — confirm that mode rather than
inferring it.

### Model and effort

Wall-clock is dominated by browser round-trips, not thinking, and this file
carries the procedure — so **low effort is right for nearly all of it**. A
mid-tier model handles routine sets. Reach for a stronger model on sets that
are graph-heavy, conceptually fussy, or low on attempts, where reading a
close call off a mosaic plot or boxplot is the real work.

### First run on a new course or platform (the canary rule)

Prove the path before spending attempts. Either run **Check** mode against a
problem the user has already solved, or enter problem 1 alone and confirm its
score before touching the rest. A past-due set is a safe place to test entry
mechanics — but it often displays the answers, so it proves nothing about
solving.

## Pick the mode first

| Situation | Mode |
|---|---|
| User supplies their answers | **Enter** — type them, confirm the on-screen problem matches, submit |
| User wants their work checked | **Check** — solve independently *before* reading their answers, then diff |
| User supplies nothing | **Solve** — work everything, self-verify, fill, submit |

In **Solve** mode, show the worked reasoning for each problem — the actual steps, not just the answer. In **Check** mode, solve first and read their answers second; reading theirs first guarantees anchoring and rubber-stamping. A disagreement means stop: enter neither, show both derivations, let the user adjudicate.

"Complete all open assignments": load the course's assignment list, then each open set's page (`/<course>/<Set>/`) to see per-problem status; skip sets already at 100%; do the earliest-due set first.

## Read the stakes before entering anything

Attempts allowed, due date and time limit decide how careful to be. Look, then say which regime you're in:

- **Attempts** — allowed and remaining. Metered (WeBWorK, often 3–12) or unlimited (many D2L quizzes, extra-credit sets)? A wrong answer on an unlimited quiz is nearly free.
- **Due date and time limit** — is the clock a factor?
- **Grading rule** — best attempt or last? (Top Hat Resubmit grading is still unverified — see references/tophat.md.)
- **Feedback** — are correct answers shown after the attempt? This decides whether a mistake is recoverable.

Don't assume — look, then say which regime you're in. Metered attempts → verify every problem before moving on. Free attempts → enter fast, verify once at the end (see Speed rules).

**Never answer for the user:** attitude and self-efficacy survey items ("I can master the content…"), prior-experience questions, or anything else with no correct answer. These often sit as a tail section on D2L pre-labs, usually flagged as not affecting the grade. Fill the graded questions, leave these blank, and tell the user exactly which ones are theirs to finish.

## Working a set: read all, solve all, then enter (default)

**This is the default way to work a WeBWorK set.** Read every problem first,
solve the whole set at once, then go back and enter one problem at a time.
Measured: 9-problem set in ~4 min this way vs ~13 min problem-by-problem, all
first-try correct in both. Solving in one pass is also more accurate than
solving between page loads — shared setups and carry-through parts are visible
at once. D2L follows the same shape by a different route: one JavaScript pass
dumps the whole quiz, then answers go in together.

1. **Bulk text read — one batch.** Problem pages have direct URLs `/<course>/<Set>/<n>/`. One `browser_batch` of `navigate` + `get_page_text` × every problem. This replaces the hardcopy PDF: downloading it needs the user's permission plus a connected folder to read it, and gives no widget info.
2. **Solve everything text-solvable immediately**; compute numerics with a short python call (one call for the whole set).
3. **Screenshot only what needs eyes** — one batch of `navigate` + `screenshot` for problems whose text references a plot/table image, plus scroll-down screenshots where a Part 2 figure or option list sits below the fold. `zoom` to read boxplot quartiles or bar heights.
4. **Report answers** (needs-review first), then **enter one problem per batch**: fill → click Submit → `find` "score received message" → `navigate` to next problem → `find` its inputs. Each batch both confirms the last problem and sets up the next.
5. Finish on the set page (`get_page_text`) to confirm every status reads 100%.

**The canary rule still applies:** confirm problem 1's score before trusting a fill method across the set.

### Falling back to problem-by-problem

The older serial method — read one problem, solve it, enter it, submit, move on
— is the fallback, not the default. Use it when:

- **the platform is Top Hat** — one question per page, sidebar navigation, no
  predictable URLs, so there is nothing to bulk-read
- **problem URLs aren't predictable** on this install, or the set page won't
  enumerate them
- **the canary fails** — problem 1's fill method didn't land; fix the method
  serially before scaling it across the set
- **the set is almost entirely figures or multi-part** — the bulk text read
  returns little, so batching saves nothing

Falling back costs time, not accuracy. Prefer it over guessing.

### Images are lost silently

`get_page_text` **drops images entirely** and gives no sign. A graph problem comes back as bare labels or just the stem. Text mentioning "below", "shown", "plot", "histogram", "boxplot", or "clicking on any image" means screenshot it. Also: option lists may be truncated or padded in text (e.g. a select offering A–H while only A–F are printed) — screenshot when options look incomplete. Default graph-interpretation problems to *needs review* unless unambiguous.

## Speed rules

Wall-clock is dominated by browser round-trips, not thinking. Spend round-trips where attempts are at risk, nowhere else:

1. **Prefer the scripted harness where available.** On a machine with the skill repo checked out, `harness/` (see harness/README.md) reads and enters WeBWorK sets deterministically — no screenshots, programmatic read-back before submit. Hand-driven entry below is the fallback for sessions without shell access (e.g. claude.ai web). In hand-driven entry, **drive widgets from JavaScript where possible**: one JS call beats click-type-screenshot per box and can't misclick from a stale frame. WeBWorK MathQuill fields have a JS API — try it first, canary-gated, with click-type as fallback (references/webwork.md). D2L is JS-driven throughout.
2. **Match verification depth to the stakes.** Metered attempts: confirm each problem's score before moving on. Free attempts: enter everything, verify once at the end.
3. **Minimise Preview.** After the canary passes, Preview only the first field of each new widget/syntax type and any entry with fractions, radicals or intervals — never plain decimals box-by-box.
4. **Never re-read what you already hold.** D2L question count comes from the JS dump, not the navigator scrollbar; WeBWorK problem text comes from the bulk read, not re-navigation. End each problem batch navigated to the next problem so its screenshot doubles as the next setup.
5. **Solve in parallel, enter in sequence** (see Parallelism). Enter mode skips references/solving.md entirely.

## When things go wrong

- **Tool call timed out or failed:** assume it may still have executed — screenshot and check page state before retrying anything that submits (see above).
- **"N of the questions remain unanswered" or a lower score than expected:** a fill didn't land. Change the entry method and canary the new one on problem 1 before spending more attempts.
- **An attempt burned unexpectedly:** stop, re-read the stakes (attempts remaining), and say the new regime before continuing.
- **Login screen or SSO/2FA mid-run:** hand the browser back; signing in is the user's job.
- **Due date passes or the set closes mid-run:** stop entering, report what landed and what didn't.

## Tool efficiency notes

- In `browser_batch`, a `scroll` action **already returns its own screenshot**. Adding a `screenshot` after it duplicates the image and wastes tokens.
- Coordinates inside a batch refer to the screenshot taken *before* the call. So a batch can click a target you've already seen and then navigate and capture the next view — but it can never click something first revealed inside the same batch.
- `find` and `read_page` refs stay valid only until the page reloads.
- Inside `browser_batch`, name sub-actions WITHOUT the `mcp__` prefix (`get_page_text`, not `mcp__claude-in-chrome__get_page_text`) — prefixed names fail on the sidepanel transport.

## Parallelism

One browser tab means entry stays sequential — parallel agents in the same Chrome would fight over the page. Agents help only for **solving** (split a large multi-set batch across solvers from the bulk-read text) or for an independent second solve on low-attempt numeric problems. With the harness, entry is serial by design (the school server bounces concurrent requests); solve in parallel via `harness split`/`merge` instead.

## Improving this skill

After a run, compare against these files and propose updates if something was wrong, missing, slow, or cost an attempt. Net-zero budget; one incident is a note, a repeat is a rule; separate observation from inference; keep course-specific facts (hosts, conventions) in memory, not here. Bump the version date on any change.

**Start any proposed rewrite from the current files, and keep `Before you start`
and the default/fallback framing.** A saved proposal replaces the whole file,
and setup guidance has been silently dropped this way twice. Mode docs were
dropped the same way once — after any rewrite, verify the mode table still has
all three rows before saving.
