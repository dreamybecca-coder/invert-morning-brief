# 输出格式规范 v3.0
> 适用于 morning-brief Skill 1 · 开源版

---

## ⚠️ 核心约束（每次写代码前重读）

1. **全文件只有顶部一个 frontmatter**，每篇文章不得内嵌 YAML 块
2. **所有正文内容必须是中文**，包括标题、摘要、分析三段
3. **内容类型标签 + 五维评分明细** 每篇必须显示
4. 三段摘要合计目标 **100-150 字**，足够判断是否值得深挖

---

## Section 1 · Telegram 推送格式

### 1.1 消息结构

```
💹 投资快报 · {YYYY.MM.DD}
━━━━━━━━━━━━━━━━━━━━

[{N}] {title_zh}
{来源} · ⭐{总分}/20 · {内容类型标签}
{one_line}
🔗 {url}

（共 10 条，按评分降序）

━━━━━━━━━━━━━━━━━━━━
回复"深挖 {序号}"触发深度分析
```

```
🤖 AI产业链快报 · {YYYY.MM.DD}
━━━━━━━━━━━━━━━━━━━━

[AI-{N}] {title_zh}
{来源} · ⭐{总分}/20 · {内容类型标签}
{one_line}
🔗 {url}

（共 10 条）

━━━━━━━━━━━━━━━━━━━━
回复"深挖 AI-{序号}"触发深度分析
```

### 1.2 内容类型标签

| content_type | Telegram 标签 | Obsidian 标签 |
|---|---|---|
| Breaking | 🔴 快讯 | `🔴 快讯` |
| News | 🟠 报道 | `🟠 报道` |
| Analysis | 🟡 深度分析 | `🟡 深度分析` |
| Opinion | 💬 评论观点 | `💬 评论观点` |
| Research | 📊 研究报告 | `📊 研究报告` |
| Official | 📋 官方公告 | `📋 官方公告` |

### 1.3 推送规范

- 投资桶和 AI 桶分两条消息，间隔 **5 秒**
- 投资桶序号：1-10；AI 桶序号：AI-1 至 AI-10
- 当日文章不足 10 条时，末尾追加："今日 {N} 条（信源更新较少）"

---

## Section 2 · Obsidian Stage 1 格式

### 2.1 文件命名（固定规则）

```
{VAULT}/01-Projects/Invert-Bot/Morning-Brief/{YYYY-MM-DD}-morning-brief-Invest news.md
{VAULT}/01-Projects/AI-Narrative-Lab/Morning-Brief/{YYYY-MM-DD}-morning-brief-AI news.md
```

Python 生成文件名：
```python
if bucket == "invest":
    filename = f"{date}-morning-brief-Invest news.md"
    subdir   = "01-Projects/Invert-Bot/Morning-Brief"
else:
    filename = f"{date}-morning-brief-AI news.md"
    subdir   = "01-Projects/AI-Narrative-Lab/Morning-Brief"
filepath = os.path.join(vault_path, subdir, filename)
```

### 2.2 文件顶部 frontmatter（唯一，全文件共用）

```markdown
---
date: {YYYY-MM-DD}
bucket: {invest | ai}
total_articles: {N}
created_by: morning-brief-skill-v3
run_time: "{HH:MM}"
source_type: news
processing_tool: morning-brief
status: done
---
```

### 2.3 每篇文章格式（完整模板）

```markdown
### 【第{N}条】{title_zh} | {来源} | ⭐{总分}/20

`{内容类型标签}` · 最强维度：{最高分维度中文名} {最高分}/4

{one_line}

[核心事实] {fact（含具体数字或关键细节，2-3句，≤80字）}

[市场影响] {impact（含具体资产/公司/板块名称，1-2句，≤60字）}

[值得关注] {watch_next（含时间节点或指标名称，1句，≤40字）}

📊 评分明细：市场联动{m}/4 · 信息稀缺{e}/4 · 因果深度{c}/4 · 时效{u}/4 · 信源{s}/4

🔗 {url}

---
```

### 2.4 字段生成逻辑（formatter.py 实现）

