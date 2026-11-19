// Project card: pops in over the dashboard. Reads one project from Flask and edits its note.md
// and the files in its sessions\ and raw\ folders.
// Every save sends back the "stamp" the card got when it opened that file. If the file changed since
// (e.g. Claude Code saved it), Flask answers 409 and we offer "Save mine anyway" / "Load the new version".
// The Note / Blocker / Unblock box at the top is different: it sends no stamp, because Flask only adds
// its own line to note.md (see sendMessage).
// Uses $, esc, ago and load from app.js, and changedFields, shortText and oneLineAt from paging.js.

const FIELDS = ["title", "status", "priority", "working_on", "next", "blocked_by", "jira", "folder"];
const GROWS = ["working_on", "next", "blocked_by"];      // these boxes grow with their text: a long value wraps, nothing is cut
const UPLOAD_LIMIT_MB = 50;     // same as app.py
let card = null;    // what Flask sent (project, text, stamp, history, files, messages) + id + sel (which view is shown)
                    // + file (the open sessions\ or raw\ file) + renaming / confirmDel / newOpen (small UI states)
                    // + drawn (what each field box showed when it was drawn; Save sends only the changed ones)

const kb = b => b >= 1024 ? Math.round(b / 1024) + " KB" : b + " B";
const extOf = name => name.includes(".") ? name.split(".").pop().toLowerCase() : "";
const pad = n => String(n).padStart(2, "0");
const today = (d = new Date()) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
const api = path => `/api/projects/${encodeURIComponent(card.id)}/${path}`;
const fileApi = (dir, name) => `files/${dir}/${encodeURIComponent(name)}`;

// A short message at the bottom of the page. seconds = how long it stays (default 3).
function toast(message, seconds = 3) {
  const t = $("toast");
  t.textContent = message;
  t.hidden = false;
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => t.hidden = true, seconds * 1000);
}

async function fetchCard(id) {
  const response = await fetch(`/api/projects/${encodeURIComponent(id)}`);
  if (!response.ok) throw new Error(response.status === 404 ? "this project is gone (moved or archived?)" : `server said ${response.status}`);
  return response.json();
}

async function fetchFile(dir, name) {
  const response = await fetch(api(fileApi(dir, name)));
  if (!response.ok) throw new Error(response.status === 404 ? "the file is gone (renamed or moved?)" : `server said ${response.status}`);
  return {...await response.json(), dir, name};
}

// toBox = true (the "+" on a dashboard row): the cursor starts in the Note / Blocker box.
async function openCard(id, toBox = false) {
  // inert = the page behind the card can't be clicked or reached with Tab, already while the card
  // loads (Enter on a row there would open another card and skip the "unsaved changes" question).
  document.querySelector(".app").inert = true;
  try {
    card = {...await fetchCard(id), id, sel: "overview"};
  } catch (err) {
    document.querySelector(".app").inert = false;
    toast(`Could not open ${id}: ${err.message}`);
    load();
    return;
  }
  drawCard();
  startChat();        // once per opening: saves and reloads redraw the card but keep the chat
  $("ov").hidden = false;
  fitFields();        // only now: a hidden box has no height to measure
  $("m-view").scrollTop = 0;      // start at the top (the Note / Blocker box), not where the last card was left
  document.body.style.overflow = "hidden";
  (toBox ? $("msg-text") : $("m-close")).focus();
}

function closeCard() {
  if (okToLeave()) hideCard();
}

function hideCard() {
  const id = card && card.id;    // card = null: already closed (Esc while an archive was saving)
  $("ov").hidden = true;
  document.body.style.overflow = "";
  document.querySelector(".app").inert = false;
  card = null;
  $("m-claude").chat = null;      // forget the chat; a late answer is dropped
  load(false, id);    // the dashboard re-reads the notes (shows what you just saved); focus back on that row
}

// ---------- unsaved changes ----------

// Everything typed in the middle column, as one string. drawView keeps a copy; a difference = unsaved edits.
const typed = () => [...$("m-view").querySelectorAll("input:not(#v-rename), select, textarea")].map(el => el.value).join("\u0000");

function okToLeave() {
  if (!card) return true;
  const renamed = $("v-rename") && $("v-rename").value.trim() !== card.file.name;
  return (typed() === card.clean && !renamed) || confirm("You have unsaved changes. Discard them?");
}

// ---------- drawing ----------

function drawCard() {
  drawHead();
  drawTree();
  drawView();
}

