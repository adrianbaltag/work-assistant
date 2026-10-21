// Slack button: asks Flask every 3 seconds what is unread. Flask never calls Slack for this:
// slack_live.py does that in the background. Glow + count while anything is unread; click = dropdown;
// click a row = the Slack app opens at that message and the row goes at once.
// Uses $ and esc from app.js.

const SLACK_EVERY_MS = 3000;
const SLACK_STATES = {checking: "checking…", reconnecting: "reconnecting…", off: "not connected", error: "error"};
let slack = null;           // the last /api/slack answer
let slackDrawn = "";        // what is on screen now, so an unchanged answer doesn't redraw (keeps hover/focus)

async function slackLoad() {
  if (document.hidden) return;          // tab not visible: no need to ask
  try {
    const response = await fetch("/api/slack");
    if (!response.ok) throw new Error(`server said ${response.status}`);
    slack = await response.json();
  } catch (err) {
    slack = {state: "error", message: `Could not reach the app (${err.message}). Is it still running in the Terminal?`,
             count: 0, mentions: [], mentions_more: 0, dms: [], dms_more: 0};
  }
  slackDraw();
}

const initials = name => String(name).split(/[\s,]+/).filter(Boolean).map(w => w[0]).join("").slice(0, 2).toUpperCase();

function slackRow(r, kind) {
  const where = kind === "mention" ? ` <span class="dd-where">in ${esc(r.where)}</span>`
    : r.where === "group DM" ? ` <span class="dd-where">group DM</span>` : "";
  const tags = r.tags.map(t => `<span class="dd-tag">${esc(t)}</span>`).join("");
  const more = r.more ? ` <span class="dd-where">+${r.more} more</span>` : "";
  return `<a class="dd-item" href="${esc(r.link)}" data-channel="${esc(r.channel)}" data-ts="${esc(r.ts)}" title="Open in Slack">
    <span class="av">${esc(initials(r.who))}</span>
    <span class="dd-txt"><b>${esc(r.who)}</b>${where}${tags}${more}<span class="dd-msg">${esc(r.text)}</span></span>
    <span class="dd-ago">${esc(r.when)}</span></a>`;
}

function slackSection(label, rows, older, kind) {
  if (!rows.length) return "";
  return `<div class="dd-label">${label} · ${rows.length + older}</div>${rows.map(r => slackRow(r, kind)).join("")}`
    + (older ? `<div class="dd-older">+${older} older: open Slack to see them</div>` : "");
}

function slackDraw() {
  const s = slack;
  const key = JSON.stringify(s);
  if (key === slackDrawn) return;
  slackDrawn = key;
  const ok = s.state === "connected";
  const button = $("nav-slack");
  button.classList.toggle("has-new", s.count > 0);
  button.classList.toggle("grey", !ok && !s.count);
  $("slack-label").textContent = ok ? "Slack" : `Slack: ${SLACK_STATES[s.state] || s.state}`;
  $("slack-n").textContent = s.count;
  $("slack-n").hidden = !s.count;
  button.title = s.message || (s.count ? `${s.count} unread in Slack` : "No new mentions or DMs");

  const sub = ok ? "Click one to open it in Slack" + (s.mode === "backup" ? " · backup mode" : "")
    : `Slack: ${SLACK_STATES[s.state] || s.state}`;
  const note = s.message && (!ok || s.mode === "backup") ? `<div class="dd-note">${esc(s.message)}</div>` : "";
  const rows = slackSection("Mentions", s.mentions, s.mentions_more, "mention")
    + slackSection("Direct messages", s.dms, s.dms_more, "dm");
  const empty = ok && !s.count ? `<div class="dd-empty"><b>All caught up.</b>No new mentions or direct messages.</div>` : "";
  $("slack-dd").innerHTML = `<div class="dd-head"><b>Slack</b><small>${esc(sub)}</small></div>${note}`
    + (rows ? `<div class="dd-list">${rows}</div>` : "") + empty;
}

function slackOpen(open) {
  $("slack-dd").hidden = !open;
  $("nav-slack").setAttribute("aria-expanded", open);
}

$("nav-slack").addEventListener("click", () => slackOpen($("slack-dd").hidden));

// Click a row: the link opens the Slack app; tell Flask so the row goes now (not ~10 s later).
$("slack-dd").addEventListener("click", async e => {
  const item = e.target.closest("[data-ts]");
  if (!item) return;
  try {
    const response = await fetch("/api/slack/opened", {method: "POST", headers: {"Content-Type": "application/json"},
      body: JSON.stringify({channel: item.dataset.channel, ts: item.dataset.ts})});
    if (response.ok) { slack = await response.json(); slackDraw(); }
  } catch (err) { /* the next check fixes the list */ }
});

document.addEventListener("click", e => { if (!$("slack-dd").hidden && !e.target.closest(".slack-wrap")) slackOpen(false); });
document.addEventListener("keydown", e => {
  if (e.key === "Escape" && !$("slack-dd").hidden) { slackOpen(false); $("nav-slack").focus(); }
});
document.addEventListener("visibilitychange", () => { if (!document.hidden) slackLoad(); });

slackLoad();
setInterval(slackLoad, SLACK_EVERY_MS);