```python
# 内容类型中文映射
TYPE_LABELS = {
    "Breaking":  "🔴 快讯",
    "News":      "🟠 报道",
    "Analysis":  "🟡 深度分析",
    "Opinion":   "💬 评论观点",
    "Research":  "📊 研究报告",
    "Official":  "📋 官方公告",
}

# 维度名称中文映射
DIM_NAMES = {
    "market_impact":    "市场联动",
    "information_edge": "信息稀缺",
    "causal_depth":     "因果深度",
    "urgency":          "时效紧迫",
    "source_authority": "信源权威",
}

def format_article_obsidian(article: dict, index: int) -> str:
    title_zh     = article.get("title_zh") or article.get("title", "")
    source       = article.get("source", "")
    score        = article.get("total", 0)
    content_type = article.get("content_type", "News")
    one_line     = article.get("one_line", "")
    fact         = article.get("fact", "摘要信息有限，建议阅读原文")
    impact       = article.get("impact", "影响待评估")
    watch_next   = article.get("watch_next", "持续关注市场动态")
    url          = article.get("url", "")
    scores       = article.get("scores", {})

    type_label = TYPE_LABELS.get(content_type, f"🟠 {content_type}")

    # 最强维度
    if scores:
        top_key   = max(scores, key=scores.get)
        top_name  = DIM_NAMES.get(top_key, top_key)
        top_score = scores[top_key]
        top_str   = f"{top_name} {top_score}/4"
    else:
        top_str = "未知"

    # 五维明细
    m = scores.get("market_impact", 0)
    e = scores.get("information_edge", 0)
    c = scores.get("causal_depth", 0)
    u = scores.get("urgency", 0)
    s = scores.get("source_authority", 0)
    score_line = f"市场联动{m}/4 · 信息稀缺{e}/4 · 因果深度{c}/4 · 时效{u}/4 · 信源{s}/4"

    return f"""
### 【第{index}条】{title_zh} | {source} | ⭐{score}/20

`{type_label}` · 最强维度：{top_str}

{one_line}

[核心事实] {fact}

[市场影响] {impact}

[值得关注] {watch_next}

📊 评分明细：{score_line}

🔗 {url}

---"""

def format_obsidian_file(articles: list, bucket: str, date: str, run_time: str) -> str:
    """生成完整 Obsidian 文件内容"""
    
    # frontmatter（全文件唯一）
    frontmatter = f"""---
date: {date}
bucket: {bucket}
total_articles: {len(articles)}
created_by: morning-brief-skill-v3
run_time: "{run_time}"
source_type: news
processing_tool: morning-brief
status: done
---"""

    # 文件标题
    date_cn = f"{date[:4]}年{date[5:7]}月{date[8:10]}日"
    if bucket == "invest":
        header = f"# 💹 投资快报 · {date_cn}"
    else:
        header = f"# 🤖 AI产业链快报 · {date_cn}"

    # 文章列表
    articles_text = ""
    for i, article in enumerate(articles, 1):
        articles_text += format_article_obsidian(article, i)

    # 页脚
    from datetime import datetime
    footer = f"\n*生成时间：{datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ')} | 共{len(articles)}条 | 运行日志：`00-Inbox/_Processed/brief-log-{date}.json`*"

    return frontmatter + "\n\n" + header + "\n\n---\n" + articles_text + footer
```

---

## Section 3 · 正确输出样本（Few-shot 锚点）

```markdown
---
date: 2026-03-07
bucket: invest
total_articles: 10
created_by: morning-brief-skill-v3
run_time: "08:35"
source_type: news
processing_tool: morning-brief
status: done
---

# 💹 投资快报 · 2026年03月07日

---

### 【第1条】黑石26亿美元私募信贷基金限制赎回 | Bloomberg Markets | ⭐16/20

`🔴 快讯` · 最强维度：市场联动 4/4

私募信贷流动性风险警示，机构赎回压力传导至公开市场。

[核心事实] 黑石旗下 BCRED 私募信贷基金触发赎回门槛限制，本季度赎回申请超出基金资产5%上限，约26亿美元赎回请求被延后处理，为2023年以来首次触发。

[市场影响] 直接压制黑石股价（BX），私募信贷板块（蓝猫/Ares/Apollo）估值预期下调；触发市场对整个另类资产赎回限制的连锁担忧；投资级信用利差扩大风险上升。

[值得关注] 关注黑石Q1季报（4月中旬）是否披露更多赎回数据，以及Ares/Apollo是否跟进触发类似机制。

📊 评分明细：市场联动4/4 · 信息稀缺3/4 · 因果深度3/4 · 时效4/4 · 信源4/4

🔗 https://bloomberg.com/...

---
```

---

## ❌ 禁止清单

| 禁止行为 | 正确做法 |
|---|---|
| 每篇文章内嵌 YAML 块 | 全文件只有顶部一个 frontmatter |
| 英文标题未翻译 | title_zh 必须是中文 |
| `[核心事实]` 无具体数字 | 必须包含数字或可验证细节 |
| `[市场影响]` 无资产名称 | 必须提及股票/指数/商品名 |
| `[值得关注]` 无时间节点 | 必须包含"X月/本周/下周五"等锚点 |
| 三段合计超 200 字 | 目标 100-150 字，精炼不冗余 |
| 最强维度只写分数不写名称 | 必须写"最强维度：市场联动 4/4" |
| 内容类型用英文 | 必须用中文标签如"🟡 深度分析" |
| "详见原文链接"作为内容 | 严禁占位符，必须生成实质内容 |