function startChat() {
  const n = card.files.sessions.length, r = card.files.raw.length;
  const plural = (count, word) => `${count} ${word} file${count === 1 ? "" : "s"}`;
  const reads = ["its note", plural(n, "session"), plural(r, "raw")];
  if (card.project.folder) {      // a work project: Claude also reads these from its work_jira folder
    reads.push("the ticket, requirements and tracking log in its work folder");
  }
  const said = reads.slice(0, -1).join(", ") + " and " + reads[reads.length - 1];
  makeChat($("m-claude"), {
    sub: "about this project only",
    intro: `I can read ${card.project.title}: ${said}. What do you need?`,
    chips: ["Update this project from the raw files",
            {label: "My next steps", ask: "Write a short paragraph about this project covering: the issue, where I "
              + "stand, the next step(s), and the fix (planned or done). Say so if the notes don't cover one of these."},
            "Summarize this project"],
    placeholder: "Ask about this project…",
    url: api("ask"),
    current: field => card.project[field] ?? "",
    approve: approveClaude,
  });
}

// Approve in the chat: save Claude's proposal, then redraw the card from the saved note.
// Unsaved typing in the card would be lost by the redraw, so ask first (decided).
async function approveClaude(proposal, stamp) {
  if (!okToLeave()) return false;
  let saved;
  try {
    const {response, data} = await post("apply", {proposal, stamp});
    if (!response.ok) return data.error;
    saved = data;
    Object.assign(card, await fetchCard(card.id));
    if (card.file) card.file = await fetchFile(card.file.dir, card.file.name);
  } catch (err) {
    return `Could not reach the app: ${err.message}. Is it still running in the terminal?`;
  }
  drawCard();
  toast(saved.session ? `Saved. New session note: ${saved.session}` : "Saved Claude's changes");
  return true;
}

function drawHead() {
  const p = card.project;
  $("m-head").innerHTML = `<div class="t"><div class="path">projects\\${esc(card.id)}\\</div>
      <h2 id="m-title">${esc(p.title)}</h2>
      <div class="pills"><span class="pill st-${esc(p.shown_status)}" id="m-status">${esc(p.shown_status)}</span><span class="pill pr-${esc(p.priority)}">${esc(p.priority)}</span>${p.jira ? `<span class="pill pr-normal">${esc(p.jira)}</span>` : ""}<span class="pill pr-normal">updated ${ago(p.days_ago)}</span></div></div>
    <button class="btn" id="m-back">← Dashboard</button><button class="x" id="m-close" aria-label="Close project">×</button>`;
}

function drawTree() {
  const item = (key, label, ext, cls = "") =>
    `<button class="item ${cls}" data-sel="${esc(key)}" aria-current="${card.sel === key}"><span class="nm">${esc(label)}</span>${ext ? `<span class="ext">${esc(ext)}</span>` : ""}</button>`;
  const group = dir => `<div class="folder"><span>${dir}\\</span><span>${card.files[dir].length}</span></div>`
    + (card.files[dir].map(f => item(`file:${dir}/${f.name}`, f.name, extOf(f.name))).join("")
       || `<div class="folder" style="padding-top:2px">empty</div>`);
  const newForm = `<div class="newfile">
      <label>Folder<select id="nf-dir"><option>sessions</option><option>raw</option></select></label>
      <label>File name<input id="nf-name" value="${today()}.md"></label><span class="err" id="nf-err" hidden></span>
      <div class="row"><button class="btn primary sm" id="nf-ok">Create</button><button class="btn sm" id="nf-cancel">Cancel</button></div></div>`;
  $("m-tree").innerHTML = `<div class="tree-actions"><button class="btn sm" id="t-new">+ New file</button><label class="btn sm" for="t-upload">Upload</label><input type="file" id="t-upload" multiple hidden></div>
    ${card.newOpen ? newForm : ""}
    ${item("overview", "Overview & fields", "", "ov")}${item("note", "note.md", "md")}${group("sessions")}${group("raw")}
    <div class="drop" id="drop">Drop files here or paste a screenshot (Ctrl+V). They go to <span class="mono">raw\\</span>.</div>`;
}

function drawView() {
  if (card.sel === "note") drawNote();
  else if (card.sel.startsWith("file:")) drawFile();
  else drawOverview();
  card.clean = typed();
}

// Draw the middle column again, but keep what is typed in the Note / Blocker box: pressing Save
// must not throw an unsent message away. It is put back after drawView, so the card still counts
// it as "unsaved" and asks before you close.
function drawViewKeepMessage() {
  const unsent = $("msg-text") ? $("msg-text").value : "";
  drawView();
  if (unsent && $("msg-text")) {
    $("msg-text").value = unsent;
    fitBox($("msg-text"));
  }
}

