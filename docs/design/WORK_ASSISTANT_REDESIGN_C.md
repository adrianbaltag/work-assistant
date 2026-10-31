# Work Assistant — Redesign "C · Soot" (build spec for Claude Code)

> **Decided 2026-10-30 — these WIN over the spec below:**
> - Rows per page = **auto-fit** to the window height (never scrolls up/down), not a fixed 10 (§3.5, §7).
> - **F5 starts clean**: no URL state; search/filters/page kept only while moving between pages (§5).
> - Filters = **search + two dropdowns** (Status: any/active/pending/idea, Priority: any/critical/high/normal)
>   + a "Clear filters" link shown only when something is set. No "+ Filter" popover, no chips (§3.3).
> - Search also matches **Working on** and **Blocked by** (§5 step 2).
> - Tile counts **follow the filters** (as the spec says); the header summary stays unfiltered.
> - Todos live in **`todos.md` in the projects folder** (`- [ ] (high) text` / `- [x] text`), file order = added order;
>   no SQLite/JSON/ids/created_at. Each change sends row number + text; a mismatch = "The list changed, reload" (§4.1).
> - Routes are **POST only** like the rest of the app (its same-site check guards POST), not PATCH/DELETE (§4.1).
> - To do is a page section like Archive (sidebar buttons), not a `/todo` route. Edit opens only via the ✎ button.
> - Keep the app's existing project sort and its "today / 1 day ago / N days ago" wording.
> - Done group keeps added order.

You are restyling an existing local web app called **Work Assistant**.
Stack: **Flask + plain HTML / CSS / JavaScript. No framework, no build step, no icon library, no CSS framework.**
It runs on one Windows laptop, desktop browser only, full screen, from **1366×768 to 1920×1080**. No phone layout.

Scope of this job:
1. Restyle the **sidebar** and the **Dashboard** page to direction C.
2. Add **filters** and **pagination** to the Dashboard table.
3. Add a new **To do** page (new route, storage, and UI).

