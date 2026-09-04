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
const formatRawLlmOutput = (value) => {
  if (typeof value !== "string") return JSON.stringify(value, null, 2);
  if (!value) return "— none —";
  try {
    const parsed = JSON.parse(value);
    return parsed && typeof parsed === "object"
      ? JSON.stringify(parsed, null, 2)
      : value;
  } catch {
    return value;
  }
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
  $("debug-output").textContent = formatRawLlmOutput(debug.output);
  $("llm-debug").classList.remove("hidden");
};
const fmtTime = (iso) => {
  if (!iso) return "";
  const d = new Date(iso);
  return isNaN(d) ? "" : d.toLocaleString([], {
    month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
};
const icon = (name) => name === "trash"
  ? '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M3 6h18M8 6V4h8v2m3 0-1 15H6L5 6m4 4v7m6-7v7"/></svg>'
  : '<svg viewBox="0 0 24 24" aria-hidden="true"><rect x="9" y="9" width="11" height="11" rx="2"/><path d="M15 9V6a2 2 0 0 0-2-2H6a2 2 0 0 0-2 2v7a2 2 0 0 0 2 2h3"/></svg>';

const showSessionId = (sessionId) => {
  $("active-session-id").textContent = sessionId || "";
  $("chat-meta").classList.toggle("hidden", !sessionId);
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
    del.setAttribute("aria-label", del.title);
    del.innerHTML = icon("trash");
    del.onclick = () => deleteCaller(c.user_id);
    wrap.append(el, del);
    box.appendChild(wrap);
  });
}

$("caller-search").oninput = (event) => {
  state.callerFilter = event.target.value.trim();
  loadCallers();
};

let globalSearchTimer;
$("global-search").oninput = (event) => {
  clearTimeout(globalSearchTimer);
  const query = event.target.value.trim();
  globalSearchTimer = setTimeout(async () => {
    if (!query) return loadCallers();
    const hits = await api(`/staff/search?q=${encodeURIComponent(query)}`);
    const box = $("callers");
    box.innerHTML = "";
    if (!hits.length) {
      box.innerHTML = '<div class="empty">No conversation matches.</div>';
      return;
    }
    hits.forEach((hit) => {
      const button = document.createElement("button");
      button.className = "row global-result";
      const title = document.createElement("div");
      title.className = "title";
      title.textContent = hit.user_id;
      const preview = document.createElement("div");
      preview.className = "preview";
      preview.textContent = hit.preview;
      const meta = document.createElement("div");
      meta.className = "meta";
      meta.textContent = fmtTime(hit.created_at);
      button.append(title, preview, meta);
      button.onclick = async () => {
        await selectCaller(hit.user_id);
        await openSession(hit.session_id);
      };
      box.appendChild(button);
    });
  }, 250);
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
  showSessionId(null);
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
    del.setAttribute("aria-label", del.title);
    del.innerHTML = icon("trash");
    del.onclick = () => deleteSession(s.session_id);
    wrap.append(el, del);
    box.appendChild(wrap);
  });
}

async function deleteSession(sessionId) {
  if (!confirm("Delete this session and all of its messages?")) return;
  await api(
    `/sessions/${encodeURIComponent(sessionId)}?user_id=${encodeURIComponent(state.caller)}`,
    { method: "DELETE" }
  );
  if (state.session === sessionId) {
    state.session = null;
    showSessionId(null);
    $("messages").innerHTML = '<div class="empty">Session deleted.</div>';
    $("summary").classList.add("hidden");
    clearLlmDebug();
  }
  await loadSessions();
  await loadCallers();
}

