// To do page: a short list of todos, kept in todos.md in the projects folder.
// Flask (todos.py) reads and writes the file; this file only draws the list and sends your clicks.
// Every answer from Flask is the whole list again (open high first, then open normal, then done),
// so after each change we simply redraw from it.
// Each change sends the todo's row number + text from the last answer. If the file changed in the
// meantime (e.g. in another browser tab), Flask answers 409: we show its message and reload the list.
// Uses $, esc and longDate from app.js.

let todos = {todos: [], open: 0, open_high: 0, done: 0};   // the last answer from Flask
let todoEditing = null;    // while a row is being edited: {row, text, draft, error}
let todoConfirm = false;   // true = the Done card head asks "Delete N done todos for good?"
let todoBusy = false;      // true while a change is on its way to Flask (ignores double clicks)

const TODO_REACH_ERROR = "Could not reach the app. Is it still running in the terminal?";
const TODO_EMPTY_EDIT = "Type something, or use × to delete it.";

// Small line icons (see .ico in app.css). aria-hidden: the button's label already says what it does.
const ICON_FLAG = '<svg class="ico" viewBox="0 0 16 16" aria-hidden="true"><path d="M4 14.5V2.5M4 3h8l-1.8 3L12 9H4"/></svg>';
const ICON_CHECK = '<svg class="ico" viewBox="0 0 16 16" aria-hidden="true"><path d="M3.5 8.5l3 3 6-7"/></svg>';

// Ask Flask. GET when there is no body, POST (JSON) when there is one.
// Returns Flask's answer; if anything goes wrong it throws an Error with a plain-English message
// (and .status = the HTTP status, e.g. 409, when Flask answered with an error).
async function todoFetch(path, body) {
  const options = body === undefined ? {}
    : {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(body)};
  let response;
  try {
    response = await fetch(path, options);
  } catch (err) {
    throw new Error(TODO_REACH_ERROR);       // no answer at all: the app is not running
  }
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    const error = new Error(data.error || `The app answered with error ${response.status}. Check the terminal where it runs.`);
    error.status = response.status;
    throw error;
  }
  return data;
}

// Read the list (page opened, app loaded, or after a 409). keepAlert = leave the red message on screen.
async function loadTodos(keepAlert = false) {
  if (!keepAlert) $("todo-alert").innerHTML = "";
  try {
    todos = await todoFetch("/api/todos");
    drawTodos();
  } catch (err) {
    $("todo-list").innerHTML = `<div class="empty bad"><b>Could not read your todos.</b>${esc(err.message)}</div>`;
  }
}

// Send one change, then redraw from Flask's answer. Returns true when it worked.
// Errors show in the red box above the list.
async function todoSend(path, body) {
  if (todoBusy) return false;
  todoBusy = true;
  $("todo-alert").innerHTML = "";
  try {
    todos = await todoFetch(path, body);
    drawTodos();
    return true;
  } catch (err) {
    $("todo-alert").innerHTML = `<div class="alert bad"><b>Could not change your todos.</b> ${esc(err.message)}</div>`;
    if (err.status === 409) await loadTodos(true);   // the file changed elsewhere: show the fresh list
    return false;
  } finally {
    todoBusy = false;
  }
}

// Sidebar badge: number of open todos; red when one of them is high; hidden at 0.
function drawTodoBadge() {
  const badge = $("todo-n");
  badge.textContent = todos.open;
  badge.hidden = !todos.open;
  badge.classList.toggle("high", todos.open_high > 0);
}

// While a row is being edited, find it again in a fresh list: its row number moves if a todo
// above it was deleted. Gone (e.g. deleted in another tab) = stop editing. Returns its place or -1.
function findEditedRow(all) {
  if (!todoEditing) return -1;
  let i = all.findIndex(t => !t.done && t.row === todoEditing.row && t.text === todoEditing.text);
  if (i < 0) i = all.findIndex(t => !t.done && t.text === todoEditing.text);
  if (i < 0) {
    todoEditing = null;
    return -1;
  }
  todoEditing.row = all[i].row;
  return i;
}