// The newline after <textarea> is on purpose: the browser drops one there, so a file's own first newline survives.
// .savebar = the warnings and the Save buttons; it sticks to the bottom of the column (app.css), always in view.
function drawNote() {
  $("m-view").innerHTML = `<div class="v-head"><h3>note.md</h3><span class="meta">the fields between the --- lines feed the dashboard</span></div>
    <textarea class="editor" id="v-text" spellcheck="false">\n${esc(card.text)}</textarea>
    <div class="savebar"><div id="v-alert"></div>
    <div class="foot"><button class="btn primary" id="v-savenote">Save note.md</button><button class="btn" id="v-undo">Undo changes</button></div></div>`;
}

function drawOverview() {
  const p = card.project;
  const input = (key, label, cls = "", hint = "") =>
    `<label class="${cls}">${label}<input id="f-${key}" value="${esc(p[key])}">${hint}</label>`;
  // Like input, but a box that grows: a long value wraps onto more lines instead of being cut (see fitFields).
  const grow = (key, label, cls = "") =>
    `<label class="${cls}">${label}<textarea class="grow" id="f-${key}" rows="1">${esc(p[key])}</textarea></label>`;
  // A value the note has but the list doesn't (e.g. "Active") stays shown, so saving never changes it silently.
  const select = (key, label, options, hint = "") => {
    const all = options.includes(p[key]) ? options : [p[key], ...options];
    return `<label>${label}<select id="f-${key}">${all.map(o => `<option ${p[key] === o ? "selected" : ""}>${esc(o)}</option>`).join("")}</select>${hint}</label>`;
  };
  // One line of plain text for a linked card: label, then the value (or a grey dash).
  const fact = (key, label, value = esc(p[key])) =>
    `<span class="k">${label}</span><span class="v" id="s-${key}">${value || '<span class="none">—</span>'}</span>`;
  // p.linked = this card follows a Claude work folder. Claude's files then fill in these four values,
  // so they are plain text here and Save never sends them. A card with no Claude folder keeps its boxes.
  const synced = !p.linked ? "" : `<div class="box facts" id="v-synced"><h4>Filled in by Claude's files</h4>
      ${fact("status", "Status", `<span class="pill st-${esc(p.status)}">${esc(p.status)}</span>`)}
      ${fact("working_on", "Working on")}
      ${fact("next", "Next step")}
      ${fact("blocked_by", "Blocked by")}</div>`;
  const yours = p.linked ? "" : `
      ${grow("working_on", "Working on", "wide")}
      ${grow("next", "Next step", "wide")}
      ${grow("blocked_by", "Blocked by")}`;
  $("m-view").innerHTML = `<div class="v-head"><h3>Overview & fields</h3><span class="meta">stored at the top of note.md</span></div>
    ${messageBox()}
    ${synced}
    <div class="grid">
      ${input("title", "Project name", "wide")}
      ${p.linked ? "" : select("status", "Status", ["active", "pending", "idea"])}
      ${select("priority", "Priority", ["critical", "high", "normal"], '<span class="hint">Only you set this. Claude never changes it.</span>')}${yours}
      ${input("jira", "Jira")}
      ${input("folder", "Code folder", "wide", '<span class="hint">Info only, e.g. work_jira\\DEMO-1111</span>')}
    </div>
    <div class="row"><button class="btn sm" id="v-openfolder">Open notes folder</button><button class="btn sm" id="v-jira">Open in Jira</button></div>
    <div class="box"><h4>History</h4><div id="v-log"></div></div>
    <div class="savebar"><div id="v-alert"></div>
    <div class="foot"><button class="btn primary" id="v-save">Save changes</button><span class="sp"></span><button class="btn danger" id="v-arch">Mark done & archive</button></div></div>`;
  card.drawn = boxValues();
  drawMessageState();
  drawLog();
  drawJiraButton();
  fitFields();
}

// What each field box holds right now, e.g. {title: "Demo", jira: ""}. Only the boxes that are on
// the card: a linked card has none for the four values Claude's files fill in.
const boxValues = () => Object.fromEntries(FIELDS.filter(k => $("f-" + k)).map(k => [k, $("f-" + k).value]));

// ---------- the Note / Blocker / Unblock box ----------

