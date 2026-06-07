# tradeAnalysis UI V2 优化执行说明（Claude CLI 可执行）

> 任务目标：基于当前仓库，将 `tradeAnalysis` 实盘交易复盘页面升级为更符合现代网页设计、金融 SaaS Dashboard、UI/UX 设计准则的界面。  
> 重点：**首屏展示核心内容、降低导入区噪音、突出风险结论、提升表格与复盘面板的可读性。**  
> 严禁修改：交易计算逻辑、CSV 解析逻辑、图片识别/OCR 逻辑、风险识别逻辑、接口协议、字段含义。

---

## 0. 执行方式

请在项目根目录执行：

```bash
claude
```

然后输入：

```text
请读取 tradeAnalysis-ui-v2-claude-cli.md，并按文档要求直接修改当前仓库中的 tradeAnalysis 页面。完成后运行 lint/typecheck/build，并输出改动摘要、涉及文件和验证结果。
```

如果希望一条命令执行：

```bash
claude "请读取 tradeAnalysis-ui-v2-claude-cli.md，并按文档要求直接修改当前仓库中的 tradeAnalysis 页面。完成后运行 lint/typecheck/build，并输出改动摘要、涉及文件和验证结果。"
```

---

## 1. 设计原则

本次 UI 优化必须遵循以下网页设计与 UI/UX 准则：

### 1.1 首屏核心内容优先

用户进入页面后，首屏应立即看到：

1. 当前复盘风险结论
2. 核心 KPI
3. 交易表格
4. 当前选中交易的分析结果

导入、图片路径、参数设置属于辅助功能，不应占据首屏主要空间。

### 1.2 信息层级清晰

页面信息优先级：

```text
P0：当前复盘结论、风险等级、关键建议
P1：KPI 指标、交易表格、当前交易分析
P2：问题列表、建议、实盘分析
P3：数据源、图片识别、上传路径、辅助状态
```

### 1.3 渐进披露

不要把所有信息一次性平铺。

- 首屏展示摘要和关键风险
- 详情放在右侧分析面板
- 问题、建议、实盘分析通过 tabs 展示
- 导入配置压缩成小卡片
- 长文本使用截断、tooltip、详情区域承载

### 1.4 视觉一致性

统一使用：

- 卡片
- Badge
- Segmented tabs
- Metric cards
- 浅色背景
- 语义色彩：蓝色主操作、绿色盈利/买入、红色风险/卖出、橙色警告

---

## 2. 目标界面结构

请将页面改造成以下结构：

```text
tradeAnalysis Page
├── Header
│   ├── Logo / 标题 / 副标题
│   └── 操作按钮：清除历史数据 / 确认导入 / 已完成
│
├── 首屏摘要区 Hero Summary
│   ├── 当前复盘：高风险
│   ├── 14 项发现 · 3 笔风险交易 · 策略一致率 50%
│   └── 复盘建议：优先复盘追涨与止损执行问题
│
├── 辅助导入区 Utility Cards
│   ├── 数据源：sample_trades.csv · 6 笔交易
│   └── 图片识别导入：图片名 / 上传按钮 / 已识别状态
│
├── KPI 区 Metric Grid
│   ├── 已实现盈亏
│   ├── 胜率
│   ├── Profit Factor
│   ├── 最大单笔仓位
│   ├── 策略一致率
│   └── 风险交易
│
└── 主工作区 Workspace
    ├── 左侧：实际交易数据表
    └── 右侧：分析结果面板
```

---

## 3. 首屏布局要求

首屏高度有限，请确保重要内容在 100vh 内展示出来。

推荐布局：

```css
.page {
  min-height: 100vh;
  background: var(--bg-page);
}

.page-header {
  height: 72px;
  background: rgba(255, 255, 255, 0.92);
  border-bottom: 1px solid var(--border-subtle);
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 32px;
  position: sticky;
  top: 0;
  z-index: 20;
  backdrop-filter: blur(8px);
}

.container {
  max-width: 1760px;
  margin: 0 auto;
  padding: 20px 32px 40px;
}

.top-grid {
  display: grid;
  grid-template-columns: minmax(520px, 1.45fr) minmax(280px, 0.55fr) minmax(360px, 0.72fr);
  gap: 16px;
}

.metric-grid {
  display: grid;
  grid-template-columns: repeat(6, minmax(0, 1fr));
  gap: 16px;
  margin-top: 16px;
}

.workspace-grid {
  display: grid;
  grid-template-columns: minmax(720px, 1.5fr) minmax(460px, 1fr);
  gap: 16px;
  margin-top: 16px;
}
```

响应式：

