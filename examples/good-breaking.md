# Few-Shot 样本 · 优质 Breaking 快讯

> 用途：scorer.py 和 formatter.py 的审美锚点。
> 此样本代表评分 ≥16、内容类型 Breaking 的理想输出形态。

---

## 原始输入

```json
{
  "title": "Fed Holds Rates Steady, Signals Two Cuts Possible in 2026",
  "source": "Bloomberg Markets",
  "published": "2026-03-01T18:00:00Z",
  "summary": "Federal Reserve kept the federal funds rate unchanged at 4.25-4.5% at its March meeting, while updated projections showed officials penciling in two quarter-point cuts for 2026, down from three previously. Chair Powell cited persistent services inflation and a still-strong labor market."
}
```

## 评分结果

```json
{
  "track": "INV",
  "content_type": "Breaking",
  "scores": {
    "market_impact": 4,
    "information_edge": 3,
    "causal_depth": 2,
    "urgency": 4,
    "source_authority": 4
  },
  "total": 17,
  "one_line": "美联储按兵不动，点阵图降息预期从3次降至2次",
  "assets_affected": ["美债", "美元", "纳斯达克"]
}
```

## Telegram 输出（正确示例）

```
[3] Fed Holds Rates Steady, Signals Two Cuts in 2026
Bloomberg Markets · ⭐17/20 · 🔴 快讯
美联储按兵不动，点阵图降息预期从3次降至2次
🔗 https://bloomberg.com/...
```

## Obsidian Stage 1 输出（正确示例）

```markdown
## [3] Fed Holds Rates Steady, Signals Two Cuts Possible in 2026

source: Bloomberg Markets
url: https://bloomberg.com/...
published: 2026-03-01T18:00:00Z
content_type: Breaking
track: INV
score_total: 17
score_detail:
  market_impact: 4
  information_edge: 3
  causal_depth: 2
  urgency: 4
  source_authority: 4
assets_affected: [美债, 美元, 纳斯达克]
tags: [morning-brief, 2026-03-01, Breaking, INV]
deep_dive: false
deep_dive_path: ""

**摘要**：美联储按兵不动，点阵图降息预期从3次降至2次

**关键细节**：
- 利率维持4.25-4.5%不变，符合市场预期
- 点阵图中位数：2026年降息2次（此前预期3次），鹰派信号
- Powell强调服务业通胀和就业市场韧性是主要制约因素
```

---

## 常见错误对比

| ❌ 错误写法 | ✅ 正确写法 |
|---|---|
| one_line = "美联储宣布利率决定，市场关注" | one_line = "点阵图降息预期从3次降至2次" |
| one_line > 25字 | 严格控制在25字以内 |
| bullet: "这是重要消息值得关注" | bullet: "服务业CPI环比+0.4%，连续3个月超预期" |
| assets_affected = ["股票"] | assets_affected = ["美债", "美元", "纳斯达克"] |
