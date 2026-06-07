const state = {
  result: null,
  currentView: "trades",
  analysisView: "trade",
  selectedTradeId: "",
  pendingImageImport: null,
  defaults: {},
  tradePage: 0,        // index into tradeDays (0 = most recent day)
  windowDays: [],      // 5-trading-day window used for analysis
};

const fields = {
  input: document.getElementById("input-source"),
  strategy: document.getElementById("strategy-source"),
  stock: document.getElementById("stock-source"),
  accountSize: document.getElementById("account-size"),
  overtradeCount: document.getElementById("overtrade-count"),
  clearButton: document.getElementById("clear-button"),
  clearConfirm: document.getElementById("clear-confirm"),
  cancelClear: document.getElementById("cancel-clear"),
  confirmClear: document.getElementById("confirm-clear"),
  imageFile: document.getElementById("image-file"),
  imagePath: document.getElementById("image-path"),
  imageAgent: document.getElementById("image-agent"),
  imageButton: document.getElementById("image-button"),
  imageConfirm: document.getElementById("image-confirm"),
  imageConfirmMessage: document.getElementById("image-confirm-message"),
  cancelImageImport: document.getElementById("cancel-image-import"),
  confirmImageImport: document.getElementById("confirm-image-import"),
  importResult: document.getElementById("import-result"),
  imageMain: document.getElementById("image-main"),
  imageSummary: document.getElementById("image-summary"),
  sourceMain: document.getElementById("source-main"),
  sourceStatus: document.getElementById("source-status"),
  sourceDrawer: document.getElementById("source-drawer"),
  toggleSource: document.getElementById("toggle-source"),
  form: document.getElementById("source-form"),
  status: document.getElementById("status-pill"),
  analyzeButton: document.getElementById("analyze-button"),
  metricsBand: document.getElementById("metrics-band"),
  tradeCount: document.getElementById("trade-count"),
  findingCount: document.getElementById("finding-count"),
  riskMeter: document.getElementById("risk-meter"),
  heroCard: document.getElementById("hero-card"),
  heroShield: document.getElementById("hero-shield"),
  heroTitle: document.getElementById("hero-title"),
  heroSub: document.getElementById("hero-sub"),
  heroAdviceText: document.getElementById("hero-advice-text"),
  dataTable: document.getElementById("data-table"),
  selectedTrade: document.getElementById("selected-trade"),
  findingSummary: document.getElementById("finding-summary"),
  findingList: document.getElementById("finding-list"),
  recommendationList: document.getElementById("recommendation-list"),
  liveAnalysis: document.getElementById("live-analysis"),
};

const viewColumns = {
  trades: [
    ["timestamp","时间"],["code","代码"],["name","名称"],["side","方向"],
    ["price","价格"],["quantity","数量"],["amount","金额"],["emotion","情绪"],["reason","理由"],
  ],
  matched: [
    ["code","代码"],["name","名称"],["quantity","数量"],
    ["buy_price","买入"],["sell_price","卖出"],["pnl","盈亏"],["pnl_pct","盈亏%"],["holding_days","持有天数"],
  ],
  open: [
    ["code","代码"],["name","名称"],["quantity","数量"],["avg_cost","成本"],
    ["amount","金额"],["first_buy_time","首次买入"],["stop_loss","止损"],["target_price","目标"],
  ],
};

function formatNumber(value, digits = 2) {
  const n = Number(value);
  if (!Number.isFinite(n)) return "";
  return n.toLocaleString("zh-CN", { minimumFractionDigits: digits, maximumFractionDigits: digits });
}
function formatCompact(value) {
  const n = Number(value);
  if (!Number.isFinite(n)) return "";
  return n.toLocaleString("zh-CN", { maximumFractionDigits: 2 });
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
  const cls = value === "BUY" ? "badge-buy" : "badge-sell";
  const text = value === "BUY" ? "买入" : "卖出";
  return `<span class="badge ${cls}">${text}</span>`;
}
function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&","&amp;").replaceAll("<","&lt;").replaceAll(">","&gt;")
    .replaceAll('"',"&quot;").replaceAll("'","&#039;");
}
function basename(value) {
  const text = String(value || "").trim();
  if (!text) return "未选择";
  return text.split(/[\\/]/).filter(Boolean).pop() || text;
}
function tradeAmount(trade) {
  return Number(trade.price || 0) * Number(trade.quantity || 0);
}