```css
@media (max-width: 1280px) {
  .top-grid,
  .workspace-grid {
    grid-template-columns: 1fr;
  }

  .metric-grid {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }
}

@media (max-width: 768px) {
  .page-header {
    height: auto;
    min-height: 72px;
    flex-direction: column;
    align-items: flex-start;
    gap: 12px;
    padding: 14px 18px;
  }

  .container {
    padding: 16px;
  }

  .metric-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .table-scroll {
    overflow-x: auto;
  }
}
```

---

## 4. Header 设计要求

Header 要克制、专业、工具感强。

内容：

```text
tradeAnalysis
实盘交易复盘 · 不构成投资建议

[清除历史数据] [确认导入] [已完成]
```

按钮语义：

- 清除历史数据：danger outline
- 确认导入：primary blue
- 已完成：success pill，不要做成很重的主按钮

---

## 5. 首屏摘要区 Hero Summary

这是本次设计的核心优化点。

原来页面顶部导入区空白太大，用户第一眼看不到结论。现在必须把当前复盘结论前置。

示例内容：

```text
当前复盘：高风险
14 项发现 · 3 笔风险交易 · 策略一致率 50%

复盘建议
优先复盘追涨与止损执行问题
```

视觉要求：

- 使用红色浅色背景或白底红色左侧图标
- 左侧放盾牌/警告 icon
- “高风险”必须醒目
- 摘要卡高度控制在 112px - 128px
- 不要使用大段文字
- 适合一眼扫读

推荐 DOM 结构：

```tsx
<Card className="hero-summary risk-high">
  <div className="hero-icon">...</div>
  <div className="hero-main">
    <h2>当前复盘：<span>高风险</span></h2>
    <p>14 项发现 · 3 笔风险交易 · 策略一致率 50%</p>
  </div>
  <Separator orientation="vertical" />
  <div className="hero-advice">
    <div className="label">复盘建议</div>
    <strong>优先复盘追涨与止损执行问题</strong>
  </div>
</Card>
```

---

## 6. 辅助导入区 Utility Cards

导入信息属于 P3 辅助信息，必须小型化。

### 数据源卡片

内容：

```text
数据源
sample_trades.csv · 6 笔交易
已加载 · 2026-05-31 22:08
```

### 图片识别卡片

内容：

```text
图片识别导入                 [上传图片]
微信图片_20260531220448_5_2.jpg
已识别 · 2026-05-31 22:09
```

要求：

- 不再展示大面积空白的 input 区
- 图片路径不要完整占据页面，可放入 tooltip 或次级详情
- 上传按钮保持可用
- 如果原逻辑必须保留 input，请视觉上做成折叠/轻量样式

---

## 7. KPI Metric Cards

KPI 是 P1 信息，需要在首屏完整展示。

数据示例：

```text
已实现盈亏     577.40       较上次复盘 +577.40
胜率           50.00%       3 胜 / 3 负
Profit Factor  1.25         总盈利 / 总亏损
最大单笔仓位   32.40%       超 30% 建议控制
策略一致率     50.00%       中等偏低
风险交易       3            占比 50.00%
```

视觉要求：

- 六张卡一行，大屏显示
- 每张卡有小图标 / 小色块
- 主数值 28px - 32px
- 辅助说明 12px - 13px
- 数字使用 tabular-nums
- 不要让卡片过高，高度建议 120px 左右

语义颜色：

- 盈利：绿色
- 最大仓位 32.40%：橙色
- 风险交易 3：红色
- 其他指标：深色文字，辅助说明可灰色或橙色

---

## 8. 主工作区：交易表格

表格是最重要的操作区域，必须高可读性。

### 表格卡片头部

```text
实际交易数据    6 笔 · 点击行查看右侧复盘

[交易] [配对] [持仓]                     [筛选] [导出] [全屏]
```

如果当前项目还没有筛选/导出/全屏功能，可以：

- 只做静态按钮但不绑定新逻辑
- 或保留现有功能按钮
- 不要为了 UI 增加复杂业务逻辑

### 表格列

```text
时间 | 代码 | 名称 | 方向 | 价格 | 数量 | 金额 | 情绪 | 理由
```

### 表格行样式

- 表头背景：`#f8fafc`
- 行高：52px - 56px
- hover：`#f8fafc`
- 选中行：`#eff6ff`
- 选中行左侧：3px 蓝色竖条
- 数字列右对齐
- 方向使用 badge
- 情绪按照风险程度着色：
  - 焦虑：橙色
  - 恐惧：红色
  - 报复：红色
  - 害怕回撤：橙色
  - 贪婪：橙色或红色

### 示例数据

请保留现有数据来源，以下仅作为 UI 参考：

