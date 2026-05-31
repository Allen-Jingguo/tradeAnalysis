const state = {
  result: null,
  currentView: "trades",
  selectedTradeId: "",
  defaults: {},
};

const fields = {
  input: document.getElementById("input-source"),
  strategy: document.getElementById("strategy-source"),
  stock: document.getElementById("stock-source"),
  accountSize: document.getElementById("account-size"),
  overtradeCount: document.getElementById("overtrade-count"),
  imageForm: document.getElementById("image-form"),
  imageFile: document.getElementById("image-file"),
  imagePath: document.getElementById("image-path"),
  imageButton: document.getElementById("image-button"),
  importResult: document.getElementById("import-result"),
  sourceSummary: document.getElementById("source-summary"),
  imageSummary: document.getElementById("image-summary"),
  analysisTools: document.getElementById("analysis-tools"),
  imageTools: document.getElementById("image-tools"),
  form: document.getElementById("source-form"),
  status: document.getElementById("status-pill"),
  analyzeButton: document.getElementById("analyze-button"),
  metricsBand: document.getElementById("metrics-band"),
  tradeCount: document.getElementById("trade-count"),
  findingCount: document.getElementById("finding-count"),
  riskMeter: document.getElementById("risk-meter"),
  dataTable: document.getElementById("data-table"),
  selectedTrade: document.getElementById("selected-trade"),
  findingList: document.getElementById("finding-list"),
  recommendationList: document.getElementById("recommendation-list"),
};

const viewColumns = {
  trades: [
    ["timestamp", "时间"],
    ["code", "代码"],
    ["name", "名称"],
    ["side", "方向"],
    ["price", "价格"],
    ["quantity", "数量"],
    ["amount", "金额"],
    ["emotion", "情绪"],
    ["reason", "理由"],
    ["plan", "计划"],
  ],
  matched: [
    ["code", "代码"],
    ["name", "名称"],
    ["quantity", "数量"],
    ["buy_price", "买入"],
    ["sell_price", "卖出"],
    ["pnl", "盈亏"],
    ["pnl_pct", "盈亏%"],
    ["holding_days", "持有天数"],
  ],
  open: [
    ["code", "代码"],
    ["name", "名称"],
    ["quantity", "数量"],
    ["avg_cost", "成本"],
    ["amount", "金额"],
    ["first_buy_time", "首次买入"],
    ["stop_loss", "止损"],
    ["target_price", "目标"],
  ],
};

function formatNumber(value, digits = 2) {
  const number = Number(value);
  if (!Number.isFinite(number)) return "";
  return number.toLocaleString("zh-CN", {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  });
}

function formatCompact(value) {
  const number = Number(value);
  if (!Number.isFinite(number)) return "";
  return number.toLocaleString("zh-CN", { maximumFractionDigits: 2 });
}

function shortTime(value) {
  if (!value) return "";
  return String(value).replace("T", " ").slice(0, 16);
}

function setStatus(text, type = "") {
  fields.status.textContent = text;
  fields.status.className = `status-pill ${type}`.trim();
}

function severityTag(severity) {
  const level = Number(severity);
  const cls = level >= 4 ? "warn" : level >= 3 ? "info" : "buy";
  return `<span class="tag ${cls} severity">${level}/4</span>`;
}

