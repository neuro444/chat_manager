// Staff dashboard. Callers are phone numbers; there is no login.
const $ = (id) => document.getElementById(id);
const state = {
  caller: null, session: null, sessions: [], forceNewSession: false,
  callerFilter: "",
};
const debugFields = [
  "latest-query", "chat-history", "session-summary", "caller-profile",
  "cross-session-memory", "reference-data", "system-prompt", "combined-input",
  "output",
];

const setStatus = (t) => { $("status").textContent = t; };
const clearLlmDebug = () => {
  $("llm-debug").classList.add("hidden");
  debugFields.forEach((field) => { $(`debug-${field}`).textContent = ""; });
};
const showLlmDebug = (debug) => {
  if (!debug) return clearLlmDebug();
  const show = (field, value) => {
    $(`debug-${field}`).textContent = typeof value === "string"
      ? (value || "— none —")
      : JSON.stringify(value, null, 2);
  };
  show("latest-query", debug.latest_query);
  show("chat-history", debug.chat_history);
  show("session-summary", debug.session_summary);
  show("caller-profile", debug.caller_profile);
  show("cross-session-memory", debug.cross_session_memory);
  show("reference-data", debug.reference_data);
  show("system-prompt", debug.system_prompt);
  show("combined-input", debug.combined_input);
  show("output", debug.output);
  $("llm-debug").classList.remove("hidden");
};
const fmtTime = (iso) => {
  if (!iso) return "";
  const d = new Date(iso);
  return isNaN(d) ? "" : d.toLocaleString([], {
    month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
};

async function api(path, opts) {
  const r = await fetch(path, opts);
  if (!r.ok) throw new Error(`${r.status} ${await r.text()}`);
  return r.headers.get("content-type")?.includes("json") ? r.json() : r;
}

// ── callers ──────────────────────────────
async function loadCallers() {
  const allRows = await api("/callers");
  const query = state.callerFilter.toLowerCase();
  const rows = allRows.filter((c) =>
    `${c.name || ""} ${c.user_id}`.toLowerCase().includes(query));
  const box = $("callers");
  box.innerHTML = "";
  if (!rows.length) { box.innerHTML = '<div class="empty">No matching callers.</div>'; return; }
  rows.forEach((c) => {
    const wrap = document.createElement("div");
    wrap.className = "row-wrap";
    const el = document.createElement("button");
    el.className = "row" + (c.user_id === state.caller ? " active" : "");
    const label = c.name ? `${c.name} · ${c.user_id}` : c.user_id;
    el.innerHTML = `<div class="title">${label}</div>
      <div class="meta">${c.session_count} call(s) · ${c.message_count} msgs<br>${fmtTime(c.last_active)}</div>`;
    el.onclick = () => selectCaller(c.user_id);
    const del = document.createElement("button");
    del.className = "delete-btn";
    del.title = "Delete caller and every session";
    del.textContent = "Delete";
    del.onclick = () => deleteCaller(c.user_id);
    wrap.append(el, del);
    box.appendChild(wrap);
  });
}

$("caller-search").oninput = (event) => {
  state.callerFilter = event.target.value.trim();
  loadCallers();
};

async function deleteCaller(userId) {
  if (!confirm(`Delete ${userId} and ALL of this caller's sessions and messages?`)) return;
  await api(`/callers?user_id=${encodeURIComponent(userId)}`, { method: "DELETE" });
  if (state.caller === userId) {
    state.caller = null;
    state.session = null;
    state.sessions = [];
    state.forceNewSession = false;
    $("active-caller").textContent = "";
    $("sessions").innerHTML = "";
    $("messages").innerHTML = '<div class="empty">Select a caller.</div>';
    $("summary").classList.add("hidden");
    clearLlmDebug();
  }
  await loadCallers();
}

async function selectCaller(userId) {
  state.caller = userId;
  state.session = null;
  state.forceNewSession = false;
  $("active-caller").textContent = userId;
  await loadCallers();
  await loadSessions();
  $("messages").innerHTML = '<div class="empty">Select a call.</div>';
  $("summary").classList.add("hidden");
  clearLlmDebug();
}

// ── sessions ─────────────────────────────
async function loadSessions(previews = {}) {
  if (!state.caller) return;
  state.sessions = await api(`/sessions?user_id=${encodeURIComponent(state.caller)}`);
  const box = $("sessions");
  box.innerHTML = "";
  if (!state.sessions.length) { box.innerHTML = '<div class="empty">No calls.</div>'; return; }
  state.sessions.forEach((s) => {
    const wrap = document.createElement("div");
    wrap.className = "row-wrap";
    const el = document.createElement("button");
    el.className = "row" + (s.session_id === state.session ? " active" : "");
    const preview = previews[s.session_id]
      ? `<div class="preview">${previews[s.session_id]}</div>` : "";
    el.innerHTML = `<div class="title">${s.title.slice(0, 60)}</div>${preview}
      <div class="meta">${fmtTime(s.updated_at)} · ${s.message_count} messages</div>`;
    el.onclick = () => openSession(s.session_id);
    const del = document.createElement("button");
    del.className = "delete-btn";
    del.title = "Delete this session";
    del.textContent = "Delete";
    del.onclick = () => deleteSession(s.session_id);
    wrap.append(el, del);
    box.appendChild(wrap);
  });
}

async function deleteSession(sessionId) {
  if (!confirm("Delete this session and all of its messages?")) return;
  await api(`/sessions/${encodeURIComponent(sessionId)}`, { method: "DELETE" });
  if (state.session === sessionId) {
    state.session = null;
    $("messages").innerHTML = '<div class="empty">Session deleted.</div>';
    $("summary").classList.add("hidden");
    clearLlmDebug();
  }
  await loadSessions();
  await loadCallers();
}

async function openSession(sid) {
  state.session = sid;
  await loadSessions();
  const msgs = await api(`/sessions/${sid}/messages`);
  renderMessages(msgs);
  const s = state.sessions.find((x) => x.session_id === sid);
  const sum = $("summary");
  if (s?.running_summary) {
    sum.textContent = "Summary: " + s.running_summary;
    sum.classList.remove("hidden");
  } else sum.classList.add("hidden");
}

function renderMessages(msgs) {
  const box = $("messages");
  box.innerHTML = "";
  if (!msgs.length) { box.innerHTML = '<div class="empty">No messages.</div>'; return; }
  msgs.forEach((m) => box.appendChild(bubble(m.role, m.content, m.created_at)));
  box.scrollTop = box.scrollHeight;
}

function bubble(role, text, ts) {
  const d = document.createElement("div");
  d.className = `bubble ${role}`;
  const content = document.createElement("span");
  content.textContent = text;
  d.appendChild(content);
  const copy = document.createElement("button");
  copy.className = "copy-btn";
  copy.textContent = "Copy";
  copy.onclick = async () => {
    await navigator.clipboard.writeText(text);
    copy.textContent = "Copied";
    setTimeout(() => { copy.textContent = "Copy"; }, 1200);
  };
  d.appendChild(copy);
  if (ts) { const s = document.createElement("span");
            s.className = "ts"; s.textContent = fmtTime(ts); d.appendChild(s); }
  return d;
}

// ── search ───────────────────────────────
let searchTimer;
$("search").oninput = (e) => {
  clearTimeout(searchTimer);
  const q = e.target.value.trim();
  searchTimer = setTimeout(async () => {
    if (!state.caller) return;
    if (!q) return loadSessions();
    const hits = await api(`/search?user_id=${encodeURIComponent(state.caller)}&q=${encodeURIComponent(q)}`);
    const previews = {};
    hits.forEach((h) => { previews[h.session_id] ||= h.preview; });
    await loadSessions(previews);
  }, 250);
};

// Enter sends; Shift+Enter is not a newline here (single-line input) but we
// guard anyway so behavior stays predictable if it becomes a textarea.
$("input").addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); $("composer").requestSubmit(); }
});

