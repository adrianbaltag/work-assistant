// Dashboard: fetch projects from Flask, draw tiles + filters + one page of the list.
// Python does the logic (sorting, days_ago, quiet); paging.js does the paging maths; this file draws.

const $ = id => document.getElementById(id);
// Shown when fetch() gets no answer at all (the app was stopped). Used by chat.js and todo.js.
const REACH_ERROR = "Could not reach the app. Is it still running in the terminal?";
const esc = s => String(s ?? "").replace(/[&<>"]/g, c => ({"&":"&amp;", "<":"&lt;", ">":"&gt;", '"':"&quot;"}[c]));
const ago = n => n === 0 ? "today" : n === 1 ? "1 day ago" : `${n} days ago`;
// A table cell's text: one line (app.css .clip), cut with "…"; hover shows all of it. Empty = a grey dash.
const clip = s => s ? `<span class="clip" title="${esc(s)}">${esc(s)}</span>` : '<span class="none">—</span>';
// A milestone cell, e.g. "M8 of 12 · hourly job runs": the number on its own line (never cut), the name under it.
// Text without " · " (no checklist in requirements.md) = a plain clip.
const step = s => {
  const [num, ...name] = String(s ?? "").split(" · ");
  if (!name.length) return clip(s);
  return `<span title="${esc(s)}"><span class="mnum">${esc(num)}</span><span class="clip">${esc(name.join(" · "))}</span></span>`;
};
const stripe = p => p.priority === "critical" ? "var(--critical)"
  : p.status === "pending" ? "var(--pending)" : p.status === "active" ? "var(--active)" : "var(--idea)";

const TABS = {
  all:      {label: "All open",   c: "var(--text)",    keep: p => true},
  critical: {label: "Critical",   c: "var(--critical)",  keep: p => p.priority === "critical"},
  pending:  {label: "Pending",    c: "var(--pending)",  keep: p => p.status === "pending"},
  quiet:    {label: "Gone quiet", c: "var(--quiet)", keep: p => p.quiet},
};
let tab = "all";
let projects = [];
// Search box + the two dropdowns. Kept while you move between sidebar pages; F5 starts clean.
const filters = {q: "", status: "", prio: ""};
let page = 1;
let perPage = 3;        // rows per page: fitRows() sets it from the window height
let readOk = false;     // false = the last read failed: the error stays on screen until a read works
let asked = 0;          // counts reads; an answer older than the one on screen is dropped
let onScreen = 0;
let focusAfter = null;  // the row to focus once a read lands: {id, from = the read that asked for it}.
                        // Kept until that read (or a newer one) lands: an older refresh must not use it up.

// Re-read the notes from disk on page load, on every tab switch, every 30 seconds and when you come
// back to this browser tab (so a card Claude just updated shows without pressing F5).
// animate = rows slide in (only for a tile click; a refresh must not flicker).
// focusId = put the keyboard focus on that project's row (the card you just closed).
async function load(animate = false, focusId = null) {
  const number = ++asked;
  if (focusId) focusAfter = {id: focusId, from: number};
  try {
    const response = await fetch("/api/projects");
    if (!response.ok) {
      // The app sends its own plain words when it can (e.g. "Can't open the projects folder ...").
      const problem = await response.json().catch(() => ({}));
      throw Object.assign(new Error(problem.error || `server said ${response.status}`), {plain: Boolean(problem.error)});
    }
    const data = await response.json();
    if (number < onScreen) return;       // a newer read already drew (e.g. the card you just saved)
    onScreen = number;
    projects = data.projects;
    readOk = true;
    drawHeader(data.today);
    draw(animate, focusAfter && focusAfter.id);
    if (focusAfter && number >= focusAfter.from) focusAfter = null;
  } catch (err) {
    if (number < onScreen) return;
    onScreen = number;
    readOk = false;
    if (focusAfter && number >= focusAfter.from) focusAfter = null;
    const advice = err.plain ? "" : ". Check the terminal where the app runs.";    // the app's words already say what to do
    put($("list"), `<div class="empty bad"><b>Could not read your projects.</b>${esc(err.message)}${advice}</div>`);
  }
}

// A date as "Friday · 30 October 2026" (CSS shows it in capitals). The To do page uses it too.
const longDate = day => day.toLocaleDateString("en-GB", {weekday: "long"}) + " · "
  + day.toLocaleDateString("en-GB", {day: "numeric", month: "long", year: "numeric"});

// The line under the title: totals for ALL open projects, the filters never change it.
function drawHeader(today) {
  $("date").textContent = longDate(new Date(today + "T12:00:00"));
  const n = k => projects.filter(TABS[k].keep).length;
  $("summary").innerHTML = `${projects.length} open · <b style="color:var(--critical)">${n("critical")} critical</b>`
    + ` · <b style="color:var(--pending)">${n("pending")} pending</b> · <b style="color:var(--quiet)">${n("quiet")} gone quiet</b>`;
}

// How many rows fit between the top of the list and the bottom of the window, so the page never
// scrolls up/down. The row, header and footer heights are read from app.css (:root --row-h etc.),
// so changing them there is enough. They never change, so they are read once (the first time).
let sizes = null;
function fitRows() {
  if ($("page-dash").hidden) return;      // hidden = nothing to measure; keep the last count
  let s = sizes;
  if (!s) {
    const css = getComputedStyle(document.documentElement);
    const px = name => parseFloat(css.getPropertyValue(name));
    s = {row: px("--row-h"), head: px("--head-h"), foot: px("--foot-h"),
         below: parseFloat(getComputedStyle($("page-dash")).paddingBottom) + 2};   // + the list's top and bottom border
    if (Object.values(s).every(Number.isFinite)) sizes = s;    // kept only if app.css had loaded (real numbers)
  }
  const top = $("list").getBoundingClientRect().top + window.scrollY;
  const room = window.innerHeight - top - s.below - s.head - s.foot;
  const first = (page - 1) * perPage;     // the top row you are looking at...
  perPage = rowsThatFit(room, s.row);
  page = pageHolding(first, perPage);     // ...stays on screen when the count changes
}

// Put new HTML in a box, but only when it differs from what is there: the 30 s refresh mostly finds
// nothing new, and a redraw would drop the keyboard focus, a hover tooltip or a half-done click.
// force = draw anyway (the slide-in on a page/tile change). Returns true when it redrew.
function put(box, html, force = false) {
  if (!force && box.drawn === html) return false;
  box.innerHTML = html;
  box.drawn = html;
  return true;
}

// The tile or list button that has the keyboard focus, as a CSS selector, so a redraw can give it back.
// A page number is found by its number, Prev/Next by data-arrow (their number changes).
function focusedInList() {
  const el = document.activeElement;
  if (!el || !($("list").contains(el) || $("tabs").contains(el))) return null;
  if (el.dataset.tab) return `[data-tab="${el.dataset.tab}"]`;
  if (el.dataset.open) return `[data-open="${CSS.escape(el.dataset.open)}"]`;
  if (el.dataset.arrow) return `[data-arrow="${el.dataset.arrow}"]`;
  if (el.dataset.go) return `[data-go="${el.dataset.go}"]:not([data-arrow])`;
  return null;
}

// Put the focus back after a redraw, so it never falls off the page. If that button is gone (Prev/Next
// went grey, the row moved to another page or was archived), the next best one that is there:
// the first row, the current page number, "Clear filters", the chosen tile.
function refocus(selector) {
  const tries = [`#tabs ${selector}`, `#list ${selector}`, "#list [data-open]", '#list [aria-current="page"]',
                 "#list [data-clear]", '#tabs [aria-selected="true"]'];
  // One look-up per try, in this order (one querySelectorAll would return them in page order instead).
  // offsetParent = null: hidden (a narrow window hides most page numbers), so it can't take the focus.
  tries.map(t => document.querySelector(t)).find(b => b && !b.disabled && b.offsetParent)?.focus();
}

function draw(animate = false, focusId = null) {
  const keep = focusId ? `[data-open="${CSS.escape(focusId)}"]` : focusedInList();
  const filtering = filtersOn(filters);
  const passed = filterProjects(projects, filters);
  const tilesDrew = put($("tabs"), Object.entries(TABS).map(([k, t]) => {
    const n = passed.filter(t.keep).length;
    return `<button role="tab" data-tab="${k}" aria-selected="${k === tab}" class="${n ? "" : "zero"}" style="--c:${t.c}">`
      + `<span class="tl">${k === "all" ? "" : `<span class="dot" style="--c:${t.c}"></span>`}${t.label}</span><span class="n">${n}</span></button>`;
  }).join(""));
  $("dash-clear").hidden = !filtering;
  $("dash-q").classList.toggle("on", Boolean(filters.q.trim()));
  $("dash-status").classList.toggle("on", Boolean(filters.status));
  $("dash-prio").classList.toggle("on", Boolean(filters.prio));

  const rows = passed.filter(TABS[tab].keep);
  const head = `<div class="prow head">${["Project", "Status", "Priority", "Working on", "Next step", "Blocked by", "Updated"]
    .map(h => `<span class="c lbl">${h}</span>`).join("")}</div>`;
  const empty = emptyMessage(passed.length, rows.length, filtering);
  const html = empty === "nomatch"
    ? `<div class="plist">${head}<div class="nomatch"><b>No projects match these filters.</b>`
      + `<button class="btn primary" data-clear>Clear filters</button></div></div>`
    : empty ? `<div class="empty"><b>Nothing here.</b>No open project matches this tab.</div>`
    : listHtml(rows, head, filtering, focusId);
  const slide = animate && !empty;
  const drew = put($("list"), html, slide);
  // The slide-in class is added after, so the next refresh compares the same HTML and leaves it alone.
  if (drew && slide) $("list").firstElementChild.classList.add("anim");
  if (keep && (drew || tilesDrew || focusId)) refocus(keep);   // focusId: the card just closed, its focus is gone
}

// One page of rows + the footer (count and page buttons). focusId = the card you just closed:
// its project may have moved (saving puts it at the top), so show the page that holds it.
function listHtml(rows, head, filtering, focusId) {
  fitRows();
  const at = focusId ? rows.findIndex(p => p.id === focusId) : -1;
  if (at >= 0) page = pageHolding(at, perPage);
  const pages = Math.ceil(rows.length / perPage);
  page = Math.min(Math.max(page, 1), pages);    // the list shrank (refresh, card closed): last page
  const from = (page - 1) * perPage;
  const shown = rows.slice(from, from + perPage);
  const count = footerText(from, shown.length, rows.length, projects.length, filtering);
  const pager = pages < 2 ? "" : `<nav class="pager" aria-label="Pages">`
    + `<button data-go="${page - 1}" data-arrow="prev" ${page === 1 ? "disabled" : ""}>‹ Prev</button>`
    + pageList(pages, page).map(n => n === "…" ? '<span class="gap">…</span>'
      : `<button data-go="${n}" ${n === page ? 'aria-current="page"' : ""}>${n}</button>`).join("")
    + `<button data-go="${page + 1}" data-arrow="next" ${page === pages ? "disabled" : ""}>Next ›</button></nav>`;

  // Each row is a button: click (or Enter) opens that project's card.
  return `<div class="plist">${head}${shown.map((p, i) => `
    <button type="button" class="prow" data-open="${esc(p.id)}" style="--stripe:${stripe(p)};animation-delay:${i * 40}ms">
      <span class="c"><span class="pname clip" title="${esc(p.title)}">${esc(p.title)}</span><span class="pjira clip">${p.jira ? esc(p.jira) : "no Jira"}</span></span>
      <span class="c"><span class="pill st-${esc(p.status)}">${esc(p.status)}</span></span>
      <span class="c"><span class="pill pr-${esc(p.priority)}">${esc(p.priority)}</span></span>
      <span class="c next">${step(p.working_on)}</span>
      <span class="c next">${step(p.next)}</span>
      <span class="c">${p.blocked_by ? `<span class="blk">${clip(p.blocked_by)}</span>` : '<span class="none">—</span>'}</span>
      <span class="c"><span class="ago ${p.quiet ? "q" : ""}">${ago(p.days_ago)}</span></span>
    </button>`).join("")}<div class="pfoot"><span>${count}</span>${pager}</div></div>`;
}

// Filters, resize, fonts: draw again from the projects already read. Not after a failed read:
// the "Could not read your projects" message must stay until the app answers again.
const redraw = () => { if (readOk) draw(); };

$("tabs").addEventListener("click", e => {
  const button = e.target.closest("[data-tab]");
  if (!button) return;
  tab = button.dataset.tab;
  page = 1;
  load(true);
});

// Filters: any change goes back to page 1. The search waits until you stop typing for 150 ms.
let typing;
$("dash-q").addEventListener("input", () => {
  clearTimeout(typing);
  typing = setTimeout(() => { filters.q = $("dash-q").value; page = 1; redraw(); }, 150);
});
$("dash-status").addEventListener("change", () => { filters.status = $("dash-status").value; page = 1; redraw(); });
$("dash-prio").addEventListener("change", () => { filters.prio = $("dash-prio").value; page = 1; redraw(); });
// Clear filters empties the search and both dropdowns; the chosen tile stays. Both Clear buttons
// vanish when clicked, so the keyboard focus goes to the search box (not lost on the page).
function clearFilters() {
  clearTimeout(typing);
  filters.q = filters.status = filters.prio = "";
  $("dash-q").value = $("dash-status").value = $("dash-prio").value = "";
  page = 1;
  redraw();
  $("dash-q").focus();
}
$("dash-clear").addEventListener("click", clearFilters);

// A new window size = a new number of rows per page (wait until the resizing stops).
let resizing;
window.addEventListener("resize", () => {
  clearTimeout(resizing);
  resizing = setTimeout(redraw, 150);
});
// Same when the web fonts (Google Fonts) arrive after the first draw: the text above the list
// changes height, so count the rows again.
document.fonts.addEventListener("loadingdone", redraw);

// Sidebar: Dashboard / To do / Ask Claude / Archive (and the dashboard's Ask Claude button). Each switch re-reads from disk.
document.querySelector(".app").addEventListener("click", e => {
  const button = e.target.closest("[data-page]");
  if (button) showPage(button.dataset.page);
});

function showPage(page) {
  if (page === "ask" && !$("page-ask").hidden) return;     // already here: keep the chat
  document.querySelectorAll(".nav[data-page]").forEach(n =>
    n.dataset.page === page ? n.setAttribute("aria-current", "page") : n.removeAttribute("aria-current"));
  $("page-dash").hidden = page !== "dash";
  $("page-todo").hidden = page !== "todo";
  $("page-ask").hidden = page !== "ask";
  $("page-archive").hidden = page !== "archive";
  if (page === "dash") load();
  else if (page === "todo") loadTodos();      // todo.js
  else if (page === "ask") askAll();
  else loadArchive();
}

// Global Ask Claude: answers only. Opening the page starts a fresh chat (decided): an old one
// may answer from notes that changed since.
function askAll() {
  makeChat($("ask-chat"), {
    sub: "about all your open projects",
    intro: "I can read the note of every open project. What do you need?",
    chips: ["What should I work on this morning?", "Which projects are blocked?",
            {label: "Quick summary", ask: "Give me a quick summary of all my open projects together: "
              + "a short paragraph or a few bullet points."},
            {label: "My next steps", ask: "For each open project, critical first, write a short paragraph "
              + "covering: the issue, where I stand, the next step(s), and the fix (planned or done). "
              + "Say so if the notes don't cover one of these."}],
    placeholder: "Ask about your projects…",
    url: "/api/ask",
    note: "Answers only. To change a project, ask in its card.",
  });
}

// Click a row = open that project's card (card.js). Also the page buttons and "Clear filters".
$("list").addEventListener("click", e => {
  const row = e.target.closest("[data-open]");
  // You dragged over the text to copy it (mouse only: Enter has e.detail 0 and always opens).
  if (row && e.detail && String(window.getSelection())) return;
  if (row) return openCard(row.dataset.open);
  const go = e.target.closest("[data-go]");
  if (go && !go.disabled) { page = Number(go.dataset.go); draw(true); return; }
  if (e.target.closest("[data-clear]")) clearFilters();
});

// Auto refresh, only while the dashboard is the page shown and the browser tab is in front.
// It redraws only the table: an open project card (a pop-up over it) is not touched.
const REFRESH_SECONDS = 30;
const dashShown = () => !$("page-dash").hidden && document.visibilityState === "visible";
setInterval(() => { if (dashShown()) load(); }, REFRESH_SECONDS * 1000);
document.addEventListener("visibilitychange", () => { if (dashShown()) load(); });

load();
