---
name: webwork-answer-entry
description: "Solve and enter answers for WeBWorK problem sets in any course (math, statistics, physics) on any WeBWorK install. Use whenever the user points at WeBWorK and wants problems worked, answers typed in, or their own work checked — including sets where the user supplies no answers and Claude must solve, self-verify, and submit. Covers solution procedures and their traps, self-verification, MathQuill input syntax, which browser methods work on those fields, reading a whole set efficiently, and preserving attempts."
---

# WeBWorK Problem Sets

Two facts drive everything:

1. Answer boxes are **MathQuill live-math editors**, not text inputs. They rewrite input as it is typed and silently ignore programmatic fill.
2. Submissions are **metered** (typically 12 attempts, partial credit). A blank or wrong submission burns one. **Preview is free and unlimited** — the most useful property of the system.

## Before you start

Setup, before any problem is touched. Claude should confirm all four.

### A browser is required

This skill drives a real browser: it reads problems off the rendered page
and types into live math fields. There is no text-only path. Either
browser works and everything below applies identically to both:

- **The Claude desktop app's built-in browser** — a browser pane inside
  the app, nothing to install. Use this if you are unsure which you have.
- **Claude in Chrome** — the extension, driving your own Chrome.

Which of these is available depends on your plan and setup. Use whichever
the session has; if neither is available, say so and stop rather than
attempting the set blind.

### Getting to the set

Claude cannot guess a course's WeBWorK address. Give it one of:

- **a direct link to the set** — fastest by a wide margin; paste the URL
  of the page you are looking at
- **your LMS and course** (D2L, Canvas, Blackboard) and let Claude
  navigate through to WeBWorK

### Signing in is the user's job

Claude has no credentials and will not ask for them.

- **Built-in browser** — keeps a persistent profile across desktop-app
  sessions, so a sign-in carries over. The first run on a new machine
  needs a real login; later runs usually open straight to the portal.
- **Chrome** — uses your normal profile, so an existing D2L or WeBWorK
  session is already live.

A page that comes back as a login screen is the signal to hand the browser
back: the user signs in, then tells Claude to continue. SSO redirect
chains and 2FA prompts belong to the user.

### Name the mode

Say "enter these answers," "check my work," or "do the whole set." Solve
mode submits answers the user has not reviewed, so Claude confirms that
mode rather than inferring it.

## Pick the mode first

| Situation | Mode |
|---|---|
| User supplies their answers | **Enter** — type them, confirm the on-screen problem matches, submit |
| User wants their work checked | **Check** — solve independently *before* reading their answers, then diff |
| User supplies nothing | **Solve** — work everything, self-verify, fill, preview, submit |

In **Solve** mode, show the worked solution before submitting — the actual steps, not just the answer. In **Check** mode, solve first and read their answers second; reading theirs first guarantees anchoring and rubber-stamping. A disagreement means stop: enter neither, show both derivations, let the user adjudicate.

## Working a full set

### Reading the set

Try the hardcopy PDF first — the set page may offer "Download Hardcopy for Current Set." It renders the whole set including figures, collapsing 20 page loads into one.

**Treat it as opportunistic, never required.** Instructors disable it per course or set, gateway sets restrict it, and server-side PDF generation can simply be broken. **One attempt — if the link is absent or generation fails, fall back to per-problem reads silently and don't mention it again.** Hunting for a missing PDF costs more than never trying.

When using the PDF: spot-check two problems against live pages the first time on a new course, since randomization is per-student. And note the PDF shows the **mathematics but not the input widget** — it won't reveal that problem 17 is two dropdowns while problem 18 is three MathQuill boxes. Solve from the PDF, enter from the live pages.

### Images are lost silently

`get_page_text` **drops images entirely** and gives no sign it did. A graph-matching problem comes back as bare labels — "(i) (ii) (iii)" — which looks like clean output and contains nothing. Never assume a text read was complete.

