---
name: morning-brief
version: "3.0"
description: >
  全自动 AI 产业链 + 投资资讯聚合推送 Skill。
  每日 08:30 从 49 个精选信源抓取资讯，经五维评分、事件级去重、
  分桶筛选后，推送 Top 20 条至 Telegram，并结构化存档至 Obsidian。
  适用于需要每日追踪 AI 产业链投资机会、美股/港股市场、宏观经济的场景。
trigger:
  schedule: "30 8 * * *"      # 每日 08:30 上海时间（UTC+8 需在 cron 环境中设置 TZ）
  manual: "python run_morning_brief.py --date today"
outputs:
  - telegram_invest:  投资桶 Top 10（发至 TELEGRAM_INVEST_CHAT_ID）
  - telegram_ai:      AI产业链桶 Top 10（发至 TELEGRAM_AI_CHAT_ID）
  - obsidian_invest:  01-Projects/Invert-Bot/Morning-Brief/YYYY-MM-DD-morning-brief-Invest news.md
  - obsidian_ai:      01-Projects/AI-Narrative-Lab/Morning-Brief/YYYY-MM-DD-morning-brief-AI news.md
tools_required:
  - python3 >= 3.10
  - feedparser        # pip install feedparser
  - requests          # pip install requests
  - python-dotenv     # pip install python-dotenv
  - llm_api           # Kimi (moonshot-v1-8k) 或 Anthropic Claude
  - telegram_bot_api  # Telegram Bot Token
  - file_write        # Obsidian vault 写入权限
env_vars_required:
  - KIMI_API_KEY      # 或 ANTHROPIC_API_KEY（二选一）
  - TELEGRAM_BOT_TOKEN
  - TELEGRAM_INVEST_CHAT_ID
  - TELEGRAM_AI_CHAT_ID
  - OBSIDIAN_VAULT_PATH
references:
  sources:      references/sources.json       # 49个信源 URL + Tier 权重
  scoring:      references/scoring.md         # 五维评分 Prompt + 硬过滤规则
  domain_map:   references/domain-map.md      # AI 产业链六层地图 + 地缘关键词
  output_fmt:   references/output-format.md   # Telegram + Obsidian 格式模板
  agent_compat: references/agent-compat.md    # 多 Agent 兼容映射
examples:
  breaking:     examples/good-breaking.md
  analysis:     examples/good-analysis.md
changelog:
  v3.0: 事件级语义去重、scorer全文抓取、硬过滤规则、GitHub开源规范
  v2.0: 五维评分、分桶决策树、双频道推送
  v1.0: 初始版本
---

# morning-brief · Skill 1 · v3.0

> **执行宪法（每次运行前默认遵守）：**
> 1. 先侦察环境，再抓取，再评分——顺序不可逆
> 2. 事件级去重优先于文本相似度去重
> 3. 付费墙失败时优雅降级，不中断流程
> 4. 每个 Phase 有独立中间文件，单独可调试
> 5. 所有 Obsidian 写入用 str_replace，严禁全量重写

---

## Phase 0 · 环境侦察（Recon）

```bash
python scripts/recon.py \
  --sources references/sources.json \
  --output  sources_status.json
```

逐一检查每个 RSS 源的 HTTP 可达性（HEAD 请求，5秒超时）。
结果写入 `sources_status.json`：`{"source_id": {"reachable": true, "latency_ms": 230}}`

退出条件：`sources_status.json` 存在且可解析，可达源数量 ≥ 10 → 进入 Phase 1。
失败处理：可达源 < 10 时推送告警至 Telegram，仍继续执行。

---

## Phase 1 · 抓取（Fetch）

```bash
python scripts/fetcher.py \
  --sources  references/sources.json \
  --status   sources_status.json \
  --hours    24 \
  --output   raw_articles.json
```

### 抓取规则

