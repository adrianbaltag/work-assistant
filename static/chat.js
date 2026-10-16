// Ask Claude chat box. Used by the project card now, and later by the global Ask Claude page.
// The chat lives only in the page: closing the card forgets it (decided). Each question sends the
// earlier chat back to Flask, because Claude remembers nothing between calls.
// Uses $ and esc from app.js.

function makeChat(box, {sub, intro, chips, placeholder, url}) {
  const chat = {history: [], busy: false, skippedShown: false};
  box.chat = chat;      // a newer chat in the same box = answers to this one are dropped
  box.innerHTML = `<div class="c-head"><span class="spark">✳</span><div><b>Ask Claude</b><small>${esc(sub)}</small></div></div>
    <div class="c-log" aria-live="polite"></div>
    <div class="c-foot">
      <div class="chips">${chips.map(c => `<button type="button" class="chip">${esc(c)}</button>`).join("")}</div>
      <div class="c-note">Every change waits for your Approve</div>
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
    chat.history.push({role: "user", text: question}, {role: "assistant", text: data.reply});
    if (data.skipped.length && !chat.skippedShown) {
      chat.skippedShown = true;
      add("skip", "Not read: " + data.skipped.join(", "));
    }
    input.focus();
  }

  add("claude", intro);
  box.querySelector(".chips").addEventListener("click", e => {
    if (e.target.closest(".chip")) send(e.target.closest(".chip").textContent);
  });
  box.querySelector("form").addEventListener("submit", e => {
    e.preventDefault();
    send(input.value);
  });
}
