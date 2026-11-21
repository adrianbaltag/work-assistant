// Ideas page: quick notes kept in ideas.md in the projects folder, newest first.
// Flask (ideas.py) reads and writes the file; this file only draws the list and sends your clicks.
// Every answer from Flask is the whole list again, so after each change we simply redraw from it.
// Each change sends the idea's row number + name from the last answer. If the file changed in the
// meantime (e.g. in another browser tab), Flask answers 409: we show its message and reload the list.
// There is no edit on purpose: to change an idea, delete it and add it again (the (i) button says so).
// Uses $, esc, longDate, REACH_ERROR from app.js, fitBox from todo.js, openNewProject from newproject.js.

let ideaList = {ideas: [], count: 0};   // the last answer from Flask
let ideaConfirm = null;    // the idea whose row asks "Delete this idea for good?": {row, name}, or null
let ideaBusy = false;      // true while a change is on its way to Flask (ignores double clicks)
let ideaAsked = 0;         // counts requests; an answer to an older one than the last drawn is ignored
let ideaDrawn = 0;

const ICON_BULB = '<svg class="ico" viewBox="0 0 16 16" aria-hidden="true"><path d="M5.8 11.5h4.4M6.4 14h3.2M8 1.8a4.4 4.4 0 0 0-2.6 8c.4.3.6.8.6 1.2v.5h4V11c0-.4.2-.9.6-1.2A4.4 4.4 0 0 0 8 1.8z"/></svg>';

// Ask Flask: GET with no body, POST (JSON) with one. Same rules as todoFetch in todo.js:
// returns the answer, or null when a newer answer is already on screen; throws a plain-English Error
// (with .status = the HTTP status when Flask answered with an error).
async function ideaFetch(path, body) {
  const options = body === undefined ? {}
    : {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(body)};
  const number = ++ideaAsked;
  let response;
  try {
    response = await fetch(path, options);
  } catch (err) {
    throw new Error(REACH_ERROR);            // no answer at all: the app is not running
  }
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    const error = new Error(data.error || `The app answered with error ${response.status}. Check the terminal where it runs.`);
    error.status = response.status;
    throw error;
  }
  if (number < ideaDrawn) return null;
  ideaDrawn = number;
  return data;
}

// Read the list (page opened, after Start as project, or after a 409). keepAlert = leave the red message.
async function loadIdeas(keepAlert = false) {
  if ($("idea-new").offsetParent) fitBox($("idea-new"));   // only while shown: a hidden box has no height
  if (!keepAlert) $("idea-alert").innerHTML = "";
  try {
    const fresh = await ideaFetch("/api/ideas");
    if (!fresh) return;
    ideaList = fresh;
    drawIdeas();
  } catch (err) {
    $("idea-list").innerHTML = `<div class="empty bad"><b>Could not read your ideas.</b>${esc(err.message)}</div>`;
  }
}

// Send one change, then redraw from Flask's answer. Returns true when it worked.
async function ideaSend(path, body) {
  if (ideaBusy) return false;
  ideaBusy = true;
  $("idea-alert").innerHTML = "";
  try {
    const fresh = await ideaFetch(path, body);
    if (fresh) {
      ideaList = fresh;
      drawIdeas();
    }
    return true;
  } catch (err) {
    $("idea-alert").innerHTML = `<div class="alert bad"><b>Could not change your ideas.</b> ${esc(err.message)}</div>`;
    if (err.status === 409) await loadIdeas(true);   // the file changed elsewhere: show the fresh list
    return false;
  } finally {
    ideaBusy = false;
  }
}

