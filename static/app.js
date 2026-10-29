// Dashboard: fetch projects from Flask, draw tabs + list.
// Python does the logic (sorting, days_ago, quiet); this file only filters and draws.

const $ = id => document.getElementById(id);
const esc = s => String(s ?? "").replace(/[&<>"]/g, c => ({"&":"&amp;", "<":"&lt;", ">":"&gt;", '"':"&quot;"}[c]));
const ago = n => n === 0 ? "today" : n === 1 ? "1 day ago" : `${n} days ago`;
// A table cell's text: at most 2 lines (app.css .clip), hover for all of it. Empty = a grey dash.
const clip = s => s ? `<div class="clip" title="${esc(s)}">${esc(s)}</div>` : '<span class="none">—</span>';
// progress "6/12" (from the ticket's requirements.md checklist) = a small bar + "6 of 12 done". None = nothing.
const progress = s => {
  const [done, all] = String(s ?? "").split("/").map(Number);
  if (!all) return "";
  return `<div class="prog"><span class="bar"><span style="width:${Math.round(100 * done / all)}%"></span></span>`
    + `<span class="n">${done} of ${all} done</span></div>`;
};
const stripe = p => p.priority === "critical" ? "var(--crit)"
  : p.status === "pending" ? "var(--pend)" : p.status === "active" ? "var(--ok)" : "var(--idea)";

const TABS = {
  all:      {label: "All open",   c: "var(--fg)",    keep: p => true},
  critical: {label: "Critical",   c: "var(--crit)",  keep: p => p.priority === "critical"},
  pending:  {label: "Pending",    c: "var(--pend)",  keep: p => p.status === "pending"},
  quiet:    {label: "Gone quiet", c: "var(--quiet)", keep: p => p.quiet},
};
let tab = "all";
let projects = [];

// Re-read the notes from disk on page load, on every tab switch, every 30 seconds and when you come
// back to this browser tab (so a card Claude just updated shows without pressing F5).
async function load() {
  try {
    const response = await fetch("/api/projects");
    if (!response.ok) throw new Error(`server said ${response.status}`);
    const data = await response.json();
    projects = data.projects;
    drawHeader(data.today);
    draw();
  } catch (err) {
    $("list").innerHTML = `<div class="empty bad"><b>Could not read your projects.</b>${esc(err.message)}. Check the terminal where the app runs.</div>`;
  }
}

function drawHeader(today) {
  const day = new Date(today + "T12:00:00");
  $("date").textContent = day.toLocaleDateString("en-GB", {weekday: "long"}) + " · "
    + day.toLocaleDateString("en-GB", {day: "numeric", month: "long", year: "numeric"});
  const n = k => projects.filter(TABS[k].keep).length;
  $("summary").innerHTML = `${projects.length} open · <b style="color:var(--crit)">${n("critical")} critical</b>`
    + ` · <b style="color:var(--pend)">${n("pending")} pending</b> · <b style="color:var(--quiet)">${n("quiet")} gone quiet</b>`;
}

function draw() {
  $("tabs").innerHTML = Object.entries(TABS).map(([k, t]) =>
    `<button role="tab" data-tab="${k}" aria-selected="${k === tab}"><span class="dot" style="--c:${t.c}"></span>${t.label}<span class="n">${projects.filter(t.keep).length}</span></button>`
  ).join("");

  const rows = projects.filter(TABS[tab].keep);
  if (!rows.length) {
    $("list").innerHTML = `<div class="empty"><b>Nothing here.</b>No open project matches this tab.</div>`;
    return;
  }
  $("list").innerHTML = `<div class="list"><table>
    <thead><tr><th>Project</th><th>Status</th><th>Priority</th><th>Working on</th><th>Next step</th><th>Blocked by</th><th>Updated</th></tr></thead>
    <tbody>${rows.map((p, i) => `
      <tr data-open="${esc(p.id)}" style="--stripe:${stripe(p)};animation-delay:${i * 40}ms">
        <td><span class="pname">${esc(p.title)}</span><span class="pjira">${p.jira ? esc(p.jira) : "no Jira"}</span></td>
        <td><span class="pill st-${esc(p.status)}">${esc(p.status)}</span></td>
        <td><span class="pill pr-${esc(p.priority)}">${esc(p.priority)}</span></td>
        <td class="next">${clip(p.working_on)}${progress(p.progress)}</td>
        <td class="next">${clip(p.next)}</td>
        <td>${p.blocked_by ? `<span class="blk">${clip(p.blocked_by)}</span>` : '<span class="none">—</span>'}</td>
        <td><span class="ago ${p.quiet ? "q" : ""}">${ago(p.days_ago)}</span></td>
      </tr>`).join("")}</tbody></table></div>`;
}

$("tabs").addEventListener("click", e => {
  const button = e.target.closest("[data-tab]");
  if (!button) return;
  tab = button.dataset.tab;
  load();
});

// Sidebar: Dashboard / Ask Claude / Archive (and the dashboard's Ask Claude button). Each switch re-reads from disk.
document.querySelector(".app").addEventListener("click", e => {
  const button = e.target.closest("[data-page]");
  if (button) showPage(button.dataset.page);
});

function showPage(page) {
  if (page === "ask" && !$("page-ask").hidden) return;     // already here: keep the chat
  document.querySelectorAll(".nav[data-page]").forEach(n =>
    n.dataset.page === page ? n.setAttribute("aria-current", "page") : n.removeAttribute("aria-current"));
  $("page-dash").hidden = page !== "dash";
  $("page-ask").hidden = page !== "ask";
  $("page-archive").hidden = page !== "archive";
  if (page === "dash") load();
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

// Click a row = open that project's card (card.js).
$("list").addEventListener("click", e => {
  const row = e.target.closest("[data-open]");
  if (row) openCard(row.dataset.open);
});

// Auto refresh, only while the dashboard is the page shown and the browser tab is in front.
// It redraws only the table: an open project card (a pop-up over it) is not touched.
const REFRESH_SECONDS = 30;
const dashShown = () => !$("page-dash").hidden && document.visibilityState === "visible";
setInterval(() => { if (dashShown()) load(); }, REFRESH_SECONDS * 1000);
document.addEventListener("visibilitychange", () => { if (dashShown()) load(); });

load();
