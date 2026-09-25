---
name: answer-entry
description: "Solve and enter answers for online homework in WeBWorK, Top Hat, or d2L (math, statistics, physics, coding). Use whenever the user points at a platform and wants problems worked, answers entered, and submitted."
---

# Online Problem Sets (WeBWorK, Top Hat, d2L Quiz)

**Identify the platform first** from the open tab: a webwork2 URL → everything below applies. `app.tophat.com` → the shared sections (modes, image loss, self-verification, solution procedures) apply, and entry mechanics come from the **Top Hat** section. A `d2l.*` URL — especially `/d2l/le/enhancedSequenceViewer/` or `/d2l/lms/quizzing/` — → the shared sections apply and entry mechanics come from the **D2L Quiz** section.

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

### First run on a new course or platform

Prove the path before spending attempts. Either run **Check** mode against a
problem the user has already solved, or enter problem 1 alone and confirm its
score before touching the rest. A past-due set is a safe place to test entry
mechanics — but it often displays the answers, so it proves nothing about
solving.

## Pick the mode first

| Situation | Mode |
|---|---|
| User supplies nothing | **Solve** — work everything, self-verify, fill, submit |

In **Solve** mode, show the worked reasoning for each problem — the actual steps, not just the answer.

"Complete all open assignments": load the course's assignment list, then each open set's page (`/<course>/<Set>/`) to see per-problem status; skip sets already at 100%; do the earliest-due set first.

**Read the stakes off the platform before entering anything.** Attempts allowed, due date and time limit decide how careful to be: WeBWorK meters submissions, while a D2L quiz is often unlimited-attempt and untimed, which makes a wrong answer nearly free. Don't assume — look, then say which regime you're in.

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

For code-output questions ("what is the value of…", "what is printed by…") the second route is **running the code**. Put every expression in the set into one python script and print the results — never reason out `rfind`, slice bounds or a format spec by hand when the interpreter will answer. Print `repr()`, and wrap printed output in markers so leading and trailing spaces are visible, because answer choices often differ only by padding.

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

### Intro programming (strings, slicing, formatting)

Run it rather than reason it. Traps worth recognising anyway:

- `3 * "125"` repeats the string; `3 * int("125")` is arithmetic; `3 * str(125)` repeats again.
- `in` on strings tests **substring**, not "any of these letters" — `"ad" in "aardvark"` is `False`.
- Negative slices: `Z[-3:]`, `Z[-6:-2]` — count from the end, stop index exclusive.
- String comparison is codepoint-wise, so every uppercase letter sorts before every lowercase one: `"Tiger" > "tiger"` is `False`. Length only decides when one string is a prefix of the other — `"ants" < "anteater"` is `False`, because the first difference (`s` vs `e`) settles it.
- `find` gives the first index, `rfind` the last, `-1` when absent; `count` counts non-overlapping occurrences.
- Format specs: width pads, `>`/`<` set alignment, `+` forces a sign. `{:.4f}` on a denormal prints `0.0000`; `{:.4f}` on a near-max float prints all 300+ digits, while `{:.4e}` stays compact.

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
fallback above). Everything else applies unchanged.

**Layout.** One question per page; the left sidebar lists items with status badges. Assigned work shows "Not answered · Due soon" and flips to "Completed" on submit. Items with **no** status or due badge are past lecture questions — leave them. Read each item with `get_page_text` **plus** a screenshot.

**Grading feedback.** "Correct answers are hidden"; submit shows only Answered/Completed. Changing a response enables **Resubmit** (unverified whether the last submission is graded). Submit/Resubmit near (1301, 695).

**Navigation.** Sidebar clicks auto-scroll the sidebar, so `find` refs go stale after one click — navigate by coordinates from a fresh screenshot.

**Images.** "Image failed to load" → click **Reload Image** before solving.

### Widgets

- **Multiple choice:** click the option row, then Submit. Rows ~50 px apart from y ≈ 210–226.
- **Drag-and-drop matching / ordering:** mouse drags unreliable. Keyboard: click the item's `=` handle → `space` → `Up`/`Down` ×N → `space`. **A move swaps** with the item at the destination. Verify with `get_page_text` ("X moved to position N").
- **Click-on-target (hotspot):** click once per correct region; place one, screenshot, then batch the rest.

## D2L Quiz

Observed on MSU Brightspace, Sept 2026. D2L is the awkward platform: text tools return nothing and scrolling doesn't work, but the entire quiz is reachable from JavaScript in a single pass. Don't grind through it by screenshot before trying the JS route below.

### Scope it first

Open the quiz list — `/d2l/lms/quizzing/user/quizzes_list.d2l?ou=<courseId>` — which reads as ordinary text. It gives the due date, availability, **attempts allowed**, and whether an attempt is already in progress.

The question navigator's visible grid **understates the question count** (a 48-question quiz showed a 15-cell grid with more below the fold). Drag the navigator's own scrollbar to the bottom and read the last number before planning or quoting scope.