**`read_page` is the detector**, because the accessibility tree enumerates `<img>` elements. Any problem with images in its body needs a screenshot. Use "click to enlarge" before judging a graph rather than squinting at a thumbnail in a 6-up grid, and default graph-identification problems to *needs review* in confidence tagging.

### Order of operations

Bulk-read and solve the whole set in one pass, then enter. But **work problem 1 fully serially first — read, fill, preview, submit, confirm the result — before scaling up.**

That first result is a canary for the entire method. Batching amplifies systematic errors: a broken fill technique caught on problem 1 costs one attempt; the same mistake bulk-applied to twenty problems costs twenty.

### Speed rules

**Speculative fills — single-answer problems only.** Skip the reconnaissance screenshot and go straight to click-and-type at the predictable position (box near (303, 267), Preview near (274, 344) on a fresh page). A miss lands in empty space, preview shows a blank box, and retrying costs nothing.

**Never speculate on multi-field problems.** There a missed click doesn't hit empty space — it hits a *neighboring filled cell* and appends garbage, and cleanup costs more than the screenshot saved.

**Do not batch multiple field-fills in tables.** This was tried repeatedly and failed more often than it worked: the page scrolls mid-batch, later clicks land a row off, and text lands in already-filled cells. Recovery consistently cost more calls than the batching saved, and there is no way to predict in advance which way a given table will go. One field per call inside tables, verified.

## Solve mode: unattended sets

When no answer key exists, Claude is the only check on Claude. The protocol below is the entire safety margin.

**Work the set to filled-and-previewed, then submit.** 

**Preview validates syntax, never correctness.** A clean preview means WeBWorK parsed the expression. It says nothing about whether the math is right. Never report a previewed answer as verified.

### Self-verification protocol

Run all five on every self-derived answer:

1. **Substitute back into the original** — not the simplified form. Catches extraneous roots.
2. **Domain-check every candidate** against the original: log arguments $>0$, even radicands $\ge 0$, denominators $\ne 0$. Reject failures explicitly and say which.
3. **Re-derive by a second route.** Factoring vs. quadratic formula; algebra vs. graph; test point vs. sign chart. Two independent routes agreeing is the bar — one derivation that re-reads itself is worth nothing.
4. **Numeric evaluation.** Compute the exact form as a decimal and confirm plausibility.
5. **Count expected solutions.** A quadratic has two; $\sin x = c$ on $[0,2\pi)$ has two. A mismatch means something was dropped.

### Confidence gating

- **Solid** — two routes agree, domain checked, numerics sane, count matches.
- **Needs review** — anything else: routes disagreed, only one route existed, unfamiliar problem type, ambiguous edge case, graph interpretation, or an answer depending on a convention the course may set differently.

Report "needs review" problems **first**, with the specific doubt named. Never bury uncertainty inside a list of confident-looking answers.

Per problem, report: the answer, a one-line derivation, and the tag.

## Read the actual problem

WeBWorK randomizes coefficients per student. Notes, a classmate's answer, or a worked example may not match what is on screen. Always read the rendered statement; in Enter mode, confirm it matches the user's answer and say so if it does not.

## Solution procedures

Claude knows the mathematics. What follows is structure and the traps that produce confidently wrong answers.

### Inequalities (test-point method)

1. Move everything to one side: a single expression compared to $0$. **Never cross-multiply by a variable expression** — its sign is unknown and the inequality may flip.
2. Boundary values are numerator zeros **and** denominator zeros. Both.
3. Order them; they partition the line.
4. Test one point per interval **numerically in the original**. Do not reason about signs abstractly, and **do not assume signs alternate** — they do not flip across an even-multiplicity root like $(x-2)^2$.
5. Endpoints: include numerator zeros only for $\le$ or $\ge$. **Never include a point where the expression is undefined**, whatever the relation.
6. **Holes:** a factor cancelling top and bottom is still excluded. $\frac{(x-1)(x+1)}{(x-1)(x-3)}$ is undefined at $x=1$ even though it simplifies away.