async function openSession(sid) {
  state.session = sid;
  showSessionId(sid);
  await loadSessions();
  const msgs = await api(`/sessions/${sid}/messages?user_id=${encodeURIComponent(state.caller)}`);
  renderMessages(msgs);
  const debug = await api(`/sessions/${sid}/debug?user_id=${encodeURIComponent(state.caller)}`);
  showLlmDebug(debug);
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
  copy.title = "Copy message";
  copy.setAttribute("aria-label", copy.title);
  copy.innerHTML = icon("copy");
  copy.onclick = async () => {
    await navigator.clipboard.writeText(text);
    copy.classList.add("copied");
    copy.title = "Copied";
    copy.setAttribute("aria-label", copy.title);
    setTimeout(() => {
      copy.classList.remove("copied");
      copy.title = "Copy message";
      copy.setAttribute("aria-label", copy.title);
    }, 1200);
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
  showSessionId(null);
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
  showSessionId(null);
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
    showSessionId(out.session_id);
    state.forceNewSession = false;
    $("messages").appendChild(bubble("assistant", out.answer, new Date().toISOString()));
    $("messages").scrollTop = $("messages").scrollHeight;
    showLlmDebug(out.llm_debug);
    setStatus("ready");
    if ($("tts-toggle").checked) speak(out.answer);
    await loadCallers(); await loadSessions();
  } catch (err) { setStatus("error"); alert(err.message); }
};

$("copy-session-id").innerHTML = icon("copy");
$("copy-session-id").onclick = async () => {
  if (!state.session) return;
  await navigator.clipboard.writeText(state.session);
  $("copy-session-id").classList.add("copied");
  setTimeout(() => $("copy-session-id").classList.remove("copied"), 1200);
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

// ── cost monitor ─────────────────────────
const COST_PIN_STORAGE_KEY = "cost-monitor-unlocked";
let costLoaded = false;

function fmtUsd(v) {
  const n = Number(v);
  return Number.isFinite(n) ? `$${n.toFixed(2)}` : "—";
}

function showView(view) {
  $("view-orders").classList.toggle("hidden", view !== "orders");
  $("view-cost").classList.toggle("hidden", view !== "cost");
  $("tab-orders").classList.toggle("active", view === "orders");
  $("tab-cost").classList.toggle("active", view === "cost");
}

function unlockedInThisBrowser() {
  return localStorage.getItem(COST_PIN_STORAGE_KEY) === "1";
}

function enterCostTab() {
  $("cost-pin-gate").classList.add("hidden");
  $("cost-content").classList.remove("hidden");
  if (!costLoaded) loadCostView();
}

function promptForPin() {
  $("cost-content").classList.add("hidden");
  $("cost-pin-gate").classList.remove("hidden");
  $("cost-pin-error").classList.add("hidden");
  $("cost-pin-input").value = "";
  $("cost-pin-input").focus();
}

$("tab-orders").onclick = () => showView("orders");
$("tab-cost").onclick = async () => {
  showView("cost");
  if (unlockedInThisBrowser()) { enterCostTab(); return; }
  // No local unlock on record yet -- ask the server whether a PIN is even
  // required before showing the prompt, so a dashboard with no PIN configured
  // never blocks on one.
  try {
    const { pin_required } = await api("/cost/pin-check");
    if (!pin_required) {
      localStorage.setItem(COST_PIN_STORAGE_KEY, "1");
      enterCostTab();
      return;
    }
  } catch { /* fall through to the PIN prompt if the check itself fails */ }
  promptForPin();
};

async function unlockCostTab() {
  const entered = $("cost-pin-input").value.trim();
  try {
    const { pin_required, correct } = await api(
      `/cost/pin-check?pin=${encodeURIComponent(entered)}`);
    if (pin_required && !correct) {
      $("cost-pin-error").classList.remove("hidden");
      return;
    }
    localStorage.setItem(COST_PIN_STORAGE_KEY, "1");
    enterCostTab();
  } catch {
    $("cost-pin-error").textContent = "Could not verify PIN.";
    $("cost-pin-error").classList.remove("hidden");
  }
}
$("cost-pin-submit").onclick = unlockCostTab;
$("cost-pin-input").addEventListener("keydown", (e) => {
  if (e.key === "Enter") { e.preventDefault(); unlockCostTab(); }
});

// ── cost filters + sort state ────────────
const costState = {
  range: "today",       // today | 7d | 30d | month | year | custom
  startDate: null,       // yyyy-mm-dd, set for custom or derived from preset
  endDate: null,
  provider: "",
  groupBy: "day",        // day | month | year, for the breakdown table
  calls: [],
  sortKey: "started_at",
  sortDir: "desc",
};

function isoDate(d) { return d.toISOString().slice(0, 10); }

function computeRangeDates(range) {
  const today = new Date();
  const end = isoDate(today);
  if (range === "today") return { start: end, end };
  if (range === "7d") {
    const d = new Date(today); d.setUTCDate(d.getUTCDate() - 6);
    return { start: isoDate(d), end };
  }
  if (range === "30d") {
    const d = new Date(today); d.setUTCDate(d.getUTCDate() - 29);
    return { start: isoDate(d), end };
  }
  if (range === "month") {
    const d = new Date(Date.UTC(today.getUTCFullYear(), today.getUTCMonth(), 1));
    return { start: isoDate(d), end };
  }
  if (range === "year") {
    const d = new Date(Date.UTC(today.getUTCFullYear(), 0, 1));
    return { start: isoDate(d), end };
  }
  return { start: costState.startDate, end: costState.endDate };
}

function applyRangePreset(range) {
  costState.range = range;
  document.querySelectorAll("#cost-date-presets .filter-btn").forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.range === range);
  });
  $("cost-custom-range").classList.toggle("hidden", range !== "custom");
  if (range === "custom") {
    if (!costState.startDate || !costState.endDate) return; // wait for Apply
  }
  const { start, end } = computeRangeDates(range);
  costState.startDate = start;
  costState.endDate = end;
  refreshCostData();
}