function drawIdeas() {
  $("ideas-date").textContent = longDate(new Date());
  const n = ideaList.count;
  $("ideas-summary").textContent = `${n} idea${n === 1 ? "" : "s"}`;
  const all = ideaList.ideas;
  if (!all.length) {
    ideaConfirm = null;
    $("idea-list").innerHTML = `<div class="tempty"><span class="circle">${ICON_BULB}</span>
      <b>No ideas yet.</b><p>Type one above when it comes to you.</p></div>`;
    return;
  }
  // The row asking "for good?" may have moved or gone (changed in another tab): then stop asking.
  if (ideaConfirm && !all.some(i => i.row === ideaConfirm.row && i.name === ideaConfirm.name)) ideaConfirm = null;

  // One row: name + date on top, details below, then [Start as project] [×].
  // i = the idea's place in Flask's list (rows carry it as data-i).
  const row = (idea, i) => {
    const asking = ideaConfirm && ideaConfirm.row === idea.row && ideaConfirm.name === idea.name;
    const text = `<div class="itext"><div class="ihead"><b class="iname">${esc(idea.name)}</b>`
      + (idea.date ? `<span class="idate">${esc(idea.date)}</span>` : "") + `</div>`
      + (idea.details ? `<p class="idetails">${esc(idea.details)}</p>` : "") + `</div>`;
    if (asking) {
      return `<li class="irow asking" data-i="${i}">${text}
        <div class="tconfirm"><span class="q">Delete this idea for good?</span>
          <button class="btn danger solid" type="button" data-act="delete-yes">Yes, delete</button>
          <button class="btn" type="button" data-act="delete-no">Cancel</button></div></li>`;
    }
    return `<li class="irow" data-i="${i}">${text}
      <button class="btn istart" type="button" data-act="start" title="Opens New project with this idea filled in">Start as project</button>
      <button class="ticon tdel" type="button" aria-label="Delete idea: ${esc(idea.name)}" title="Delete" data-act="delete">×</button>
    </li>`;
  };
  $("idea-list").innerHTML = `<div class="tcard"><ul class="tlist" aria-label="Ideas, newest first">`
    + all.map(row).join("") + `</ul></div>`;
}

// After a redraw, put the focus on this idea's button (act), or on the box when it is gone.
function focusIdea(row, name, act) {
  const i = ideaList.ideas.findIndex(x => x.row === row && x.name === name);
  const button = i < 0 ? null : $("idea-list").querySelector(`[data-i="${i}"] [data-act="${act}"]`);
  (button || $("idea-new")).focus();
}

// Add: Enter or the Add button. Empty (or only spaces) = do nothing.
$("idea-add").addEventListener("submit", async e => {
  e.preventDefault();                       // stay on this page (a form would reload it)
  const input = $("idea-new");
  const text = input.value.trim();
  if (!text) return;
  if (await ideaSend("/api/ideas", {text})) {
    input.value = "";
    fitBox(input);                          // back to one row
  }
  input.focus();
});

// The box grows as you type. Enter = save; Shift+Enter = a new line (the browser's own, so we let it be).
$("idea-new").addEventListener("input", e => fitBox(e.target));
$("idea-new").addEventListener("keydown", e => {
  if (e.key === "Enter" && !e.shiftKey && !e.isComposing) {
    e.preventDefault();
    $("idea-add").requestSubmit();          // same as clicking Add
  }
});
window.addEventListener("resize", () => { if ($("idea-new").offsetParent) fitBox($("idea-new")); });

// (i): show or hide "To change an idea, delete it and add it again."
$("idea-info").addEventListener("click", () => {
  const open = $("idea-help").hidden;
  $("idea-help").hidden = !open;
  $("idea-info").setAttribute("aria-expanded", String(open));
});

// The buttons in the list: data-act says which job, data-i on the row says which idea.
$("idea-list").addEventListener("click", async e => {
  const button = e.target.closest("button[data-act]");
  if (!button) return;
  const act = button.dataset.act;
  const idea = ideaList.ideas[button.closest("[data-i]").dataset.i];
  if (act === "start") {
    openNewProject({title: idea.name, description: idea.details, idea: {row: idea.row, name: idea.name}});
  } else if (act === "delete") {            // first click: ask first
    ideaConfirm = {row: idea.row, name: idea.name};
    drawIdeas();
    $("idea-list").querySelector('[data-act="delete-no"]').focus();
  } else if (act === "delete-no") {
    ideaConfirm = null;
    drawIdeas();
    focusIdea(idea.row, idea.name, "delete");
  } else if (act === "delete-yes") {
    ideaConfirm = null;
    if (!await ideaSend("/api/ideas/delete", {row: idea.row, name: idea.name})) drawIdeas();
    $("idea-new").focus();
  }
});

// Esc in the "for good?" row = Cancel.
$("idea-list").addEventListener("keydown", e => {
  if (e.key === "Escape" && e.target.closest(".tconfirm")) {
    const idea = ideaList.ideas[e.target.closest("[data-i]").dataset.i];
    ideaConfirm = null;
    drawIdeas();
    focusIdea(idea.row, idea.name, "delete");
  }
});
