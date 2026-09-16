---
name: webwork-answer-entry
description: "Solve and enter answers for online homework in WeBWorK or Top Hat (math, statistics, physics). Use whenever the user points at either platform and wants problems worked, answers entered, or their own work checked."
---

# Online Problem Sets (WeBWorK, Top Hat)

**Identify the platform first** from the open tab: a webwork2 URL → everything below applies. `app.tophat.com` → the shared sections (modes, image loss, self-verification, solution procedures) apply, and entry mechanics come from the **Top Hat** section at the end.

For WeBWorK, two facts drive everything:

1. Typed answer boxes are **MathQuill live-math editors**, not text inputs. They rewrite input as it is typed and silently ignore programmatic fill.
2. Submissions are **metered** (often 3–12 attempts; extra-credit sets may be unlimited). A blank or wrong submission burns one. **Preview is free and unlimited.**

Because attempts are the scarce resource: **a timed-out or failed tool call may still have executed.** Screenshot and check the page state before retrying anything that submits — a blind retry can burn a second attempt or double-submit.

## Before you start

Setup, before any problem is touched.

### A browser is required

This skill drives a real browser: it reads problems off the rendered page and
types into live widgets. There is no text-only path. Either browser works —
measured no speed difference, and they keep **separate logins**:

- **Claude in Chrome** — the extension, driving your own Chrome. Existing D2L
  or WeBWorK sessions are already live in it.
- **The Claude desktop app's built-in browser** — a pane inside the app,
  nothing to install; keeps its own profile across sessions.

If neither is available, say so and stop rather than working the set blind.

### Site permission is the first thing that will stop you (Chrome)

Claude in Chrome gates access per site. The first `navigate` to a new LMS or
WeBWorK host returns a permission stop, not a page. This is normal and
one-time per site: tell the user to allow the site in the extension, wait,
and retry. Do not treat it as a broken tool or work around it.

### Getting to the set

Claude cannot guess a course's address. Ask for either:

- **a direct link** — paste the URL of the set or problem page (fastest)
- **the LMS and course** (D2L, Canvas, Blackboard) and navigate through

WeBWorK problem pages have predictable URLs once you have one:
`/<course>/<Set>/<n>/`, set page `/<course>/<Set>/`.

### Signing in is the user's job

Claude has no credentials and will not ask for them. A page that comes back as
a login screen is the signal to hand the browser back: the user signs in, then
says continue. SSO redirect chains and 2FA prompts belong to the user.

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

### First run in a new course

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

In **Solve** mode, show the worked reasoning for each problem — the actual steps, not just the answer. In **Check** mode, solve first and read their answers second. A disagreement means stop: enter neither, show both derivations, let the user adjudicate.

"Complete all open assignments": load the course's assignment list, then each open set's page (`/<course>/<Set>/`) to see per-problem status; skip sets already at 100%; do the earliest-due set first.

## Working a set: read all, solve all, then enter (default)

**This is the default way to work a WeBWorK set.** Read every problem first,
solve the whole set at once, then go back and enter one problem at a time.
Measured: 9-problem set in ~4 min this way vs ~13 min problem-by-problem, all
first-try correct in both. Solving in one pass is also more accurate than
solving between page loads — shared setups and carry-through parts are visible
at once.

1. **Bulk text read — one batch.** Problem pages have direct URLs `/<course>/<Set>/<n>/`. One `browser_batch` of `navigate` + `get_page_text` × every problem. This replaces the hardcopy PDF: downloading it needs the user's permission plus a connected folder to read it, and gives no widget info.
2. **Solve everything text-solvable immediately**; compute numerics with a short python call (one call for the whole set).
3. **Screenshot only what needs eyes** — one batch of `navigate` + `screenshot` for problems whose text references a plot/table image, plus scroll-down screenshots where a Part 2 figure or option list sits below the fold. `zoom` to read boxplot quartiles or bar heights.
4. **Report answers** (needs-review first), then **enter one problem per batch**: fill → click Submit → `find` "score received message" → `navigate` to next problem → `find` its inputs. Each batch both confirms the last problem and sets up the next.
5. Finish on the set page (`get_page_text`) to confirm every status reads 100%.

**Canary still applies:** confirm problem 1's score before trusting a fill method across the set.

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

