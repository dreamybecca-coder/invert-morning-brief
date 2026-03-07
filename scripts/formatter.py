#!/usr/bin/env python3
"""
Phase 4a · Formatter — 格式化输出 v2.2

输入:  daily_brief.json
输出:  formatted_brief.json

格式规范见 references/output-format.md。
变更（v2.1）：
  - Telegram 标题改用 title_zh（中文）
  - Obsidian: 全文件唯一 frontmatter + 纯中文段落格式，无文章内嵌 YAML
变更（v2.2）：
  - Obsidian 每篇文章新增：内容类型标签 + 最强维度 + 五维评分明细行
"""

import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).parent.parent

# Telegram 用简短标签
TYPE_LABELS = {
    "Breaking":  "🔴 快讯",
    "News":      "🟠 报道",
    "Analysis":  "🟡 深度",
    "Opinion":   "💬 观点",
    "Research":  "📊 研报",
    "Official":  "📋 官方",
}

# Obsidian 用完整标签
TYPE_LABELS_OB = {
    "Breaking":  "🔴 快讯",
    "News":      "🟠 报道",
    "Analysis":  "🟡 深度分析",
    "Opinion":   "💬 评论观点",
    "Research":  "📊 研究报告",
    "Official":  "📋 官方公告",
}

# 五维名称（Obsidian 展示用）
DIM_NAMES = {
    "market_impact":     "市场联动",
    "information_edge":  "信息稀缺",
    "causal_depth":      "因果深度",
    "urgency":           "时效紧迫",
    "source_authority":  "信源权威",
}

# 维度展示顺序
DIM_ORDER = ["market_impact", "information_edge", "causal_depth", "urgency", "source_authority"]


def _top_dim(scores: dict) -> str:
    """返回最强维度的中文名称和分值，如 '因果深度 4/4'"""
    if not scores:
        return "—"
    best_key = max(scores, key=lambda k: scores.get(k, 0))
    best_val = scores.get(best_key, 0)
    return f"{DIM_NAMES.get(best_key, best_key)} {best_val}/4"


def _score_detail(scores: dict) -> str:
    """返回五维评分明细行，如 '市场联动3/4 · 信息稀缺2/4 · 因果深度4/4 · 时效紧迫3/4 · 信源权威2/4'"""
    parts = []
    for dim in DIM_ORDER:
        val = scores.get(dim, 0)
        parts.append(f"{DIM_NAMES[dim]}{val}/4")
    return " · ".join(parts)


SEP = "━" * 20


# ── Telegram 格式 ─────────────────────────────────────────────────────────────

def _format_telegram(date: str, articles: list[dict], bucket: str) -> str:
    date_fmt = datetime.strptime(date, "%Y-%m-%d").strftime("%Y.%m.%d")
    short_note = ""

    if bucket == "invest":
        header = f"💹 投资快报 · {date_fmt}"
        footer = '回复"深挖 序号"触发深度分析 | Skill 2'
    else:
        header = f"🤖 AI产业链快报 · {date_fmt}"
        footer = '回复"深挖 AI-序号"触发深度分析 | Skill 2'

    if len(articles) < 10:
        short_note = f"\n（今日 {len(articles)} 条）"

    lines = [header, SEP, ""]

    for art in articles:
        display_id = art["display_id"]

        # 优先用 title_zh（中文），fallback 到英文原标题
        title = art.get("title_zh") or art.get("title", "")
        if len(title) > 40:
            title = title[:40] + "…"

        source = art.get("source_name", "")
        score = art.get("total_score", 0)
        label = TYPE_LABELS.get(art.get("content_type", "News"), "🟠 报道")
        one_line = art.get("one_line", "")
        url = art.get("url", "")

        lines.append(f"[{display_id}] {title}")
        lines.append(f"{source} · ⭐{score}/20 · {label}")
        lines.append(one_line)
        lines.append(f"🔗 {url}")
        lines.append("")

    lines.append(SEP)
    lines.append(footer + short_note)

    return "\n".join(lines)


# ── Obsidian 格式 ─────────────────────────────────────────────────────────────