```text
2026-05-06 10:12 | 300750 | 宁德时代 | 买入 | 215.50 | 200 | 43,100.00 | 焦虑 | 突破买入，担心踏空
2026-05-07 14:45 | 300750 | 宁德时代 | 卖出 | 204.00 | 200 | 40,800.00 | 恐惧 | 跌破后止损
2026-05-07 15:05 | 600519 | 贵州茅台 | 买入 | 1,620.00 | 100 | 162,000.00 | 报复 | 想把刚才亏损赚回来
2026-05-10 10:30 | 600519 | 贵州茅台 | 卖出 | 1,650.00 | 100 | 165,000.00 | 害怕回撤 | 赚一点先落袋
2026-05-11 09:50 | 002475 | 立讯精密 | 买入 | 35.20 | 1,000 | 35,200.00 | 贪婪 | 看到快速拉升追入
2026-05-11 10:20 | 002475 | 立讯精密 | 买入 | 34.00 | 1,000 | 34,000.00 | 焦虑 | 下跌后补仓摊低成本
```

---

## 9. 右侧分析结果面板

右侧面板用于承载“为什么这笔交易有问题”。

### 面板头部

```text
分析结果
14 项发现 · 当前交易高风险                     [高风险]
```

### Tabs

```text
[当前交易] [问题] [建议] [实盘分析]
```

使用 segmented control 样式，当前选中项突出。

### 风险摘要

```text
本次交易存在明显的追涨与情绪驱动特征，入场依据不足，风险控制缺失。
```

样式：

- 红色浅底
- 左侧警告 icon
- 短句，不要超过两行

### 当前交易卡片

内容：

```text
300750 宁德时代                         [买入]

成交时间：2026-05-06 10:12
成交金额：43,100.00
情绪：焦虑
关联问题：5 项
风险等级：高风险

交易理由：
突破买入，担心踏空。入场依据偏主观，缺少量价确认与回撤预案。

计划：
突破210买入，跌破205止损，目标235。建议补充仓位上限与触发条件。
```

要求：

- 代码 + 名称作为标题
- 买入 badge 右侧显示
- 详情信息两列排版
- 交易理由/计划单独分行，方便阅读
- “关联问题 5 项”用蓝色链接样式或 badge

### 问题列表

下方展示前两个最关键问题：

```text
1 追涨入场    高风险
  价格突破后立即买入，但没有等待有效确认。

2 情绪驱动    高风险
  “担心踏空”是主要动机，和交易计划一致性较弱。
```

---

## 10. 设计 Token

请优先使用 CSS 变量或项目现有主题变量。

```css
:root {
  --bg-page: #f6f8fb;
  --bg-card: #ffffff;

  --border-subtle: #e5e7eb;
  --border-strong: #cbd5e1;

  --text-primary: #0f172a;
  --text-secondary: #475569;
  --text-muted: #64748b;

  --primary: #2563eb;
  --primary-soft: #eff6ff;

  --success: #16a34a;
  --success-soft: #dcfce7;

  --danger: #dc2626;
  --danger-soft: #fee2e2;
  --danger-bg: #fef2f2;

  --warning: #f97316;
  --warning-soft: #ffedd5;

  --radius-card: 16px;
  --radius-control: 10px;

  --shadow-card: 0 1px 2px rgba(15, 23, 42, 0.04),
                 0 12px 32px rgba(15, 23, 42, 0.03);
}
```

---

## 11. 推荐组件拆分

请按当前技术栈适配。若项目是 React，建议拆分为：

```text
TradeAnalysisPage
├── TradeAnalysisHeader
├── ReviewHeroSummary
├── UtilityCards
│   ├── DataSourceCard
│   └── ImageImportCard
├── MetricGrid
│   └── MetricCard
└── ReviewWorkspace
    ├── TradeTablePanel
    │   ├── TradeTableToolbar
    │   └── TradeTable
    └── AnalysisPanel
        ├── RiskAlert
        ├── AnalysisTabs
        ├── CurrentTradeDetail
        └── IssuePreviewList
```

要求：

- 如果已有组件体系，优先复用现有 Button/Card/Badge/Tabs
- 如果项目使用 Tailwind，优先使用 Tailwind class
- 如果项目使用 CSS Modules，新增 `tradeAnalysis.module.css` 或维护已有样式文件
- 不要为了 UI 引入大型第三方库
- 可以使用现有 icon 库；如果没有 icon 库，用简洁文字/icon 占位即可

---

## 12. 不要修改的内容

不得修改：

- CSV 解析逻辑
- 图片识别/OCR 逻辑
- 盈亏、胜率、Profit Factor、仓位、策略一致率等计算逻辑
- 风险交易识别逻辑
- 交易配对逻辑
- 持仓计算逻辑
- 后端 API 协议
- 数据字段名称与含义

允许修改：

