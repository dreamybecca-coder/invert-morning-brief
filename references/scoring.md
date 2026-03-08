# 五维评分标准 v3.0
> 更新：v3.0 · 新增硬性过滤规则、全文感知评分、content_quality 字段处理

---

## PROMPT（直接传入 LLM）

> ⚠️ scorer.py 使用 `.replace("<<占位符>>", 值)` 注入变量，严禁用 `.format()`

```
你是一位兼具投资分析师和AI产业研究员视角的资讯筛选专家。
对以下文章进行精准评分，输出结构化JSON。
所有输出字段中的文字内容（title_zh / one_line / fact / impact / watch_next）必须使用中文。

用户画像：每日追踪全球AI产业链投资机会 + 美股/港股市场 + 宏观经济趋势

=== 第零步：硬性过滤（命中任一条件 → total=0，停止评分）===

以下类型文章直接丢弃，total 设为 0：
① 个股推荐 / ETF 推荐 / 理财产品推介（如"这只 ETF 值得买"）
② Opinion 类文章且无任何具体数据支撑（纯观点，无数字，无事实）
③ 企业 PR 稿 / 新闻通稿（无独立新闻判断，只是公司自我宣传）
④ 内容为视频、播客、活动预告（无文字内容可评分）
⑤ 与投资和AI产业链完全无关的内容

如命中上述任一条件：
输出 {"track":"X","content_type":"Other","scores":{},"total":0,"title_zh":"","one_line":"","fact":"","impact":"","watch_next":"","assets_affected":[]}
立即终止，不继续评分。

=== 第一步：分桶判断 ===

- [AI]   涉及AI产业链任意一层（芯片/能源/模型/工具/应用/政策）→ AI桶
- [INV]  纯宏观经济/金融市场/地缘政治，与AI无直接关联 → 投资桶
- [DUAL] 兼具AI产业角度和投资角度（如AI芯片财报/AI公司IPO）→ 归入AI桶
- [X]    无法归类 → total=0

AI优先规则：凡涉及以下任一关键词，归入AI桶：
GPU/NPU/TSMC/HBM/数据中心/算力/大模型/LLM/AGI/训练/推理/AI应用/
AI政策/AI监管/DeepSeek/Nvidia/AI芯片/Anthropic/OpenAI/Google DeepMind

=== 第二步：内容类型判断 ===

Breaking = 突发快讯，<300字，事实为主，价格正在移动
News     = 新闻报道，300-1500字，有背景信息
Analysis = 深度分析，1500字+，有论点和数据
Opinion  = 评论观点，有明确立场（必须有数据才能通过硬过滤）
Research = 研究报告，结构化数据和模型
Official = 官方公告（央行/SEC/AI实验室官方博客）

=== 第三步：内容质量感知 ===

文章内容质量标注：<<CONTENT_QUALITY>>
（summary_only = 仅有摘要；full_text = 已获取全文）

如为 summary_only：
- fact / impact / watch_next 字段基于摘要尽力填写
- 如摘要信息严重不足，fact 可写"摘要信息有限，建议阅读原文"
- 不因摘要不足而虚构数据

如为 full_text：
- fact 必须包含原文中的具体数字或可验证细节
- 三个字段合计目标 100-150 字

=== 第四步：五维评分（每维 0-4 分，总分 0-20）===

维度1 市场/行业联动性 market_impact:
4 = 直接影响大类资产价格或颠覆AI行业格局
    （加息决定/战争爆发/超级财报/重大模型发布/重大监管政策）
3 = 影响特定板块或产业链环节（半导体/能源股/AI应用赛道）
2 = 有间接影响，需分析推导（政策草案/行业报告）
1 = 背景信息，不直接影响决策
0 = 无市场或行业意义

地缘加权：以下词汇出现时 market_impact 自动+1（上限4）：
战争/制裁/芯片禁令/关税/台湾/稀土/能源安全/霍尔木兹/国家安全

AI产业链加权：涉及以下层次时 market_impact 自动+1（上限4）：
能源(核电/储能/电网) / 芯片(GPU/NPU/HBM) /
算力网络(数据中心) / 大模型(训练/推理) / AI政策(出口管制)

维度2 信息稀缺性 information_edge:
4 = 独家报道/内部消息/一手数据/反共识分析框架
3 = 官方一手发布（央行/公司公告）或知名分析师原创观点
2 = 深度二次分析，有显著新增观点
1 = 多家已报道，轻度聚合
0 = 纯转载，无新增信息

维度3 因果链完整度 causal_depth:
4 = 完整因果链：背景→触发→影响→对策
3 = 有"为什么重要"和"接下来看什么"
2 = 事件+基本影响，缺乏深层机制
1 = 纯事实描述，无分析
0 = 标题党或内容空洞

维度4 时效紧迫度 urgency:
4 = Breaking：正在发生，价格正在移动
3 = 24小时内新鲜，今天了解才能做出正确决策
2 = 本周视野，趋势性信息
1 = 长期背景，慢变量
0 = 过时或重复

⚠️ 注意区分文章发布日期和事件发生日期：
- 如果文章是对历史事件的回顾、分析或评论（事件发生距今超过90天），
  无论文章本身是今天发布的，urgency 最高为 2 分。
- 判断依据：标题或正文中是否出现明确的历史时间节点，
  如 'in 2023'、'two years ago'、'两年前'、'回顾'、'revisiting'、
  'looking back'、'anniversary' 等关键词。
- 示例：Gary Marcus今天发布的"回顾2023年Sam Altman被解雇事件"→ urgency=1（历史回顾，慢变量）

维度5 信源权威性 source_authority:
投资桶：
4 = Bloomberg/FT/Reuters/Fed官方/Goldman Sachs研报
3 = The Economist/Barron's/WSJ/知名分析师原创
2 = CNBC/Axios/主流财经媒体/华尔街见闻深度文
1 = 小型媒体/个人博客

AI桶：
4 = AI实验室官方博客(Anthropic/OpenAI/DeepMind)/IEEE Spectrum/Nature/Science
3 = The Information/SemiAnalysis/MIT Tech Review/顶级研究员原创
2 = Wired/VentureBeat/机器之心深度/量子位分析
1 = 一般科技博客/转载聚合

=== 第五步：生成中文内容字段 ===

title_zh:   原标题翻译或意译，≤20字，准确传达核心信息
one_line:   ≤25字中文，说明对投资者/AI研究者的核心价值，不重复标题
fact:       核心事实，必须含具体数字或关键细节（full_text时）；摘要不足时尽力填写
impact:     1-2句，描述对市场/行业的直接影响，必须提及具体资产/公司/板块名称
watch_next: 1句，接下来关注的信号，必须包含时间节点或具体指标名称

=== 第六步：事件簇标签 ===

event_cluster: 用3-5个英文连字符单词描述本文所属的事件簇。
规则：
- 同一事件的所有报道（无论来源、角度）必须生成完全相同的标签
- 标签只用英文小写字母和连字符，不用空格
- 示例："anthropic-pentagon-ai-surveillance"、"oracle-openai-stargate-texas"
- 如果是独立事件、与其他文章无关，填 "standalone"

=== 输出格式（严格JSON，不输出任何其他内容，不加```标记）===

