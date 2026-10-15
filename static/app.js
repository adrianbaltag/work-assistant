// Dashboard: fetch projects from Flask, draw tabs + list.
// Python does the logic (sorting, days_ago, quiet); this file only filters and draws.

const $ = id => document.getElementById(id);
const esc = s => String(s ?? "").replace(/[&<>"]/g, c => ({"&":"&amp;", "<":"&lt;", ">":"&gt;", '"':"&quot;"}[c]));
const ago = n => n === 0 ? "today" : n === 1 ? "1 day ago" : `${n} days ago`;
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

// Re-read the notes from disk on page load and on every tab switch (no timer, no refresh button).
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
    <thead><tr><th>Project</th><th>Status</th><th>Priority</th><th>Next step</th><th>Blocked by</th><th>Updated</th></tr></thead>
    <tbody>${rows.map((p, i) => `
      <tr data-open="${esc(p.id)}" style="--stripe:${stripe(p)};animation-delay:${i * 40}ms">
        <td><span class="pname">${esc(p.title)}</span><span class="pjira">${p.jira ? esc(p.jira) : "no Jira"}</span></td>
        <td><span class="pill st-${esc(p.status)}">${esc(p.status)}</span></td>
        <td><span class="pill pr-${esc(p.priority)}">${esc(p.priority)}</span></td>
        <td class="next">${esc(p.next) || '<span class="none">—</span>'}</td>
        <td>${p.blocked_by ? `<span class="blk">${esc(p.blocked_by)}</span>` : '<span class="none">—</span>'}</td>
        <td><span class="ago ${p.quiet ? "q" : ""}">${ago(p.days_ago)}</span></td>
      </tr>`).join("")}</tbody></table></div>`;
}

$("tabs").addEventListener("click", e => {
  const button = e.target.closest("[data-tab]");
  if (!button) return;
  tab = button.dataset.tab;
  load();
});

// Click a row = open that project's card (card.js).
$("list").addEventListener("click", e => {
  const row = e.target.closest("[data-open]");
  if (row) openCard(row.dataset.open);
});

load();