$("new-chat").onclick = () => {
  state.session = null;
  state.forceNewSession = true;
  $("messages").innerHTML = '<div class="empty">New call — type or speak to start.</div>';
  $("summary").classList.add("hidden");
  clearLlmDebug();
  loadSessions();
  $("input").focus();
};

$("change-caller").onclick = async () => {
  const caller = prompt("Caller phone number:", "+15555550100");
  if (!caller?.trim()) return;
  state.caller = caller.trim();
  state.session = null;
  state.forceNewSession = true;
  $("active-caller").textContent = state.caller;
  $("messages").innerHTML = '<div class="empty">New caller — type or speak to start.</div>';
  $("summary").classList.add("hidden");
  clearLlmDebug();
  await loadCallers();
  await loadSessions();
  $("input").focus();
};

// ── sending (staff testing as the caller) ─
$("composer").onsubmit = async (e) => {
  e.preventDefault();
  const text = $("input").value.trim();
  if (!text) return;
  const caller = state.caller || prompt("Caller phone number:", "+9190000 00000");
  if (!caller) return;
  state.caller = caller;
  $("input").value = "";
  $("messages").appendChild(bubble("user", text, new Date().toISOString()));
  setStatus("thinking…");
  try {
    const out = await api("/chat", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        user_id: caller,
        session_id: state.session,
        message: text,
        include_llm_debug: true,
        new_session: state.forceNewSession,
      }),
    });
    state.session = out.session_id;
    state.forceNewSession = false;
    $("messages").appendChild(bubble("assistant", out.answer, new Date().toISOString()));
    $("messages").scrollTop = $("messages").scrollHeight;
    showLlmDebug(out.llm_debug);
    setStatus("ready");
    if ($("tts-toggle").checked) speak(out.answer);
    await loadCallers(); await loadSessions();
  } catch (err) { setStatus("error"); alert(err.message); }
};

// ── voice ────────────────────────────────
async function speak(text) {
  try {
    setStatus("speaking…");
    const r = await fetch("/tts", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text }),
    });
    if (!r.ok) { setStatus("tts unavailable"); return; }
    const audio = new Audio(URL.createObjectURL(await r.blob()));
    audio.onended = () => setStatus("ready");
    audio.play();
  } catch { setStatus("tts error"); }
}

let recorder, chunks = [];
$("mic").onclick = async () => {
  const btn = $("mic");
  if (recorder && recorder.state === "recording") { recorder.stop(); return; }
  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    recorder = new MediaRecorder(stream);
    chunks = [];
    recorder.ondataavailable = (e) => chunks.push(e.data);
    recorder.onstop = async () => {
      stream.getTracks().forEach((t) => t.stop());
      btn.classList.remove("recording");
      setStatus("transcribing…");
      const fd = new FormData();
      fd.append("file", new Blob(chunks, { type: "audio/webm" }), "audio.webm");
      try {
        const { text } = await api("/stt", { method: "POST", body: fd });
        $("input").value = text;
        setStatus("ready");
        if (text) $("composer").requestSubmit();
      } catch { setStatus("stt error"); }
    };
    recorder.start();
    btn.classList.add("recording");
    setStatus("recording… click to stop");
  } catch { alert("Microphone unavailable"); }
};

loadCallers().then(() => setStatus("ready"));
setInterval(() => { if (!document.hidden) loadCallers(); }, 10000);