// The box at the top of every card: one text box and three buttons.
// Note = one History line by you. Blocker = that, and the project is blocked by you until Unblock.
// Unblock needs no words; its button shows only while your blocker is on (drawMessageState).
function messageBox() {
  const where = card.project.linked ? "Goes into the History, and Claude gets it in its next session."
    : "Goes into the History.";
  return `<div class="box" id="msg"><h4>Note or blocker</h4>
      <textarea class="grow" id="msg-text" rows="1" aria-label="Note or blocker" placeholder="e.g. Dana said: Northeast markets only"></textarea>
      <div class="row msg-btns"><button class="btn sm primary" id="msg-note">Note</button><button class="btn sm" id="msg-blocker">Blocker</button><button class="btn sm" id="msg-unblock" hidden>Unblock</button><span class="hint">${where}</span></div>
      <div id="msg-alert" role="alert"></div>
      <div id="msg-state"></div></div>`;
}

const MESSAGE_KINDS = {note: "Note", blocker: "Blocker", unblock: "Unblock"};

// Under the buttons: who blocks the project now ("you" = your Blocker, "log" = Claude's tracking log),
// and on a linked card the last messages with "waiting for Claude" or "seen by Claude <date>".
function drawMessageState() {
  const p = card.project;
  $("msg-unblock").hidden = !p.blockers.some(b => b.by === "you");
  const blocked = p.blockers.map(b =>
    `<div class="blocked">Blocked by <span class="by">${esc(b.by)}</span>${esc(b.text || "pending")}</div>`).join("");
  const sent = (card.messages || []).map(m => `<li><span class="k">${MESSAGE_KINDS[m.kind]}</span>`
    + `<span class="clip" title="${esc(m.text)}">${esc(m.text) || "—"}</span><span class="st">${esc(m.status)}</span></li>`).join("");
  $("msg-state").innerHTML = (blocked ? `<div id="msg-blocked">${blocked}</div>` : "")
    + (sent ? `<ul class="sent" id="msg-sent" aria-label="Sent to Claude">${sent}</ul>` : "");
}

// An error from the box, shown right under its buttons. If you moved to another view meanwhile
// (note.md, a file), the box is not on screen: then it is shown as a toast.
function messageError(text) {
  if ($("msg-alert")) $("msg-alert").innerHTML = text ? `<span class="err">${esc(text)}</span>` : "";
  else if (text) toast(text, 8);
}

// Send what is in the box. No stamp is needed: Flask adds only its own things to note.md (one History
// line, and your blocker), so it never answers "this note changed since you opened it".
// A sent message can't be edited. Only the parts that show it are drawn again (title pills, this box,
// the History), so anything you typed in the field boxes stays.
function sendMessage(kind) {
  const box = $("msg-text"), text = box.value.trim();
  messageError("");
  if (!text && kind !== "unblock") {
    messageError("Type a few words first.");
    return box.focus();
  }
  if (card.sending) return;      // a second click while the first is on its way
  card.sending = true;
  const id = card.id;
  act("message", {kind, text}, async data => {
    if (!card || card.id !== id) return;      // the card was closed meanwhile
    if ($("msg-text")) {                      // the box as it is now (a Save may have drawn it again)
      $("msg-text").value = "";
      fitBox($("msg-text"));
      $("msg-text").focus();                  // ready for the next one (and Unblock, now hidden, can't keep the focus)
    }
    toast(kind === "note" ? "Note added" : kind === "blocker" ? "Blocked by you" : "Unblocked");
    await afterMessage(data);
  }, messageError).finally(() => { if (card && card.id === id) card.sending = false; });
}

// After a message: read the card again and show what the message changed.
// The card's stamp (and its copy of note.md) moves on only when it is safe:
// - note.md was unchanged before the message (data.before). If someone else had saved it meanwhile,
//   the stamp stays old, so "Save changes" still warns about that.
// - you are still on this view. If you switched to note.md while the message was on its way, that
//   editor shows the text from before the message: with the old stamp, saving it gives the usual
//   "this note changed" warning and never wipes the new History line.
async function afterMessage(data) {
  let fresh;
  try {
    fresh = await fetchCard(card.id);
  } catch (err) {
    return messageError(`Sent, but the card could not be read again (${err.message}). Close it and open it again.`);
  }
  const onOverview = Boolean($("msg"));
  if (onOverview && card.stamp === data.before) Object.assign(card, {stamp: data.stamp, text: fresh.text});
  Object.assign(card, {project: fresh.project, history: fresh.history, messages: fresh.messages});
  drawHead();
  if (onOverview) {
    drawMessageState();
    drawLog();
  }
}