| 参数 | 值 | 说明 |
|------|----|------|
| 时效窗口 | 24h | 严格过滤，不保留昨日文章 |
| S 层每源上限 | 5 条 | |
| A 层每源上限 | 3 条 | |
| B 层每源上限 | 2 条 | |
| C 层每源上限 | 0 条 | 日常不启用 |
| 批次间隔 | 3s | 防 rate limit |
| Hash 去重窗口 | 48h | 跨天 URL 去重 |

### 全文抓取（v3.0 新增）

RSS 摘要通常 < 200 字，质量严重不足。fetcher.py 在存储 RSS 摘要后，
**异步尝试**抓取每篇文章的全文（失败不阻塞主流程）：

```python
# 全文抓取顺序（每源最多尝试 2 个策略，总超时 8s）
strategies = [
    lambda url: url,                              # 直接抓原文
    lambda url: f"https://archive.ph/{url}",      # 付费墙绕过
]

for strategy in strategies:
    try:
        html = fetch_url(strategy(original_url), timeout=8)
        text = extract_main_text(html)            # 提取正文，去除导航/广告
        if len(text) > 500:
            article["full_text"] = text[:3000]    # 截取前3000字
            article["has_full_text"] = True
            break
    except Exception:
        continue

# 全文抓取失败时：
article["full_text"] = article["summary"]         # 降级用摘要
article["has_full_text"] = False
article["content_quality"] = "summary_only"       # 标注质量
```

退出条件：`raw_articles.json` 文章数 ≥ 20 → 进入 Phase 2。

---

## Phase 2 · 评分（Score）

```bash
python scripts/scorer.py \
  --input      raw_articles.json \
  --scoring    references/scoring.md \
  --domain-map references/domain-map.md \
  --output     scored_articles.json
```

### 分桶决策树

```
文章
 │
 ├─ 涉及 AI 产业链任意一层？→ YES → AI 桶（不再进投资桶）
 │
 ├─ 纯宏观/地缘/金融，与 AI 无直接关联？→ YES → 投资桶
 │
 └─ 无法归类 / 硬性过滤条件命中 → 丢弃（total = 0）
```

**硬性过滤（v3.0 新增，total 强制 = 0）：**
- 个股推荐 / ETF 推荐 / 理财产品推介
- Opinion 类文章且无具体数据支撑（纯观点无信息量）
- 内容为企业 PR 稿（无独立新闻价值）

评分 Prompt 完整内容见 `references/scoring.md`，此处黑盒调用。

**LLM 调用规范：**
```python
BATCH_SIZE     = 15      # 每批文章数
BATCH_INTERVAL = 3.0     # 批次间隔（秒）
MAX_RETRY      = 3       # 401/429 最大重试次数
RETRY_BACKOFF  = [30, 60, 120]  # 退避间隔（秒）
```

退出条件：`scored_articles.json` 存在，两桶均有评分结果 → 进入 Phase 3。

---

## Phase 3 · 事件级去重 + 精选（Select）

```bash
python scripts/selector.py \
  --input  scored_articles.json \
  --output daily_brief.json
```

### 3.1 事件级语义去重（v3.0 核心升级）

> **问题根源**：旧版 Jaccard 文本去重只能识别"文字重复"，
> 无法识别"同一事件被不同媒体报道多次"。
> 新版改为基于**命名实体组合**的事件指纹去重。

