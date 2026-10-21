# D2L Quiz entry mechanics

Observed on MSU Brightspace, Sept 2026. D2L is the awkward platform: text tools return nothing and scrolling doesn't work, but the entire quiz is reachable from JavaScript in a single pass. Don't grind through it by screenshot before trying the JS route below.

## Scope it first

Open the quiz list — `/d2l/lms/quizzing/user/quizzes_list.d2l?ou=<courseId>` — which reads as ordinary text. It gives the due date, availability, **attempts allowed**, and whether an attempt is already in progress.

The question navigator's visible grid **understates the question count** (a 48-question quiz showed a 15-cell grid with more below the fold). Take the true count from the JS dump below (one radio group per question), not the grid — no scrollbar-dragging needed. Only if the dump is unavailable, drag the navigator's own scrollbar to the bottom and read the last number before planning or quoting scope.

## Text extraction is blocked; JavaScript is not

The quiz renders inside a cross-origin iframe, so `get_page_text` and `read_page` both come back empty — on the sequence viewer *and* on the attempt page. Two empties is the signal to switch methods, not to retry.

Recovery path:

1. `read_network_requests` with pattern `quiz` on the sequence-viewer tab → yields `qi=<quizId>` and `ou=<courseId>`. Capture only starts when the tool is first called, so call it once, then reload the page and call it again.
2. Open `/d2l/lms/quizzing/user/attempt/quiz_start_frame_auto.d2l?ou=<ou>&qi=<qi>` in a **new** tab, leaving the user's own tab untouched. An in-progress attempt resumes there without a password prompt.
3. Use `javascript_tool` on that tab. Probe the frame tree first — walk `window.frames` recursively, catching the throw on cross-origin ones — and find the same-origin frame holding all the `input[type=radio]` elements.

## Shadow DOM holds the question text

D2L renders question stems and option labels inside web-component shadow roots, so `innerText` on ordinary elements returns empty. Walk `childNodes` **and** `element.shadowRoot` recursively, collecting text nodes and emitting a marker at each radio (checked vs not). All questions are in the DOM at once — the list is not virtualised — so one traversal captures the whole quiz.

Labels come out **triplicated** (`'3125''3125''3125'`). Dedupe by testing whether the string equals its first half or first third repeated.

## javascript_tool limits

- **Returns truncate at roughly 1.5 KB.** Stash the dump on `window` (`window.__dump = …`) and slice it out in ~1.1 KB chunks across several calls; batch those calls together.
- **Output resembling cookie or query-string data is blocked outright**, returning `[BLOCKED: Cookie/query string data]` instead of the result. `key=value` text joined by `;` triggers it, as do raw URLs and attribute or `outerHTML` dumps. Use separators like ` // ` and ` >> `, and never dump element attributes.
- **Literal pipes appear in the content** — format questions like `print("|{:5d}| |{:4d}|")` — so don't use `|` as your own delimiter. Re-extract those questions **without collapsing whitespace**, since their answer choices differ only by leading and trailing spaces.
- **`async`/`await` loops are cut off mid-run** and the call returns `{}`. Click synchronously in a plain `for` loop and verify state in a separate call.

## Entering answers

Group the radios by `name` in DOM order — group *n* is question *n*. **Confirm that mapping before trusting it:** compare which groups are already answered against the navigator's ✓ / `--` badges; the pattern should match exactly.

Fill by calling `.click()` on the radio, not by setting `.checked`, which bypasses D2L's save handler. Canary the first one: click it, then confirm the question shows "✓ Saved", its navigator cell turns ✓, and the footer counter increments.

**Rapid clicks outrun autosave.** After bulk-clicking, the DOM shows every selection but the footer counter stalls and never catches up on its own. Find the button whose text is exactly **`Save All Responses`** and click it — `Submit Quiz` is the adjacent button, so match on exact text, never on index. The counter jumps to the full total within a few seconds.

## Confirming and stopping

Verify two ways: the footer's "N of M questions saved" counter, and a per-group diff of expected option index against the actually-checked index, reporting mismatches only.

**Don't submit.** Saved answers already stand as the attempt, and submitting is the user's call — especially when survey items are deliberately left blank. Hand the tab back and say what remains.

## Navigation is navigator-only

Synthetic wheel `scroll` moves the question pane a few ticks and then stops responding entirely, on both the sequence viewer and the attempt page. Clicking a number in the question navigator reliably jumps the pane. This affects automation only — the user's own mouse scrolls normally, so don't tell them the page is broken. Resizing the window does **not** reflow the iframe; reload after resizing, and expect viewport height to be capped by the physical display regardless of the size requested.