// Open in Jira uses what is in the Jira box right now (saved or not) + jira_url from settings.ini.
const jiraLink = () => {
  const key = $("f-jira").value.trim();
  return card.jira_url && key ? `${card.jira_url}/browse/${encodeURIComponent(key)}` : "";
};
function drawJiraButton() {
  const b = $("v-jira"), link = jiraLink();
  b.disabled = !link;
  b.title = !card.jira_url ? "Set jira_url=https://... in settings.ini first" : link || "Type the ticket in the Jira box first";
}
const openJira = () => window.open(jiraLink(), "_blank", "noopener");
const openFolder = () => act("open-folder", {}, async () => toast("Opened the notes folder."));

// Make each growing box (GROWS, and the Note / Blocker box) as tall as its text. fitBox is the To do
// page's helper (todo.js). A box that is not on screen (the card is closed, another view is shown,
// or a linked card that has no such box) is skipped.
function fitFields() {
  for (const id of [...GROWS.map(key => "f-" + key), "msg-text"]) {
    const box = $(id);
    if (box && box.offsetParent) fitBox(box);
  }
}

const HISTORY_CHARS = 200;      // a History line longer than this is cut, with a "Read more" button

// One History line. A long one shows its start (shortText, in paging.js) and a "Read more" button.
// data-more = the line's place in card.history, so the click below can find its full text again.
function logLine(h, i) {
  const short = shortText(h.text, HISTORY_CHARS);
  const more = short === null ? ""
    : ` <button class="linkbtn" type="button" data-more="${i}" aria-expanded="false">Read more</button>`;
  return `<li><span class="who ${h.who.startsWith("Claude") ? "c" : ""}">${esc(h.who || "note")}</span>`
    + `<span><span>${esc(short === null ? h.text : short)}</span>${more}<span class="d">${esc(h.date)}</span></span></li>`;
}

function drawLog() {
  $("v-log").innerHTML = card.history.length
    ? `<ul class="log">${card.history.map(logLine).join("")}</ul>`
    : `<p class="none" style="margin-top:10px">No history yet.</p>`;
}

// "Read more" on a long History line: show all of it, and turn the button into "Show less" (and back).
function toggleMore(button) {
  const text = card.history[Number(button.dataset.more)].text;
  const open = button.getAttribute("aria-expanded") !== "true";
  button.previousElementSibling.textContent = open ? text : shortText(text, HISTORY_CHARS);
  button.setAttribute("aria-expanded", String(open));
  button.textContent = open ? "Show less" : "Read more";
}

function drawFile() {
  const f = card.file;
  const body = f.kind === "text" ? `<textarea class="editor" id="v-text" spellcheck="false">\n${esc(f.text)}</textarea>`
    : f.kind === "image" ? `<div class="imgprev"><img src="${api(fileApi(f.dir, f.name))}/bytes?v=${encodeURIComponent(f.stamp)}" alt="${esc(f.name)}"></div>`
    : `<div class="empty"><b>Can't show this file here.</b>It is not plain text (for example Excel or PDF), or it is bigger than 1 MB. Rename and Delete still work.</div>`;
  $("m-view").innerHTML = `<div class="v-head" id="v-head"></div>${body}
    <div class="savebar"><div id="v-confirm"></div><div id="v-alert"></div><div class="foot" id="v-foot"></div></div>`;
  drawFileBar();
}

// Title, delete question and buttons only, so Rename and Delete never wipe what you typed in the file.
function drawFileBar() {
  const f = card.file;
  $("v-head").innerHTML = (card.renaming
      ? `<input id="v-rename" value="${esc(f.name)}" aria-label="New file name" style="flex:1;min-width:160px">`
      : `<h3>${esc(f.name)}</h3>`)
    + `<span class="meta">${f.dir}\\ · ${kb(f.size)}</span>`;
  $("v-confirm").innerHTML = card.confirmDel
    ? `<div class="alert bad"><b>Delete ${esc(f.name)}?</b> Nothing is deleted for good: the file moves to this project's <span class="mono">archive\\${f.dir}\\</span> folder.
       <div class="row"><button class="btn danger solid sm" id="v-del-yes">Yes, move to archive</button><button class="btn sm" id="v-del-no">Cancel</button></div></div>`
    : "";
  $("v-foot").innerHTML = (f.kind === "text" ? `<button class="btn primary" id="v-savefile">Save</button><button class="btn" id="v-undo">Undo changes</button>` : "")
    + (card.renaming ? `<button class="btn" id="v-rename-ok">Save name</button><button class="btn" id="v-rename-no">Cancel</button>` : `<button class="btn" id="v-renamebtn">Rename</button>`)
    + `<span class="sp"></span><button class="btn danger" id="v-del">Delete</button>`;
}

