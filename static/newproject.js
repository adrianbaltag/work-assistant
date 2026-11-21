// "+ New project": a small pop-in form. Flask makes projects\<ID>\ (note.md + empty sessions\ and raw\),
// then the new project's card opens. Uses $, esc from app.js and openCard, toast from card.js.

// npIdea = the idea this form was opened for ("Start as project" on the Ideas page: {row, name}),
// null for a plain "+ New project". Flask then puts the idea's details in the card and removes the idea.
let npIdea = null;

// fill = {title, description, idea} from the Ideas page; nothing = an empty form.
function openNewProject(fill) {
  $("np-form").reset();
  $("np-alert").innerHTML = "";
  npIdea = fill && fill.idea ? fill.idea : null;
  if (npIdea) {
    $("np-title").value = fill.title;
    $("np-desc").value = fill.description;
  }
  showWorkFields();
  $("np").hidden = false;
  $("np-id").focus();
}

const closeNewProject = () => $("np").hidden = true;

// "Created by" and "Ticket description" only matter for a work project: hide them when the box is unticked.
const showWorkFields = () => $("np-work-fields").hidden = !$("np-work").checked;

async function createProject(e) {
  e.preventDefault();       // stop the browser's own form submit (it would reload the page)
  const body = {id: $("np-id").value, title: $("np-title").value, status: $("np-status").value,
                work: $("np-work").checked, created_by: $("np-by").value, description: $("np-desc").value};
  if (npIdea) body.idea = npIdea;
  const button = $("np-create");
  if (button.disabled) return;      // a double click would send a second "create"
  button.disabled = true;
  try {
    const response = await fetch("/api/projects", {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(body)});
    const data = await response.json();
    if (response.status === 409 && npIdea) loadIdeas();     // the idea changed elsewhere: fresh list behind the form
    if (!response.ok) throw new Error(data.error || `server said ${response.status}`);
    closeNewProject();
    if (npIdea) loadIdeas();                                 // the idea has left the list
    openCard(data.id);
    if (data.note) toast(data.note, 5);    // 5 s: longer message. e.g. the work_jira folder already existed, so it was left alone
  } catch (err) {
    $("np-alert").innerHTML = `<span class="err">${esc(err.message)}</span>`;
  } finally {
    button.disabled = false;
  }
}

$("new-project").addEventListener("click", () => openNewProject());   // () =>: the click must not become "fill"
$("np-form").addEventListener("submit", createProject);
$("np-work").addEventListener("change", showWorkFields);
$("np-cancel").addEventListener("click", closeNewProject);
$("np").addEventListener("click", e => { if (e.target === $("np")) closeNewProject(); });   // click outside
document.addEventListener("keydown", e => { if (e.key === "Escape" && !$("np").hidden) closeNewProject(); });