function emptyResult() {
  return {
    trades: [], matched: [], open_positions: [], strategy_signals: [], stock_profiles: [],
    findings: [], recommendations: [],
    metrics: { trade_count:0, matched_count:0, open_position_count:0, strategy_signal_count:0,
      strategy_alignment_rate:0, stock_risk_trade_count:0, realized_pnl:0,
      win_rate:0, profit_factor:0, max_single_trade_pct:0 },
  };
}

// ── Hero Summary ──
function renderHero() {
  const { findings, metrics } = state.result;
  const maxSev = Math.max(0, ...findings.map(f => Number(f.severity || 0)));
  const isHigh = maxSev >= 4, isMed = maxSev >= 3;

  const riskText = isHigh ? "高风险" : isMed ? "中风险" : "低风险";
  fields.heroCard.className = `card hero-card${(!isHigh && !isMed) ? " safe" : ""}`;
  fields.heroShield.textContent = isHigh ? "!" : isMed ? "▲" : "✓";
  fields.heroTitle.innerHTML = `当前复盘：<span>${riskText}</span>`;

  const parts = [];
  if (findings.length) parts.push(`${findings.length} 项发现`);
  if (metrics.stock_risk_trade_count) parts.push(`${metrics.stock_risk_trade_count} 笔风险交易`);
  if (metrics.strategy_signal_count) parts.push(`策略一致率 ${formatNumber(metrics.strategy_alignment_rate)}%`);
  fields.heroSub.textContent = parts.join(" · ") || "上传截图或选择数据源后点击分析";

  const topFinding = findings[0];
  fields.heroAdviceText.textContent = topFinding ? topFinding.advice.slice(0, 40) + (topFinding.advice.length > 40 ? "…" : "") : "—";
}

// ── Metrics ──
const METRIC_DEFS = [
  { key: "realized_pnl",           label: "已实现盈亏",  icon: "↗", bg: "bg-green",  fmt: v => formatNumber(v),               cls: v => Number(v)>=0?"positive":"negative", help: () => "" },
  { key: "win_rate",               label: "胜率",        icon: "◎", bg: "bg-blue",   fmt: v => `${formatNumber(v)}%`,         cls: () => "", help: (m) => `${m.matched_count||0} 笔配对` },
  { key: "profit_factor",          label: "Profit Factor",icon:"◴",bg: "bg-purple",  fmt: v => formatNumber(v),               cls: () => "", help: () => "总盈利 / 总亏损" },
  { key: "max_single_trade_pct",   label: "最大单笔仓位",icon: "◷", bg: "bg-orange", fmt: v => `${formatNumber(v)}%`,         cls: v => Number(v)>30?"text-orange":"", help: v => Number(v)>30?"超 30% 建议控制":"" },
  { key: "strategy_alignment_rate",label: "策略一致率",  icon: "☷", bg: "bg-teal",   fmt: v => `${formatNumber(v)}%`,         cls: () => "", help: (m) => m.strategy_signal_count ? (Number(m.strategy_alignment_rate)<60?"中等偏低":"") : "无策略信号" },
  { key: "stock_risk_trade_count", label: "风险交易",    icon: "△", bg: "bg-red",    fmt: v => formatCompact(v),              cls: v => Number(v)>0?"text-red":"", help: (m) => m.trade_count ? `占比 ${formatNumber(Number(m.stock_risk_trade_count)/m.trade_count*100)}%` : "" },
];

function renderMetrics() {
  const m = state.result.metrics;
  fields.metricsBand.innerHTML = METRIC_DEFS.map(def => {
    const rawVal = m[def.key];
    const val = def.fmt(rawVal);
    const cls = typeof def.cls === "function" ? def.cls(rawVal) : def.cls;
    const help = typeof def.help === "function" ? def.help(m) : def.help;
    return `<div class="card metric-card">
      <div class="metric-icon ${def.bg}">${def.icon}</div>
      <div>
        <div class="metric-label">${def.label}</div>
        <div class="metric-value ${cls}">${val}</div>
        ${help ? `<div class="metric-help ${cls}">${help}</div>` : ""}
      </div>
    </div>`;
  }).join("");

  const maxSev = Math.max(0, ...state.result.findings.map(f => Number(f.severity || 0)));
  const riskClass = maxSev >= 4 ? "high" : maxSev >= 3 ? "medium" : "low";
  const riskText  = maxSev >= 4 ? "▲ 高风险" : maxSev >= 3 ? "▲ 中风险" : "● 低风险";
  fields.riskMeter.className = `risk-badge ${riskClass}`;
  fields.riskMeter.textContent = riskText;
}

