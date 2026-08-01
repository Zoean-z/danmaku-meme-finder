const app = {
  state: null,
  candidateIndex: 0,
  selectedTags: new Set(),
  documentKey: null,
  collectionTimer: null,
};

const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => [...document.querySelectorAll(selector)];

async function request(path, options = {}) {
  const response = await fetch(path, {
    ...options,
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
  });
  const payload = await response.json();
  if (!response.ok) throw new Error(payload.error || `请求失败：${response.status}`);
  return payload;
}

async function loadState() {
  setBusy(true);
  try {
    app.state = await request("/api/state");
    app.candidateIndex = Math.min(app.candidateIndex, Math.max(0, app.state.queue.length - 1));
    render();
  } catch (error) {
    toast(error.message, true);
  } finally {
    setBusy(false);
    renderCollection();
  }
}

function render() {
  renderMetrics();
  renderCollection();
  renderCandidate();
  renderDocuments();
}

function renderCollection() {
  const state = app.state?.collection || { phase: "idle", active: false };
  const labels = {
    idle: "当前未运行",
    running: "正在采集弹幕",
    stopping: "正在停止并落库",
    stopped: "已手动停止",
    completed: "采集已完成",
    failed: "采集失败",
  };
  $("#collection-status-title").textContent = labels[state.phase] || state.phase;
  $("#collection-status-dot").className = `collection-status-dot ${state.active ? "active" : state.phase}`;
  $("#collection-badge").textContent = state.active ? "运行中" : state.phase === "failed" ? "失败" : "待机";
  $("#collection-session").textContent = state.sessionId || "—";
  $("#collection-imported").textContent = Number(state.importedMessages || 0).toLocaleString("zh-CN");
  $("#collection-candidates").textContent = state.candidateCount == null ? "—" : Number(state.candidateCount).toLocaleString("zh-CN");
  $("#collection-elapsed").textContent = collectionElapsed(state);
  $("#collection-message").textContent = state.error || (state.active
    ? "采集器正在本机运行；页面会自动刷新导入数量。停止后才会生成最终候选。"
    : "开始后会运行现有 Node 采集器，并每 5 秒批量导入 SQLite。停止时会安全写入剩余弹幕并生成最多 20 条候选。");
  $("#start-collection-button").disabled = Boolean(state.active);
  $("#stop-collection-button").disabled = !state.active || state.phase === "stopping";
  scheduleCollectionPoll(Boolean(state.active));
}

function collectionElapsed(state) {
  if (!state.startedAt) return "—";
  const end = state.active ? Date.now() : Date.parse(state.finishedAt || state.startedAt);
  const seconds = Math.max(0, Math.floor((end - Date.parse(state.startedAt)) / 1000));
  const minutes = Math.floor(seconds / 60);
  return `${String(minutes).padStart(2, "0")}:${String(seconds % 60).padStart(2, "0")}`;
}

function scheduleCollectionPoll(active) {
  if (!active) {
    clearTimeout(app.collectionTimer);
    app.collectionTimer = null;
    return;
  }
  if (app.collectionTimer) return;
  app.collectionTimer = setTimeout(async () => {
    app.collectionTimer = null;
    try {
      const result = await request("/api/collection");
      app.state.collection = result.collection;
      renderCollection();
      if (!result.collection.active) await loadState();
    } catch (error) {
      toast(error.message, true);
    }
  }, 2000);
}

async function startCollection() {
  const rawDuration = $("#collection-duration").value.trim();
  const minutes = rawDuration ? Number(rawDuration) : null;
  if (minutes != null && (!Number.isInteger(minutes) || minutes < 1 || minutes > 720)) {
    toast("采集时长必须是 1 到 720 分钟的整数", true);
    return;
  }
  setBusy(true);
  try {
    const result = await request("/api/collection/start", {
      method: "POST",
      body: JSON.stringify({ durationSeconds: minutes == null ? null : minutes * 60 }),
    });
    app.state.collection = result.collection;
    renderCollection();
    toast("弹幕采集已启动");
  } catch (error) {
    toast(error.message, true);
  } finally {
    setBusy(false);
    renderCollection();
  }
}