### Logarithmic and exponential equations

- Combine to a single log, then exponentiate. **Extraneous roots are the norm** — every candidate must satisfy the original domain. $\ln x + \ln(x-3) = \ln 10$ requires $x>3$, killing the $-2$ root.
- Same base both sides → equate exponents. Otherwise $a^{x}=b \Rightarrow x=\frac{\ln b}{\ln a}$, left exact.

### Absolute value

$|A|=c$: solve $A=\pm c$; no solution if $c<0$. $|A|<c \Rightarrow -c<A<c$; $|A|>c \Rightarrow A<-c$ or $A>c$. Or run the test-point method on $|A|-c$, which is how WeBWorK often scaffolds it.

### Inverse functions

Swap and solve. A **restricted domain picks the branch**: $f(x)=x^2+1,\ x\ge0$ gives $f^{-1}=\sqrt{x-1}$, positive root only. Domain of $f^{-1}$ = range of $f$.

### Trigonometry

Exact values: reference angle, then quadrant sign, rationalized as the course does ($\tan\frac{5\pi}{6}=-\frac{\sqrt3}{3}$). Equations on an interval: find **every** solution in it, not just the principal one.

### Simplification and domain

Simplifying often **enlarges** the domain, and WeBWorK asks about exactly that. The identity holds only where the *original* was defined: $\frac{1-\cos^2x}{\sin x}=\sin x$ requires $\sin x \ne 0$.

### Graph identification

Match on intercept, asymptote, and domain, not overall shape: $e^x$ through $(0,1)$ with a left horizontal asymptote; $\ln x$ through $(1,0)$ with a vertical asymptote at $0$; $\sqrt x$ from the origin, $x\ge0$ only.

### Statistics courses

Stats sets differ from algebra sets in three ways that matter:

- **Rounding replaces exactness.** The "exact unless told otherwise" rule below **flips** — stats problems want decimals to a stated precision. WeBWorK compares numerically with a tolerance (often 0.1% relative), so extra precision is usually safe, but rounding *intermediate* steps can push the final answer outside tolerance. **Carry full precision through, round only at the end.**
- **Carry-through parts.** Part (a)'s standard error feeds (b)'s test statistic feeds (c)'s p-value. Solve the chain as one computation rather than re-entering rounded intermediates.
- **Far more image-dependent.** Histograms, boxplots, scatterplots, regression output. The proportion of problems where text extraction silently loses everything is much higher than in algebra — check for images aggressively.

### Answer form

- **Exact unless told otherwise** (algebra); **decimals to stated precision** (stats).
- Multiple solutions: comma-separated list. Intervals: interval notation, `U` for union.
- Empty solution set: `NONE` (or `DNE` where the problem says so).

## Entering answers (MathQuill)

**Fill → preview → verify → submit.** Never submit without previewing, even for a single digit.

### The arrow-out rule

`/` opens a fraction and **the cursor stays in the denominator**. Everything typed afterward keeps going into it. Press `Right` to climb out first.

| Intent | Type this |
|---|---|
| `-1/2, 3` | `-1/2` → `Right` → `,3` |
| `-√3/2` | `-sqrt(3)` → `Right` → `/2` |
| `π/6, 5π/6` | `pi/6` → `Right` → `,5pi/6` |

Without it, `-1/2,3` becomes $-\frac{1}{2,3}$ and WeBWorK rejects it with *"Operands of '/' can't be lists."* `sqrt` behaves identically — the cursor stays inside the radical, so `-sqrt(3)/2` typed straight through puts the fraction *under* the radical.

No arrow-out needed when nothing follows: `(5x+2)/3`, `ln(12)/ln(5)`, `(ln(7)-1)/3`.

### Other conversions