## Self-verification

When no answer key exists, Claude is the only check on Claude. On Top Hat, correct answers are hidden even after submission, so it is the *only* check ever. **WeBWorK Preview validates syntax, never correctness.**

### Protocol

Run all five on every self-derived computational answer:

1. **Substitute back into the original** — not the simplified form.
2. **Domain-check every candidate** (log arguments $>0$, even radicands $\ge 0$, denominators $\ne 0$).
3. **Re-derive by a second route.** One derivation that re-reads itself is worth nothing.
4. **Numeric evaluation** for plausibility.
5. **Count expected solutions.**

Conceptual items (variable types, study design, parameter vs statistic) can't run all five: check against the textbook definition and name any convention the course might set differently.

### Confidence gating

- **Solid** — routes agree / definition unambiguous.
- **Needs review** — anything else: graph interpretation, convention-dependent answers, or a matching item whose "right" option isn't literally offered (then pick the option consistent with the other matches — e.g. population = the group the parameter describes).

Report "needs review" problems **first**, with the doubt named.

## Read the actual problem

WeBWorK randomizes values per student; Top Hat may pre-shuffle drag-and-drop options. Always read the rendered statement and the widget's current state.

## Solution procedures

### Inequalities (test-point method)

1. One side vs $0$. **Never cross-multiply by a variable expression.**
2. Boundaries = numerator zeros **and** denominator zeros.
3. Test one point per interval **numerically in the original**; don't assume signs alternate (even-multiplicity roots).
4. Include numerator zeros only for $\le$/$\ge$; **never** include undefined points. Cancelled factors are still holes.

### Logarithmic and exponential equations

Combine, exponentiate, domain-check every candidate — extraneous roots are the norm. $a^{x}=b \Rightarrow x=\frac{\ln b}{\ln a}$, left exact.

### Absolute value

$|A|=c$: $A=\pm c$ (none if $c<0$). $|A|<c \Rightarrow -c<A<c$; $|A|>c \Rightarrow A<-c$ or $A>c$.

### Inverse functions

Swap and solve; a restricted domain picks the branch. Domain of $f^{-1}$ = range of $f$.

### Trigonometry

Reference angle + quadrant sign, rationalized. Find **every** solution in the interval.

### Simplification and domain

Identities hold only where the *original* was defined.

### Graph identification

Match on intercept, asymptote, domain — not overall shape.

### Statistics courses

- **Decimals to stated precision; carry full precision, round only at the end.**
- **Carry-through parts:** solve chained parts as one computation.
- **Variable types:** yes/no or labels → nominal; ordered categories (low/medium/high, education level) → ordinal; measured or counted quantities → numerical. A sample size, a study's headline result ("42% lower risk"), or other single study-level number is **not a variable**.
- **Parameter vs statistic:** known population value → parameter; value computed from the sample → statistic.
- **Two-way tables:** marginal = row/col total ÷ grand total; joint = cell ÷ grand total; conditional = cell ÷ the *given* row/col total. **Base-rate / diagnostic tables** on a hypothetical 10,000: diseased = rate×10,000; TP = sensitivity×diseased; TN = specificity×healthy; fill the rest by subtraction. Enter unrounded cell values (e.g. 536.79). Raising the base rate raises P(disease | positive).
- **Mosaic plots:** column **width** = that variable's marginal share (widest = most entries); segment **height within a column** = conditional share. Pick the plot whose columns are the variable you're conditioning on.
- **Boxplots:** read Q1/median/Q3/whiskers/outliers per group; "proportion above x" follows from where x falls (above Q3 → <25%, above median → <50%). Match an unlabeled histogram to a group by its **min/max range and outliers** first, then peak location.
- **SD vs a benchmark:** compare the benchmark with roughly range/4–range/6 of the bulk.
- **Adding one value:** mean falls iff value < mean; recompute median as the new middle; SD rises iff |value − mean| is large relative to SD — just compute all candidates in python.
- **Paired data:** mean of differences = difference of means; SD of differences ≠ difference of SDs.
- **Shape and center:** the mean is pulled toward the long tail. "Symmetric" includes multimodal mirror-image shapes.
- **Spread from dot plots:** all points at one value = zero; mass at both extremes = most.
- **Confounders** must plausibly relate to both explanatory and response variables.