document.querySelectorAll("#cost-date-presets .filter-btn").forEach((btn) => {
  btn.onclick = () => applyRangePreset(btn.dataset.range);
});

$("cost-custom-apply").onclick = () => {
  const start = $("cost-range-start").value;
  const end = $("cost-range-end").value;
  if (!start || !end) return;
  costState.startDate = start;
  costState.endDate = end;
  refreshCostData();
};

$("cost-provider-filter").onchange = (e) => {
  costState.provider = e.target.value;
  refreshCostData();
};

document.querySelectorAll("#cost-group-toggle .filter-btn").forEach((btn) => {
  btn.onclick = () => {
    costState.groupBy = btn.dataset.group;
    document.querySelectorAll("#cost-group-toggle .filter-btn").forEach((b) =>
      b.classList.toggle("active", b === btn));
    loadCostBreakdownAndSummary();
  };
});

async function loadCostView() {
  costLoaded = true;
  const { start, end } = computeRangeDates(costState.range);
  costState.startDate = start;
  costState.endDate = end;
  await refreshCostData();
}

async function refreshCostData() {
  await Promise.all([loadCostToday(), loadCostCalls(), loadCostBreakdownAndSummary()]);
}

async function loadCostToday() {
  const box = $("cost-today");
  box.innerHTML = '<div class="empty">Loading…</div>';
  try {
    const d = await api("/cost/api/internal/costs/daily");
    box.innerHTML = "";
    const cards = [
      ["Phone", fmtUsd(d.phone_cost_usd)],
      ["WhatsApp", "not yet tracked"],
      ["Fixed (server)", fmtUsd(d.fixed_cost_usd)],
      ["Total today", fmtUsd(d.total_cost_usd)],
    ];
    cards.forEach(([label, value]) => {
      const card = document.createElement("div");
      card.className = "cost-card";
      const labelEl = document.createElement("div");
      labelEl.className = "cost-card-label";
      labelEl.textContent = label;
      const valueEl = document.createElement("div");
      valueEl.className = "cost-card-value";
      valueEl.textContent = value;
      card.append(labelEl, valueEl);
      box.appendChild(card);
    });
  } catch (err) {
    renderEmpty(box, `Cost data unavailable (${err.message}).`);
  }
}

