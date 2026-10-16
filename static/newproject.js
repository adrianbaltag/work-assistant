// "+ New project": a small pop-in form. Flask makes projects\<ID>\ (note.md + empty sessions\ and raw\),
// then the new project's card opens. Uses $, esc from app.js and openCard from card.js.

function openNewProject() {
  $("np-form").reset();
  $("np-alert").innerHTML = "";
  $("np").hidden = false;
  $("np-id").focus();
}

const closeNewProject = () => $("np").hidden = true;

async function createProject(e) {
  e.preventDefault();       // stop the browser's own form submit (it would reload the page)
  const body = {id: $("np-id").value, title: $("np-title").value, status: $("np-status").value};
  const button = $("np-create");
  if (button.disabled) return;      // a double click would send a second "create"
  button.disabled = true;
  try {
    const response = await fetch("/api/projects", {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(body)});
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || `server said ${response.status}`);
    closeNewProject();
    openCard(data.id);
  } catch (err) {
    $("np-alert").innerHTML = `<span class="err">${esc(err.message)}</span>`;
  } finally {
    button.disabled = false;
  }
}

$("new-project").addEventListener("click", openNewProject);
$("np-form").addEventListener("submit", createProject);
$("np-cancel").addEventListener("click", closeNewProject);
$("np").addEventListener("click", e => { if (e.target === $("np")) closeNewProject(); });   // click outside
document.addEventListener("keydown", e => { if (e.key === "Escape" && !$("np").hidden) closeNewProject(); });
