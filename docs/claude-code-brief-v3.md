# Claude Code 修复指令 v3 · morning-brief 完整重构

## 背景与目标

当前系统存在三个核心问题：
1. 同一事件被多源重复报道，占用宝贵配额（如 Anthropic vs 五角大楼出现4次）
2. scorer.py 只用 RSS 摘要评分，信息量不足，内容字段质量低
3. 部分文章通过硬过滤规则（个股推荐/纯观点/PR稿）仍进入选取池

本次修复需要更新以下文件，然后做一次完整测试。

---

## Step 1：替换 references/ 目录下的配置文件

```bash
cd /Users/rebecca/Documents/INVERT.BOT/morning-brief-skill1

# 替换以下文件（使用我提供的新版本）：
# references/scoring.md     → scoring v3.0（新增硬过滤规则 + 全文感知）
# references/output-format.md → output-format v3.0（五维明细 + 格式模板）
```

---

## Step 2：升级 scripts/fetcher.py

**核心变化：新增全文抓取逻辑**

在现有 `fetch_source()` 函数抓取完 RSS 摘要后，增加 `fetch_full_texts()` 步骤：

```python
def fetch_full_text(url: str, domain: str) -> tuple[str | None, bool]:
    """尝试获取全文，返回 (text, is_full)"""
    PAYWALL_DOMAINS = {
        "bloomberg.com", "ft.com", "wsj.com",
        "economist.com", "barrons.com", "theinformation.com",
    }
    headers = {"User-Agent": "Mozilla/5.0 (compatible; MorningBrief/3.0)"}
    
    # 策略1：直接抓
    try:
        resp = requests.get(url, headers=headers, timeout=8)
        if resp.status_code == 200:
            text = extract_main_text(resp.text)   # 去除HTML标签提取正文
            if len(text) > 800:
                return text[:3000], True
    except Exception:
        pass
    
    # 策略2：付费域名尝试 archive.ph
    if any(d in domain for d in PAYWALL_DOMAINS):
        try:
            resp = requests.get(f"https://archive.ph/{url}", headers=headers, timeout=8)
            if resp.status_code == 200:
                text = extract_main_text(resp.text)
                if len(text) > 800:
                    return text[:3000], True
        except Exception:
            pass
    
    return None, False


def extract_main_text(html: str) -> str:
    """从HTML提取正文"""
    import re
    # 去除 script/style/nav
    html = re.sub(r'<(script|style|nav|header|footer)[^>]*>.*?</\1>',
                  '', html, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r'<[^>]+>', ' ', html)
    return re.sub(r'\s+', ' ', text).strip()


def fetch_full_texts(articles: list) -> list:
    """对所有文章异步尝试全文抓取，失败不阻塞"""
    for art in articles:
        try:
            text, is_full = fetch_full_text(art["url"], art.get("domain", ""))
            if is_full and text:
                art["full_text"]       = text
                art["has_full_text"]   = True
                art["content_quality"] = "full_text"
        except Exception:
            pass
        time.sleep(0.3)
    return articles
```

在 `run()` 函数的 RSS 抓取结束后、保存 `raw_articles.json` 之前，调用：
```python
all_articles = fetch_full_texts(all_articles)
```

每篇文章新增字段：
```python
article["full_text"]       = summary      # 默认等于摘要，全文抓取成功后更新
article["has_full_text"]   = False        # 全文抓取是否成功
article["content_quality"] = "summary_only"  # summary_only | full_text
article["domain"]          = domain       # 用于判断是否为付费域名
```

---

## Step 3：升级 scripts/scorer.py

**核心变化：使用全文评分 + 传入 content_quality 字段**

在 `build_prompt()` 函数中修改内容选择逻辑：

```python
def build_prompt(article: dict, prompt_template: str) -> str:
    # 优先用全文，失败时用摘要
    content = article.get("full_text") or article.get("summary", "")
    content_quality = "full_text" if article.get("has_full_text") else "summary_only"
    
    prompt = prompt_template
    prompt = prompt.replace("<<TITLE>>",           article.get("title", ""))
    prompt = prompt.replace("<<CONTENT>>",         content[:2000])
    prompt = prompt.replace("<<SOURCE>>",          article.get("source", ""))
    prompt = prompt.replace("<<PUBLISHED>>",       article.get("published", ""))
    prompt = prompt.replace("<<CONTENT_QUALITY>>", content_quality)
    return prompt
```

**注意**：scoring.md 的 Prompt 里占位符格式已改为 `<<FIELD>>`，确认 scorer.py 的 build_prompt() 用 `.replace()` 而不是 `.format()`。

---

## Step 4：完全替换 scripts/selector.py

这是改动最大的文件。**请用我提供的 selector.py 全量替换**（不是局部修改）。

核心新增逻辑：
1. `extract_event_fingerprint()` — 从 `assets_affected` 提取事件指纹
2. `deduplicate_by_event()` — 相同指纹只保留最高分一篇
3. `select_by_quota()` — 按配额筛选（原有逻辑优化）

---

## Step 5：验证测试

```bash
cd /Users/rebecca/Documents/INVERT.BOT/morning-brief-skill1

# 1. 验证环境和引用文件
python scripts/validate.py --check-all

# 2. 全链路干跑（不推送不写Obsidian）
python run_morning_brief.py --dry-run --date today

# 3. 重点检查 selector.py 的去重日志
# 运行后查看日志里是否有 "[Dedup] 去重丢弃" 的记录
# 如果今天有重复事件应该能看到

# 4. 确认 scorer.py 的全文抓取统计
# 日志里应该有 "[Fetch] 全文获取: X/Y 篇成功" 这一行

# 5. 格式验证：检查 Obsidian 文件
# 每篇文章应包含：
# ✅ `🟡 深度分析` · 最强维度：XXX X/4
# ✅ 📊 评分明细：市场联动X/4 · ...
# ✅ [核心事实] 含具体数字
# ✅ [值得关注] 含时间节点

# 6. 确认无问题后，真实运行一次
python run_morning_brief.py --date today
```

---

## 验收标准 checklist

**去重验证：**
- [ ] Anthropic vs 五角大楼这类多源报道同一事件，只出现一次
- [ ] 日志中有去重记录（`[Dedup] 去重丢弃`）
- [ ] 被去重的文章显示 `dedup_reason: same_event:...`

**全文抓取验证：**
- [ ] 日志中有全文抓取统计行
- [ ] `raw_articles.json` 中部分文章有 `has_full_text: true`
- [ ] `has_full_text: true` 的文章 `full_text` 长度明显大于 `summary`

**内容质量验证：**
- [ ] `[核心事实]` 字段包含具体数字（不是"摘要信息有限"）
- [ ] `[市场影响]` 包含具体资产/公司名称
- [ ] 没有个股推荐/ETF推荐/PR稿类文章进入最终列表
- [ ] 投资桶和AI桶均无明显重复事件

**格式验证：**
- [ ] 每篇文章有内容类型标签（中文）
- [ ] 每篇文章有最强维度标注（维度名+分数）
- [ ] 每篇文章末尾有五维评分明细
- [ ] Obsidian 文件只有顶部一个 frontmatter