function sideTag(side) {
  const value = String(side || "");
  const cls = value === "BUY" ? "buy" : "sell";
  const text = value === "BUY" ? "买入" : "卖出";
  return `<span class="tag ${cls}">${text}</span>`;
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function basename(value) {
  const text = String(value || "").trim();
  if (!text) return "未选择";
  return text.split(/[\\/]/).filter(Boolean).pop() || text;
}

function tradeAmount(trade) {
  return Number(trade.price || 0) * Number(trade.quantity || 0);
}

function metricItems(metrics) {
  return [
    ["已实现盈亏", formatNumber(metrics.realized_pnl), Number(metrics.realized_pnl) >= 0 ? "positive" : "negative"],
    ["胜率", `${formatNumber(metrics.win_rate)}%`, ""],
    ["Profit Factor", formatNumber(metrics.profit_factor), ""],
    ["最大单笔仓位", `${formatNumber(metrics.max_single_trade_pct)}%`, ""],
    ["策略一致率", `${formatNumber(metrics.strategy_alignment_rate)}%`, metrics.strategy_signal_count ? "" : "muted"],
    ["风险标的交易", formatCompact(metrics.stock_risk_trade_count), ""],
  ];
}

function renderMetrics() {
  const metrics = state.result.metrics;
  fields.metricsBand.innerHTML = metricItems(metrics).map(([label, value, cls]) => `
    <div class="metric-card">
      <div class="metric-label">${label}</div>
      <div class="metric-value ${cls}">${value}</div>
    </div>
  `).join("");

  const maxSeverity = Math.max(0, ...state.result.findings.map((item) => Number(item.severity || 0)));
  const riskClass = maxSeverity >= 4 ? "high" : maxSeverity >= 3 ? "medium" : "low";
  const riskText = maxSeverity >= 4 ? "高风险" : maxSeverity >= 3 ? "中风险" : "低风险";
  fields.riskMeter.className = `risk-meter ${riskClass}`;
  fields.riskMeter.textContent = riskText;
}

function dataForCurrentView() {
  if (state.currentView === "matched") return state.result.matched;
  if (state.currentView === "open") return state.result.open_positions;
  return state.result.trades.map((trade) => ({ ...trade, amount: tradeAmount(trade) }));
}

function cellValue(row, key) {
  const value = row[key];
  if (key === "timestamp" || key === "first_buy_time") return shortTime(value);
  if (key === "side") return sideTag(value);
  if (["price", "buy_price", "sell_price", "avg_cost", "amount", "pnl"].includes(key)) {
    const cls = key === "pnl" && Number(value) < 0 ? "negative" : "";
    return `<span class="${cls}">${formatNumber(value)}</span>`;
  }
  if (["pnl_pct", "holding_days", "stop_loss", "target_price"].includes(key)) return formatNumber(value);
  if (key === "quantity") return formatCompact(value);
  return escapeHtml(value);
}

function renderTable() {
  const rows = dataForCurrentView();
  const columns = viewColumns[state.currentView];
  fields.tradeCount.textContent = `${rows.length} 笔`;
  fields.dataTable.querySelector("thead").innerHTML = `<tr>${columns.map(([, label]) => `<th>${label}</th>`).join("")}</tr>`;
  fields.dataTable.querySelector("tbody").innerHTML = rows.map((row, index) => {
    const tradeId = row.trade_id || `${state.currentView}-${index}`;
    const selected = tradeId === state.selectedTradeId ? "selected" : "";
    return `
      <tr class="${selected}" data-trade-id="${escapeHtml(tradeId)}" data-index="${index}">
        ${columns.map(([key]) => `<td title="${escapeHtml(row[key] ?? "")}">${cellValue(row, key)}</td>`).join("")}
      </tr>
    `;
  }).join("");
}

function selectedTrade() {
  return state.result.trades.find((trade) => trade.trade_id === state.selectedTradeId) || null;
}

function findingRelatedToTrade(finding, trade) {
  if (!trade) return false;
  const text = `${finding.evidence || ""} ${finding.advice || ""} ${finding.title || ""}`;
  return text.includes(trade.code) || text.includes(trade.name);
}

function renderSelectedTrade() {
  const trade = selectedTrade();
  if (!trade) {
    fields.selectedTrade.innerHTML = `<div class="empty-state">选择一笔交易查看对应问题和建议</div>`;
    return;
  }

  const related = state.result.findings.filter((finding) => findingRelatedToTrade(finding, trade));
  fields.selectedTrade.innerHTML = `
    <div class="selected-title">
      <span>${escapeHtml(trade.code)} ${escapeHtml(trade.name)}</span>
      ${sideTag(trade.side)}
    </div>
    <div class="selected-grid">
      <div><span>成交时间</span>${shortTime(trade.timestamp)}</div>
      <div><span>成交金额</span>${formatNumber(tradeAmount(trade))}</div>
      <div><span>情绪</span>${escapeHtml(trade.emotion || "未记录")}</div>
      <div><span>关联问题</span>${related.length} 项</div>
      <div><span>理由</span>${escapeHtml(trade.reason || "未记录")}</div>
      <div><span>计划</span>${escapeHtml(trade.plan || "未记录")}</div>
    </div>
  `;
}

function renderFindings() {
  const trade = selectedTrade();
  fields.findingCount.textContent = `${state.result.findings.length} 项`;
  fields.findingList.innerHTML = state.result.findings.map((finding) => {
    const related = findingRelatedToTrade(finding, trade);
    return `
      <article class="finding-card ${related ? "related" : ""}">
        <div class="finding-head">
          <div class="finding-title">${escapeHtml(finding.title)}</div>
          ${severityTag(finding.severity)}
        </div>
        <div class="finding-body">
          <div>${escapeHtml(finding.evidence)}</div>
          <div class="finding-advice">${escapeHtml(finding.advice)}</div>
        </div>
      </article>
    `;
  }).join("") || `<div class="empty-state">暂无明显问题</div>`;
}

function renderRecommendations() {
  fields.recommendationList.innerHTML = state.result.recommendations.map((item) => `
    <article class="recommendation-card">
      <div class="recommendation-title">${escapeHtml(item.stage)}：${escapeHtml(item.title)}</div>
      <ul>${item.actions.map((action) => `<li>${escapeHtml(action)}</li>`).join("")}</ul>
    </article>
  `).join("");
}

function renderAll() {
  renderMetrics();
  renderTable();
  renderSelectedTrade();
  renderFindings();
  renderRecommendations();
}

function updateSourceSummary() {
  const tradeText = state.result ? `${state.result.metrics.trade_count} 笔交易` : "待分析";
  fields.sourceSummary.textContent = `${basename(fields.input.value)} · ${tradeText}`;
}

async function analyze() {
  setStatus("分析中");
  fields.analyzeButton.disabled = true;
  try {
    const response = await fetch("/api/analyze", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        input: fields.input.value,
        strategy: fields.strategy.value,
        stock: fields.stock.value,
        account_size: fields.accountSize.value,
        overtrade_daily_count: fields.overtradeCount.value,
      }),
    });
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.error || "分析失败");
    state.result = payload.result;
    state.selectedTradeId = state.result.trades[0]?.trade_id || "";
    renderAll();
    updateSourceSummary();
    fields.analysisTools.open = false;
    setStatus("已完成", "ready");
  } catch (error) {
    setStatus("出错", "error");
    fields.findingList.innerHTML = `<div class="empty-state">${escapeHtml(error.message)}</div>`;
  } finally {
    fields.analyzeButton.disabled = false;
  }
}

