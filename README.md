# webwork-answer-entry

A Claude skill for working online problem sets — reading the problems,
solving them, and entering answers without burning attempts.

Covers **WeBWorK** and **Top Hat**. Course-agnostic: nothing in it is tied to
one school, server, or semester.

WeBWorK's typed answer boxes are MathQuill live-math editors, not text inputs.
They rewrite input as you type and silently ignore programmatic fill, so the
obvious approach submits a *blank* answer and spends a graded attempt telling
you nothing. This skill encodes what actually works: which entry method each
widget needs, the input syntax, the traps in common problem types, and a
self-verification protocol for when Claude is solving rather than transcribing.

## Install

**claude.ai** — download this repo as a ZIP (green *Code* button →
*Download ZIP*), then Settings → Capabilities → Skills → upload it.

**Claude Code / desktop** — clone into your skills directory:

```bash
git clone https://github.com/Ejk216/webwork-answer-entry.git \
  ~/.claude/skills/webwork-answer-entry
```

The file needs to land at `~/.claude/skills/webwork-answer-entry/SKILL.md`.
Start a new session and Claude picks it up.

## What you need

**A browser Claude can drive.** Either works — no measured speed difference
between them, and they keep separate logins:

- **Claude in Chrome** — the extension, driving your own Chrome
- **the built-in browser** in the Claude desktop app — nothing to install

**Expect one permission stop.** Claude in Chrome gates access per site, so the
first time it opens your LMS or WeBWorK host you'll be asked to allow that
site. That's normal and one-time — allow it and tell Claude to continue.

**You sign in.** Claude never asks for credentials. If a page comes back as a
login screen, take the browser, sign in, and say continue.

**Model and effort.** Low effort is right for almost all of this — the clock is
dominated by browser round-trips, not thinking, and the skill carries the
procedure. A mid-tier model handles routine sets fine. Save a stronger model
for graph-heavy sets, conceptually fussy ones, or sets with few attempts.

## Use

Paste the URL of the problem set and say which mode you want:

| You say | Claude does |
|---|---|
| "Here are my answers, enter them" | **Enter** — types them, confirming each on-screen problem matches what you wrote |
| "Check my work" | **Check** — solves independently *first*, then compares; a disagreement stops the run |
| "Do the whole set" | **Solve** — works everything, self-verifies, enters, submits |

On WeBWorK the default path is to read every problem, solve the whole set at
once, then enter them one at a time — about 3× faster than going
problem-by-problem, with the same accuracy. Top Hat runs one at a time, since
there's nothing to bulk-read.

**On a first run in a new course, prove the path before spending attempts:**
use Check mode on a problem you've already solved, or enter problem 1 alone and
confirm its score before letting it do the rest.

## A word on how to use this

This is at its most useful when you already understand the material and the
entry is the tedious part — a twenty-problem set you can already do, typed in
by hand one MathQuill box at a time.

Check mode is the one worth reaching for while you're still learning: you
solve, Claude solves independently, and the disagreements are where the
learning is. Solve mode hands in work you did not do. Your course's academic
integrity policy governs that, not this README — know what yours says.

## License

MIT — see [LICENSE](LICENSE).