function renderEmpty(box, text) {
  box.innerHTML = "";
  const message = document.createElement("div");
  message.className = "empty";
  message.textContent = text;
  box.appendChild(message);
}

const CALLS_COLUMNS = [
  { key: "started_at", label: "Started" },
  { key: "status", label: "Status" },
  { key: "providers", label: "Providers" },
  { key: "total_input_tokens", label: "Input tokens" },
  { key: "total_output_tokens", label: "Output tokens" },
  { key: "total_cost_usd", label: "Cost" },
];

function sortCalls(calls) {
  const { sortKey, sortDir } = costState;
  const dir = sortDir === "asc" ? 1 : -1;
  return [...calls].sort((a, b) => {
    let av = a[sortKey], bv = b[sortKey];
    if (sortKey === "providers") { av = (av || []).join(", "); bv = (bv || []).join(", "); }
    if (sortKey === "total_cost_usd") { av = Number(av); bv = Number(bv); }
    if (av == null) av = "";
    if (bv == null) bv = "";
    if (av < bv) return -1 * dir;
    if (av > bv) return 1 * dir;
    return 0;
  });
}

async function loadCostCalls() {
  const box = $("cost-calls-table");
  box.innerHTML = '<div class="empty">Loading…</div>';
  try {
    const params = new URLSearchParams({
      start_date: costState.startDate, end_date: costState.endDate, limit: "200",
    });
    if (costState.provider) params.set("provider", costState.provider);
    const data = await api(`/cost/api/internal/calls?${params}`);
    costState.calls = data.calls || [];
    renderCostCallsTable();
  } catch (err) {
    renderEmpty(box, `Cost data unavailable (${err.message}).`);
  }
}

function renderCostCallsTable() {
  const box = $("cost-calls-table");
  const calls = sortCalls(costState.calls);
  if (!calls.length) { renderEmpty(box, "No calls in this range."); return; }
  box.innerHTML = "";
  const table = document.createElement("table");
  const thead = document.createElement("thead");
  const headRow = document.createElement("tr");
  CALLS_COLUMNS.forEach((col) => {
    const th = document.createElement("th");
    th.className = "sortable";
    const isActive = costState.sortKey === col.key;
    th.textContent = col.label + (isActive ? (costState.sortDir === "asc" ? " ▲" : " ▼") : "");
    th.onclick = () => {
      if (costState.sortKey === col.key) {
        costState.sortDir = costState.sortDir === "asc" ? "desc" : "asc";
      } else {
        costState.sortKey = col.key;
        costState.sortDir = "asc";
      }
      renderCostCallsTable();
    };
    headRow.appendChild(th);
  });
  thead.appendChild(headRow);
  table.appendChild(thead);
  const tbody = document.createElement("tbody");
  calls.forEach((c) => {
    const tr = document.createElement("tr");
    tr.className = "cost-row";
    const cells = [
      fmtTime(c.started_at),
      c.status,
      (c.providers || []).join(", "),
      String(c.total_input_tokens ?? 0),
      String(c.total_output_tokens ?? 0),
      fmtUsd(c.total_cost_usd),
    ];
    cells.forEach((text) => {
      const td = document.createElement("td");
      td.textContent = text;
      tr.appendChild(td);
    });
    tr.onclick = () => openCostDrilldown(c.call_id);
    tbody.appendChild(tr);
  });
  table.appendChild(tbody);
  box.appendChild(table);
}