### Text extraction is blocked; JavaScript is not

The quiz renders inside a cross-origin iframe, so `get_page_text` and `read_page` both come back empty — on the sequence viewer *and* on the attempt page. Two empties is the signal to switch methods, not to retry.

Recovery path:

1. `read_network_requests` with pattern `quiz` on the sequence-viewer tab → yields `qi=<quizId>` and `ou=<courseId>`. Capture only starts when the tool is first called, so call it once, then reload the page and call it again.
2. Open `/d2l/lms/quizzing/user/attempt/quiz_start_frame_auto.d2l?ou=<ou>&qi=<qi>` in a **new** tab, leaving the user's own tab untouched. An in-progress attempt resumes there without a password prompt.
3. Use `javascript_tool` on that tab. Probe the frame tree first — walk `window.frames` recursively, catching the throw on cross-origin ones — and find the same-origin frame holding all the `input[type=radio]` elements.

### Shadow DOM holds the question text

D2L renders question stems and option labels inside web-component shadow roots, so `innerText` on ordinary elements returns empty. Walk `childNodes` **and** `element.shadowRoot` recursively, collecting text nodes and emitting a marker at each radio (checked vs not). All questions are in the DOM at once — the list is not virtualised — so one traversal captures the whole quiz.

Labels come out **triplicated** (`'3125''3125''3125'`). Dedupe by testing whether the string equals its first half or first third repeated.

### javascript_tool limits

- **Returns truncate at roughly 1.5 KB.** Stash the dump on `window` (`window.__dump = …`) and slice it out in ~1.1 KB chunks across several calls; batch those calls together.
- **Output resembling cookie or query-string data is blocked outright**, returning `[BLOCKED: Cookie/query string data]` instead of the result. `key=value` text joined by `;` triggers it, as do raw URLs and attribute or `outerHTML` dumps. Use separators like ` // ` and ` >> `, and never dump element attributes.
- **Literal pipes appear in the content** — format questions like `print("|{:5d}| |{:4d}|")` — so don't use `|` as your own delimiter. Re-extract those questions **without collapsing whitespace**, since their answer choices differ only by leading and trailing spaces.
- **`async`/`await` loops are cut off mid-run** and the call returns `{}`. Click synchronously in a plain `for` loop and verify state in a separate call.

### Entering answers

Group the radios by `name` in DOM order — group *n* is question *n*. **Confirm that mapping before trusting it:** compare which groups are already answered against the navigator's ✓ / `--` badges; the pattern should match exactly.

Fill by calling `.click()` on the radio, not by setting `.checked`, which bypasses D2L's save handler. Canary the first one: click it, then confirm the question shows "✓ Saved", its navigator cell turns ✓, and the footer counter increments.

**Rapid clicks outrun autosave.** After bulk-clicking, the DOM shows every selection but the footer counter stalls and never catches up on its own. Find the button whose text is exactly **`Save All Responses`** and click it — `Submit Quiz` is the adjacent button, so match on exact text, never on index. The counter jumps to the full total within a few seconds.

### Confirming and stopping

Verify two ways: the footer's "N of M questions saved" counter, and a per-group diff of expected option index against the actually-checked index, reporting mismatches only.

**Don't submit.** Saved answers already stand as the attempt, and submitting is the user's call — especially when survey items are deliberately left blank. Hand the tab back and say what remains.

### Navigation is navigator-only

Synthetic wheel `scroll` moves the question pane a few ticks and then stops responding entirely, on both the sequence viewer and the attempt page. Clicking a number in the question navigator reliably jumps the pane. This affects automation only — the user's own mouse scrolls normally, so don't tell them the page is broken. Resizing the window does **not** reflow the iframe; reload after resizing, and expect viewport height to be capped by the physical display regardless of the size requested.

## Tool efficiency notes

- In `browser_batch`, a `scroll` action **already returns its own screenshot**. Adding a `screenshot` after it duplicates the image and wastes tokens.
- Coordinates inside a batch refer to the screenshot taken *before* the call. So a batch can click a target you've already seen and then navigate and capture the next view — but it can never click something first revealed inside the same batch.
- `find` and `read_page` refs stay valid only until the page reloads.

## Parallelism

One browser tab means entry stays sequential — parallel agents in the same Chrome would fight over the page. Agents help only for **solving** (split a large multi-set batch across solvers from the bulk-read text) or for an independent second solve on low-attempt numeric problems. The built-in browser is not faster than Chrome and has separate logins.

## Improving this skill

After a run, compare against this file and propose updates if something was wrong, missing, slow, or cost an attempt. Net-zero budget; one incident is a note, a repeat is a rule; separate observation from inference; keep course-specific facts (hosts, conventions) in memory, not here.

**Start any proposed rewrite from the current file, and keep `Before you start`
and the default/fallback framing.** A saved proposal replaces the whole file,
and setup guidance has been silently dropped this way twice.