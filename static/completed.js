// Completed tab: the end of each open row ("In progress" or "✓ Complete"), the "Move to Completed?"
// pop-up, the Completed rows and their Restore button. Python decides which row may be completed
// (p.ready, see ready_to_complete in app.py); this file only draws and asks.
// Uses $, esc, load, refocus, REACH_ERROR, projects and completed from app.js, toast from card.js.

// p.ready values that give the green button: no work folder, ticket closed, no requirements.md yet,
// or a ticket from before ticket-flow (it never gets the Status line, so you decide).
const CAN_COMPLETE = ["no_ticket", "closed", "no_requirements", "old_ticket"];

// The end of an open row. A note that can't be read (p.problem) gets an empty cell.
function rowEnd(p) {
  if (p.problem) return '<span class="pend"></span>';
  if (CAN_COMPLETE.includes(p.ready)) {
    return `<button type="button" class="pend" data-complete="${esc(p.id)}" title="Move to Completed"`
      + ` aria-label="Complete ${esc(p.title)}: move it to Completed"><span class="go">✓ Complete</span></button>`;
  }
  const why = p.ready === "away" ? "Can't see the work folder right now (moved, or the VPN is off)."
    : p.ready === "unreadable" ? "Can't read its requirements.md right now (open in another program?)."
    : "Still in progress. Turns into ✓ Complete when Claude closes the ticket.";
  return `<span class="pend" title="${why}"><span class="wait">In progress</span></span>`;
}

// One row on the Completed tab: name + Jira, finished date, how it ended, Restore. No card opens from here.
const doneRow = (p, i) => `
    <div class="prow-wrap" style="animation-delay:${i * 40}ms">
    <div class="prow cdone">
      <span class="c"><span class="pname clip" title="${esc(p.title)}">${esc(p.title)}</span><span class="pjira clip">${p.jira ? esc(p.jira) : "no Jira"}</span></span>
      <span class="c"><span class="ago">${esc(p.finished)}</span></span>
      <span class="c">${clip(p.ended)}</span>
    </div><span class="pend"><button type="button" class="btn sm" data-restore="${esc(p.id)}" aria-label="Restore ${esc(p.title)} to the dashboard">Restore</button></span>
    </div>`;

// ---------- "Move to Completed?" ----------

let completing = null;      // the project the pop-up asks about
let prodFolder = null;      // where its ticket folder goes: the folder found by its tag, or null = ask (the box)

// The folder's own name (the last part of its path), e.g. "ABC-1" from C:\Users\me\Desktop\work_jira\ABC-1.
const lastPart = path => String(path || "").split(/[\\/]/).filter(Boolean).pop() || "";

async function askComplete(id) {
  const p = projects.find(x => x.id === id);
  if (!p) return;
  completing = p;
  prodFolder = null;
  const name = `<b>${esc(p.title)}</b>`;
  const lead = p.ready === "closed" ? `${name}: its ticket is closed.`
    : p.ready === "no_requirements" ? `${name}: its work folder has no requirements.md, so the app can't tell `
      + "if the ticket is done. You decide."
    : p.ready === "old_ticket" ? `${name} was started before ticket-flow, so the app can't tell `
      + "if the ticket is done. You decide."
    : `${name} has no ticket folder. You decide when it is done.`;
  $("cp-where").hidden = true;
  $("cp-alert").innerHTML = "";
  if (p.ready === "no_ticket") {
    $("cp-text").innerHTML = `${lead} The card leaves the dashboard and shows on the Completed tab. `
      + "Restore there brings it back.";
  } else {
    // A ticket card: its work folder moves too. Ask Flask where to (the folder with the hidden tag file).
    let where;
    try {
      const response = await fetch("/api/prod-folder");
      where = await response.json();
    } catch (err) {
      if (completing === p) completing = null;
      toast(REACH_ERROR);
      return;
    }
    // Another row was clicked while we waited: its pop-up is the one that counts, drop this late answer.
    if (completing !== p) return;
    prodFolder = where.folder;
    const folder = `<b>${esc(lastPart(p.folder) || p.id)}</b>`;
    $("cp-text").innerHTML = `${lead} The card moves to the Completed tab, and the folder ${folder} moves `
      + `from work_jira to ${prodFolder ? `<b>${esc(prodFolder)}</b>` : "the folder below"}. `
      + "Restore brings both back.";
    if (!prodFolder) showWhere(where.suggest);
  }
  $("cp").hidden = false;
  $("cp-yes").focus();
}

