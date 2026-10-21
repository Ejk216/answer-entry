# Top Hat entry mechanics

Top Hat runs **problem-by-problem** — there is no bulk-read path (see the
fallback in SKILL.md). Everything else applies unchanged.

**Layout.** One question per page; the left sidebar lists items with status badges. Assigned work shows "Not answered · Due soon" and flips to "Completed" on submit. Items with **no** status or due badge are past lecture questions — leave them. Read each item with `get_page_text` **plus** a screenshot.

**Grading feedback.** "Correct answers are hidden"; submit shows only Answered/Completed. Changing a response enables **Resubmit** (unverified whether the last submission is graded). Submit/Resubmit near (1301, 695).

**Navigation.** Sidebar clicks auto-scroll the sidebar, so `find` refs go stale after one click — navigate by coordinates from a fresh screenshot.

**Images.** "Image failed to load" → click **Reload Image** before solving.

## Widgets

- **Multiple choice:** click the option row, then Submit. Rows ~50 px apart from y ≈ 210–226.
- **Drag-and-drop matching / ordering:** mouse drags unreliable. Keyboard: click the item's `=` handle → `space` → `Up`/`Down` ×N → `space`. **A move swaps** with the item at the destination. Verify with `get_page_text` ("X moved to position N").
- **Click-on-target (hotspot):** click once per correct region; place one, screenshot, then batch the rest.