### Answer form (WeBWorK)

Exact unless told otherwise (algebra); decimals to stated precision (stats); comma-separated lists; interval notation with `U`; `NONE`/`DNE` for empty sets.

## Entering answers in WeBWorK

### Widget → method (observed on webwork2 2.19)

| Widget | Method | Preview? |
|---|---|---|
| `<select>` dropdown | `form_input` with the option text | No |
| Radio / checkbox | `form_input` with `true` on the ref from `find` | No |
| MathQuill typed box | coordinate `left_click` → `type` | Yes if any fractions/radicals/intervals; optional for plain decimals |
| Submit button | `left_click` by ref (from `find`) or by coordinate | — |

- **Never `form_input` a MathQuill box** — it submits blank and burns an attempt.
- `find` returns dropdown/radio/checkbox refs in page order; option order matches the printed list. Refs are valid until the page reloads.
- On pages mixing typed boxes and dropdowns, **type first, then `form_input`** (form_input can scroll the page).

### Typed boxes: batching

- Plain-decimal fills of several boxes in one batch worked (including two 3×3 contingency tables filled bottom-up in one batch each) — rows don't resize for plain numbers. Screenshot once after the batch to verify every cell.
- Still **one field per call** when entries contain fractions or radicals (rows grow and shift).
- **Re-screenshot after any scroll** before clicking — the page can settle 10–20 px after scrolling, and after a tool timeout the viewport origin can shift (a screenshot came back 782 px tall with a white band). Clicks from a stale frame silently miss.
- If a batch times out, its actions may still have run: screenshot and check state before retrying anything.

### MathQuill syntax

- `/` leaves the cursor in the denominator; press `Right` before continuing (`-1/2` → `Right` → `,3`). Same for `sqrt`.
- Infinity: `inf`, never `infinity`. `pi`, `sqrt`, `ln(`, `sin(` convert. `(` auto-closes; `U` for union.
- Orange dot on the info button = bad parse; trust Preview's popup.
- To clear a field, **reload the page**.

### Multi-part problems

Parts unlock on **Preview**, not Submit. Fill all parts, then submit once. Sign patterns must match the final answer.

### Confirming results

`find` "score received message" after submitting — returns "You received a score of N%" cheaply. `All of the answers are correct.` = done. `N of the questions remain unanswered.` = fill didn't land; change method. Finish on the set page for the status table.

## Top Hat

Top Hat runs **problem-by-problem** — there is no bulk-read path (see the
fallback above). Everything else (modes, self-verification, solution
procedures) applies unchanged.

**Layout.** One question per page; the left sidebar lists items with status badges. Assigned work shows "Not answered · Due soon" and flips to "Completed" on submit. Items with **no** status or due badge are past lecture questions — leave them. Read each item with `get_page_text` **plus** a screenshot.

**Grading feedback.** "Correct answers are hidden"; submit shows only Answered/Completed. Changing a response enables **Resubmit** (unverified whether the last submission is graded). Submit/Resubmit near (1301, 695).

**Navigation.** Sidebar clicks auto-scroll the sidebar, so `find` refs go stale after one click — navigate by coordinates from a fresh screenshot.

**Images.** "Image failed to load" → click **Reload Image** before solving.

### Widgets

- **Multiple choice:** click the option row, then Submit. Rows ~50 px apart from y ≈ 210–226.
- **Drag-and-drop matching / ordering:** mouse drags unreliable. Keyboard: click the item's `=` handle → `space` → `Up`/`Down` ×N → `space`. **A move swaps** with the item at the destination. Verify with `get_page_text` ("X moved to position N").
- **Click-on-target (hotspot):** click once per correct region; place one, screenshot, then batch the rest.

## Parallelism

One browser tab means entry stays sequential — parallel agents in the same Chrome would fight over the page. Agents help only for **solving** (split a large multi-set batch across solvers from the bulk-read text) or for an independent second solve on low-attempt numeric problems. The built-in browser is not faster than Chrome and has separate logins.

## Improving this skill

After a run, compare against this file and propose updates if something was wrong, missing, slow, or cost an attempt. Net-zero budget; one incident is a note, a repeat is a rule; separate observation from inference; keep course-specific facts (hosts, conventions) in memory, not here.