// ── Trading day pagination ──
function dateKey(ts) {
  return String(ts || "").slice(0, 10); // "YYYY-MM-DD"
}

// Returns unique trading days sorted descending (most recent first)
function getTradeDays() {
  const days = [...new Set(state.result.trades.map(t => dateKey(t.timestamp)))];
  return days.filter(Boolean).sort().reverse();
}

// Given an anchor day index and all days (sorted desc), return 5 consecutive
// trading days ending at that anchor (i.e. the window includes the anchor day
// plus up to 4 earlier trading days). Skips weekends by definition because
// only days that actually have trades are included.
function getWindowDays(allDays, anchorIdx) {
  // allDays is sorted descending; window = 5 days starting from anchorIdx
  return allDays.slice(anchorIdx, anchorIdx + 5);
}

function initPagination() {
  state.tradePage = 0;
  const allDays = getTradeDays();
  state.windowDays = getWindowDays(allDays, 0);
}

// ── Table ──
function dataForCurrentView() {
  if (state.currentView === "matched") return state.result.matched;
  if (state.currentView === "open") return state.result.open_positions;
  const allTrades = state.result.trades.map(t => ({ ...t, amount: tradeAmount(t) }));
  // For trades view: show only current page's day, sorted descending by timestamp
  const allDays = getTradeDays();
  if (!allDays.length) return allTrades;
  const day = allDays[state.tradePage];
  return allTrades
    .filter(t => dateKey(t.timestamp) === day)
    .sort((a, b) => String(b.timestamp).localeCompare(String(a.timestamp)));
}

function emotionClass(text) {
  const s = String(text||"").toLowerCase();
  if (["报复","恐惧","害怕","怕亏"].some(k => s.includes(k))) return "emotion-danger";
  if (["焦虑","贪婪","追高","踏空","fomo"].some(k => s.includes(k))) return "emotion-warning";
  return "";
}

function cellValue(row, key) {
  const value = row[key];
  if (key === "timestamp" || key === "first_buy_time") return shortTime(value);
  if (key === "side") return sideTag(value);
  if (["price","buy_price","sell_price","avg_cost","amount","pnl"].includes(key)) {
    const cls = key === "pnl" && Number(value) < 0 ? "negative" : "";
    return `<span class="${cls}">${formatNumber(value)}</span>`;
  }
  if (["pnl_pct","holding_days","stop_loss","target_price"].includes(key)) return formatNumber(value);
  if (key === "quantity") return formatCompact(value);
  if (key === "emotion") {
    const cls = emotionClass(value);
    return cls ? `<span class="${cls}">${escapeHtml(value)}</span>` : escapeHtml(value);
  }
  return escapeHtml(value);
}

function renderTable() {
  const rows = dataForCurrentView();
  const columns = viewColumns[state.currentView];

  // Pagination bar (trades view only)
  let paginationHtml = "";
  if (state.currentView === "trades") {
    const allDays = getTradeDays();
    const total = allDays.length;
    const cur = state.tradePage;
    const day = allDays[cur] || "";
    fields.tradeCount.textContent = `${day} · ${rows.length} 笔`;
    if (total > 1) {
      paginationHtml = `<div class="table-pagination">
        <button class="page-btn" id="page-prev" ${cur >= total-1 ? "disabled" : ""}>‹ 前一天</button>
        <span class="page-info">${day} (第 ${cur+1}/${total} 天)</span>
        <button class="page-btn" id="page-next" ${cur === 0 ? "disabled" : ""}>后一天 ›</button>
      </div>`;
    }
  } else {
    fields.tradeCount.textContent = `${rows.length} 笔`;
  }

  fields.dataTable.querySelector("thead").innerHTML =
    `<tr>${columns.map(([,label]) => `<th>${label}</th>`).join("")}</tr>`;
  fields.dataTable.querySelector("tbody").innerHTML = rows.map((row, index) => {
    const tradeId = row.trade_id || `${state.currentView}-${index}`;
    const selected = tradeId === state.selectedTradeId ? "selected" : "";
    return `<tr class="${selected}" data-trade-id="${escapeHtml(tradeId)}" data-index="${index}">
      ${columns.map(([key]) => `<td class="${["price","buy_price","sell_price","avg_cost","amount","pnl","pnl_pct","quantity","holding_days","stop_loss","target_price"].includes(key)?"num":""}" title="${escapeHtml(row[key]??"")}"> ${cellValue(row, key)}</td>`).join("")}
    </tr>`;
  }).join("");

  // Inject pagination below table, remove old one first
  const existing = document.getElementById("trade-pagination");
  if (existing) existing.remove();
  if (paginationHtml) {
    const wrap = document.createElement("div");
    wrap.id = "trade-pagination";
    wrap.innerHTML = paginationHtml;
    fields.dataTable.closest(".card").appendChild(wrap);
    wrap.querySelector("#page-prev")?.addEventListener("click", () => {
      const allDays = getTradeDays();
      if (state.tradePage < allDays.length - 1) {
        state.tradePage++;
        state.windowDays = getWindowDays(allDays, state.tradePage);
        state.selectedTradeId = "";
        renderTable();
        renderSelectedTrade();
        renderFindings();
        renderLiveAnalysis();
      }
    });
    wrap.querySelector("#page-next")?.addEventListener("click", () => {
      const allDays = getTradeDays();
      if (state.tradePage > 0) {
        state.tradePage--;
        state.windowDays = getWindowDays(allDays, state.tradePage);
        state.selectedTradeId = "";
        renderTable();
        renderSelectedTrade();
        renderFindings();
        renderLiveAnalysis();
      }
    });
  }
}