async function stopCollection() {
  setBusy(true);
  try {
    const result = await request("/api/collection/stop", { method: "POST", body: "{}" });
    app.state.collection = result.collection;
    renderCollection();
    toast("正在停止，剩余弹幕会继续落库");
  } catch (error) {
    toast(error.message, true);
  } finally {
    setBusy(false);
    renderCollection();
  }
}

function renderMetrics() {
  const counts = app.state?.counts || {};
  const values = [
    ["待审核", counts.pending || 0],
    ["正式梗", counts.approved || 0],
    ["本地不通过", counts.rejected || 0],
    ["直播场次", counts.sessions || 0],
  ];
  $("#metrics").innerHTML = values.map(([label, value]) => `<div class="metric"><span>${label}</span><strong>${Number(value).toLocaleString("zh-CN")}</strong></div>`).join("");
  $("#pending-badge").textContent = counts.pending || 0;
  $("#context-total").textContent = counts.candidates || 0;
  $("#context-pending").textContent = counts.pending || 0;
  $("#context-approved").textContent = counts.approved || 0;
}

function renderCandidate() {
  const queue = app.state?.queue || [];
  const candidate = queue[app.candidateIndex];
  const hasCandidate = Boolean(candidate);
  $("#candidate-progress").textContent = hasCandidate ? `${app.candidateIndex + 1} / ${queue.length}` : "队列已清空";
  $("#candidate-source").textContent = hasCandidate ? "候选" : "完成";
  $("#candidate-text").textContent = hasCandidate ? candidate.text : "当前没有尚未审核的候选。";
  $("#candidate-facts").innerHTML = hasCandidate
    ? `<span><strong>${candidate.count || 0}</strong>次出现</span><span><strong>${candidate.uniqueUsers || 0}</strong>位独立用户</span><span>最近 ${formatDate(candidate.lastSeenAt)}</span>`
    : "";
  $("#approve-button").disabled = !hasCandidate;
  $("#reject-button").disabled = !hasCandidate;
  $("#reject-similar-button").disabled = !hasCandidate;
  $("#skip-button").disabled = queue.length < 2;
  const tags = app.state?.tags || {};
  $("#tag-list").innerHTML = Object.entries(tags).sort(([a], [b]) => a.localeCompare(b)).map(([code, label]) =>
    `<button class="tag-button ${app.selectedTags.has(code) ? "selected" : ""}" data-tag="${escapeHtml(code)}"><code>${escapeHtml(code)}</code>${escapeHtml(label)}</button>`
  ).join("");
  $$(".tag-button").forEach((button) => button.addEventListener("click", () => toggleTag(button.dataset.tag)));
}

function renderDocuments() {
  const documents = app.state?.documents || [];
  if (!documents.length) return;
  if (!app.documentKey || !documents.some((item) => item.key === app.documentKey)) app.documentKey = documents[0].key;
  $("#document-list").innerHTML = documents.map((document) =>
    `<button class="document-button ${document.key === app.documentKey ? "active" : ""}" data-document="${escapeHtml(document.key)}">${escapeHtml(document.label)}</button>`
  ).join("");
  $$(".document-button").forEach((button) => button.addEventListener("click", () => selectDocument(button.dataset.document)));
  showDocument(app.documentKey, false);
}

function selectDocument(key) {
  app.documentKey = key;
  $$(".document-button").forEach((button) => button.classList.toggle("active", button.dataset.document === key));
  showDocument(key, true);
}

function showDocument(key, replaceEditor) {
  const document = app.state.documents.find((item) => item.key === key);
  if (!document) return;
  $("#document-key").textContent = document.key;
  $("#document-title").textContent = document.label;
  if (replaceEditor || !$("#document-editor").value) {
    $("#document-editor").value = JSON.stringify(document.payload, null, 2);
  }
}

function toggleTag(code) {
  if (app.selectedTags.has(code)) app.selectedTags.delete(code);
  else app.selectedTags.add(code);
  renderCandidate();
}