function drawTodos() {
  drawTodoBadge();
  $("todo-date").textContent = longDate(new Date());
  $("todo-summary").innerHTML = `${todos.open} open`
    + (todos.open_high ? ` · <b class="crit">${todos.open_high} high</b>` : "")
    + ` · ${todos.done} done`;

  const all = todos.todos;
  const editIndex = findEditedRow(all);
  const typing = document.activeElement && document.activeElement.id === "todo-edit";

  if (!all.length) {
    todoConfirm = false;
    $("todo-list").innerHTML = `<div class="tempty"><span class="circle">${ICON_CHECK}</span>
      <b>All clear.</b><p>No todos yet. Add one above when something comes up.</p></div>`;
    return;
  }

  // Split into the three cards. i = the todo's place in Flask's list (rows carry it as data-i).
  const high = [], normal = [], done = [];
  all.forEach((t, i) => (t.done ? done : t.high ? high : normal).push(i));
  if (!done.length) todoConfirm = false;

  // One open row: [○] text [flag] [✎ Edit] [×]. The row being edited gets a text box instead.
  const openRow = i => {
    const t = all[i];
    if (i === editIndex) return editRow(t, i);
    const flag = t.high ? "High priority, click for normal" : "Normal priority, click for high";
    return `<li class="trow" data-i="${i}">
      <button class="tcheck" type="button" role="checkbox" aria-checked="false" aria-label="${esc(t.text)}" title="Mark done" data-act="done"></button>
      <span class="ttext" title="${esc(t.text)}">${esc(t.text)}</span>
      <button class="ticon tflag${t.high ? " on" : ""}" type="button" aria-label="${flag}" title="${flag}" data-act="high">${ICON_FLAG}</button>
      <button class="tedit" type="button" data-act="edit"${editIndex >= 0 ? " disabled" : ""}><span aria-hidden="true">✎</span> Edit</button>
      <button class="ticon tdel" type="button" aria-label="Delete" title="Delete" data-act="delete">×</button>
    </li>`;
  };
  // One done row: [✓] struck-through text [×]. Clicking ✓ unticks it.
  const doneRow = i => {
    const t = all[i];
    return `<li class="trow" data-i="${i}">
      <button class="tcheck" type="button" role="checkbox" aria-checked="true" aria-label="${esc(t.text)}" title="Not done yet" data-act="done">${ICON_CHECK}</button>
      <span class="ttext" title="${esc(t.text)}">${esc(t.text)}</span>
      <button class="ticon tdel" type="button" aria-label="Delete" title="Delete" data-act="delete">×</button>
    </li>`;
  };

  const n = done.length;
  const doneHead = todoConfirm
    ? `<div class="tconfirm"><span class="q">Delete ${n} done todo${n === 1 ? "" : "s"} for good?</span>
        <button class="btn danger solid" type="button" data-act="clear-yes">Yes, delete</button>
        <button class="btn" type="button" data-act="clear-no">Cancel</button></div>`
    : `<div class="thead"><span class="lbl">Done · ${n}</span>
        <button class="btn clear" type="button" data-act="clear">Clear done</button></div>`;

  $("todo-list").innerHTML =
    (high.length ? `<div class="tcard"><div class="thead">${ICON_FLAG}<span class="lbl crit">High · ${high.length}</span></div>
      <ul class="tlist" aria-label="High priority">${high.map(openRow).join("")}</ul></div>` : "")
    + (normal.length ? `<div class="tcard"><div class="thead"><span class="lbl">Normal · ${normal.length}</span></div>
      <ul class="tlist" aria-label="Normal priority">${normal.map(openRow).join("")}</ul></div>` : "")
    + (done.length ? `<div class="tcard done">${doneHead}
      <ul class="tlist" aria-label="Done">${done.map(doneRow).join("")}</ul></div>` : "");

  if (todoEditing && todoEditing.error) setEditError(true);
  if (todoEditing && typing) $("todo-edit").focus();    // a redraw while you type keeps you typing
}

// The row being edited: [faded ○] [text box] [Save] [Cancel]. Its tick, flag and × are off meanwhile.
function editRow(t, i) {
  return `<li class="trow editing" data-i="${i}">
    <button class="tcheck" type="button" role="checkbox" aria-checked="false" aria-label="${esc(t.text)}" disabled></button>
    <div class="tfield">
      <input id="todo-edit" value="${esc(todoEditing.draft)}" maxlength="500" aria-label="Edit todo" autocomplete="off">
      <p class="terr" id="todo-edit-err" hidden>${TODO_EMPTY_EDIT}</p>
    </div>
    <button class="btn primary" type="button" data-act="save">Save</button>
    <button class="btn" type="button" data-act="cancel">Cancel</button>
  </li>`;
}