- 页面布局
- 组件结构
- CSS / Tailwind class
- UI 文案展示方式
- Badge/颜色/间距/卡片
- tab 外观
- 表格样式
- 详情面板布局

---

## 13. 可访问性与可用性要求

- 主要按钮有清晰 hover/focus 状态
- danger 操作保留二次确认，如果项目原本已有
- 表格行可点击时 cursor 使用 pointer
- 选中行状态不只依赖颜色，左侧增加蓝色竖条
- badge 文字必须可读，不要使用低对比度颜色
- 长文本需要截断或换行，不能撑破布局
- 小屏幕下表格横向滚动，不要挤压列宽
- 不要让页面横向溢出

---

## 14. 性能与首屏体验

本页面是数据型 Dashboard，请注意：

- 首屏不要渲染过大的图片预览
- 图片路径和上传区域不要占据大块空间
- KPI 和表格应优先展示
- 如果数据加载中，使用 skeleton 或轻量 loading
- 不要引入不必要的大型依赖
- 不要把所有 tab 内容同时重度渲染，优先展示当前 tab

---

## 15. 验收标准

### 视觉验收

- 首屏能直接看到风险结论、KPI、交易表格、分析面板
- 导入区不再占据大面积首屏空间
- 高风险状态明显但不刺眼
- 表格行、数字、买卖方向、情绪都易读
- 右侧面板能清晰解释当前交易的问题
- 整体风格像现代金融 SaaS dashboard

### 功能验收

- CSV 导入仍可用
- 图片识别导入仍可用
- 清除历史数据仍可用
- 点击交易行仍能联动右侧分析
- tabs 切换正常
- 指标数值与优化前一致
- 风险交易数量与优化前一致

### 工程验收

- 无 TypeScript 错误
- 无 ESLint 错误
- 无 build 错误
- 无明显 console error
- 没有引入不必要的大型 UI 库
- 样式结构清晰、可维护

---

## 16. 执行步骤

请按以下顺序执行：

1. 扫描项目结构，找到 tradeAnalysis 页面入口、组件和样式文件。
2. 判断技术栈：React / Vue / Svelte / 原生 JS / Tailwind / CSS Modules 等。
3. 找出当前交易数据、KPI、分析结果、导入状态的来源。
4. 保持所有数据逻辑不动，只重构 UI 结构。
5. 先实现 Header + Hero Summary + Utility Cards。
6. 再实现 KPI Metric Grid。
7. 再优化交易表格。
8. 再优化右侧分析结果面板。
9. 做响应式适配。
10. 运行 lint / typecheck / build。
11. 输出改动摘要、涉及文件、验证结果。
12. 如果某些功能因项目限制无法实现，明确说明原因和替代方案。

---

## 17. 最终效果参考

目标界面应接近以下描述：

```text
┌──────────────────────────────────────────────────────────────────────────────┐
│ tradeAnalysis        实盘交易复盘 · 不构成投资建议       清除 / 导入 / 完成 │
└──────────────────────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────┐ ┌──────────────┐ ┌──────────────────┐
│ 当前复盘：高风险                     │ │ 数据源       │ │ 图片识别导入     │
│ 14项发现 · 3笔风险交易 · 一致率50%   │ │ csv · 6笔    │ │ 已识别 / 上传    │
│ 复盘建议：优先复盘追涨与止损执行问题 │ │ 已加载       │ │ 图片文件名       │
└──────────────────────────────────────┘ └──────────────┘ └──────────────────┘

┌──── KPI ────┐ ┌──── KPI ────┐ ┌──── KPI ────┐ ┌──── KPI ────┐ ┌──── KPI ────┐ ┌──── KPI ────┐
│ 盈亏 577.40 │ │ 胜率 50%    │ │ PF 1.25     │ │ 仓位 32.4%  │ │ 一致率 50%  │ │ 风险 3      │
└─────────────┘ └─────────────┘ └─────────────┘ └─────────────┘ └─────────────┘ └─────────────┘

┌──────────────────────────────────────────────┐ ┌────────────────────────────┐
│ 实际交易数据                                 │ │ 分析结果        高风险     │
│ [交易][配对][持仓]              [筛选][导出] │ │ 当前交易/问题/建议/分析    │
│ 表格：选中行高亮、买卖标签、数字右对齐       │ │ 风险摘要 + 当前交易详情     │
│                                              │ │ 问题预览列表                │
└──────────────────────────────────────────────┘ └────────────────────────────┘
```

---

## 18. 最终给用户的输出格式

完成后请输出：

```text
已完成 tradeAnalysis UI V2 优化。

改动摘要：
1. ...
2. ...

涉及文件：
- ...

验证结果：
- lint: pass / 未配置 / fail
- typecheck: pass / 未配置 / fail
- build: pass / 未配置 / fail

注意事项：
- ...
```