- **Infinity: type `inf`, never `infinity`.** MathQuill converts `inf` to ∞ on sight, leaving `infinity` as `∞inity`.
- `pi` → π, `sqrt` → √; `ln(`, `sin(` render as functions.
- `(` auto-closes; `)` moves past it. `]` closes with a bracket, so `(-2,4]` works.
- Union: `U`, as in `(-inf,-1]U(3,inf)`.

### Reading the parse

An **orange dot on the info button** beside a field means the parse is wrong. Preview shows a *"You Entered"* popup with the parsed form and the error. Trust that over the rendered box — the box can look right while the parse is not.

### Clearing a field

`ctrl+a` + `Backspace` is unreliable; leftover parens and radicals survive and corrupt the retry. **Reload the problem page** for a clean field.

## Browser technique

**What fails:**

- **`form_input` on answer boxes — fails silently and costs an attempt.** It sets the visible value, but the form submits blank and WeBWorK records *"N of the questions remain unanswered"* at 0%. Never use it on a MathQuill field. (Observed on webwork2 2.19; treat as true everywhere until proven otherwise.)
- **Ref-based clicks** focus the field, but typed text frequently does not land.
- **`Tab`** jumps into the math palette, not the next cell.

**What works:** screenshot → `left_click` at coordinates → `type` in the same batch → screenshot to verify. `form_input` *does* work on `<select>` dropdowns.

**Fighting the scroll.** The page jumps after `form_input`, after every preview reload, and sometimes on field focus. Stale coordinates land in the wrong row and silently overwrite a neighbouring cell. **Re-screenshot before clicking anything** following a preview or dropdown change — buttons move when a fraction grows a field or a banner appears. Text in the wrong cell is usually still focused: clear and retype in place.

**Table fill order.** Fractions make their row taller and push rows below down → **fill bottom-up**. Typing in the left (interval) column widens it and shifts columns right → **fill the value column first**. Set **sign dropdowns first** (one scroll jump), then screenshot and fill text cells.

## Multi-part problems

Inequality problems show Part 1 with Parts 2–3 collapsed.

**Parts unlock on Preview, not on Submit.** Preview after Part 1 to reveal Part 2, fill it, preview again to reveal Part 3, fill it, then submit **once** — the whole problem scores on a single attempt. Submitting Part 1 alone to unlock the rest wastes attempts and records a partial score.

Part 2 asks for values and signs at printed test points, sometimes interval labels too. Evaluate at each test point and enter them without stopping to ask. The sign pattern **must** be consistent with the final answer; if it is not, something is wrong upstream — stop rather than submitting.

## Confirming results

After any submission, read the page text:

- `All of the answers are correct.` / `The answer is correct.` — done
- `N of the questions remain unanswered.` — the fill did not land; do not retry the same method
- `You have N attempts remaining.` — track the budget

At the end, load the set page (`.../<SetName>?effectiveUser=<user>`) for the per-problem status table and confirm the total. Always state which answers came from the user and which were derived.

## Improving this skill

Before finishing a run, compare what happened against this file. If something here was wrong, missing, or cost an attempt — or a wrong answer revealed a gap in the solution procedures — propose an updated SKILL.md. WeBWorK grades the work, so unlike most tasks there is real ground truth to learn from: when an answer comes back incorrect, determine whether it was a method error or an entry error before recording anything.

Four disciplines keep this from degrading:

- **Net-zero budget.** Every addition forces a pass at what can be cut or tightened. A file that only grows stops being read carefully.
- **Earn the entry.** One incident is a note; a repeat is a rule. Add immediately only if it would have changed the outcome. Otherwise the file fills with superstition from one-off page glitches.
- **Separate observation from inference.** "`form_input` submitted blank on webwork2 2.19" is an observation. "`form_input` never works on MathQuill" is a guess until seen elsewhere. Recording a wrong causal model is worse than recording nothing, because future runs will trust it.
- **Keep course-specific facts out.** Which host a course lives on, whether it offers hardcopy, its rounding convention — those belong in memory or a project file, not here. This file is about WeBWorK in general and should stay portable across courses and semesters.