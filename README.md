# 🤖 Invert Morning Brief

> AI 产业链 + 投资资讯每日自动聚合系统
> 全自动 · 每日 08:30 · Telegram 推送 · Obsidian 存档

---

## 核心功能

每天早上 8:30，系统自动：

1. 从 **49 个精选信源**（Bloomberg / SemiAnalysis / MIT Tech Review 等）抓取过去 24 小时资讯
2. 尝试绕过付费墙获取全文，失败时优雅降级
3. 用 **五维评分体系**（市场联动 / 信息稀缺 / 因果深度 / 时效 / 信源权威）对每篇文章打分
4. 执行**事件级语义去重**，同一事件多源报道只保留最高分一篇
5. 分投资桶 / AI 产业链桶各推送 Top 10 至 **Telegram**
6. 结构化存档至 **Obsidian**（含内容类型标签 + 五维评分明细 + 三段中文摘要）

---

## 效果示例

**Telegram 推送**（每日两条消息）：

```
💹 投资快报 · 2026.03.07
━━━━━━━━━━━━━━━━━━━━

[1] 黑石26亿美元私募信贷基金限制赎回
Bloomberg Markets · ⭐16/20 · 🔴 快讯
私募信贷赎回门槛触发，机构流动性压力向公开市场传导
🔗 https://bloomberg.com/...
```

**Obsidian 存档**（每日两个 Markdown 文件）：

```
01-Projects/Invert-Bot/Morning-Brief/2026-03-07-morning-brief-Invest news.md
01-Projects/AI-Narrative-Lab/Morning-Brief/2026-03-07-morning-brief-AI news.md
```

每篇文章包含：内容类型标签 · 最强维度评分 · 三段中文摘要 · 五维评分明细

---

## 快速开始

### 1. 克隆仓库

```bash
git clone https://github.com/your-username/invert-morning-brief.git
cd invert-morning-brief
```

### 2. 安装依赖

```bash
pip install -r requirements.txt
```

### 3. 配置环境变量

```bash
cp .env.example .env
# 编辑 .env，填入你的 API Keys
```

必填项：

| 变量 | 说明 |
|------|------|
| `KIMI_API_KEY` | Moonshot AI API Key（或用 `ANTHROPIC_API_KEY`）|
| `TELEGRAM_BOT_TOKEN` | Telegram Bot Token |
| `TELEGRAM_INVEST_CHAT_ID` | 投资桶推送频道 ID |
| `TELEGRAM_AI_CHAT_ID` | AI 桶推送频道 ID（可与投资桶相同）|
| `OBSIDIAN_VAULT_PATH` | Obsidian Vault 本地路径 |

### 4. 验证环境

```bash
python scripts/validate.py --check-all
```

### 5. 干跑测试（不推送、不写文件）

```bash
python run_morning_brief.py --dry-run --date today
```

### 6. 设置每日自动运行

```bash
# 编辑 crontab
crontab -e

# 添加以下行（08:30 上海时间）
30 8 * * * cd /path/to/invert-morning-brief && /usr/bin/python3 run_morning_brief.py --date today >> logs/cron.log 2>&1
```

**macOS 注意**：确保 Mac 在 08:30 不处于睡眠状态。推荐在系统设置中关闭自动睡眠，或使用 `launchd` 替代 cron。

---

## 项目结构