// Warnings sit just above the Save buttons and scroll into view, so they are never off-screen.
function showAlert(html) {
  $("v-alert").innerHTML = html;
  if (html) $("v-alert").scrollIntoView({block: "nearest", behavior: "smooth"});
}

// ---------- talking to Flask ----------

// POST to this project's API: JSON, or a FormData for uploads. Returns the response and its JSON.
async function post(path, body) {
  const options = body instanceof FormData ? {method: "POST", body}
    : {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(body)};
  const response = await fetch(api(path), options);
  const data = await response.json().catch(() => ({error: `server said ${response.status}`}));
  return {response, data};
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
  const {response, data} = await post(path, {...body, force});
  if (response.status === 409) {
    const name = card.file ? card.file.name : "note.md";
    card.retry = () => save(path, body, done, true);
    showAlert(`<div class="alert warn"><b>${card.file ? "This file" : "This note"} changed since you opened it.</b> Someone (maybe Claude Code) saved ${esc(name)} after you opened it here.
      <div class="row"><button class="btn sm" id="v-reload">Load the new version</button><button class="btn sm" id="v-force">Save mine anyway</button></div>
      <span class="hint">"Save mine anyway" first copies their version to <span class="mono">archive\\</span>, so nothing is lost.</span></div>`);
    return;
  }
  if (!response.ok) {
    showAlert(`<span class="err">${esc(data.error)}</span>`);
    return;
  }
  await done(data);
}

// New file, rename, delete, upload: no stamp needed. Errors go to `fail` (default: the alert above the buttons).
async function act(path, body, done, fail = message => showAlert(`<span class="err">${esc(message)}</span>`)) {
  try {
    const {response, data} = await post(path, body);
    if (!response.ok) return fail(data.error);
    await done(data);
  } catch (err) {
    fail(`Could not reach the app: ${err.message}. Is it still running in the terminal?`);
  }
}

// After a note.md save, re-read the whole card: fields, history and "updated" all come from note.md.
// The new stamp is kept first, so if the re-read fails the next save still isn't a false conflict.
async function reread(data) {
  card.stamp = data.stamp;
  Object.assign(card, await fetchCard(card.id), {stamp: data.stamp});
}

// After a file change: the new file list and "updated". note.md's text and stamp stay as they were.
async function refreshFiles() {
  const fresh = await fetchCard(card.id);
  card.files = fresh.files;
  card.project.days_ago = fresh.project.days_ago;
}

// ---------- note.md ----------

// Save changes: only the boxes you changed are sent (changedFields, in paging.js). A box you did not
// touch is never written, and a linked card has no boxes for the values Claude's files fill in.
// What is typed in the Note / Blocker box stays where it is (drawViewKeepMessage).
const saveFields = () => {
  const fields = changedFields(card.drawn, boxValues());
  if (!Object.keys(fields).length) return toast("Nothing to save: no field was changed");
  save("fields", {fields, stamp: card.stamp},
    async data => { await reread(data); drawHead(); drawViewKeepMessage(); toast("Saved"); });
};
const saveNote = () => save("note", {text: $("v-text").value, stamp: card.stamp},
  async data => { await reread(data); drawHead(); drawView(); toast("Saved note.md"); });

async function reloadCard() {
  try {
    Object.assign(card, await fetchCard(card.id));
    if (card.file) card.file = await fetchFile(card.file.dir, card.file.name);
  } catch (err) {
    return toast(`Could not load it: ${err.message}`);
  }
  drawHead();
  drawTree();
  drawViewKeepMessage();      // the new version of the note; an unsent Note / Blocker text stays
  toast("Loaded the new version");
}

// ---------- sessions\ and raw\ files ----------

async function showFile(dir, name) {
  card.file = await fetchFile(dir, name);
  card.sel = `file:${dir}/${name}`;
  card.renaming = card.confirmDel = false;
  drawTree();
  drawView();
  $("m-view").scrollTop = 0;      // another view: start at its top
}

async function pick(key) {
  if (key === card.sel || !okToLeave()) return;
  if (key.startsWith("file:")) {
    const cut = key.indexOf("/");
    try {
      await showFile(key.slice(5, cut), key.slice(cut + 1));
    } catch (err) {
      toast(`Could not open it: ${err.message}`);
      await refreshFiles();
      drawTree();
    }
    return;
  }
  Object.assign(card, {sel: key, file: null, renaming: false, confirmDel: false});
  drawTree();
  drawView();
  $("m-view").scrollTop = 0;
}

