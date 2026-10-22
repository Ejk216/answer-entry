# Top Hat entry mechanics

Top Hat has a JSON API under the app — the harness speaks it directly
(see Handoff below). Hand-driven browser entry remains the fallback.

**API (reverse-engineered Oct 2026 from live app traffic).** Bearer JWT
(`jwt/accessToken` in localStorage) + `Course-Id` header. Course tree at
`/api/v1/tree_data/` (folders + module_items); numeric→content-id bridge
at `/api/content/course/<id>/id_mappings/`; question bodies at
`/api/content-delivery/course/<id>/content/<cid>/` (document tree:
paragraphs plus `multiple_choice_question`/`multiple_choice_option`
nodes with numeric ids); answers POST to
`/api/question/v3/review/questions/<cid>/responses/` as
`{"data": {"1": [<option-id>]}}`; status from
`/api/v2/answered_items/<course>/`.

**Grading feedback.** The submit response *is* the grade:
`graded_response` carries per-part status plus `points` — no separate
check needed. (The web UI hides correctness; the API does not.)
Changing a response enables **Resubmit** (unverified whether the last
submission is graded). Only items in an **open** assignment fetch —
anything else 403s; that error means past-due, unreleased, or
review-closed, not a bug.

**Scope: single-part multiple-choice.** Other question types raise
instead of guessing. Drag-and-drop, hotspot, and numeric entry stay
hand-driven until their API shapes are captured.

**Layout (hand-driven fallback).** One question per page; the left
sidebar lists items with status badges. Assigned work shows "Not
answered · Due soon" and flips to "Completed" on submit. Items with
**no** status or due badge are past lecture questions — leave them.
Read each item with `get_page_text` **plus** a screenshot.
Submit/Resubmit near (1301, 695).

**Navigation.** Sidebar clicks auto-scroll the sidebar, so `find` refs go stale after one click — navigate by coordinates from a fresh screenshot.

**Images.** "Image failed to load" → click **Reload Image** before solving.

## Widgets

- **Multiple choice:** click the option row, then Submit. Rows ~50 px apart from y ≈ 210–226.
- **Drag-and-drop matching / ordering:** mouse drags unreliable. Keyboard: click the item's `=` handle → `space` → `Up`/`Down` ×N → `space`. **A move swaps** with the item at the destination. Verify with `get_page_text` ("X moved to position N").
- **Click-on-target (hotspot):** click once per correct region; place one, screenshot, then batch the rest.

## Handoff to the harness (fast path)

When the user runs the local harness, you solve — it enters. Give the
user these commands (from `harness/`), then solve from the fetch dump
they paste back and emit `answers.json` (`set_url` = any course URL
containing `/e/<code>/`, one label-or-`index:N` answer per question):

```bash
uv run harness th-auth 'https://app.tophat.com/e/<code>/'
uv run harness th-fetch '<item-URL>' --folder '<folder-title>' --out dumps/<NAME>
uv run harness validate answers.json --problems dumps/<NAME>/problems.json
uv run harness th-enter answers.json --problems dumps/<NAME>/problems.json --only 1
uv run harness th-enter answers.json --problems dumps/<NAME>/problems.json
uv run harness th-status '<item-URL>' --folder '<folder-title>'
```

Canary first: the `--only 1` submit must grade `correct` before the
rest. A 403 on fetch means the item isn't open — say so, don't retry
blindly. Never hand-transcribe answers into chat prose.
