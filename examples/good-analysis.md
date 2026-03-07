# Few-Shot 样本 · 优质深度分析（Analysis）

> 用途：评分和格式化的审美锚点。
> 此样本代表评分 ≥18、内容类型 Analysis 的理想输出形态。

---

## 原始输入

```json
{
  "title": "GB300 Production Begins: CoWoS Yield Jumps 40%, TSMC Sole Beneficiary",
  "source": "SemiAnalysis",
  "published": "2026-03-01T10:00:00Z",
  "summary": "Nvidia's GB300 Blackwell Ultra architecture has entered mass production at TSMC. CoWoS-S packaging yield rates have improved to 82% from 58% in H100 era, driven by TSMC's refined bonding process. SK Hynix HBM4 wins exclusive supply for GB300, with Samsung locked out. Cloud hyperscalers have placed orders totaling 2.4M units for H2 2026 delivery. Power consumption per chip drops from 700W to 580W despite 2.5x performance uplift."
}
```

## 评分结果

```json
{
  "track": "AI",
  "content_type": "Analysis",
  "scores": {
    "market_impact": 4,
    "information_edge": 4,
    "causal_depth": 4,
    "urgency": 3,
    "source_authority": 4
  },
  "total": 19,
  "one_line": "GB300量产，台积电CoWoS良率跳升至82%，SK Hynix独占HBM4",
  "assets_affected": ["NVDA", "TSM", "000660.KS"]
}
```

## Telegram 输出（正确示例）

```
[AI-1] GB300 Production Begins: CoWoS Yield Jumps 40%…
SemiAnalysis · ⭐19/20 · 🟡 深度
GB300量产，台积电CoWoS良率跳升至82%，SK Hynix独占HBM4
🔗 https://semianalysis.com/...
```

## Obsidian Stage 1 输出（正确示例）

```markdown
## [AI-1] GB300 Production Begins: CoWoS Yield Jumps 40%, TSMC Sole Beneficiary

source: SemiAnalysis
url: https://semianalysis.com/...
published: 2026-03-01T10:00:00Z
content_type: Analysis
track: AI
score_total: 19
score_detail:
  market_impact: 4
  information_edge: 4
  causal_depth: 4
  urgency: 3
  source_authority: 4
assets_affected: [NVDA, TSM, SK Hynix]
industry_layer: 芯片层/算力基础设施层
tags: [morning-brief, 2026-03-01, Analysis, AI]
deep_dive: false
deep_dive_path: ""

**摘要**：GB300量产，台积电CoWoS良率跳升至82%，SK Hynix独占HBM4

**关键细节**：
- CoWoS-S封装良率从H100时代58%升至82%，台积电独家，竞争壁垒加深
- SK Hynix赢得GB300全部HBM4供应，三星被排除在外（股价信号）
- 超大规模云厂商H2 2026备货240万片，对应约$480亿营收预期
```

---

## 评分标准说明（为何此文得分19）

- **market_impact = 4**：直接影响Nvidia/TSMC/SK Hynix三家上市公司，涉及全球最大AI算力供应链
- **information_edge = 4**：独家良率数据（82%）和独家供应商锁定信息，市场此前不知
- **causal_depth = 4**：完整链条：技术突破(良率)→供应方赢家(TSMC/SKHynix)→需求方订单量→营收预期
- **urgency = 3**：量产已开始，重要但价格已部分反映，非当日Breaking
- **source_authority = 4**：SemiAnalysis Dylan Patel团队，半导体产业链最权威独立分析师