function renderCostSummary(summary) {
  const box = $("cost-summary-panel");
  box.innerHTML = "";
  const rows = [
    ["Total cost", fmtUsd(summary.total_cost_usd)],
    ["Calls", String(summary.call_count)],
    ["Avg cost / call", fmtUsd(summary.avg_cost_per_call_usd)],
    ["OpenAI", fmtUsd(summary.openai_cost_usd)],
    ["ElevenLabs", fmtUsd(summary.elevenlabs_cost_usd)],
    ["Plivo", fmtUsd(summary.plivo_cost_usd)],
    ["Fixed (server)", fmtUsd(summary.fixed_cost_usd)],
  ];
  rows.forEach(([label, value]) => {
    const row = document.createElement("div");
    row.className = "cost-summary-row";
    const labelEl = document.createElement("span");
    labelEl.className = "cost-summary-label";
    labelEl.textContent = label;
    const valueEl = document.createElement("span");
    valueEl.className = "cost-summary-value";
    valueEl.textContent = value;
    row.append(labelEl, valueEl);
    box.appendChild(row);
  });
}

const BREAKDOWN_COLUMNS = [
  ["period", "Date"], ["call_count", "Calls"], ["openai_cost_usd", "OpenAI"],
  ["elevenlabs_cost_usd", "ElevenLabs"], ["plivo_cost_usd", "Plivo"],
  ["fixed_cost_usd", "Fixed"], ["total_cost_usd", "Total"],
];

async function loadCostBreakdownAndSummary() {
  const summaryBox = $("cost-summary-panel");
  const box = $("cost-breakdown-table");
  summaryBox.innerHTML = '<div class="empty">Loading…</div>';
  box.innerHTML = '<div class="empty">Loading…</div>';
  let data;
  try {
    const params = new URLSearchParams({
      group_by: costState.groupBy, start_date: costState.startDate, end_date: costState.endDate,
    });
    data = await api(`/cost/api/internal/costs/breakdown?${params}`);
  } catch (err) {
    renderEmpty(summaryBox, `Summary unavailable (${err.message}).`);
    renderEmpty(box, `Breakdown unavailable (${err.message}).`);
    return;
  }
  renderCostSummary(data.summary);
  const periods = data.periods || [];
  if (!periods.length) { renderEmpty(box, "No cost data in this range."); return; }
  box.innerHTML = "";
  const table = document.createElement("table");
  const thead = document.createElement("thead");
  const headRow = document.createElement("tr");
  BREAKDOWN_COLUMNS.forEach(([, label]) => {
    const th = document.createElement("th");
    th.textContent = label;
    headRow.appendChild(th);
  });
  thead.appendChild(headRow);
  table.appendChild(thead);
  const tbody = document.createElement("tbody");
  periods.slice().reverse().forEach((p) => {
    const tr = document.createElement("tr");
    tr.className = "cost-row";
    BREAKDOWN_COLUMNS.forEach(([key]) => {
      const td = document.createElement("td");
      if (key === "period") td.textContent = p.period;
      else if (key === "call_count") td.textContent = String(p.call_count);
      else td.textContent = fmtUsd(p[key]);
      tr.appendChild(td);
    });
    tr.onclick = () => {
      if (costState.groupBy !== "day") return;
      costState.range = "custom";
      costState.startDate = p.period;
      costState.endDate = p.period;
      document.querySelectorAll("#cost-date-presets .filter-btn").forEach((btn) =>
        btn.classList.toggle("active", btn.dataset.range === "custom"));
      $("cost-custom-range").classList.remove("hidden");
      $("cost-range-start").value = p.period;
      $("cost-range-end").value = p.period;
      refreshCostData();
    };
    tbody.appendChild(tr);
  });
  table.appendChild(tbody);
  box.appendChild(table);
}

async function openCostDrilldown(callId) {
  const panel = $("cost-drilldown");
  const body = $("cost-drilldown-body");
  panel.classList.remove("hidden");
  body.textContent = "Loading…";
  try {
    const detail = await api(`/cost/api/internal/calls/${encodeURIComponent(callId)}`);
    body.textContent = JSON.stringify(detail, null, 2);
  } catch (err) {
    body.textContent = `Unavailable: ${err.message}`;
  }
}
$("cost-drilldown-close").onclick = () => $("cost-drilldown").classList.add("hidden");