const saveFile = () => {
  const {dir, name} = card.file, text = $("v-text").value;
  save(fileApi(dir, name), {text, stamp: card.file.stamp}, async data => {
    Object.assign(card.file, {text, stamp: data.stamp});
    await refreshFiles();
    const listed = card.files[dir].find(f => f.name === name);
    if (listed) card.file.size = listed.size;
    drawHead();
    drawTree();
    drawView();
    toast(`Saved ${name}`);
  });
};

const toggleNew = open => {
  card.newOpen = open;
  drawTree();
  if (open) $("nf-name").focus();
};

const createFile = () => {
  const dir = $("nf-dir").value, name = $("nf-name").value.trim();
  if (!okToLeave()) return;
  const fail = message => { $("nf-err").textContent = message; $("nf-err").hidden = false; };
  act(`files/${dir}`, {name}, async data => {
    await refreshFiles();
    card.newOpen = false;
    await showFile(dir, data.name);
    toast(`Created ${dir}\\${data.name}`);
  }, fail);
};

const startRename = () => { card.renaming = true; drawFileBar(); $("v-rename").select(); };
const cancelRename = () => { card.renaming = false; drawFileBar(); };
const doRename = () => {
  const {dir, name} = card.file;
  act(`${fileApi(dir, name)}/rename`, {name: $("v-rename").value.trim()}, async data => {
    Object.assign(card, {sel: `file:${dir}/${data.name}`, renaming: false});
    card.file.name = data.name;
    await refreshFiles();
    drawHead();
    drawTree();
    drawFileBar();
    toast(`Renamed to ${data.name}`);
  });
};

const askDelete = () => { card.confirmDel = true; drawFileBar(); $("v-confirm").scrollIntoView({block: "nearest"}); };
const cancelDelete = () => { card.confirmDel = false; drawFileBar(); };
const doDelete = () => {
  const {dir, name} = card.file;
  act(`${fileApi(dir, name)}/delete`, {}, async () => {
    await refreshFiles();
    Object.assign(card, {sel: "overview", file: null, confirmDel: false});
    drawHead();
    drawTree();
    drawView();
    toast(`${name} moved to archive\\${dir}\\`);
  });
};

// Mark done & archive: Flask moves the whole folder to projects\_archive\ and sets status: done.
const askArchive = () => showAlert(`<div class="alert bad"><b>Mark done and archive this project?</b> The whole folder moves to
  <span class="mono">_archive\\</span>. Nothing is deleted: Restore on the Archive page brings it back.
  <div class="row"><button class="btn danger solid sm" id="v-arch-yes">Yes, archive</button><button class="btn sm" id="v-arch-no">Cancel</button></div></div>`);
const doArchive = () => {
  if (!okToLeave()) return;
  const title = card.project.title;
  act("archive", {}, async () => {
    hideCard();
    toast(`${title} archived. Restore it from the Archive page.`);
  });
};

// Upload button, drag-and-drop and pasted screenshots all end here. Flask saves them in raw\ and never overwrites.
function upload(files, names = files.map(f => f.name)) {
  if (files.reduce((sum, f) => sum + f.size, 0) > UPLOAD_LIMIT_MB * 1024 * 1024) {
    return showAlert(`<span class="err">Upload too big (${UPLOAD_LIMIT_MB} MB max at once).</span>`);
  }
  const form = new FormData();
  files.forEach((f, i) => form.append("files", f, names[i]));
  act("upload", form, async data => {
    await refreshFiles();
    drawHead();
    drawTree();
    toast(`Added to raw\\: ${data.names.join(", ")}`);
  });
}

const screenshotName = f => {
  const d = new Date();
  return `screenshot-${today(d)}-${pad(d.getHours())}${pad(d.getMinutes())}${pad(d.getSeconds())}.${f.type.split("/")[1] || "png"}`;
};

// ---------- events ----------

