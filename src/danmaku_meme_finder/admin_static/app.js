const app = {
  state: null,
  candidateIndex: 0,
  selectedTags: new Set(),
  documentKey: null,
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
  }
}

function render() {
  renderMetrics();
  renderCandidate();
  renderDocuments();
}

function renderMetrics() {
  const counts = app.state?.counts || {};
  const values = [
    ["待审核", counts.pending || 0],
    ["正式梗", counts.approved || 0],
    ["本地不通过", counts.rejected || 0],
    ["直播场次", counts.sessions || 0],
    ["月报", counts.reports || 0],
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
  $("#candidate-source").textContent = hasCandidate ? sourceLabel(candidate.source) : "完成";
  $("#candidate-text").textContent = hasCandidate ? candidate.text : "当前没有尚未审核的候选。";
  $("#candidate-facts").innerHTML = hasCandidate
    ? `<span><strong>${candidate.count || 0}</strong>次出现</span><span><strong>${candidate.uniqueUsers || 0}</strong>位独立用户</span><span>最近 ${formatDate(candidate.lastSeenAt)}</span>`
    : "";
  $("#approve-button").disabled = !hasCandidate;
  $("#reject-button").disabled = !hasCandidate;
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

async function createReport() {
  const month = window.prompt("输入月份（YYYY-MM）", new Date().toISOString().slice(0, 7));
  if (!month) return;
  if (!/^\d{4}-\d{2}$/.test(month)) {
    toast("月份格式应为 YYYY-MM", true);
    return;
  }
  const year = month.slice(0, 4);
  const monthNumber = Number(month.slice(5));
  const payload = {
    schemaVersion: 1,
    id: `monthly-${month}`,
    month,
    title: `${year}年${monthNumber}月总结`,
    publishedAt: `${month}-01`,
    startDate: `${month}-01`,
    endDate: `${month}-01`,
    coverUrl: `/covers/reports/${month}.png`,
    summary: "",
    sessionCount: 0,
    memeCount: 0,
    barrageCount: 0,
    eventTitles: [],
    topTagCodes: [],
    sections: [{ heading: "本月概览", paragraphs: [""] }],
  };
  setBusy(true);
  try {
    const result = await request("/api/documents", {
      method: "POST",
      body: JSON.stringify({ key: `report:${month}`, payload }),
    });
    app.state = result.state;
    app.documentKey = `report:${month}`;
    render();
    switchView("content");
    toast("月报草稿和索引已创建");
  } catch (error) {
    toast(error.message, true);
  } finally {
    setBusy(false);
  }
}

async function publish() {
  if (!window.confirm("将重建活跃目录、月度归档和趋势摘要，并推送到 GitHub。继续吗？")) return;
  setBusy(true);
  $("#publish-result").textContent = "正在重建目录并推送……";
  try {
    const result = await request("/api/publish", { method: "POST", body: "{}" });
    app.state = result.state;
    render();
    $("#publish-result").textContent = `${result.message}；目录共 ${Number(result.catalogItems).toLocaleString("zh-CN")} 条。`;
    toast(result.published ? "GitHub 发布完成" : "公开数据没有变化");
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

function sourceLabel(source) {
  return source === "high_frequency" ? "高频候选" : source === "long_text" ? "长文本候选" : source || "候选";
}
function formatDate(value) { return typeof value === "string" ? value.slice(0, 16).replace("T", " ") : "未知"; }
function escapeHtml(value) { return String(value).replace(/[&<>'"]/g, (char) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;" })[char]); }

$$(`.nav-item`).forEach((button) => button.addEventListener("click", () => switchView(button.dataset.view)));
$("#refresh-button").addEventListener("click", loadState);
$("#approve-button").addEventListener("click", () => review("approve"));
$("#reject-button").addEventListener("click", () => review("reject"));
$("#skip-button").addEventListener("click", skipCandidate);
$("#save-document-button").addEventListener("click", saveDocument);
$("#new-report-button").addEventListener("click", createReport);
$("#publish-button").addEventListener("click", publish);
window.addEventListener("keydown", (event) => {
  if (["INPUT", "TEXTAREA"].includes(document.activeElement?.tagName)) return;
  if (!$("#review-view").classList.contains("active")) return;
  if (event.key === "Enter") review("approve");
  if (event.key.toLowerCase() === "x") review("reject");
  if (event.key.toLowerCase() === "s") skipCandidate();
});

loadState();
