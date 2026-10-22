# WeBWorK entry mechanics

Observed on webwork2 2.19.

## Widget → method

| Widget | Method | Preview? |
|---|---|---|
| `<select>` dropdown | `form_input` with the option text | No |
| Radio / checkbox | `form_input` with `true` on the ref from `find` | No |
| MathQuill typed box | JS API (`.latex('')` then `.write()`); click-type fallback | Yes if any fractions/radicals/intervals; optional for plain decimals |
| Submit button | JS `#submitAnswers_id` click; `left_click` fallback | — |

- **Never `form_input` a MathQuill box** — it submits blank and burns an attempt.
- `find` returns dropdown/radio/checkbox refs in page order; option order matches the printed list. Refs are valid until the page reloads.
- On pages mixing typed boxes and dropdowns, **type first, then `form_input`** (form_input can scroll the page).

## Typed boxes: batching (click-type fallback)

- Plain-decimal fills of several boxes in one batch worked (including two 3×3 contingency tables filled bottom-up in one batch each) — rows don't resize for plain numbers. Screenshot once after the batch to verify every cell.
- Still **one field per call** when entries contain fractions or radicals (rows grow and shift).
- **Re-screenshot after any scroll** before clicking — the page can settle 10–20 px after scrolling, and after a tool timeout the viewport origin can shift (a screenshot came back 782 px tall with a white band). Clicks from a stale frame silently miss.
- If a batch times out, its actions may still have run: screenshot and check state before retrying anything.

## MathQuill syntax

- `/` leaves the cursor in the denominator; press `Right` before continuing (`-1/2` → `Right` → `,3`). Same for `sqrt`.
- Infinity: `inf`, never `infinity`. `pi`, `sqrt`, `ln(`, `sin(` convert. `(` auto-closes; `U` for union.
- Orange dot on the info button = bad parse; trust Preview's popup.
- To clear a field, **reload the page**.

## Driving entry from JavaScript (validated primary)

Hand-clicking is the fallback. The validated fast path fills a whole problem
with `javascript_tool` — no screenshots, no coordinates:

1. **One script per problem** that inventories, fills, and reads back: dump the widgets (MathQuill fields, radios, dropdowns, checkboxes with their input IDs), fill each, and return the hidden values for comparison. A separate dump pass before filling doubles the calls for no reason.
2. **MathQuill:** `MQ = MathQuill.getInterface(2)`, then per field `.latex('')` to clear and `.write(value)` to fill. Write LaTeX, not keystrokes: `-\frac{1}{2},3` is unambiguous to the API — the `Right`-after-`/` dance is a typing-only concern. **Never set a hidden input's `.value` directly** — the editor state won't match and the submit may carry stale content.
3. **Radios/checkboxes:** DOM `.click()` on the input. **Dropdowns:** set the matching option value and dispatch a `change` event.
4. **Submit:** `document.getElementById('submitAnswers_id').click()`. If the call errors, the click may still have gone through — read the page text for the score before retrying (see the timeout rule in SKILL.md).
5. **Confirm** by reading the page text (`All of the answers are correct` / score), never by trusting the tool result alone.

Validated end-to-end on webwork2 2.19, Oct 2026: 8-problem set, first-try
correct throughout. The canary rule still governs unfamiliar installs: prove
the sequence on problem 1 before trusting it across the set. If `MathQuill` is
undefined on the page, fall back to click-type below.

## Multi-part problems

Parts unlock on **Preview**, not Submit. Fill all parts, then submit once. Sign patterns must match the final answer.

## Answer form

Exact unless told otherwise (algebra); decimals to stated precision (stats); comma-separated lists; interval notation with `U`; `NONE`/`DNE` for empty sets.

## Preview policy

Preview validates syntax, never correctness. After the canary passes, Preview only the first field of each new syntax type and any entry with fractions, radicals or intervals — never plain decimals box-by-box. Multi-part problems always need one Preview to unlock their later parts.

## Confirming results

`find` "score received message" after submitting — returns "You received a score of N%" cheaply. `All of the answers are correct.` = done. `N of the questions remain unanswered.` = fill didn't land; change method. Finish on the set page for the status table.

On metered attempts, confirm each problem before moving on. On unlimited attempts, entering the whole set and verifying once at the end is faster — the set page shows every status.

## Handoff to the harness (fast path)

When the user runs the local harness, you solve — it enters. Emit the answer
file as a JSON code block (schema below) so the user can save it as
`answers.json`, then give the commands. Never hand-transcribe answers into
chat prose for the user to retype.

```json
{"problems": [{"n": 1, "url": "<problem-1-url>",
  "answers": [{"value": "14"}, {"value": "green"},
              {"value": ["A", "C"], "type": "checkbox"}]}]}
```

- One entry per blank **in page order** (the fetch dump numbers them).
- Select/radio: the option **label** exactly as printed, or `index:N`.
- Checkbox: a list of labels plus `"type": "checkbox"`.
- `set_url` may replace per-problem `url`s.

Commands for the user (from `harness/`):

```bash
uv run harness validate answers.json --problems dumps/<SET>/problems.json
uv run harness http-enter answers.json --only 1   # canary, then the set
uv run harness http-enter answers.json
uv run harness http-status '<set-URL>'            # final verification
```

If `validate` reports errors, fix the answers file — don't proceed to entry.

School sessions expire after a few hours; commands detect it and try a
headless refresh on their own. If that reports it needs the user, run
`http-auth --refresh` first and fall back to an interactive `http-auth`
(check "Keep me signed in" so future refreshes heal alone).