function fileToDataUrl(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result);
    reader.onerror = () => reject(reader.error || new Error("读取图片失败"));
    reader.readAsDataURL(file);
  });
}

function showImportResult(html) {
  fields.importResult.classList.add("active");
  fields.importResult.innerHTML = html;
}

async function importImage() {
  setStatus("识别中");
  fields.imageButton.disabled = true;
  showImportResult("正在识别图片...");
  try {
    const file = fields.imageFile.files[0];
    const body = file
      ? { filename: file.name, data_url: await fileToDataUrl(file) }
      : { image_path: fields.imagePath.value };

    const response = await fetch("/api/import-image", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.error || "图片识别失败");

    fields.input.value = payload.csv_path;
    if (fields.strategy.value === state.defaults.strategy) fields.strategy.value = "";
    if (fields.stock.value === state.defaults.stock) fields.stock.value = "";

    const skipped = payload.skipped_count ? `，跳过 ${payload.skipped_count} 条未成交或不完整记录` : "";
    showImportResult(`<strong>已识别 ${payload.imported_count} 条成交记录</strong>${skipped}。OCR：${escapeHtml(payload.engine)}。`);
    fields.imageSummary.textContent = `已识别 ${payload.imported_count} 条 · 跳过 ${payload.skipped_count} 条`;
    await analyze();
    fields.imageTools.open = false;
  } catch (error) {
    setStatus("出错", "error");
    showImportResult(escapeHtml(error.message));
  } finally {
    fields.imageButton.disabled = false;
  }
}

async function loadDefaults() {
  const response = await fetch("/api/defaults");
  const defaults = await response.json();
  state.defaults = defaults;
  fields.input.value = defaults.input;
  fields.strategy.value = defaults.strategy;
  fields.stock.value = defaults.stock;
  fields.imagePath.value = defaults.image || "";
  fields.sourceSummary.textContent = basename(defaults.input);
  fields.imageSummary.textContent = defaults.image ? basename(defaults.image) : "上传或输入本地截图路径";
  fields.accountSize.value = defaults.account_size;
  fields.overtradeCount.value = defaults.overtrade_daily_count;
  await analyze();
}

fields.form.addEventListener("submit", (event) => {
  event.preventDefault();
  analyze();
});

fields.imageForm.addEventListener("submit", (event) => {
  event.preventDefault();
  importImage();
});

document.querySelectorAll(".segment").forEach((button) => {
  button.addEventListener("click", () => {
    document.querySelectorAll(".segment").forEach((item) => item.classList.remove("active"));
    button.classList.add("active");
    state.currentView = button.dataset.view;
    renderTable();
  });
});

fields.dataTable.addEventListener("click", (event) => {
  const row = event.target.closest("tr[data-trade-id]");
  if (!row || state.currentView !== "trades") return;
  state.selectedTradeId = row.dataset.tradeId;
  renderTable();
  renderSelectedTrade();
  renderFindings();
});

loadDefaults();