// ── Selected trade (current trade panel) ──
function selectedTrade() {
  return state.result.trades.find(t => t.trade_id === state.selectedTradeId) || null;
}
function findingRelatedToTrade(finding, trade) {
  if (!trade) return false;
  const text = `${finding.evidence||""} ${finding.advice||""} ${finding.title||""}`;
  return text.includes(trade.code) || text.includes(trade.name);
}

function renderSelectedTrade() {
  const trade = selectedTrade();
  if (!trade) {
    fields.selectedTrade.innerHTML = `<div class="empty-state">选择一笔交易查看对应问题和建议</div>`;
    return;
  }
  const related = state.result.findings.filter(f => findingRelatedToTrade(f, trade));
  const maxSev = Math.max(0, ...related.map(f => Number(f.severity||0)));
  const riskLabel = maxSev >= 4 ? "高风险" : maxSev >= 3 ? "中风险" : maxSev >= 1 ? "低风险" : "无问题";
  const riskCls   = maxSev >= 4 ? "detail-danger" : maxSev >= 3 ? "text-orange" : "";

  const riskAlert = related.length
    ? `<div class="risk-alert"><span>♢</span><span>${escapeHtml(related[0].evidence.slice(0,80))}${related[0].evidence.length>80?"…":""}</span></div>`
    : "";

  const issues = related.slice(0, 3).map((f, i) => `
    <div class="issue-item">
      <div class="issue-index">${i+1}</div>
      <div><div class="issue-title">${escapeHtml(f.title)}</div><div class="issue-desc">${escapeHtml(f.evidence.slice(0,60))}…</div></div>
      ${severityTag(f.severity)}
    </div>`).join("");

  fields.selectedTrade.innerHTML = `
    ${riskAlert}
    <div class="detail-card">
      <div class="detail-head">
        <div class="stock-title">${escapeHtml(trade.code)}　${escapeHtml(trade.name)}</div>
        ${sideTag(trade.side)}
      </div>
      <div class="detail-grid">
        <div class="detail-row"><div class="detail-label">成交时间:</div><div class="detail-value">${shortTime(trade.timestamp)}</div></div>
        <div class="detail-row"><div class="detail-label">关联问题:</div><div class="detail-value detail-link">${related.length} 项</div></div>
        <div class="detail-row"><div class="detail-label">成交金额:</div><div class="detail-value">${formatNumber(tradeAmount(trade))}</div></div>
        <div class="detail-row"><div class="detail-label">风险等级:</div><div class="detail-value ${riskCls}">${riskLabel}</div></div>
        <div class="detail-row"><div class="detail-label">情绪:</div><div class="detail-value">${escapeHtml(trade.emotion||"未记录")}</div></div>
      </div>
      <div class="detail-notes">
        <div class="note-line"><div class="detail-label">交易理由:</div><div>${escapeHtml(trade.reason||"未记录")}</div></div>
        <div class="note-line"><div class="detail-label">计划:</div><div>${escapeHtml(trade.plan||"未记录")}</div></div>
      </div>
    </div>
    ${issues ? `<div class="issue-list">${issues}</div>` : ""}
  `;
}

