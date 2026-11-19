// Dashboard paging maths: pure functions, no page or window in here, so tests/test_paging_js.py can
// run this file in Node. The browser loads it before app.js, which uses these functions.

const SEARCH_IN = ["title", "jira", "working_on", "next", "blocked_by", "my_blocker"];
const MIN_ROWS = 3;     // a very short window shows 3 rows and scrolls a little, not 1 row per page

const filtersOn = filters => Boolean(filters.q.trim() || filters.status || filters.prio);

// The projects that pass the search box AND both dropdowns.
// The Status dropdown looks at the status the row shows (shown_status: "pending" while someone blocks
// the project), not at the one saved in the note.
function filterProjects(projects, filters) {
  const q = filters.q.trim().toLowerCase();
  return projects.filter(p =>
    (!q || SEARCH_IN.some(field => String(p[field] ?? "").toLowerCase().includes(q)))
    && (!filters.status || (p.shown_status ?? p.status) === filters.status)
    && (!filters.prio || p.priority === filters.prio));
}

// The card's Save: only the boxes whose text is not what the card drew go to Flask.
// drawn = {field: text when the card was drawn}, now = {field: text in the box now}.
// A box you did not touch is never sent, so Save can't write an old value over a newer one in the note.
function changedFields(drawn, now) {
  return Object.fromEntries(Object.entries(now).filter(([field, text]) => text !== drawn[field]));
}

// Rows that fit in `room` pixels. A row height that could not be read (empty or 0) also gives MIN_ROWS.
function rowsThatFit(room, rowH) {
  const n = Math.floor(room / rowH);
  return Number.isFinite(n) && n > MIN_ROWS ? n : MIN_ROWS;
}

// The page that shows row number `first` (0 = the first row) at `perPage` rows a page.
const pageHolding = (first, perPage) => Math.floor(first / perPage) + 1;

// The page buttons: all of them up to 7 pages, else 7 slots like "1 … 4 5 6 … 12".
function pageList(pages, current) {
  if (pages <= 7) return Array.from({length: pages}, (_, i) => i + 1);
  const mid = Math.min(Math.max(current, 4), pages - 3);
  return [1, mid - 2 === 2 ? 2 : "…", mid - 1, mid, mid + 1, mid + 2 === pages - 1 ? pages - 1 : "…", pages];
}

// The footer's left side, e.g. "1–4 of 20 projects" or "1–4 of 6 · filtered from 20".
// from = index of the first row shown, shown = rows on this page, total = rows in the tile, all = open projects.
function footerText(from, shown, total, all, filtered) {
  const range = shown === 1 ? `${from + 1}` : `${from + 1}–${from + shown}`;
  return filtered ? `<b>${range}</b> of ${total} · filtered from ${all}`
    : `<b>${range}</b> of ${total} ${total === 1 ? "project" : "projects"}`;
}

// What an empty list says. passed = projects the filters let through, inTile = those in the chosen tile.
// "nomatch" = "No projects match these filters." (the filters hid everything);
// "empty" = "Nothing here." (no projects, or the chosen tile has none of the ones passed); null = rows to show.
function emptyMessage(passed, inTile, filtered) {
  if (inTile) return null;
  return filtered && !passed ? "nomatch" : "empty";
}

// A long line (a History line on the card) cut to about `limit` characters, ending in "…".
// It is cut at a space so no word is split; one very long word is cut where the limit is.
// null = the text fits, so there is nothing to cut and no "Read more" button to show.
function shortText(text, limit) {
  if (text.length <= limit) return null;
  const cut = text.slice(0, limit);
  const space = cut.lastIndexOf(" ");
  // A space in the first half would throw away too much text: then cut at the limit instead.
  return (space > limit / 2 ? cut.slice(0, space) : cut).trimEnd() + "…";
}

// Text for a one-line field: every line break, with the spaces around it, becomes one space.
// Returns [the new text, where the text cursor belongs in it]: the cursor stays right after the same
// character as before, so typing goes on where you were (cursor = its place in the old text).
function oneLineAt(text, cursor) {
  const clean = part => part.replace(/\s*\n\s*/g, " ");
  return [clean(text), clean(text.slice(0, cursor)).length];
}

// Node (the tests) reads the functions from here; the browser has no `module` and just uses them.
if (typeof module !== "undefined") {
  module.exports = {filtersOn, filterProjects, rowsThatFit, pageHolding, pageList, footerText, emptyMessage, shortText,
                    oneLineAt, changedFields};
}