async function review(decision) {
  const candidate = app.state?.queue?.[app.candidateIndex];
  if (!candidate) return;
  if (decision === "approve" && app.selectedTags.size === 0) {
    toast("通过前至少选择一个标签", true);
    return;
  }
  setBusy(true);
  try {
    const result = await request("/api/review", {
      method: "POST",
      body: JSON.stringify({ key: candidate.normalizedText || candidate.text, decision, tags: [...app.selectedTags] }),
    });
    app.state = result.state;
    app.candidateIndex = Math.min(app.candidateIndex, Math.max(0, app.state.queue.length - 1));
    app.selectedTags.clear();
    render();
    toast(decision === "approve" ? `已收录为 #${result.catalogId}` : "已标记为不通过，仅保存在本地");
  } catch (error) {
    toast(error.message, true);
  } finally {
    setBusy(false);
  }
}

function skipCandidate() {
  const length = app.state?.queue?.length || 0;
  if (length < 2) return;
  app.candidateIndex = (app.candidateIndex + 1) % length;
  app.selectedTags.clear();
  renderCandidate();
}

async function saveDocument() {
  if (!app.documentKey) return;
  let payload;
  try {
    payload = JSON.parse($("#document-editor").value);
  } catch (error) {
    toast(`JSON 格式错误：${error.message}`, true);
    return;
  }
  setBusy(true);
  try {
    const result = await request("/api/documents", {
      method: "POST",
      body: JSON.stringify({ key: app.documentKey, payload }),
    });
    app.state = result.state;
    render();
    toast("已原子保存到本地文件");
  } catch (error) {
    toast(error.message, true);
  } finally {
    setBusy(false);
  }
}

function managedDocument(key) {
  return app.state?.documents?.find((item) => item.key === key)?.payload;
}

function uniqueId(records, preferred) {
  const used = new Set(records.map((record) => record?.id).filter(Boolean));
  if (!used.has(preferred)) return preferred;
  let suffix = 2;
  while (used.has(`${preferred}-${suffix}`)) suffix += 1;
  return `${preferred}-${suffix}`;
}

async function saveCreatedRecord(key, payload, message) {
  setBusy(true);
  try {
    const result = await request("/api/documents", {
      method: "POST",
      body: JSON.stringify({ key, payload }),
    });
    app.state = result.state;
    app.documentKey = key;
    render();
    switchView("content");
    selectDocument(key);
    toast(message);
  } catch (error) {
    toast(error.message, true);
  } finally {
    setBusy(false);
  }
}

async function createEvent() {
  const title = window.prompt("赛事名称");
  if (!title?.trim()) return;
  const today = new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Shanghai" }).format(new Date());
  const startDate = window.prompt("开始日期（YYYY-MM-DD）", today);
  if (!startDate) return;
  const endDate = window.prompt("结束日期（YYYY-MM-DD）", startDate);
  if (!endDate) return;
  const document = structuredClone(managedDocument("events") || { schemaVersion: 1, events: [] });
  const preferredId = `event-${startDate}`;
  const id = window.prompt("赛事编号", uniqueId(document.events, preferredId));
  if (!id?.trim()) return;
  document.events.push({
    id: id.trim(),
    title: title.trim(),
    startDate,
    endDate,
    coverUrl: `/covers/events/${id.trim()}.png`,
    teams: [],
    streamTitle: title.trim(),
  });
  await saveCreatedRecord("events", document, "赛事已创建，可继续编辑封面和参赛队伍");
}

async function createSession() {
  const today = new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Shanghai" }).format(new Date());
  const date = window.prompt("直播日期（YYYY-MM-DD）", today);
  if (!date) return;
  const title = window.prompt("直播标题", `直播收录 · ${date}`);
  if (!title?.trim()) return;
  const document = structuredClone(managedDocument("sessions") || { schemaVersion: 1, sessions: [] });
  const preferredId = `6657-${date.replaceAll("-", "")}-manual`;
  const id = window.prompt("场次编号", uniqueId(document.sessions, preferredId));
  if (!id?.trim()) return;
  document.sessions.push({
    id: id.trim(),
    date,
    title: title.trim(),
    coverUrl: `/covers/sessions/${date}.png`,
    summary: "",
    memeCount: 0,
    barrageCount: 0,
    messageCount: 0,
    roomId: 6657,
    sourceUrl: "https://www.douyu.com/6657",
    observedStartedAt: null,
    observedEndedAt: null,
    tagCodes: [],
  });
  await saveCreatedRecord("sessions", document, "直播场次已创建；采集产生的场次仍会自动写入");
}