def _format_obsidian(date: str, articles: list[dict], bucket: str) -> str:
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    date_cn = datetime.strptime(date, "%Y-%m-%d").strftime("%Y年%m月%d日")
    run_time = datetime.now().strftime("%H:%M")

    if bucket == "invest":
        bucket_emoji = "💹"
        bucket_cn = "投资"
    else:
        bucket_emoji = "🤖"
        bucket_cn = "AI产业链"

    # ── 顶部唯一 frontmatter ──────────────────────────────────────────────────
    lines = [
        "---",
        f"date: {date}",
        f"bucket: {bucket}",
        f"total_articles: {len(articles)}",
        "created_by: morning-brief-skill-v1",
        f'run_time: "{run_time}"',
        "source_type: news",
        "processing_tool: morning-brief",
        "status: done",
        "---",
        "",
        f"# {bucket_emoji} {bucket_cn}快报 · {date_cn}",
        "",
        "---",
        "",
    ]

    # ── 每篇文章：纯中文段落，无内嵌 YAML ────────────────────────────────────
    for i, art in enumerate(articles, start=1):
        display_id = art.get("display_id", str(i))
        title_zh = art.get("title_zh") or art.get("title", "（无标题）")
        source = art.get("source_name", "")
        score = art.get("total_score", 0)
        one_line = art.get("one_line", "")
        fact = art.get("fact") or "详见原文"
        impact = art.get("impact") or "影响待评估"
        watch_next = art.get("watch_next") or "持续关注"
        url = art.get("url", "")
        scores = art.get("scores", {})
        content_type = art.get("content_type", "News")
        type_label_ob = TYPE_LABELS_OB.get(content_type, "🟠 报道")
        top_dim_str = _top_dim(scores)
        detail_str = _score_detail(scores)

        lines.append(f"### 【第{i}条】{title_zh} | {source} | ⭐{score}/20")
        lines.append("")
        lines.append(f"`{type_label_ob}` · 最强维度：{top_dim_str}")
        lines.append("")
        if one_line:
            lines.append(one_line)
            lines.append("")
        lines.append(f"[核心事实] {fact}")
        lines.append("")
        lines.append(f"[市场影响] {impact}")
        lines.append("")
        lines.append(f"[值得关注] {watch_next}")
        lines.append("")
        lines.append(f"📊 评分明细：{detail_str}")
        lines.append("")
        lines.append(f"🔗 {url}")
        lines.append("")
        lines.append("---")
        lines.append("")

    # ── 页脚 ──────────────────────────────────────────────────────────────────
    lines.append(
        f"*生成时间：{now_str} | 共{len(articles)}条 | "
        f"运行日志：`00-Inbox/_Processed/brief-log-{date}.json`*"
    )

    return "\n".join(lines)


# ── 主函数 ────────────────────────────────────────────────────────────────────

def run_format(date: str, dry_run: bool, input_file: str = "daily_brief.json",
               output_file: str = "formatted_brief.json") -> dict:
    brief = json.loads(Path(input_file).read_text(encoding="utf-8"))

    invest_articles = brief["buckets"]["invest"]
    ai_articles = brief["buckets"]["ai"]

    invest_tg = _format_telegram(date, invest_articles, "invest")
    ai_tg = _format_telegram(date, ai_articles, "ai")
    invest_ob = _format_obsidian(date, invest_articles, "invest")
    ai_ob = _format_obsidian(date, ai_articles, "ai")

    output = {
        "date": date,
        "invest": {"telegram": invest_tg, "obsidian": invest_ob},
        "ai": {"telegram": ai_tg, "obsidian": ai_ob},
    }

    if output_file:
        Path(output_file).write_text(
            json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    total = len(invest_articles) + len(ai_articles)
    return {"status": "success", "count": total}


if __name__ == "__main__":
    import argparse, os, logging
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")

    env_file = ROOT / ".env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())

    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default=datetime.now().strftime("%Y-%m-%d"))
    args = parser.parse_args()

    result = run_format(date=args.date, dry_run=False,
                        input_file="daily_brief.json",
                        output_file="formatted_brief.json")
    print(result)