Out of scope: the project card pop-up that opens when you click a row (keep it working, don't redesign it), Ask Claude, Archive, Slack internals.

**Before writing code:** read the existing templates, CSS, JS, and Flask routes. Reuse what exists (data loading, the "gone quiet" rule, the project pop-up, how projects are stored). Then make a short plan and follow the order in §9.

---

## 1. Design tokens — put these in one CSS file and use only these

```css
:root {
  /* blacks — slightly warm, never navy / blue-grey / purple */
  --bg:          #0E0D0C;  /* page background */
  --sidebar:     #121110;  /* sidebar, table header, table footer */
  --panel:       #161514;  /* cards, table body, inputs on panels */
  --raised:      #1D1C1A;  /* buttons, popover, row being edited */
  --hover:       #22201E;  /* row hover, active nav item */
  --border:      #2A2826;  /* default borders, row dividers use --hover */
  --border-strong:#383532; /* button borders, popover border */
  --border-focus:#6E6A64;  /* input with a value / open button */

  /* text */
  --text:        #EEEAE5;
  --text-muted:  #A39E97;
  --text-label:  #8F8A83;  /* small mono labels — keep ≥ this light for contrast */
  --text-off:    #5E5A55;  /* disabled items, dashes */

  /* meaning colours — use ONLY for meaning */
  --critical:    #F25C54;
  --high:        #F28A84;  /* high priority = red OUTLINE, not a new colour */
  --pending:     #F2B544;
  --active:      #3FCF8E;
  --idea:        #A39E97;
  --quiet:       #7DB9F5;  /* "gone quiet" */
  --slack:       #A78BFA;
  --claude:      #E9875B;

  /* tinted fills (same colour at low alpha) */
  --critical-bg: rgba(242, 92, 84, .14);
  --pending-bg:  rgba(242,181, 68, .13);
  --active-bg:   rgba( 63,207,142, .12);
  --idea-bg:     rgba(163,158,151, .12);

  --radius:      14px;   /* cards, table panel, tiles, popover */
  --radius-sm:   12px;   /* buttons, inputs, nav items */
  --radius-xs:   7px;    /* pills */
}
```

Fonts (Google Fonts link in `<head>`):
`Poppins` 400/500/600/700 for all text, `JetBrains Mono` 400/500/600 for dates, ticket IDs, counts, and small uppercase labels.

```html
<link href="https://fonts.googleapis.com/css2?family=Poppins:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;600&display=swap" rel="stylesheet">
```

Rules:
- `body { background: var(--bg); color: var(--text); font-family: Poppins, sans-serif; margin: 0 }`, `* { box-sizing: border-box }`.
- **Small label style** (`.lbl`): JetBrains Mono, 10.5px, `letter-spacing: .12em`, uppercase, `var(--text-label)`.
- No gradients, no glassmorphism, no blur. The only shadow allowed is on the filter popover (`0 16px 40px rgba(0,0,0,.55)`).
- Icons are small inline `<svg>` with `stroke="currentColor"`, 16px, stroke-width 1.6. No icon library.

---

## 2. Page shell (both pages)

```
┌──────────┬──────────────────────────────────────────────┐
│ sidebar  │ main (padding 28px 40px 24px, column, gap 16) │
│ 240px    │                                              │
└──────────┴──────────────────────────────────────────────┘
```
- Wrapper: `display:flex; min-height:100vh`.
- Sidebar: `flex: 0 0 240px; background: var(--sidebar); border-right: 1px solid var(--hover); padding: 24px 14px;` column, gap 4px. **Not** sticky/fixed.
- Main: `flex: 1 1 0; min-width: 0;` ← `min-width:0` is what stops the table from pushing past the window.

### Sidebar contents (top to bottom)
1. **Brand**: a 28×28 square, radius 9px, background `var(--text)`, containing a dark 3-bar icon; then "Work Assistant" (16px, 700).
2. **Nav links** (`<a>`, height 42px, padding 0 14px, radius 12px, 14px/500, colour `--text-muted`, gap 12px between icon and text):
   - Dashboard
   - **To do** + count badge (open todos). Badge: mono 11px/600, pill, min-width 22px, height 20px, pushed right (`margin-left:auto`). **Badge background is `--critical` when at least one open todo is high, otherwise `--border-strong` with `--text`.** Hide the badge when the count is 0.
   - Ask Claude (asterisk icon in `--claude`)
   - Archive
   - Hover: background `--raised`, text `--text`. Current page: background `--hover`, text `--text`, `box-shadow: inset 0 0 0 1px var(--border)`, `aria-current="page"`.
3. **Slack button** (a real `<button>`, full width, margin-top 16px, height 40px, radius 12px): background `#1A1626`, border `#3A3150`, `#` icon in `--slack`, label "Slack", unread badge with background `--slack` and dark text. Hide the badge when unread = 0. If Slack isn't connected, keep the existing "not connected" behaviour but in this style.
4. **Coming later** box: margin-top 28px, padding 14px, `border: 1px dashed var(--border)`, radius 14px. `.lbl` "Coming later", then two items, "Morning brief" and "Calendar", in `--text-off` with `pointer-events:none` and `aria-disabled="true"`.

---

## 3. Dashboard page

### 3.1 Header
Flex row, space-between, aligned to the bottom.
- Left column, gap 6px:
  - `.lbl` date with letter-spacing .16em: `FRIDAY · 30 OCTOBER 2026` (today's date)
  - `<h1>` "Your projects", 28px, 700
  - Summary, 14px `--text-muted`: `34 open · 3 critical · 5 pending · 11 gone quiet`. The last three numbers are in 600 weight and coloured `--critical`, `--pending`, `--quiet`. These counts are for **all** open projects and **do not change with filters**.
- Right: two buttons, gap 10px, height 40px, radius 12px, 13px/600:
  - **Ask Claude**: background `#1F1510`, border `#5A3524`, text and icon `--claude`.
  - **+ New project**: background `--text`, text `--bg` (the one light button).

### 3.2 Quick tabs = 4 stat tiles
A row of 4 equal tiles (`flex:1 1 0; min-width:0`, gap 12px), each a `<button role="tab">` inside `role="tablist"`:

| Tile | Number colour |
|---|---|
| All open | `--text` |
| Critical | `--critical` (plus a 6px dot) |
| Pending | `--pending` (plus a dot) |
| Gone quiet | `--quiet` (plus a dot) |

Tile: height 72px, padding 12px 16px, radius 14px, background `--panel`, border `--border`, column with space-between: the label (12.5px/500, `--text-muted`) on top and the number below (22px/700).
Selected tile: background `--raised`, **border `--text`**, label colour `--text`, `aria-selected="true"`.
Tile numbers = counts **after the filters are applied** (see §5). A tile whose count is 0 gets its text in `--text-off`.

### 3.3 Toolbar (search + filter) — sits under the tiles
Row, gap 10px, aligned to the centre:
1. **Search input** (`type="search"`, 380px wide, max 45%): height 40px, radius 12px, background `--panel`, border `--border`, magnifier icon inside on the left (padding-left 38px). Placeholder: `Search name, ticket or next step…`. When it has text, the border becomes `--border-focus` and the background `--raised`.
2. **"+ Filter" button**. Click opens a **popover** under it (absolute, top 48px, width 280px, padding 10px, radius 14px, background `--raised`, border `--border-strong`, the shadow above, `z-index` above the table):
   - `.lbl` STATUS, then 3 checkbox rows: active (green dot), pending (amber dot), idea (grey dot). Each row shows its count on the right in mono 11px `--text-label`.
   - A 1px divider.
   - `.lbl` PRIORITY, then 3 checkbox rows: critical (text in `--critical`), high (text in `--high`), normal.
   - Rows: height 34px, radius 8px, hover background `--border`. Use real `<input type="checkbox">` + `<label>`, styled with a 16px box (radius 5px, border 1.5px `--border-focus`).
   - Ticking a box **applies at once** (no Apply button). The popover stays open so you can tick several. It closes on Esc, on a click outside, or on clicking "+ Filter" again.
3. **Active filter chips**, shown after the button, one chip per group that has something ticked:
   - `Status is active` · `Status is active, pending` · `Priority is critical, high`
   - Chip: height 32px, pill, background `--hover`, border `--border-strong`, 12.5px. The values are in 600 weight. A round `×` button (22px, `aria-label="Remove status filter"`) clears **that whole group**.
4. **"Clear all"**: a text button, underlined, shown only when search or any chip is active. It clears the search and every chip, and goes back to page 1. (The selected tile stays as it is.)
5. When nothing is active, show `No filters` in 13px `--text-label` instead of chips.

### 3.4 Table — must ALWAYS fit the window width (no sideways scroll)
Build it with **CSS grid rows, not `<table>`**, so the columns can't overflow:

```css
.row {
  display: grid;
  grid-template-columns:
    minmax(0,2.1fr)   /* Project            */
    100px             /* Status             */
    100px             /* Priority           */
    minmax(0,1.9fr)   /* Working on         */
    minmax(0,2fr)     /* Next step          */
    minmax(0,1.4fr)   /* Blocked by         */
    112px;            /* Updated — fixed, never cut off */
  align-items: center;
  height: 46px;
  border-top: 1px solid var(--hover);
}
.c { padding: 0 14px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: 13px; }
```
- Table panel: background `--panel`, border `--border`, radius 14px, `overflow:hidden`, column.
- Header row: height 38px, background `--sidebar`, `.lbl` text, no top border. Columns: PROJECT, STATUS, PRIORITY, WORKING ON, NEXT STEP, BLOCKED BY, UPDATED.
- Every cell cuts long text with "…". Put the full text in a `title` attribute so you can hover to read it.
- Each body row is an `<a href="#">` (or a `<button>`) that opens the **existing project card pop-up**. Hover: background `--hover`.

**Left stripe** on each row: `box-shadow: inset 3px 0 0 <colour>`. Colour rule: **critical priority → `--critical`, otherwise by status** (active → `--active`, pending → `--pending`, idea → `--idea`). Give the first cell padding-left 17px so the text clears the stripe.

**Cells**
| Column | Content |
|---|---|
| Project | Line 1: name, 600 weight. Line 2: ticket ID in mono 10.5px `--text-label` (or `no Jira`). |
| Status | Pill: height 22px, padding 0 8px, radius 7px, 11.5px/600, a 6px dot + the word. active = `--active` on `--active-bg`; pending = `--pending` on `--pending-bg`; idea = `--idea` on `--idea-bg`. |
| Priority | Pill, same size. critical = `--critical` on `--critical-bg`; high = `--high` text + `box-shadow: inset 0 0 0 1px rgba(242,92,84,.5)`, no fill; normal = `--idea` text + an inset 1px `--border-strong` outline. |
| Working on | `M8/12` in mono 11px `--text-muted`, margin-right 8px, then the step name. If there is none: `—` in `--text-off`. |
| Next step | `M9` in mono (or `→` if it has no milestone number), then the name. If there is none: `—`. |
| Blocked by | Text in `--pending`, or `—` in `--text-off`. |
| Updated | Mono 12px, e.g. `15 days ago`, `yesterday`, `2 hours ago`. Colour `--quiet` when the project is gone quiet (use the app's existing rule), otherwise `--text-label`. |

### 3.5 Pagination footer (inside the table panel, under the last row)
- Background `--sidebar`, top border 1px `--hover`, padding 10px 14px 10px 17px, space-between.
- Left: `11–20 of 34 projects` (the range in `--text` 600, the rest `--text-muted`, 13px). When filtered: `1–10 of 19 · filtered from 34`.
- Right: `‹ Prev` · page numbers · `Next ›`, as `<button>`s 34px high, radius 10px, background `--panel`, border `--border`. Current page: background `--text`, text `--bg`, `aria-current="page"`. Prev/Next are disabled at the ends. With more than 7 pages, show `1 … 4 5 6 … 12`.
- **Hide the page buttons when there's only one page**; keep the count text.
- 10 rows per page.

### 3.6 No results
When the filters match nothing, replace the rows with a centred block inside the panel: `No projects match these filters.` (14px/600) and a light **Clear filters** button (background `--text`, text `--bg`).

---

## 4. To do page (new)

Route: e.g. `/todo` (match the app's style). Same sidebar, with "To do" as the current item.

### 4.1 Data
Store the todos however the app already stores its data (SQLite table or JSON file — check first). Fields:
`id`, `text` (string, trimmed, not empty), `high` (bool), `done` (bool), `created_at` (timestamp, used for ordering).

JSON endpoints (or form posts, whichever fits the app):
- `GET  /api/todos` → list
- `POST /api/todos` `{text}` → create (normal, not done)
- `PATCH /api/todos/<id>` `{text?|high?|done?}` → update one field
- `DELETE /api/todos/<id>` → delete at once
- `DELETE /api/todos/done` → delete all done todos

The server also refuses empty or whitespace-only text (400).

### 4.2 Layout
Main area: the header, then a column with `max-width: 860px`, gap 14px.
- **Header**: `.lbl` date, `<h1>` "To do", summary `6 open · 2 high · 3 done` (the "2 high" part in `--critical` 600).
- **Add bar**: a `<form>` box (padding 8px, radius 16px, background `--panel`, border `--border`) containing:
  - an input `Add a todo…` (height 44px, radius 10px, background `--bg`, border `--border`, 14.5px)
  - a visible **Add** button (height 44px, padding 0 24px, background `--text`, text `--bg`)
  - Enter submits too. Trim the text; if it's empty, do nothing. After adding: clear the input and keep focus in it.
- **High card**: shown only if there is at least one open high todo. Head row 44px: a red flag icon + `.lbl` `HIGH · 2` in `--critical`.
- **Normal card**: head `.lbl` `NORMAL · 4`.
- **Done card** (at the bottom): background `--sidebar`, border `--hover`. Head: `.lbl` `DONE · 3` on the left, **Clear done** button on the right (border `rgba(242,92,84,.4)`, text `--critical`). Hidden when nothing is done.
- Cards: background `--panel`, border `--border`, radius 14px, `overflow:hidden`.

### 4.3 Open todo row (min-height 50px, padding 0 10px 0 18px, gap 14px, top border 1px `--hover`, hover `--raised`)
`[○ checkbox] [text …] [flag] [✎ Edit] [×]`
- **Checkbox**: a 20px round `<button role="checkbox" aria-checked>`, border 1.6px `--border-focus`. Click → done.
- **Text**: 14px, one line, cut with "…" (full text in `title`).
- **Priority flag**: a 32px square icon `<button>`, radius 9px. High = filled flag, `--critical` on `--critical-bg`; normal = outline flag in `--border-focus`, hover `--high`. **One click switches**. `aria-label` says the current state and what a click does ("High priority, click for normal").
- **✎ Edit**: 32px high, padding 0 11px, radius 9px, border `--border`, 12.5px, text `--text-muted`.
- **×**: a 32px square, 18px glyph, `--text-label`; hover `--critical` on `--critical-bg`. `aria-label="Delete"`. **Deletes at once, no question.**

### 4.4 Order
Inside the open list: **high first, then oldest `created_at` first**. A new todo goes to the bottom of its group. Switching a todo's priority moves it into the other group, placed by its `created_at`.

### 4.5 Editing
- Click **✎ Edit**: the row becomes `[faded checkbox] [text input] [Save] [Cancel]`. The row background is `--raised`; the input is 40px, radius 10px, border 1.5px `--text`, background `--bg`, focused, with the text selected.
- **Save** (light button) and **Cancel** (dark button) are always visible. Enter = Save, Esc = Cancel (only while that input has focus; no global key handlers).
- **Only one row edits at a time.** While a row is editing, every other row's **✎ Edit is `disabled`** (text `#45413D`, border `--raised`, no hover). Their checkboxes, flags and × keep working.
- Saving empty or whitespace-only text is refused: the input border turns `--critical`, and a 12px message appears under it in `--high`: `Please type something — an empty todo can't be saved.` Use `aria-invalid="true"` + `aria-describedby`. The message clears as soon as you type.

### 4.6 Done group
- Done rows: min-height 44px, a filled round checkbox (background `--border-strong` + a check icon), text struck through in `--text-label`, and a × delete. No flag or edit buttons. **Any priority** goes here.
- Clicking the checkbox **unticks** it: it goes back to the open list in its correct ordered place.
- Order inside Done: most recently done first (or `created_at` — either is fine, be consistent).
- **Clear done**: the first click turns the Done card's head into a confirm bar (height 58px, background `rgba(242,92,84,.08)`): `Delete 3 done todos for good?` with the live count, a **Yes, delete** button (background `--critical`, dark text) and a **Cancel** button. Esc = Cancel. Confirm → `DELETE /api/todos/done`.

### 4.7 Empty state (no todos at all)
Under the add bar: one card with a dashed border and background `--sidebar`, holding a 40px circle with a check icon, then **All clear.** (15px/600) and `No todos yet. Add one above when something comes up.` (13px `--text-muted`). There are no High / Normal / Done cards.

### 4.8 Sidebar badge
Always shows the number of **open** todos and turns red when at least one is high (§2). Update it right away on add, tick, untick, priority switch and delete — no page reload.

---

## 5. Filter + tab + pagination logic (Dashboard)

Do it **in the browser**: load all open projects once (from the existing route or a new `GET /api/projects`), then filter, count, sort and slice in JS. 30–100 rows is instant.

**State** (one object) — keep it in the URL with `history.replaceState`, so reload and Back keep the view:
```
?q=report&status=active,pending&prio=critical,high&tab=quiet&page=2
```
Missing param = default (`q=''`, all statuses, all priorities, `tab=all`, `page=1`).

**Pipeline**
1. `base` = all open projects.
2. **Search** `q` (case-insensitive, trimmed) matches the name, the ticket ID or the next-step text. Wait about 150ms after typing stops.
3. **Status**: if any are ticked, keep only rows whose status is one of them (OR inside a group).
4. **Priority**: same (OR inside a group). Groups combine with AND.
5. → `filtered`. The **tile counts** come from `filtered`: All = `filtered.length`; Critical = priority critical; Pending = status pending; Gone quiet = the quiet rule.
6. **Tab** narrows `filtered` further → `shown`.
7. **Sort** `shown`: priority (critical, high, normal), then oldest update first. (Keep the current sort if the app already has one.)
8. **Paginate**: 10 per page. If `page` is past the last page, use the last page.

**Rules**
- Any change to search, filters or tab → `page = 1`.
- The popover counts show what you'd get for each value given the *other* filters and the search (normal faceted counts). A value with 0 is greyed out but can still be ticked.
- Summary line in the header = totals for all open projects, never filtered.
- "filtered from N" in the footer appears only when search or a filter is active.

---

## 6. Accessibility basics
- Real `<button>`, `<a href>`, `<input>` + `<label>` everywhere. Never put click handlers on a `div` or `span`.
- Icon-only buttons get an `aria-label`. Decorative SVGs get `aria-hidden="true"`.
- Visible focus: `:focus-visible { outline: 2px solid var(--text); outline-offset: 2px; }`.
- Text contrast: keep small text at `--text-label` (#8F8A83) or lighter, never darker, except for disabled items.

---

## 7. What NOT to do
- No frameworks, Tailwind, Bootstrap, icon fonts, or npm build.
- No sideways scroll anywhere. If something overflows, fix the grid (`minmax(0, …)`, `min-width: 0`) — don't add `overflow-x`.
- No `vh`-based fixed heights on the table; let the page scroll vertically if 10 rows don't fit on a 768px-tall screen.
- Don't use the meaning colours for decoration.
- Don't change how the project card pop-up works.

---

## 8. Acceptance checklist (test at 1366×768 AND 1920×1080)
- [ ] The Updated column is fully visible; no horizontal scrollbar at either size.
- [ ] Long names, next steps and blockers end in "…" and show the full text on hover.
- [ ] 34 test projects → `1–10 of 34`, 4 pages; Prev is disabled on page 1 and Next on page 4.
- [ ] Ticking Status: active → a chip appears, the tiles recount, the footer says `· filtered from 34`, and you're on page 1.
- [ ] A chip's × clears that group; Clear all clears everything; reloading keeps the state (URL).
- [ ] Filters that match nothing → the "No projects match" block with a working Clear filters.
- [ ] Clicking a row still opens the project card.
- [ ] To do: add via the button and via Enter; an empty add does nothing.
- [ ] Order: high first, then oldest; a new todo goes to the bottom of its group.
- [ ] The flag switches priority in one click and the row moves group.
- [ ] Edit: only one at a time, other Edit buttons disabled; an empty save shows the inline error; Esc cancels.
- [ ] × deletes at once. Tick → Done (struck through). Untick → back in the right place.
- [ ] Clear done asks once with the right count, then deletes.
- [ ] No todos → the empty state. The sidebar badge count and red/grey colour stay correct after every action.

---

## 9. Suggested build order
1. Read the existing code; list the files you'll touch.
2. Add the token CSS (§1) and fonts; restyle the shell + sidebar (§2).
3. Dashboard header + tiles + table restyle with the grid columns (§3.1–3.4). Check the width at 1366.
4. Filters + chips + popover + pagination + URL state (§3.3, §3.5, §5).
5. To do: storage + endpoints (§4.1), then the UI (§4.2–4.7), then the badge (§4.8).
6. Go through the checklist (§8) at both sizes.