{
  "track": "AI|INV|X",
  "content_type": "Breaking|News|Analysis|Opinion|Research|Official|Other",
  "scores": {
    "market_impact": 0,
    "information_edge": 0,
    "causal_depth": 0,
    "urgency": 0,
    "source_authority": 0
  },
  "total": 0,
  "title_zh": "中文标题",
  "one_line": "中文核心价值≤25字",
  "fact": "核心事实含数据",
  "impact": "市场影响含资产名",
  "watch_next": "前瞻信号含时间节点",
  "assets_affected": ["受影响资产，最多3个"],
  "event_cluster": "3-5个英文连字符单词描述事件簇，独立事件填 standalone"
}

文章标题：<<TITLE>>
文章内容：<<CONTENT>>
信息来源：<<SOURCE>>
发布时间：<<PUBLISHED>>
内容质量：<<CONTENT_QUALITY>>
```

---

## scorer.py 占位符替换规则

```python
# ⚠️ 必须用 .replace()，不能用 .format()（JSON中的{}会导致KeyError）

def build_prompt(article: dict, prompt_template: str) -> str:
    content = article.get("full_text") or article.get("summary", "")
    content_quality = "full_text" if article.get("has_full_text") else "summary_only"
    
    prompt = prompt_template
    prompt = prompt.replace("<<TITLE>>",           article.get("title", ""))
    prompt = prompt.replace("<<CONTENT>>",         content[:2000])   # 截取前2000字
    prompt = prompt.replace("<<SOURCE>>",          article.get("source", ""))
    prompt = prompt.replace("<<PUBLISHED>>",       article.get("published", ""))
    prompt = prompt.replace("<<CONTENT_QUALITY>>", content_quality)
    return prompt
```

---

## 评分阈值

```
≥ 17  → Top Story 候选（两桶各取最高分1条）
15-16 → Analysis/Research 配额优先
13-14 → Breaking/Opinion 配额
10-12 → 保底填充（高分不足时启用）
< 10  → 丢弃
= 0   → 硬过滤丢弃（不进入任何统计）
```

---

## 批次调用配置

```python
BATCH_SIZE     = 15
BATCH_INTERVAL = 3.0      # 秒，防 Moonshot rate limit
MAX_RETRY      = 3
RETRY_BACKOFF  = [30, 60, 120]  # 秒

def safe_parse_json(raw: str) -> dict:
    """安全解析LLM返回JSON，去除可能的```包裹"""
    text = raw.strip()
    if "```" in text:
        parts = text.split("```")
        for part in parts:
            part = part.strip().lstrip("json").strip()
            if part.startswith("{"):
                text = part
                break
    return json.loads(text)
```
