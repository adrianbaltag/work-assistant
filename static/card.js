// Project card: pops in over the dashboard. Reads one project from Flask and edits its note.md
// and the files in its sessions\ and raw\ folders.
// Every save sends back the "stamp" the card got when it opened that file. If the file changed since
// (e.g. Claude Code saved it), Flask answers 409 and we offer "Save mine anyway" / "Load the new version".
// Uses $, esc, ago and load from app.js.

const FIELDS = ["title", "status", "priority", "next", "blocked_by", "jira", "folder"];
const UPLOAD_LIMIT_MB = 50;     // same as app.py
let card = null;    // what Flask sent (project, text, stamp, history, files) + id + sel (which view is shown)
                    // + file (the open sessions\ or raw\ file) + renaming / confirmDel / newOpen (small UI states)

const kb = b => b >= 1024 ? Math.round(b / 1024) + " KB" : b + " B";
const extOf = name => name.includes(".") ? name.split(".").pop().toLowerCase() : "";
const pad = n => String(n).padStart(2, "0");
const today = (d = new Date()) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
const api = path => `/api/projects/${encodeURIComponent(card.id)}/${path}`;
const fileApi = (dir, name) => `files/${dir}/${encodeURIComponent(name)}`;

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

async function fetchFile(dir, name) {
  const response = await fetch(api(fileApi(dir, name)));
  if (!response.ok) throw new Error(response.status === 404 ? "the file is gone (renamed or moved?)" : `server said ${response.status}`);
  return {...await response.json(), dir, name};
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
  if (okToLeave()) hideCard();
}

function hideCard() {
  $("ov").hidden = true;
  document.body.style.overflow = "";
  card = null;
  load();       // the dashboard re-reads the notes, so it shows what you just saved
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

// The newline after <textarea> is on purpose: the browser drops one there, so a file's own first newline survives.
function drawNote() {
  $("m-view").innerHTML = `<div class="v-head"><h3>note.md</h3><span class="meta">the fields between the --- lines feed the dashboard</span></div>
    <textarea class="editor" id="v-text" spellcheck="false">\n${esc(card.text)}</textarea>
    <div id="v-alert"></div>
    <div class="foot"><button class="btn primary" id="v-savenote">Save note.md</button><button class="btn" id="v-undo">Undo changes</button></div>`;
}

function drawOverview() {
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
    <div class="row"><button class="btn sm" id="v-openfolder">Open notes folder</button><button class="btn sm" id="v-jira">Open in Jira</button></div>
    <div class="box"><h4>Add a line to the history</h4>
      <textarea id="f-line" rows="2" placeholder="e.g. Senior said: Northeast markets only"></textarea>
      <div class="row" style="margin-top:8px"><button class="btn sm" id="v-addline">Add line</button></div>
      <div id="v-log"></div></div>
    <div id="v-alert"></div>
    <div class="foot"><button class="btn primary" id="v-save">Save changes</button><span class="sp"></span><button class="btn danger" id="v-arch">Mark done & archive</button></div>`;
  drawLog();
  drawJiraButton();
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

function drawLog() {
  $("v-log").innerHTML = card.history.length
    ? `<ul class="log">${card.history.map(h => `<li><span class="who ${h.who.startsWith("Claude") ? "c" : ""}">${esc(h.who || "note")}</span><span>${esc(h.text)}<span class="d">${esc(h.date)}</span></span></li>`).join("")}</ul>`
    : `<p class="none" style="margin-top:10px">No history yet.</p>`;
}

function drawFile() {
  const f = card.file;
  const body = f.kind === "text" ? `<textarea class="editor" id="v-text" spellcheck="false">\n${esc(f.text)}</textarea>`
    : f.kind === "image" ? `<div class="imgprev"><img src="${api(fileApi(f.dir, f.name))}/bytes?v=${encodeURIComponent(f.stamp)}" alt="${esc(f.name)}"></div>`
    : `<div class="empty"><b>Can't show this file here.</b>It is not plain text (for example Excel or PDF), or it is bigger than 1 MB. Rename and Delete still work.</div>`;
  $("m-view").innerHTML = `<div class="v-head" id="v-head"></div>${body}<div id="v-confirm"></div><div id="v-alert"></div><div class="foot" id="v-foot"></div>`;
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

const saveFields = () => save("fields", {fields: Object.fromEntries(FIELDS.map(k => [k, $("f-" + k).value])), stamp: card.stamp},
  async data => { await reread(data); drawHead(); drawView(); toast("Saved"); });
const saveNote = () => save("note", {text: $("v-text").value, stamp: card.stamp},
  async data => { await reread(data); drawHead(); drawView(); toast("Saved note.md"); });
// Adding a line redraws only the history list, so unsaved field edits stay in the form.
const addLine = () => {
  const text = $("f-line").value.trim();
  if (!text) return;
  save("history", {text, stamp: card.stamp}, async data => { await reread(data); $("f-line").value = ""; drawHead(); drawLog(); toast("Line added"); });
};

async function reloadCard() {
  try {
    Object.assign(card, await fetchCard(card.id));
    if (card.file) card.file = await fetchFile(card.file.dir, card.file.name);
  } catch (err) {
    return toast(`Could not load it: ${err.message}`);
  }
  drawCard();
  toast("Loaded the new version");
}

// ---------- sessions\ and raw\ files ----------

async function showFile(dir, name) {
  card.file = await fetchFile(dir, name);
  card.sel = `file:${dir}/${name}`;
  card.renaming = card.confirmDel = false;
  drawTree();
  drawView();
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
  "v-save": saveFields, "v-savenote": saveNote, "v-addline": addLine, "v-savefile": saveFile,
  "v-undo": () => { $("v-text").value = card.file ? card.file.text : card.text; },
  "v-reload": reloadCard, "v-force": () => card.retry(),
  "t-new": () => toggleNew(true), "nf-cancel": () => toggleNew(false), "nf-ok": createFile,
  "v-renamebtn": startRename, "v-rename-ok": doRename, "v-rename-no": cancelRename,
  "v-del": askDelete, "v-del-yes": doDelete, "v-del-no": cancelDelete,
  "v-arch": askArchive, "v-arch-yes": doArchive, "v-arch-no": () => showAlert(""),
  "v-openfolder": openFolder, "v-jira": openJira,
};

$("ov").addEventListener("input", e => { if (e.target.id === "f-jira") drawJiraButton(); });

$("ov").addEventListener("click", e => {
  if (e.target === $("ov")) return closeCard();        // click outside the card
  const item = e.target.closest("[data-sel]");
  if (item) return pick(item.dataset.sel);
  const button = e.target.closest("button[id]");
  if (button && ACTIONS[button.id]) ACTIONS[button.id]();
});

document.addEventListener("keydown", e => {
  if (!card) return;
  if (e.key === "Enter" && e.target.id === "v-rename") doRename();
  else if (e.key === "Enter" && e.target.id === "nf-name") createFile();
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