// The one-time box: where completed ticket folders go. Shown only while no folder has the tag file.
function showWhere(suggest) {
  prodFolder = null;
  $("cp-folder").value = suggest || "";
  $("cp-where").hidden = false;
}

// Close the pop-up. back = put the focus on that row's Complete button again (Cancel, Esc).
function closeComplete(back = true) {
  $("cp").hidden = true;
  if (back && completing) refocus(`[data-complete="${CSS.escape(completing.id)}"]`);
  completing = null;
}

async function doComplete() {
  const button = $("cp-yes");
  if (button.disabled || !completing) return;     // a double click would send a second "complete"
  button.disabled = true;
  const p = completing;
  // A ticket card sends where its folder goes (the found folder, or what is in the box). A plain card sends nothing.
  const options = {method: "POST"};
  if (p.ready !== "no_ticket") {
    options.headers = {"Content-Type": "application/json"};
    options.body = JSON.stringify({prod_folder: prodFolder || $("cp-folder").value});
  }
  try {
    const response = await fetch(`/api/projects/${encodeURIComponent(p.id)}/complete`, options);
    const data = await response.json().catch(() => ({error: response.status === 404
      ? "This project is gone (completed already, or its folder moved?). Reload the page (F5)." : `server said ${response.status}`}));
    if (data.need_folder) showWhere(data.suggest);      // the tag file went missing since the pop-up opened
    if (!response.ok) throw new Error(data.error);
    closeComplete(false);
    toast(`${p.title} moved to Completed.`);
    await load();
    refocus("[data-open]");       // its row is gone: the focus goes to the first row
  } catch (err) {
    const words = err instanceof TypeError ? REACH_ERROR : err.message;     // TypeError = no answer at all
    $("cp-alert").innerHTML = `<span class="err">${esc(words)}</span>`;
  } finally {
    button.disabled = false;
  }
}

$("cp-yes").addEventListener("click", doComplete);
$("cp-folder").addEventListener("keydown", e => { if (e.key === "Enter") doComplete(); });
$("cp-cancel").addEventListener("click", () => closeComplete());
$("cp-cancel-x").addEventListener("click", () => closeComplete());
$("cp").addEventListener("click", e => { if (e.target === $("cp")) closeComplete(); });   // click outside
document.addEventListener("keydown", e => { if (e.key === "Escape" && !$("cp").hidden) closeComplete(); });

// ---------- Restore ----------

// A note above the list that stays (also when you change tabs) until you click its X.
function dashNote(html) {
  $("dash-alert").insertAdjacentHTML("beforeend", `<div class="alert warn has-x" role="status"><span>${html}</span>`
    + '<button type="button" class="x sm" data-close-note aria-label="Close this message">×</button></div>');
}

$("dash-alert").addEventListener("click", e => {
  const x = e.target.closest("[data-close-note]");
  if (x) x.closest(".alert").remove();
});

// Flask moves the ticket folder back (if Complete moved one), then the card (with a time suffix only if the
// name is taken now). Errors stay above the list until the next try; notes stay until their X.
async function restoreProject(id) {
  const p = completed.find(x => x.id === id);
  if (!p) return;
  $("dash-alert").querySelectorAll(".alert.bad").forEach(a => a.remove());
  try {
    const response = await fetch(`/api/completed/${encodeURIComponent(id)}/restore`, {method: "POST"});
    const data = await response.json().catch(() => ({error: response.status === 404
      ? "It is gone (restored already?). Reload the page (F5)." : `server said ${response.status}`}));
    if (!response.ok) throw new Error(data.error);
    const shownAs = data.id !== id ? ` as ${data.id}` : "";
    toast(`${p.title} is back on the dashboard${shownAs}.`);
    if (data.warning) dashNote(`<b>${esc(p.title)}:</b> ${esc(data.warning)}`);
    if (data.still_closed) {
      dashNote(`<b>${esc(p.title)} is back, but its ticket is still closed.</b> If something broke, open Claude `
        + "in its folder and say <b>reopen: what broke</b>.");
    }
  } catch (err) {
    const words = err instanceof TypeError ? REACH_ERROR : err.message;
    $("dash-alert").insertAdjacentHTML("afterbegin",
      `<div class="alert bad"><b>Could not restore.</b> ${esc(words)}</div>`);
  }
  await load();
  refocus("[data-restore]");      // its row may be gone: the focus goes to the next Restore button
}
