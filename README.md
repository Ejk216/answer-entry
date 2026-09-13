# webwork-answer-entry

A Claude skill for working WeBWorK problem sets — reading the problems,
solving them, and typing answers into the live math fields without
burning attempts.

WeBWorK's answer boxes are MathQuill live-math editors, not text inputs.
They rewrite input as you type and silently ignore programmatic fill, so
a naive attempt submits blank and costs you a graded attempt. This skill
encodes what actually works: the input syntax, the browser technique, the
traps in common problem types, and a self-verification protocol for when
Claude is solving rather than transcribing.

Course-agnostic. Nothing in it is specific to one school, server, or
semester.

## Install

**claude.ai** — download this repo as a ZIP (green *Code* button →
*Download ZIP*), then Settings → Capabilities → Skills → upload it.

**Claude Code / desktop** — clone into your skills directory:

```bash
git clone https://github.com/Ejk216/webwork-answer-entry.git \
  ~/.claude/skills/webwork-answer-entry
```

The file needs to land at `~/.claude/skills/webwork-answer-entry/SKILL.md`.
Restart or start a new session and Claude picks it up.

## What you need

A browser Claude can drive. Either works:

- the **built-in browser** in the Claude desktop app — nothing to install
- **Claude in Chrome**, the extension, driving your own Chrome

The skill's techniques are identical in both. Availability depends on
your plan and setup.

You sign in to your own LMS and WeBWorK. Claude never asks for
credentials. The desktop app's built-in browser keeps a profile between
sessions, so signing in once usually sticks; Chrome uses whatever session
you already have.

## Use

Paste the URL of the problem set and say which mode you want:

| You say | Claude does |
|---|---|
| "Here are my answers, enter them" | **Enter** — types them, confirms each on-screen problem matches |
| "Check my work" | **Check** — solves independently *first*, then diffs against yours |
| "Do the whole set" | **Solve** — works everything, self-verifies, fills, previews, submits |

Solve mode submits answers you have not seen. Claude confirms before
running it.

## A word on how to use this

This is a tool for working problems, and it is at its most useful when
you already understand the material and the entry is the tedious part —
a twenty-problem set of algebra you can already do, entered by hand,
one MathQuill box at a time.

Check mode is the one worth reaching for while you are still learning:
you solve, Claude solves independently, and the disagreements are where
the learning is. Solve mode hands in work you did not do. Your course's
academic integrity policy governs that, not this README — know what yours
says before you use it.

## License

MIT — see [LICENSE](LICENSE).
