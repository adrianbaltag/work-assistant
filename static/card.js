// Project card: pops in over the dashboard. Reads one project from Flask and edits its note.md.
// Every save sends back the "stamp" the card got when it opened. If note.md changed since
// (e.g. Claude Code saved it), Flask answers 409 and we offer "Save mine anyway" / "Load the new version".
// Uses $, esc, ago and load from app.js.

const FIELDS = ["title", "status", "priority", "next", "blocked_by", "jira", "folder"];
let card = null;    // what Flask sent (project, text, stamp, history) + id + sel (which view is shown)

function toast(message) {
  const t = $("toast");
  t.textContent = message;
  t.hidden = false;
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => t.hidden = true, 3000);
}

async function fetchCard(id) {
  const response = await fetch(`/api/projects/${encodeURIComponent(id)}`);
  if (!response.ok) throw new Error(response.status === 404 ? "this project is gone (moved or archived?)" : `server said ${response.status}`);
  return response.json();
}

async function openCard(id) {
  try {
    card = {...await fetchCard(id), id, sel: "overview"};
  } catch (err) {
    toast(`Could not open ${id}: ${err.message}`);
    load();
    return;
  }
  drawCard();
  $("ov").hidden = false;
  document.body.style.overflow = "hidden";
  $("m-close").focus();
}

function closeCard() {
  $("ov").hidden = true;
  document.body.style.overflow = "";
  card = null;
  load();       // the dashboard re-reads the notes, so it shows what you just saved
}

function drawCard() {
  drawHead();
  drawTree();
  drawView();
  $("m-claude").innerHTML = `<div class="c-head"><span class="spark">✳</span><div><b>Ask Claude</b><small>about this project</small></div></div>
    <div class="empty c-soon"><b>Coming soon.</b>Built after the gateway test at the office.</div>`;
}

function drawHead() {
  const p = card.project;
  $("m-head").innerHTML = `<div class="t"><div class="path">projects\\${esc(card.id)}\\</div>
      <h2 id="m-title">${esc(p.title)}</h2>
      <div class="pills"><span class="pill st-${esc(p.status)}">${esc(p.status)}</span><span class="pill pr-${esc(p.priority)}">${esc(p.priority)}</span>${p.jira ? `<span class="pill pr-normal">${esc(p.jira)}</span>` : ""}<span class="pill pr-normal">updated ${ago(p.days_ago)}</span></div></div>
    <button class="btn" id="m-back">← Dashboard</button><button class="x" id="m-close" aria-label="Close project">×</button>`;
}

function drawTree() {
  const item = (key, label, ext, cls = "") =>
    `<button class="item ${cls}" data-sel="${key}" aria-current="${card.sel === key}"><span class="nm">${label}</span>${ext ? `<span class="ext">${ext}</span>` : ""}</button>`;
  const later = dir => `<div class="folder"><span>${dir}\\</span><span>soon</span></div>`;
  $("m-tree").innerHTML = item("overview", "Overview & fields", "", "ov") + item("note", "note.md", "md") + later("sessions") + later("raw");
}

function drawView() {
  if (card.sel === "note") {
    $("m-view").innerHTML = `<div class="v-head"><h3>note.md</h3><span class="meta">the fields between the --- lines feed the dashboard</span></div>
      <textarea class="editor" id="v-text" spellcheck="false">${esc(card.text)}</textarea>
      <div id="v-alert"></div>
      <div class="foot"><button class="btn primary" id="v-savenote">Save note.md</button><button class="btn" id="v-undo">Undo changes</button></div>`;
    return;
  }
  const p = card.project;
  const input = (key, label, cls = "", hint = "") =>
    `<label class="${cls}">${label}<input id="f-${key}" value="${esc(p[key])}">${hint}</label>`;
  // A value the note has but the list doesn't (e.g. "Active") stays shown, so saving never changes it silently.
  const select = (key, label, options, hint = "") => {
    const all = options.includes(p[key]) ? options : [p[key], ...options];
    return `<label>${label}<select id="f-${key}">${all.map(o => `<option ${p[key] === o ? "selected" : ""}>${esc(o)}</option>`).join("")}</select>${hint}</label>`;
  };
  $("m-view").innerHTML = `<div class="v-head"><h3>Overview & fields</h3><span class="meta">stored at the top of note.md</span></div>
    <div class="grid">
      ${input("title", "Project name", "wide")}
      ${select("status", "Status", ["active", "pending", "idea"])}
      ${select("priority", "Priority", ["critical", "high", "normal"], '<span class="hint">Only you set this. Claude never changes it.</span>')}
      ${input("next", "Next step", "wide")}
      ${input("blocked_by", "Blocked by")}
      ${input("jira", "Jira")}
      ${input("folder", "Code folder", "wide", '<span class="hint">Info only, e.g. work_jira\\DEMO-1111</span>')}
    </div>
    <div class="row"><button class="btn sm" disabled title="Coming soon">Open notes folder</button><button class="btn sm" disabled title="Coming soon">Open in Jira</button></div>
    <div class="box"><h4>Add a line to the history</h4>
      <textarea id="f-line" rows="2" placeholder="e.g. Senior said: Northeast markets only"></textarea>
      <div class="row" style="margin-top:8px"><button class="btn sm" id="v-addline">Add line</button></div>
      <div id="v-log"></div></div>
    <div id="v-alert"></div>
    <div class="foot"><button class="btn primary" id="v-save">Save changes</button><span class="sp"></span><button class="btn danger" disabled title="Coming soon">Mark done & archive</button></div>`;
  drawLog();
}

