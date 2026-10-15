// Archive page: finished projects (in projects\_archive\) and deleted files (in each open project's archive\).
// Restore moves them back; Flask adds a time suffix if the name is taken, so nothing is ever overwritten.
// Uses $, esc and load from app.js, toast from card.js.

let archive = {projects: [], files: []};

async function loadArchive() {
  try {
    const response = await fetch("/api/archive");
    if (!response.ok) throw new Error(`server said ${response.status}`);
    archive = await response.json();
    drawArchive();
  } catch (err) {
    $("arch-list").innerHTML = `<div class="empty bad"><b>Could not read the archive.</b>${esc(err.message)}. Check the terminal where the app runs.</div>`;
  }
}

// dir "" = an old note.md copy from "Save mine anyway": it restores into raw\, never over the live note.md.
const wasIn = f => f.dir ? `${esc(f.dir)}\\` : `note.md copy <span class="hint">(restores to raw\\)</span>`;

function drawArchive() {
  const {projects, files} = archive;
  $("arch-list").innerHTML = `
    <div class="date sec">Finished projects</div>
    ${projects.length ? `<div class="list plain"><table>
      <thead><tr><th>Project</th><th>Finished</th><th>Files</th><th></th></tr></thead>
      <tbody>${projects.map((p, i) => `<tr>
        <td><span class="pname">${esc(p.title)}</span><span class="pjira">${esc(p.id)}${p.jira && p.jira !== p.id ? " · " + esc(p.jira) : ""}</span></td>
        <td class="ago">${esc(p.finished)}</td>
        <td class="ago">${p.files}</td>
        <td><button class="btn sm" data-restore-project="${i}">Restore</button></td></tr>`).join("")}</tbody></table></div>`
      : `<div class="empty"><b>No archived projects.</b>Projects you mark done land here.</div>`}
    <div class="date sec" style="margin-top:22px">Deleted files, from all open projects</div>
    ${files.length ? `<div class="list plain"><table>
      <thead><tr><th>File</th><th>Project</th><th>Was in</th><th></th></tr></thead>
      <tbody>${files.map((f, i) => `<tr>
        <td class="mono" style="font-size:.82rem">${esc(f.name)}</td>
        <td>${esc(f.title)}<span class="pjira">${esc(f.project)}</span></td>
        <td class="ago">${wasIn(f)}</td>
        <td><button class="btn sm" data-restore-file="${i}">Restore</button></td></tr>`).join("")}</tbody></table></div>`
      : `<div class="empty"><b>No deleted files.</b>When you delete a file inside a project, it lands here and in that project's archive\\ folder.</div>`}`;
}

// POST a restore, then re-read the archive. Errors (e.g. a file open in Excel) stay on screen until the next try.
async function restore(path, body, done) {
  $("arch-alert").innerHTML = "";
  try {
    const response = await fetch(path, {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(body)});
    const data = await response.json().catch(() => ({error: response.status === 404 ? "it is gone (moved or restored already?)" : `server said ${response.status}`}));
    if (!response.ok) throw new Error(data.error);
    toast(done(data));
  } catch (err) {
    $("arch-alert").innerHTML = `<div class="alert bad"><b>Could not restore.</b> ${esc(err.message)}</div>`;
  }
  loadArchive();
}

$("arch-list").addEventListener("click", e => {
  const button = e.target.closest("button");
  if (!button) return;
  if (button.dataset.restoreProject) {
    const p = archive.projects[button.dataset.restoreProject];
    restore(`/api/archive/projects/${encodeURIComponent(p.id)}/restore`, {},
      data => `${p.title} is back on the Dashboard${data.id !== p.id ? ` as ${data.id}` : ""}.`);
  } else if (button.dataset.restoreFile) {
    const f = archive.files[button.dataset.restoreFile];
    restore("/api/archive/files/restore", {project: f.project, dir: f.dir, name: f.name},
      data => `Restored to ${f.project}\\${data.where.replace("/", "\\")}`);
  }
});
