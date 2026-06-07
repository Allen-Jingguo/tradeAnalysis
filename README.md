# tradeAnalysis

`tradeAnalysis` 用于投喂真人实盘操作数据，分析交易行为、心理偏差、执行问题和优化路径。它不是医疗/心理诊断工具，也不是投资建议工具；定位是交易复盘和行为校正。

## 能做什么

- 导入 CSV / JSON / JSONL 实盘买卖点数据。
- 可选导入策略信号 CSV / JSON / JSONL，也支持 HTTP/HTTPS URL；可对接 StockPilot 导出的 CSV 或 StockPilot API 返回的 JSON。
- 可选导入标的画像/风险数据，用于判断股票标的是否存在评分低、趋势弱、流动性不足、波动过高、风险标签等问题。
- 按 FIFO 配对买卖，计算已实现盈亏、胜率、平均盈亏、持有时间、交易频率、仓位占比。
- 识别常见操作心理问题：
  - 无计划交易
  - 无止损交易
  - 追涨/FOMO
  - 亏损后报复性交易
  - 过度交易
  - 止损延迟
  - 过早止盈
  - 亏损持有过久、盈利持有过短
  - 非计划补仓摊平
  - 单笔仓位过大
- 识别策略执行问题：
  - 与策略信号冲突
  - 无策略支持的系统外交易
  - 策略信号执行延迟
  - 相对信号价滑点过大
  - 未带入策略止损/目标价
- 新交易出现后自动做风险重评：把最近一个交易日的新交易和之前的历史交易对照，判断风险是改善了还是恶化了，给出：
  - 综合风险分变化（基线 → 当前）；
  - 已消除 / 新增 / 仍未解决的问题；
  - 计划覆盖率、止损记录率、情绪干净率、仓位合规率等可比指标的升降；
  - 每一笔新买入的逐项体检（评分、结论、已做到的点、待改进的点）；
  - 汇总后的"改善点"和"待改善点"。
- 输出 Markdown 和 JSON 报告，便于后续接入 AllClaw/飞书/网页 UI。

## 快速开始

```bash
cd /Users/allenan/tradeAnalysis
python3 -m trade_analysis.cli analyze --input data/sample_trades.csv --out output/sample_report.md --json-out output/sample_report.json --account-size 500000 --print
```

启动本地界面：

```bash
python3 -m trade_analysis.webapp --host 127.0.0.1 --port 8765
```

打开 `http://127.0.0.1:8765` 后，可以查看实际交易明细、配对交易、持仓、分析问题和操作建议。界面默认加载样例数据，也可以把成交数据、策略信号和标的画像输入框改成自己的本地文件路径或 URL。

界面也支持图片识别导入。上传券商 App 的历史委托截图，或输入本地图片路径后点击“识别导入”，系统会把已成交记录转换成 `output/image_imported_trades.csv` 并自动重新分析。成交数量为 0 的未成交委托会跳过。

命令行导入图片：

```bash
python3 -m trade_analysis.cli image-import \
  --image "/Users/allenan/Desktop/微信图片_20260531220448_5_2.jpg" \
  --out output/image_imported_trades.csv
```

带策略信号和标的画像一起分析：

```bash
python3 -m trade_analysis.cli analyze \
  --input data/sample_trades.csv \
  --strategy-source data/sample_strategy_signals.csv \
  --stock-source data/sample_stock_profiles.csv \
  --out output/sample_with_strategy_report.md \
  --json-out output/sample_with_strategy_report.json \
  --account-size 500000 \
  --print
```

从 URL 拉取策略信号：

```bash
python3 -m trade_analysis.cli analyze \
  --input data/my_trades.csv \
  --strategy-source "https://example.com/signals.json" \
  --http-header "Authorization=Bearer YOUR_TOKEN"
```

StockPilot API 鉴权会自动读取环境变量并写入请求头：

```bash
export STOCKPILOT_CLIENT_ID="your_client_id"
export STOCKPILOT_CLIENT_SECRET="your_client_secret"
python3 -m trade_analysis.cli analyze --input data/my_trades.csv --strategy-source "https://api.stockpilot.dev/..."
```

生成空模板：

```bash
python3 -m trade_analysis.cli template --out data/my_trades.csv
```

生成带样例的模板：

```bash
python3 -m trade_analysis.cli template --out data/sample_template.csv --sample
```

## CSV 字段

| 字段 | 必填 | 说明 |
|---|---|---|
| `timestamp` | 是 | `YYYY-MM-DD HH:MM[:SS]` |
| `code` | 是 | 股票/基金代码 |
| `name` | 否 | 名称 |
| `side` | 是 | `BUY`/`SELL`，也支持 `买入`/`卖出` |
| `price` | 是 | 成交价 |
| `quantity` | 是 | 成交数量 |
| `fee` | 否 | 手续费、印花税等总费用 |
| `reason` | 建议 | 实际买卖理由 |
| `plan` | 建议 | 交易前计划 |
| `emotion` | 建议 | 情绪：焦虑/贪婪/恐惧/报复/平静等 |
| `market_context` | 建议 | 大盘/板块背景 |
| `stop_loss` | 建议 | 计划止损价 |
| `target_price` | 建议 | 计划目标价 |
| `day_high/day_low` | 可选 | 用于识别追高 |
| `post_price_1d/3d/5d` | 可选 | 卖出后价格，用于判断过早止盈/卖飞 |
| `tags` | 可选 | 分号或逗号分隔标签 |

中文券商导出字段也做了别名兼容，例如 `成交时间`、`证券代码`、`买卖`、`成交价格`、`成交数量`。

## 策略信号字段

策略信号支持 CSV / JSON / JSONL，本地路径或 URL。StockPilot 扫描器导出 CSV 后可直接作为 `--strategy-source` 输入。

| 字段 | 必填 | 说明 |
|---|---|---|
| `code` | 是 | 股票代码 |
| `timestamp` | 否 | 信号生成时间；为空时视为无时间限制的候选信号 |
| `action` | 否 | `BUY`/`SELL`/`AVOID`/`HOLD`，为空默认 `BUY` |
| `strategy` | 否 | 策略名或扫描器名 |
| `price` | 否 | 信号价，用于计算滑点 |
| `stop_loss` | 否 | 策略止损 |
| `target_price` | 否 | 策略目标价 |
| `valid_until` | 否 | 信号有效期 |
| `confidence` | 否 | 评分/置信度 |
| `reason` / `risk_tags` | 否 | 策略理由、风险标签 |

## 标的画像字段

标的画像用于判断“股票标的本身是否有问题”，通过 `--stock-source` 输入。

| 字段 | 必填 | 说明 |
|---|---|---|
| `code` | 是 | 股票代码 |
| `score` | 否 | 标的评分，默认低于 60 视为风险 |
| `trend` | 否 | 趋势状态，包含 `DOWN`/`弱`/`破位` 等会触发风险 |
| `avg_volume` | 否 | 日均成交量，默认低于 500000 视为流动性不足 |
| `market_cap` | 否 | 市值，支持 `亿`/`万`/`B`/`M` 后缀 |
| `volatility_pct` | 否 | 波动率百分比，默认高于 8 视为高波动 |
| `risk_tags` | 否 | 风险标签，如 `退市`、`低流动性`、`趋势转弱`、`追高风险` |

## 后续扩展方向

- 接入券商成交单导出格式适配器。
- 增加 Web UI：上传成交 CSV、策略信号、标的画像，查看错误分布、周/月复盘。
- 接入 LLM：把结构化指标和原始理由交给模型生成更细的心理复盘。