// ── Findings ──
function renderFindingSummary() {
  const counts = {
    high: state.result.findings.filter(f => Number(f.severity||0) >= 4).length,
    med:  state.result.findings.filter(f => Number(f.severity||0) === 3).length,
    low:  state.result.findings.filter(f => Number(f.severity||0) <= 2).length,
  };
  fields.findingSummary.innerHTML = `
    <div class="summary-card"><span>高风险</span><strong>${counts.high}</strong></div>
    <div class="summary-card"><span>中风险</span><strong>${counts.med}</strong></div>
    <div class="summary-card"><span>低风险</span><strong>${counts.low}</strong></div>
  `;
}

function renderFindings() {
  const trade = selectedTrade();
  fields.findingCount.textContent = `${state.result.findings.length} 项发现`;
  renderFindingSummary();
  fields.findingList.innerHTML = state.result.findings.map(f => {
    const related = findingRelatedToTrade(f, trade);
    return `<details class="finding-card${related?" related":""}">
      <summary><div class="finding-title">${escapeHtml(f.title)}</div>${severityTag(f.severity)}</summary>
      <div class="finding-body">
        <div>${escapeHtml(f.evidence)}</div>
        <div class="finding-advice">${escapeHtml(f.advice)}</div>
      </div>
    </details>`;
  }).join("") || `<div class="empty-state">暂无明显问题</div>`;
}

// ── Recommendations ──
function renderRecommendations() {
  fields.recommendationList.innerHTML = state.result.recommendations.map(item => `
    <article class="recommendation-card">
      <div class="recommendation-title">${escapeHtml(item.stage)}：${escapeHtml(item.title)}</div>
      <ul>${item.actions.map(a => `<li>${escapeHtml(a)}</li>`).join("")}</ul>
    </article>`).join("") || `<div class="empty-state">暂无操作建议</div>`;
}

// ── Live Analysis ──
const EMOTION_KEYWORDS = ["报复","回本","赚回来","revenge","焦虑","急躁","着急","慌","冲动","panic","恐惧","害怕","怕亏","扛不住","fear","贪婪","梭哈","满仓","重仓","怕踏空","fomo","追高","追涨","错过","踏空","无聊","手痒","随手"];
function hasEmotion(text) {
  const raw = String(text||"").toLowerCase();
  return EMOTION_KEYWORDS.some(k => raw.includes(k));
}
function buildPositionAdvice(position, findings) {
  const CRITICAL = ["stop_loss_violation","revenge_trading","unplanned_averaging_down","strategy_signal_conflict"];
  const WARNING  = ["no_stop_loss","no_trade_plan","emotion_driven_trading","fomo_chasing","oversized_position"];
  const inText = f => f.evidence.includes(position.code) || f.evidence.includes(position.name);
  const critical = findings.filter(f => CRITICAL.includes(f.type) && inText(f));
  const warning  = findings.filter(f => WARNING.includes(f.type) && inText(f));
  const hasNoExit = position.stop_loss <= 0 && position.target_price <= 0;
  const emotional = hasEmotion(position.emotion + " " + position.reason);
  if (critical.length || (hasNoExit && emotional))
    return { action:"建议减仓或退出", cls:"action-exit", reason: critical.map(f=>f.title).join("；")||"无止损且情绪建仓" };
  if (warning.length || hasNoExit)
    return { action:"持仓观察，补录退出条件", cls:"action-watch", reason: hasNoExit?"缺少止损/目标价":warning.map(f=>f.title).join("；") };
  return { action:"按计划持有", cls:"action-hold", reason: position.plan||"已有止损和目标价" };
}