```python
def extract_event_fingerprint(article: dict) -> str:
    """
    提取文章的事件指纹：核心实体组合。
    相同指纹 = 同一事件。
    
    逻辑：
    1. 取 assets_affected（如 ["Anthropic", "Pentagon"]）
    2. 排序后 join（顺序无关）
    3. 如 assets_affected 为空，取 title_zh 前10字作为指纹
    """
    assets = sorted(article.get("assets_affected", []))
    if assets:
        return "|".join(assets).lower()
    return article.get("title_zh", "")[:10]


def deduplicate_by_event(articles: list) -> list:
    """
    同一事件指纹，只保留评分最高的一篇。
    
    规则：
    - 相同指纹的文章视为同一事件
    - 保留 total 最高的一篇
    - 次高的文章标记为 dedup_reason: "same_event"，计入日志但不进入选取池
    
    特殊处理：
    - 指纹为空或长度 < 3 的文章不参与事件去重（视为独立事件）
    - 单实体指纹（如只有 "NVDA"）不参与去重（避免误杀）
    """
    from collections import defaultdict
    
    event_groups = defaultdict(list)
    no_dedup = []
    
    for art in articles:
        fp = extract_event_fingerprint(art)
        if len(fp) < 3 or fp.count("|") == 0:
            # 指纹太短或单实体：不去重
            no_dedup.append(art)
        else:
            event_groups[fp].append(art)
    
    result = list(no_dedup)
    for fp, group in event_groups.items():
        # 按评分降序，只保留第一篇
        group.sort(key=lambda x: x["total"], reverse=True)
        result.append(group[0])
        # 记录被去重的文章（用于日志）
        for dropped in group[1:]:
            dropped["dedup_reason"] = f"same_event:{fp}"
    
    return result
```

### 3.2 每桶配额

**投资桶 Top 10：**

| 内容类型 | 配额 | 最低分 |
|----------|------|--------|
| Breaking 快讯 | 3 | ≥ 14 |
| Analysis 深度 | 3 | ≥ 15 |
| Opinion 观点 | 2 | ≥ 13 |
| Research 研报 | 1 | ≥ 12 |
| Top Story 头条 | 1 | 当日最高分 |

**AI 产业链桶 Top 10：**

| 内容类型 | 配额 | 最低分 |
|----------|------|--------|
| Breaking 快讯 | 2 | ≥ 14 |
| Analysis 深度 | 4 | ≥ 15 |
| Opinion 观点 | 2 | ≥ 13 |
| Research 论文 | 1 | ≥ 12 |
| Top Story 头条 | 1 | 当日最高分 |

配额不足时：依次降低分数线至 ≥ 10，仍不足则以实际数量推送，末尾注明"今日 X 条"。

退出条件：`daily_brief.json` 两桶各有文章 → 进入 Phase 4。

---

## Phase 4 · 格式化 + 推送（Format & Push）

```bash
python scripts/formatter.py \
  --input    daily_brief.json \
  --template references/output-format.md \
  --output   formatted_brief.json

python scripts/pusher.py \
  --brief    formatted_brief.json \
  --vault    $OBSIDIAN_VAULT_PATH
```

格式规范见 `references/output-format.md`。
Few-shot 样本见 `examples/`。

退出条件：
- Telegram 两条消息发送成功（返回 message_id）
- Obsidian 两个文件写入成功（size > 500 bytes）
→ Phase 4 完成，记录 `status: success`

---

## Phase 5 · 日志归档（Log）

```bash
python scripts/logger.py --date today
```

日志写入：
```
{VAULT}/00-Inbox/_Processed/brief-log-YYYY-MM-DD.json
```

包含：运行时长 / 各源抓取量 / 评分分布 / 去重统计 / 推送状态 / token 用量估算。

---

## 全局错误处理

| 错误类型 | 处理方式 |
|----------|----------|
| RSS 源不可达 | 跳过，记录日志，继续 |
| 全文抓取失败 | 降级用摘要，标注 content_quality: summary_only |
| LLM API 401 | 退避重试 3 次（30s/60s/120s），失败则跳过该批次 |
| LLM API 429 | 同上 |
| Obsidian 写入失败 | 备份至 `~/morning-brief-backup/`，不影响 Telegram |
| Telegram 推送失败 | 重试 3 次（间隔 10s），失败记录日志 |

---

## 快速验证

```bash
# 验证环境和引用文件
python scripts/validate.py --check-all

# 全链路干跑（不推送、不写 Obsidian）
python run_morning_brief.py --dry-run --date today

# 单 Phase 调试
python run_morning_brief.py --phase score --date today --dry-run
```