const ACTIONS = {
  "m-back": closeCard, "m-close": closeCard,
  "v-save": saveFields, "v-savenote": saveNote, "v-savefile": saveFile,
  "msg-note": () => sendMessage("note"), "msg-blocker": () => sendMessage("blocker"), "msg-unblock": () => sendMessage("unblock"),
  "v-undo": () => { $("v-text").value = card.file ? card.file.text : card.text; },
  "v-reload": reloadCard, "v-force": () => card.retry(),
  "t-new": () => toggleNew(true), "nf-cancel": () => toggleNew(false), "nf-ok": createFile,
  "v-renamebtn": startRename, "v-rename-ok": doRename, "v-rename-no": cancelRename,
  "v-del": askDelete, "v-del-yes": doDelete, "v-del-no": cancelDelete,
  "v-arch": askArchive, "v-arch-yes": doArchive, "v-arch-no": () => showAlert(""),
  "v-openfolder": openFolder, "v-jira": openJira,
};

$("ov").addEventListener("input", e => {
  if (e.target.id === "f-jira") drawJiraButton();
  if (e.target.classList.contains("grow")) {          // a growing box: one line of text, as tall as it needs
    if (e.target.value.includes("\n")) {              // a line break got in (e.g. text dragged into the box)
      const [text, at] = oneLineAt(e.target.value, e.target.selectionEnd);
      e.target.value = text;
      e.target.setSelectionRange(at, at);             // setting .value throws the cursor to the end: put it back
    }
    fitBox(e.target);
  }
});
// Pasting text with line breaks into a growing box: put it in as one line, the way typing would.
// insertText keeps the cursor right after the pasted text and lets Ctrl+Z undo the paste.
$("ov").addEventListener("paste", e => {
  const text = e.clipboardData ? e.clipboardData.getData("text") : "";
  if (!e.target.classList || !e.target.classList.contains("grow") || !text.includes("\n")) return;   // the usual paste is fine
  e.preventDefault();
  const clean = oneLineAt(text, 0)[0];
  if (!document.execCommand("insertText", false, clean)) {          // a browser without insertText: no undo, same text
    e.target.setRangeText(clean, e.target.selectionStart, e.target.selectionEnd, "end");
  }
  fitBox(e.target);
});
window.addEventListener("resize", () => { if (card) fitFields(); });      // a narrower window wraps the text sooner

$("ov").addEventListener("click", e => {
  if (e.target === $("ov")) return closeCard();        // click outside the card
  const item = e.target.closest("[data-sel]");
  if (item) return pick(item.dataset.sel);
  const more = e.target.closest("[data-more]");        // "Read more" / "Show less" on a History line
  if (more) return toggleMore(more);
  const button = e.target.closest("button[id]");
  if (button && ACTIONS[button.id]) ACTIONS[button.id]();
});

document.addEventListener("keydown", e => {
  if (!card) return;
  if (e.key === "Enter" && e.target.id === "v-rename") doRename();
  else if (e.key === "Enter" && e.target.id === "nf-name") createFile();
  else if (e.key === "Enter" && e.target.classList.contains("grow")) e.preventDefault();   // a field is one line: no line break
  else if (e.key !== "Escape") return;
  else if (card.renaming) cancelRename();          // Esc closes the small thing first, then the card
  else if (card.confirmDel) cancelDelete();
  else if (card.newOpen) toggleNew(false);
  else if ($("v-arch-yes")) showAlert("");
  else closeCard();
});

$("m-tree").addEventListener("change", e => {
  if (e.target.id === "t-upload" && e.target.files.length) {
    upload([...e.target.files]);
    e.target.value = "";
  }
});
$("m-tree").addEventListener("dragover", e => { e.preventDefault(); $("drop").classList.add("over"); });
$("m-tree").addEventListener("dragleave", e => { if (!$("m-tree").contains(e.relatedTarget)) $("drop").classList.remove("over"); });
$("m-tree").addEventListener("drop", e => {
  e.preventDefault();
  $("drop").classList.remove("over");
  if (e.dataTransfer.files.length) upload([...e.dataTransfer.files]);
});
// A file dropped anywhere else would make the browser open it and leave the app, losing typed edits.
const isFileDrag = e => e.dataTransfer && [...e.dataTransfer.types].includes("Files");
window.addEventListener("dragover", e => { if (isFileDrag(e)) e.preventDefault(); });
window.addEventListener("drop", e => { if (isFileDrag(e)) e.preventDefault(); });

document.addEventListener("paste", e => {
  if (!card) return;
  const images = [...(e.clipboardData?.files || [])].filter(f => f.type.startsWith("image/"));
  if (!images.length) return;      // plain text pastes into the box as usual
  e.preventDefault();
  upload(images, images.map(screenshotName));
});

// Closing or reloading the browser tab with unsaved edits: the browser asks "Leave site?".
window.addEventListener("beforeunload", e => {
  if (card && typed() !== card.clean) e.preventDefault();
});