function renderLiveAnalysis() {
  const { findings, open_positions } = state.result;
  // Use trades in the current 5-day window
  const windowSet = new Set(state.windowDays);
  const trades = state.result.trades.filter(t => windowSet.has(dateKey(t.timestamp)));

  const windowLabel = state.windowDays.length
    ? `${state.windowDays[state.windowDays.length-1]} ～ ${state.windowDays[0]}（${state.windowDays.length} 个交易日）`
    : "";
  const weaknessHtml = findings.slice(0,5).map(f => `
    <div class="live-weakness-item">
      <div class="live-weakness-title">${escapeHtml(f.title)}${severityTag(f.severity)}</div>
      <div class="live-weakness-evidence">${escapeHtml(f.evidence)}</div>
    </div>`).join("") || `<div class="empty-state">无明显缺点</div>`;

  const tradeErrors = trades.map(t => {
    const related = findings.filter(f => findingRelatedToTrade(f, t));
    return related.length ? `<div class="live-trade-error"><span class="live-trade-label">${escapeHtml(t.code)} ${sideTag(t.side)} ${shortTime(t.timestamp)}</span><span class="live-trade-issues">${related.map(f=>escapeHtml(f.title)).join("，")}</span></div>` : null;
  }).filter(Boolean).slice(0,6).join("") || `<div class="empty-state">未识别出交易级别问题</div>`;

  const positionHtml = open_positions.length
    ? open_positions.map(pos => {
        const { action, cls, reason } = buildPositionAdvice(pos, findings);
        const noExit = pos.stop_loss<=0 && pos.target_price<=0;
        return `<div class="live-position-row">
          <div class="live-position-name">${escapeHtml(pos.code)} ${escapeHtml(pos.name)}</div>
          <div class="live-position-action ${cls}">${escapeHtml(action)}</div>
          <div class="live-position-meta">${noExit?'<span class="tag warn">无退出条件</span> ':""} 成本 ${formatNumber(pos.avg_cost)} × ${formatCompact(pos.quantity)}</div>
          <div class="live-position-reason">${escapeHtml(reason)}</div>
        </div>`;
      }).join("")
    : `<div class="empty-state">无持仓</div>`;

  const priorityHtml = findings.filter(f=>f.severity>=3).slice(0,3).map((f,i) =>
    `<div class="live-priority-item"><span class="live-priority-num">${i+1}</span>${escapeHtml(f.advice)}</div>`
  ).join("") || `<div class="empty-state">暂无</div>`;

  if (!findings.length && !trades.length) {
    fields.liveAnalysis.innerHTML = `<div class="empty-state">上传截图后自动生成实盘分析</div>`;
    return;
  }

  const windowHeader = windowLabel
    ? `<div class="live-window-label">复盘窗口：${escapeHtml(windowLabel)}</div>`
    : "";

  fields.liveAnalysis.innerHTML = `
    ${windowHeader}
    <div class="live-section"><div class="live-section-title">交易缺点分析</div><div class="live-weakness-list">${weaknessHtml}</div></div>
    <div class="live-section"><div class="live-section-title">交易错误分析（窗口内 ${trades.length} 笔）</div><div class="live-trade-errors">${tradeErrors}</div></div>
    <div class="live-section"><div class="live-section-title">股票持仓建议</div><div class="live-positions">${positionHtml}</div></div>
    <div class="live-section live-section-priority"><div class="live-section-title">优先改进事项</div><div class="live-priorities">${priorityHtml}</div></div>
  `;
}

// ── Render all ──
function renderAnalysisView() {
  document.querySelectorAll(".analysis-segment").forEach(b =>
    b.classList.toggle("active", b.dataset.analysisView === state.analysisView));
  document.querySelectorAll(".analysis-panel").forEach(p =>
    p.classList.toggle("active", p.dataset.analysisPanel === state.analysisView));
}

function renderAll() {
  initPagination();
  renderHero();
  renderMetrics();
  renderTable();
  renderSelectedTrade();
  renderFindings();
  renderRecommendations();
  renderLiveAnalysis();
  renderAnalysisView();
}

// ── Source summary ──
function updateSourceSummary() {
  const src = fields.input ? fields.input.value : "";
  fields.sourceMain.textContent = src
    ? `${basename(src)} · ${state.result.metrics.trade_count} 笔交易`
    : "—";
  if (state.result.metrics.trade_count) {
    fields.sourceStatus.innerHTML = `<span class="dot"></span>已加载`;
  }
}

// ── Analyze ──
async function analyze() {
  setStatus("分析中");
  if (fields.analyzeButton) fields.analyzeButton.disabled = true;
  try {
    const response = await fetch("/api/analyze", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        input: fields.input ? fields.input.value : "",
        strategy: fields.strategy ? fields.strategy.value : "",
        stock: fields.stock ? fields.stock.value : "",
        account_size: fields.accountSize ? fields.accountSize.value : "",
        overtrade_daily_count: fields.overtradeCount ? fields.overtradeCount.value : "",
      }),
    });
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.error || "分析失败");
    state.result = payload.result;
    state.selectedTradeId = state.result.trades[0]?.trade_id || "";
    renderAll();
    updateSourceSummary();
    setStatus("已完成", "ready");
  } catch (error) {
    setStatus("出错", "error");
    fields.findingList.innerHTML = `<div class="empty-state">${escapeHtml(error.message)}</div>`;
  } finally {
    if (fields.analyzeButton) fields.analyzeButton.disabled = false;
  }
}

