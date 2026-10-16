// Ask Claude chat box. Used by the project card and by the global Ask Claude page.
// The chat lives only in the page: closing the card forgets it (decided). Each question sends the
// earlier chat back to Flask, because Claude remembers nothing between calls.
// Uses $ and esc from app.js.
// Optional (project panel only): current(field) = the field's value now, approve(proposal, stamp) =
// save Claude's proposal; resolves to true (saved), false (you cancelled) or an error message.
// A chip is a question, or {label, ask}: a short button that sends a longer, more precise question.

function makeChat(box, {sub, intro, chips, placeholder, url, current, approve,
                        note = "Every change waits for your Approve"}) {
  const chat = {history: [], busy: false, skippedShown: ""};
  box.chat = chat;      // a newer chat in the same box = answers to this one are dropped
  box.innerHTML = `<div class="c-head"><span class="spark">✳</span><div><b>Ask Claude</b><small>${esc(sub)}</small></div></div>
    <div class="c-log" aria-live="polite"></div>
    <div class="c-foot">
      <div class="chips">${chips.map(c => `<button type="button" class="chip" data-ask="${esc(c.ask ?? c)}">${esc(c.label ?? c)}</button>`).join("")}</div>
      <div class="c-note">${esc(note)}</div>
      <form class="c-ask"><input placeholder="${esc(placeholder)}" aria-label="Your question" autocomplete="off">
        <button class="btn primary">Send</button></form>
    </div>`;
  const log = box.querySelector(".c-log");
  const input = box.querySelector("input");

  function add(kind, text) {
    const div = document.createElement("div");
    div.className = `msg ${kind}`;
    div.textContent = text;
    log.append(div);
    log.scrollTop = log.scrollHeight;
    return div;
  }

  async function send(question) {
    question = question.trim();
    if (!question || chat.busy) return;
    chat.busy = true;
    box.classList.add("busy");
    input.value = "";
    add("you", question);
    const waiting = add("claude wait", "Claude is reading the files…");
    let data;
    try {
      const response = await fetch(url, {method: "POST", headers: {"Content-Type": "application/json"},
                                         body: JSON.stringify({question, history: chat.history})});
      data = await response.json().catch(() => ({error: `The app answered ${response.status}.`}));
    } catch (err) {
      data = {error: "Could not reach the app. Is it still running?"};
    }
    if (box.chat !== chat) return;      // the card was closed (or another one opened) meanwhile
    chat.busy = false;
    box.classList.remove("busy");
    if (data.error) {
      waiting.className = "msg err";
      waiting.textContent = data.error;
      return;      // not added to the history, so asking again works
    }
    waiting.className = "msg claude";
    waiting.textContent = data.reply;
    const said = {role: "assistant", text: data.reply};
    chat.history.push({role: "user", text: question}, said);
    if (data.proposal && approve) showProposal(data.proposal, data.stamp, said);
    const skipped = data.skipped.join(", ");      // shown again only when it changes (notes can change mid-chat)
    if (skipped && skipped !== chat.skippedShown) add("skip", "Not read: " + skipped);
    chat.skippedShown = skipped;
    input.focus();
  }

  // Claude's suggested changes, with Approve / Reject. The chat history gets a plain-text copy,
  // and later what you chose, so Claude knows in its next answers.
  function showProposal(proposal, stamp, said) {
    const lines = proposal.fields.map(f => `${f.field}: "${current(f.field) || "(empty)"}" → "${f.value || "(empty)"}"`);
    if (proposal.history_line) lines.push(`History line: ${proposal.history_line}`);
    said.text += `\n\n(I suggested: ${[...lines, ...(proposal.session_note ? ["a new session note"] : [])].join("; ")}.)`;

    const div = add("proposal", "");
    div.innerHTML = `<b>Suggested changes</b>
      <ul>${proposal.fields.map(f => `<li><span class="k">${esc(f.field)}</span>
            <s>${esc(current(f.field) || "(empty)")}</s> → <span>${esc(f.value || "(empty)")}</span></li>`).join("")}
        ${proposal.history_line ? `<li><span class="k">History</span> ${esc(proposal.history_line)}</li>` : ""}
        ${proposal.session_note ? `<li><details><summary><span class="k">New session note</span> in sessions\\, named by today's date</summary>
            <pre>${esc(proposal.session_note)}</pre></details></li>` : ""}</ul>
      <div class="row"><button type="button" class="btn sm primary">Approve</button><button type="button" class="btn sm">Reject</button></div>
      <div class="p-said"></div>`;
    const [yes, no] = div.querySelectorAll(".row button");
    const status = div.querySelector(".p-said");
    const finish = text => {
      div.querySelector(".row").remove();
      status.textContent = text;
      said.text += ` (${text})`;
    };
    no.addEventListener("click", () => finish("Rejected. Nothing changed."));
    yes.addEventListener("click", async () => {
      yes.disabled = no.disabled = true;
      status.textContent = "";
      const result = await approve(proposal, stamp);
      if (box.chat !== chat) return;
      yes.disabled = no.disabled = false;
      if (result === true) finish("Approved and saved.");
      else if (result) status.textContent = result;       // an error: the buttons stay, so you can try again
    });
  }

  add("claude", intro);
  box.querySelector(".chips").addEventListener("click", e => {
    const chip = e.target.closest(".chip");
    if (chip) send(chip.dataset.ask);
  });
  box.querySelector("form").addEventListener("submit", e => {
    e.preventDefault();
    send(input.value);
  });
}