async function publish() {
  if (!window.confirm("将重建公开目录并推送到 GitHub。发布成功后，会清理本轮已审核场次的本地 JSONL 和 SQLite 原始弹幕；未审核或正在采集的数据不会删除。继续吗？")) return;
  setBusy(true);
  $("#publish-result").textContent = "正在重建目录并推送……";
  try {
    const result = await request("/api/publish", { method: "POST", body: "{}" });
    app.state = result.state;
    render();
    const cleanup = result.cleanup || {};
    const removed = Number(cleanup.databaseMessagesRemoved || 0).toLocaleString("zh-CN");
    $("#publish-result").textContent = `${result.message}；目录共 ${Number(result.catalogItems).toLocaleString("zh-CN")} 条；已清理 ${removed} 条本地原始弹幕。`;
    toast(result.published ? "GitHub 发布与本地清理完成" : "公开数据未变化；本地清理完成");
  } catch (error) {
    $("#publish-result").textContent = error.message;
    toast(error.message, true);
  } finally {
    setBusy(false);
  }
}

function switchView(view) {
  $$(".nav-item").forEach((button) => button.classList.toggle("active", button.dataset.view === view));
  $$(".view").forEach((section) => section.classList.toggle("active", section.id === `${view}-view`));
  const copy = {
    collection: ["本机采集", "开始一次新的弹幕采集"],
    review: ["审核队列", "把值得保留的弹幕挑出来"],
    content: ["内容数据", "维护网站真正读取的文件"],
    publish: ["发布中心", "检查并更新公开数据"],
  }[view];
  $("#eyebrow").textContent = copy[0];
  $("#page-title").textContent = copy[1];
}

function setBusy(busy) {
  document.body.classList.toggle("busy", busy);
  $$(`button`).forEach((button) => {
    if (busy) button.dataset.wasDisabled = String(button.disabled);
    button.disabled = busy || button.dataset.wasDisabled === "true";
    if (!busy) delete button.dataset.wasDisabled;
  });
}

let toastTimer;
function toast(message, error = false) {
  const element = $("#toast");
  element.textContent = message;
  element.classList.toggle("error", error);
  element.classList.add("visible");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => element.classList.remove("visible"), 2600);
}

function formatDate(value) { return typeof value === "string" ? value.slice(0, 16).replace("T", " ") : "未知"; }
function escapeHtml(value) { return String(value).replace(/[&<>'"]/g, (char) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;" })[char]); }

$$(`.nav-item`).forEach((button) => button.addEventListener("click", () => switchView(button.dataset.view)));
$("#refresh-button").addEventListener("click", loadState);
$("#start-collection-button").addEventListener("click", startCollection);
$("#stop-collection-button").addEventListener("click", stopCollection);
$("#approve-button").addEventListener("click", () => review("approve"));
$("#reject-button").addEventListener("click", () => review("reject"));
$("#reject-similar-button").addEventListener("click", () => review("reject_similar"));
$("#skip-button").addEventListener("click", skipCandidate);
$("#save-document-button").addEventListener("click", saveDocument);
$("#new-event-button").addEventListener("click", createEvent);
$("#new-session-button").addEventListener("click", createSession);
$("#publish-button").addEventListener("click", publish);
window.addEventListener("keydown", (event) => {
  if (["INPUT", "TEXTAREA"].includes(document.activeElement?.tagName)) return;
  if (!$("#review-view").classList.contains("active")) return;
  if (event.key === "Enter") review("approve");
  if (event.key.toLowerCase() === "x") review("reject");
  if (event.key.toLowerCase() === "b") review("reject_similar");
  if (event.key.toLowerCase() === "s") skipCandidate();
});

loadState();