// ── Image import ──
function fileToDataUrl(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result);
    reader.onerror = () => reject(reader.error || new Error("读取图片失败"));
    reader.readAsDataURL(file);
  });
}

function imagePathList() {
  if (!fields.imagePath) return [];
  return fields.imagePath.value.split(/[\n,，]+/).map(s => s.trim()).filter(Boolean);
}

function prepareImageImport() {
  const files = Array.from(fields.imageFile ? fields.imageFile.files || [] : []);
  const paths = imagePathList();
  if (!files.length && !paths.length) {
    setStatus("出错", "error");
    fields.importResult.textContent = "请先选择图片文件，或输入本地图片路径。";
    return;
  }
  state.pendingImageImport = { files, paths, agent: fields.imageAgent ? fields.imageAgent.value : "local" };
  const count = files.length || paths.length;
  fields.imageSummary.textContent = `待确认 ${count} 张图片`;
  setStatus("待确认");
  // open confirm
  const agentText = state.pendingImageImport.agent === "deepseek-v4-pro" ? "DeepSeek V4 Pro Agent 校正" : "本地 OCR";
  if (files.length) {
    const names = files.slice(0,3).map(f=>f.name).join("、");
    const more = files.length > 3 ? `等 ${files.length} 张` : "";
    fields.imageConfirmMessage.textContent = `将使用${agentText}上传并识别 ${count} 张图片：${names}${more}。`;
  } else {
    fields.imageConfirmMessage.textContent = `将使用${agentText}识别 ${count} 个本地图片路径。`;
  }
  fields.imageConfirm.hidden = false;
  fields.confirmImageImport.focus();
}

async function importImage(pending) {
  if (!pending) return;
  fields.imageConfirm.hidden = true;
  state.pendingImageImport = null;
  setStatus("识别中");
  fields.imageButton.disabled = true;
  fields.confirmImageImport.disabled = true;
  fields.importResult.textContent = "正在识别图片...";
  try {
    const body = pending.files.length
      ? { files: await Promise.all(pending.files.map(async f => ({ filename: f.name, data_url: await fileToDataUrl(f) }))) }
      : { image_paths: pending.paths };
    body.agent = pending.agent;

    const response = await fetch("/api/import-image", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.error || "图片识别失败");

    if (fields.input) fields.input.value = payload.csv_path;
    if (fields.strategy && fields.strategy.value === state.defaults.strategy) fields.strategy.value = "";
    if (fields.stock && fields.stock.value === state.defaults.stock) fields.stock.value = "";

    const dup = payload.duplicate_count ? `，去重 ${payload.duplicate_count} 条` : "";
    const skip = payload.skipped_count ? `，跳过 ${payload.skipped_count} 条` : "";
    fields.importResult.textContent = `已识别 ${payload.imported_count} 条成交记录${dup}${skip}。OCR：${payload.engine}`;
    fields.imageMain.textContent = `已识别 ${payload.imported_count} 条`;
    fields.imageSummary.textContent = `已识别 ${payload.imported_count} 条 · 去重 ${payload.duplicate_count||0} 条`;
    fields.imageStatus && (fields.imageStatus.innerHTML = `<span class="dot"></span>已识别`);

    await analyze();
    state.analysisView = "live";
    renderAnalysisView();
  } catch (error) {
    setStatus("出错", "error");
    fields.importResult.textContent = error.message;
  } finally {
    fields.imageButton.disabled = false;
    fields.confirmImageImport.disabled = false;
  }
}