// Show or clear the "empty text" message under the edit box (screen readers hear it too).
function setEditError(on) {
  todoEditing.error = on;
  const input = $("todo-edit");
  if (on) {
    input.setAttribute("aria-invalid", "true");
    input.setAttribute("aria-describedby", "todo-edit-err");
  } else {
    input.removeAttribute("aria-invalid");
    input.removeAttribute("aria-describedby");
  }
  $("todo-edit-err").hidden = !on;
}

// After a redraw, put the keyboard focus back on the same todo's button (act = which button).
// Not there any more (e.g. deleted) = focus the "Add a todo…" box.
function focusTodo(text, act) {
  const i = todos.todos.findIndex(t => t.text === text);
  const button = i < 0 ? null : $("todo-list").querySelector(`[data-i="${i}"] [data-act="${act}"]`);
  if (button && !button.disabled) button.focus();
  else $("todo-new").focus();
}

function startEdit(t) {
  todoEditing = {row: t.row, text: t.text, draft: t.text, error: false};
  drawTodos();
  $("todo-edit").focus();
  $("todo-edit").select();
}

function cancelEdit() {
  const text = todoEditing.text;
  todoEditing = null;
  drawTodos();
  focusTodo(text, "edit");
}

async function saveEdit() {
  const newText = $("todo-edit").value.trim();
  if (!newText) {                                   // empty: refuse, say why, stay in the box
    setEditError(true);
    $("todo-edit").focus();
    return;
  }
  if (newText === todoEditing.text) return cancelEdit();   // nothing changed: no need to ask Flask
  const {row, text} = todoEditing;
  if (await todoSend("/api/todos/text", {row, text, new_text: newText})) {
    todoEditing = null;
    drawTodos();
    focusTodo(newText, "edit");
  }
}

function closeConfirm() {
  todoConfirm = false;
  drawTodos();
  $("todo-list").querySelector('[data-act="clear"]').focus();
}

// Add bar: Enter or the Add button. Empty (or only spaces) = do nothing.
$("todo-add").addEventListener("submit", async e => {
  e.preventDefault();                       // stay on this page (a form would reload it)
  const input = $("todo-new");
  const text = input.value.trim();
  if (!text) return;
  if (await todoSend("/api/todos", {text})) input.value = "";
  input.focus();
});

// Every button in the list: data-act says which job it does, data-i on its row says which todo.
$("todo-list").addEventListener("click", async e => {
  const button = e.target.closest("button[data-act]");
  if (!button) return;
  const act = button.dataset.act;
  const row = button.closest("[data-i]");
  const t = row ? todos.todos[row.dataset.i] : null;

  if (act === "done") {
    await todoSend("/api/todos/done", {row: t.row, text: t.text, done: !t.done});
    focusTodo(t.text, "done");
  } else if (act === "high") {
    await todoSend("/api/todos/high", {row: t.row, text: t.text, high: !t.high});
    focusTodo(t.text, "high");
  } else if (act === "delete") {
    await todoSend("/api/todos/delete", {row: t.row, text: t.text});   // at once, no question (decided)
    focusTodo(t.text, "delete");
  } else if (act === "edit") {
    startEdit(t);
  } else if (act === "save") {
    saveEdit();
  } else if (act === "cancel") {
    cancelEdit();
  } else if (act === "clear") {             // first click: ask first
    todoConfirm = true;
    drawTodos();
    $("todo-list").querySelector('[data-act="clear-no"]').focus();
  } else if (act === "clear-no") {
    closeConfirm();
  } else if (act === "clear-yes") {
    await todoSend("/api/todos/clear-done", {});
    $("todo-new").focus();
  }
});

// Typing in the edit box: remember the text (a redraw puts it back) and clear the "empty" message.
$("todo-list").addEventListener("input", e => {
  if (e.target.id !== "todo-edit") return;
  todoEditing.draft = e.target.value;
  if (todoEditing.error) setEditError(false);
});

// Keys, only while the focus is inside the list: in the edit box Enter = Save, Esc = Cancel;
// in the "Delete N done todos?" bar Esc = Cancel. Clicking somewhere else does nothing.
$("todo-list").addEventListener("keydown", e => {
  if (e.target.id === "todo-edit") {
    if (e.key === "Enter" && !e.isComposing) {
      e.preventDefault();
      saveEdit();
    } else if (e.key === "Escape") {
      e.preventDefault();
      cancelEdit();
    }
  } else if (e.key === "Escape" && e.target.closest(".tconfirm")) {
    closeConfirm();
  }
});

loadTodos();   // once when the app opens, so the sidebar badge is right before you open To do
