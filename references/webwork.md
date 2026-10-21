# WeBWorK entry mechanics

Observed on webwork2 2.19.

## Widget → method

| Widget | Method | Preview? |
|---|---|---|
| `<select>` dropdown | `form_input` with the option text | No |
| Radio / checkbox | `form_input` with `true` on the ref from `find` | No |
| MathQuill typed box | coordinate `left_click` → `type` | Yes if any fractions/radicals/intervals; optional for plain decimals |
| Submit button | `left_click` by ref (from `find`) or by coordinate | — |

- **Never `form_input` a MathQuill box** — it submits blank and burns an attempt.
- `find` returns dropdown/radio/checkbox refs in page order; option order matches the printed list. Refs are valid until the page reloads.
- On pages mixing typed boxes and dropdowns, **type first, then `form_input`** (form_input can scroll the page).

## Typed boxes: batching

- Plain-decimal fills of several boxes in one batch worked (including two 3×3 contingency tables filled bottom-up in one batch each) — rows don't resize for plain numbers. Screenshot once after the batch to verify every cell.
- Still **one field per call** when entries contain fractions or radicals (rows grow and shift).
- **Re-screenshot after any scroll** before clicking — the page can settle 10–20 px after scrolling, and after a tool timeout the viewport origin can shift (a screenshot came back 782 px tall with a white band). Clicks from a stale frame silently miss.
- If a batch times out, its actions may still have run: screenshot and check state before retrying anything.

## MathQuill syntax

- `/` leaves the cursor in the denominator; press `Right` before continuing (`-1/2` → `Right` → `,3`). Same for `sqrt`.
- Infinity: `inf`, never `infinity`. `pi`, `sqrt`, `ln(`, `sin(` convert. `(` auto-closes; `U` for union.
- Orange dot on the info button = bad parse; trust Preview's popup.
- To clear a field, **reload the page**.

## Driving MathQuill from JavaScript (experimental, canary-gated)

Click-type costs a batch per box plus verification screenshots, and clicks can
miss from a stale frame. MathQuill fields expose a JS API that may fill a whole
problem in one `javascript_tool` call. **Unvalidated as of 2026-10-21 — the
canary rule governs:** prove it on problem 1 (fill via JS, confirm the rendered
field in Preview, submit, confirm the score) before trusting it across the set.
On success, use it for the set and update this section with what worked; on any
doubt, fall back to click-type without spending further attempts on the method.

1. Find the fields: MathQuill marks editable elements with the `mq-editable-field` class. Enumerate them in page order; if the class isn't present, inspect one answer box's markup before proceeding.
2. Get the API: `MQ = MathQuill.getInterface(2)`, then `MQ.MathField(el)` per element. If `MathQuill` is undefined on the page, stop and fall back to click-type.
3. Prefer `.write('…')` over `.latex('…')`: `write` goes through the same keystroke handling as typed input, so page hooks and the hidden answer field update as they would for typing. `latex` sets content directly and may bypass them — canary the exact call you plan to use.
4. Escape for the API, not the keyboard: the `Right`-after-`/` dance is a typing concern; as LaTeX, `-\frac{1}{2},3` is unambiguous.

## Multi-part problems

Parts unlock on **Preview**, not Submit. Fill all parts, then submit once. Sign patterns must match the final answer.

## Answer form

Exact unless told otherwise (algebra); decimals to stated precision (stats); comma-separated lists; interval notation with `U`; `NONE`/`DNE` for empty sets.

## Preview policy

Preview validates syntax, never correctness. After the canary passes, Preview only the first field of each new syntax type and any entry with fractions, radicals or intervals — never plain decimals box-by-box. Multi-part problems always need one Preview to unlock their later parts.

## Confirming results

`find` "score received message" after submitting — returns "You received a score of N%" cheaply. `All of the answers are correct.` = done. `N of the questions remain unanswered.` = fill didn't land; change method. Finish on the set page for the status table.

On metered attempts, confirm each problem before moving on. On unlimited attempts, entering the whole set and verifying once at the end is faster — the set page shows every status.