async function clearHistory() {
  fields.clearConfirm.hidden = true;
  setStatus("清除中");
  fields.clearButton.disabled = true;
  try {
    const response = await fetch("/api/clear-history", { method:"POST", headers:{"Content-Type":"application/json"}, body:"{}" });
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.error || "清除失败");
    state.result = emptyResult();
    state.selectedTradeId = "";
    state.currentView = "trades";
    state.analysisView = "trade";
    document.querySelectorAll(".segment").forEach(b => b.classList.toggle("active", b.dataset.view==="trades"));
    if (fields.input) fields.input.value = "";
    if (fields.strategy) fields.strategy.value = "";
    if (fields.stock) fields.stock.value = "";
    if (fields.imageFile) fields.imageFile.value = "";
    if (fields.imagePath) fields.imagePath.value = "";
    fields.importResult.textContent = "";
    fields.sourceMain.textContent = "—";
    fields.sourceStatus.innerHTML = "";
    fields.imageMain.textContent = "未选择";
    fields.imageSummary.textContent = "上传或输入本地截图路径";
    renderAll();
    setStatus("已清除", "ready");
  } catch (error) {
    setStatus("出错", "error");
  } finally {
    fields.clearButton.disabled = false;
  }
}

async function loadDefaults() {
  const response = await fetch("/api/defaults");
  const defaults = await response.json();
  state.defaults = defaults;
  if (fields.input) fields.input.value = defaults.input;
  if (fields.strategy) fields.strategy.value = defaults.strategy;
  if (fields.stock) fields.stock.value = defaults.stock;
  // 不预填图片路径，避免页面加载时误触发确认弹窗
  if (defaults.accountSize) fields.accountSize.value = defaults.account_size;
  if (defaults.overtradeCount) fields.overtradeCount.value = defaults.overtrade_daily_count;
  if (fields.accountSize) fields.accountSize.value = defaults.account_size;
  if (fields.overtradeCount) fields.overtradeCount.value = defaults.overtrade_daily_count;
  fields.sourceMain.textContent = basename(defaults.input);
  if (defaults.image) {
    fields.imageMain.textContent = basename(defaults.image);
    fields.imageSummary.textContent = basename(defaults.image);
  }
  await analyze();
}

// ── Event listeners ──
fields.form && fields.form.addEventListener("submit", e => { e.preventDefault(); analyze(); });
fields.imageButton.addEventListener("click", prepareImageImport);
fields.clearButton.addEventListener("click", () => { fields.clearConfirm.hidden = false; fields.confirmClear.focus(); });
fields.cancelClear.addEventListener("click", () => { fields.clearConfirm.hidden = true; });
fields.confirmClear.addEventListener("click", clearHistory);
fields.clearConfirm.addEventListener("click", e => { if (e.target===fields.clearConfirm) fields.clearConfirm.hidden=true; });
fields.cancelImageImport.addEventListener("click", () => { fields.imageConfirm.hidden=true; state.pendingImageImport=null; setStatus(state.result?.metrics?.trade_count?"已完成":"待分析", state.result?.metrics?.trade_count?"ready":""); });
fields.confirmImageImport.addEventListener("click", () => importImage(state.pendingImageImport));
fields.imageConfirm.addEventListener("click", e => { if (e.target===fields.imageConfirm) { fields.imageConfirm.hidden=true; state.pendingImageImport=null; } });

fields.imageFile && fields.imageFile.addEventListener("change", () => {
  const files = Array.from(fields.imageFile.files || []);
  if (files.length) {
    fields.imageMain.textContent = files.length===1 ? files[0].name : `${files.length} 张图片`;
  }
});

fields.toggleSource && fields.toggleSource.addEventListener("click", () => {
  fields.sourceDrawer.hidden = !fields.sourceDrawer.hidden;
  fields.toggleSource.textContent = fields.sourceDrawer.hidden ? "⌄" : "⌃";
});

document.addEventListener("keydown", e => {
  if (e.key !== "Escape") return;
  if (!fields.clearConfirm.hidden) fields.clearConfirm.hidden = true;
  if (!fields.imageConfirm.hidden) { fields.imageConfirm.hidden=true; state.pendingImageImport=null; }
});

document.querySelectorAll(".segment").forEach(btn => {
  btn.addEventListener("click", () => {
    document.querySelectorAll(".segment").forEach(b => b.classList.remove("active"));
    btn.classList.add("active");
    state.currentView = btn.dataset.view;
    renderTable();
  });
});

document.querySelectorAll(".analysis-segment").forEach(btn => {
  btn.addEventListener("click", () => {
    state.analysisView = btn.dataset.analysisView;
    renderAnalysisView();
  });
});

fields.dataTable.addEventListener("click", e => {
  const row = e.target.closest("tr[data-trade-id]");
  if (!row || state.currentView !== "trades") return;
  state.selectedTradeId = row.dataset.tradeId;
  state.analysisView = "trade";
  renderTable();
  renderSelectedTrade();
  renderFindings();
  renderAnalysisView();
});

loadDefaults();