function drawLog() {
  $("v-log").innerHTML = card.history.length
    ? `<ul class="log">${card.history.map(h => `<li><span class="who ${h.who.startsWith("Claude") ? "c" : ""}">${esc(h.who || "note")}</span><span>${esc(h.text)}<span class="d">${esc(h.date)}</span></span></li>`).join("")}</ul>`
    : `<p class="none" style="margin-top:10px">No history yet.</p>`;
}

// Warnings sit just above the Save buttons and scroll into view, so they are never off-screen.
function showAlert(html) {
  $("v-alert").innerHTML = html;
  if (html) $("v-alert").scrollIntoView({block: "nearest", behavior: "smooth"});
}

// Send one save to Flask. On 409 show the conflict choice; "Save mine anyway" resends with force.
async function save(path, body, done, force = false) {
  showAlert("");
  try {
    await send(path, body, done, force);
  } catch (err) {
    showAlert(`<span class="err">Could not save: ${esc(err.message)}. Is the app still running in the terminal?</span>`);
  }
}

async function send(path, body, done, force) {
  const response = await fetch(`/api/projects/${encodeURIComponent(card.id)}/${path}`, {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({...body, stamp: card.stamp, force}),
  });
  const data = await response.json().catch(() => ({error: `server said ${response.status}`}));
  if (response.status === 409) {
    card.retry = () => save(path, body, done, true);
    showAlert(`<div class="alert warn"><b>This note changed since you opened it.</b> Someone (maybe Claude Code) saved note.md after you opened this card.
      <div class="row"><button class="btn sm" id="v-reload">Load the new version</button><button class="btn sm" id="v-force">Save mine anyway</button></div>
      <span class="hint">"Save mine anyway" first copies their version to <span class="mono">archive\\</span>, so nothing is lost.</span></div>`);
    return;
  }
  if (!response.ok) {
    showAlert(`<span class="err">${esc(data.error)}</span>`);
    return;
  }
  const fresh = await fetchCard(card.id);
  Object.assign(card, fresh, {stamp: data.stamp});
  done();
}

const saveFields = () => save("fields", {fields: Object.fromEntries(FIELDS.map(k => [k, $("f-" + k).value]))},
  () => { drawHead(); drawView(); toast("Saved"); });
const saveNote = () => save("note", {text: $("v-text").value},
  () => { drawHead(); drawView(); toast("Saved note.md"); });
// Adding a line redraws only the history list, so unsaved field edits stay in the form.
const addLine = () => {
  const text = $("f-line").value.trim();
  if (!text) return;
  save("history", {text}, () => { $("f-line").value = ""; drawHead(); drawLog(); toast("Line added"); });
};

async function reloadCard() {
  Object.assign(card, await fetchCard(card.id));
  drawCard();
  toast("Loaded the new version");
}

const ACTIONS = {
  "m-back": closeCard, "m-close": closeCard,
  "v-save": saveFields, "v-savenote": saveNote, "v-addline": addLine,
  "v-undo": () => { $("v-text").value = card.text; },
  "v-reload": reloadCard, "v-force": () => card.retry(),
};

$("ov").addEventListener("click", e => {
  if (e.target === $("ov")) return closeCard();        // click outside the card
  const pick = e.target.closest("[data-sel]");
  if (pick) {
    card.sel = pick.dataset.sel;
    drawTree();
    drawView();
    return;
  }
  const button = e.target.closest("button[id]");
  if (button && ACTIONS[button.id]) ACTIONS[button.id]();
});

document.addEventListener("keydown", e => {
  if (e.key === "Escape" && card) closeCard();
});