```
invert-morning-brief/
│
├── run_morning_brief.py      # 主入口，Phase 编排器
│
├── scripts/                  # 各 Phase 执行脚本
│   ├── recon.py              # Phase 0: 信源可达性检查
│   ├── fetcher.py            # Phase 1: RSS 抓取 + 全文提取
│   ├── scorer.py             # Phase 2: 五维评分（调用 LLM）
│   ├── selector.py           # Phase 3: 事件去重 + 配额筛选
│   ├── formatter.py          # Phase 4a: 格式化
│   ├── pusher.py             # Phase 4b: Telegram 推送 + Obsidian 写入
│   ├── logger.py             # Phase 5: 日志归档
│   └── validate.py           # 环境验证工具
│
├── references/               # 规则配置文件（Skill 文档）
│   ├── sources.json          # 49 个信源配置（URL + Tier + 权重）
│   ├── scoring.md            # 五维评分 Prompt（直接传入 LLM）
│   ├── output-format.md      # Telegram + Obsidian 格式规范
│   ├── domain-map.md         # AI 产业链六层地图 + 关键词权重
│   └── agent-compat.md       # 多 Agent 运行环境兼容说明
│
├── examples/                 # Few-shot 样本（格式锚点）
│   ├── good-breaking.md      # 优质快讯样本
│   └── good-analysis.md      # 优质深度分析样本
│
├── SKILL.md                  # Skill 主文档（完整设计规范）
├── requirements.txt
├── .env.example
└── README.md
```

---

## 信源列表

49 个精选信源，分两桶：

**投资桶（24 源）**：Bloomberg / FT / Reuters / WSJ / The Economist / Wolf Street / Seeking Alpha / Barron's / CNBC / Axios / Financial Times Economy / Wall Street Journal / 华尔街见闻 / 36Kr 投资 / 富途牛牛 ...

**AI 产业链桶（25 源）**：SemiAnalysis / MIT Tech Review / Anthropic Blog / OpenAI Blog / Wired AI / IEEE Spectrum / The Information / Interconnects / DataCenter Dynamics / arXiv cs.AI / 机器之心 / 量子位 / 36Kr AI / 少数派 ...

完整配置见 `references/sources.json`。

---

## 评分体系说明

每篇文章由 LLM 在五个维度各打 0-4 分（总分 0-20）：

| 维度 | 说明 |
|------|------|
| 市场联动 | 对资产价格或产业格局的直接影响程度 |
| 信息稀缺 | 是否独家 / 有信息增量 |
| 因果深度 | 背景 → 触发 → 影响因果链完整度 |
| 时效紧迫 | 今天了解是否影响决策 |
| 信源权威 | Bloomberg/官方公告 > 独立分析师 > 聚合媒体 |

硬性过滤（自动丢弃）：
- 个股 / ETF 推荐文章
- 无数据支撑的纯观点文章
- 企业 PR 稿

---

## 去重机制

**v3.0 新增事件级语义去重**，解决同一事件被多个媒体报道导致的配额浪费。

原理：提取每篇文章的核心实体组合（如"Anthropic + Pentagon"）作为事件指纹，相同指纹只保留评分最高的一篇。

---

## 配合 Skill 2（deep-dive）使用

看到感兴趣的文章，在 Telegram 回复：

```
深挖 AI-3
深挖 投资-2 AI-5
```

Skill 2 将自动：
1. 多源情报收集（web search + 付费墙绕过）
2. NotebookLM 式多源交叉分析
3. 写入 Obsidian 02-Areas 深度笔记
4. 生成公众号素材草稿

Skill 2 仓库：[链接待补充]

---

## Token 消耗参考

| 操作 | 估算 Token |
|------|-----------|
| 每篇文章评分 | ~800 tokens |
| 每日 40 篇文章 | ~32,000 tokens |
| Kimi moonshot-v1-8k 费用 | ~¥0.5-1.0/天 |

---

## 技术栈

- Python 3.10+
- feedparser（RSS 解析）
- requests（HTTP 抓取）
- Moonshot AI / Anthropic Claude（评分和内容生成）
- Telegram Bot API（推送）
- Obsidian（本地知识库存档）

---

## 贡献

欢迎 PR 和 Issue，特别是：
- 新的高质量信源（请在 PR 中说明 Tier 评级理由）
- 评分体系改进
- 对其他 LLM 的适配

---

## License

MIT License · 自由使用，署名即可

---

*由 [Invert.bot](https://invert.bot) 开源 · AI 投资研究工具*
