#!/usr/bin/env python3
"""
Phase 3 · Selector — 按配额选出 Top 20（两桶各 10 条）

输入:  scored_articles.json
输出:  daily_brief.json

配额（SKILL.md Phase 3）：
  投资桶: Breaking×3(≥14), Analysis×3(≥15), Opinion×2(≥13), Research×1(≥12), TopStory×1
  AI桶:   Breaking×2(≥14), Analysis×4(≥15), Opinion×2(≥13), Research×1(≥12), TopStory×1

主题去重: Jaccard > 0.35 的同一事件只保留最高分
"""

import json
import logging
import re
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).parent.parent

log = logging.getLogger(__name__)

INVEST_QUOTAS = [
    ("Breaking",  3, 14),
    ("Analysis",  3, 15),
    ("Opinion",   2, 13),
    ("Research",  1, 12),
]
AI_QUOTAS = [
    ("Breaking",  2, 14),
    ("Analysis",  4, 15),
    ("Opinion",   2, 13),
    ("Research",  1, 12),
]
JACCARD_THRESHOLD_SAME_SOURCE = 0.15   # 同一信源相似文章直接去重
JACCARD_THRESHOLD_CROSS_SOURCE = 0.25  # 跨信源相同事件去重（含 assets_affected）
FALLBACK_MIN_SCORE = 10
TARGET_PER_BUCKET = 10

# 中英文停用词（简化版）
STOPWORDS = {
    "the", "a", "an", "is", "in", "of", "to", "and", "for", "on", "at",
    "with", "that", "this", "it", "as", "are", "was", "be", "has", "have",
    "by", "from", "will", "its", "or", "but", "not", "as", "new",
    "的", "了", "在", "是", "和", "与", "对", "为", "以", "由", "但",
}


# ── 事件指纹去重（v3.0）─────────────────────────────────────────────────────

def _extract_event_fingerprint(article: dict) -> str:
    """
    提取文章事件指纹，用于跨源同事件去重。
    规则：
    - 取 assets_affected 排序后 join（如 "anthropic|pentagon"）
    - assets_affected 为空时，取 title_zh 前8字
    - 单实体（只有1个资产）不参与去重，返回空字符串
    """
    assets = sorted([a.lower().strip() for a in article.get("assets_affected", []) if a.strip()])
    if len(assets) >= 2:
        return "|".join(assets)
    # 单实体或无资产：用标题前8字作弱指纹
    title_fp = article.get("title_zh", "")[:8].strip()
    if len(title_fp) >= 4:
        return f"title:{title_fp}"
    return ""  # 无法生成指纹，不参与去重


def _deduplicate_by_event(articles: list[dict]) -> tuple[list[dict], list[dict]]:
    """
    事件级去重：相同指纹只保留评分最高的一篇。
    返回 (保留列表, 去重日志列表)
    """
    event_groups: dict[str, list] = defaultdict(list)
    no_dedup: list = []
    dropped_log: list = []

    for art in articles:
        fp = _extract_event_fingerprint(art)
        if not fp:
            no_dedup.append(art)
        else:
            event_groups[fp].append(art)

    kept = list(no_dedup)

    for fp, group in event_groups.items():
        group.sort(key=lambda x: x.get("total_score", 0), reverse=True)
        kept.append(group[0])
        for dropped in group[1:]:
            dropped_log.append({
                "title_zh":     dropped.get("title_zh", ""),
                "source_name":  dropped.get("source_name", ""),
                "total_score":  dropped.get("total_score", 0),
                "dedup_reason": f"same_event:{fp}",
                "kept_instead": group[0].get("title_zh", ""),
            })
            log.info(f"[Dedup] 去重丢弃：{dropped.get('title_zh','')} "
                     f"({dropped.get('source_name','')}, {dropped.get('total_score',0)}分) "
                     f"→ 保留：{group[0].get('title_zh','')}")

    return kept, dropped_log


# ── 事件簇去重（v3.1）────────────────────────────────────────────────────────

def _deduplicate_by_cluster(articles: list[dict]) -> tuple[list[dict], list[dict]]:
    """
    LLM 语义标签去重：相同 event_cluster（非 standalone）只保留评分最高的一篇。
    这是第二层去重，在指纹去重之后、Jaccard 去重之前执行。
    """
    cluster_groups: dict[str, list] = defaultdict(list)
    standalone: list = []
    dropped_log: list = []

    for art in articles:
        cluster = art.get("event_cluster", "standalone").strip().lower()
        if not cluster or cluster == "standalone":
            standalone.append(art)
        else:
            cluster_groups[cluster].append(art)

    kept = list(standalone)

    for cluster, group in cluster_groups.items():
        group.sort(key=lambda x: x.get("total_score", 0), reverse=True)
        kept.append(group[0])
        for dropped in group[1:]:
            dropped_log.append({
                "title_zh":     dropped.get("title_zh", ""),
                "source_name":  dropped.get("source_name", ""),
                "total_score":  dropped.get("total_score", 0),
                "dedup_reason": f"same_cluster:{cluster}",
                "kept_instead": group[0].get("title_zh", ""),
            })
            log.info(f"[Cluster] 去重丢弃：{dropped.get('title_zh','')} "
                     f"({dropped.get('source_name','')}, {dropped.get('total_score',0)}分) "
                     f"→ 保留：{group[0].get('title_zh','')} [cluster={cluster}]")

    return kept, dropped_log


# ── Jaccard 去重 ──────────────────────────────────────────────────────────────

def _tokenize(text: str) -> set[str]:
    words = re.findall(r"[a-zA-Z\u4e00-\u9fff]+", text.lower())
    return {w for w in words if w not in STOPWORDS and len(w) > 1}


def _jaccard(a: dict, b: dict) -> float:
    """Jaccard 相似度，文本包含 title_zh + title + one_line + assets_affected"""
    def _text(art: dict) -> str:
        return " ".join([
            art.get("title_zh", ""),
            art.get("title", ""),
            art.get("one_line", ""),
            " ".join(art.get("assets_affected", [])),
        ])
    words_a = _tokenize(_text(a))
    words_b = _tokenize(_text(b))
    if not words_a or not words_b:
        return 0.0
    inter = words_a & words_b
    union = words_a | words_b
    return len(inter) / len(union)


def _dedup_jaccard(articles: list[dict]) -> list[dict]:
    """同一事件多篇报道只留最高分（已按分降序）。
    同源阈值 0.15，跨源阈值 0.25，均含 assets_affected 实体。
    """
    kept: list[dict] = []
    group_counter = 0
    for art in articles:
        duplicate = False
        for existing in kept:
            j = _jaccard(art, existing)
            # 同一信源用更低阈值（更容易去重）
            threshold = (JACCARD_THRESHOLD_SAME_SOURCE
                         if art.get("source_name") == existing.get("source_name")
                         else JACCARD_THRESHOLD_CROSS_SOURCE)
            if j > threshold:
                log.info(f"[Jaccard] 去重 j={j:.2f}>{threshold} "
                         f"({art.get('source_name','')}): {art.get('title_zh','')[:30]}")
                if "dedup_group" not in existing:
                    group_counter += 1
                    existing["dedup_group"] = f"event-{group_counter:03d}"
                art["dedup_group"] = existing["dedup_group"]
                duplicate = True
                break
        if not duplicate:
            kept.append(art)
    return kept


# ── 配额选取 ──────────────────────────────────────────────────────────────────

def _select_bucket(articles: list[dict], quotas: list[tuple],
                   bucket_name: str) -> list[dict]:
    if not articles:
        return []

    # 按分降序
    articles = sorted(articles, key=lambda a: a["total_score"], reverse=True)
    # Jaccard 去重
    articles = _dedup_jaccard(articles)

    if not articles:
        return []

    # Top Story：当日最高分，不限类型
    top_story = articles[0]
    top_story = {**top_story, "slot": "TopStory"}
    used_ids: set[str] = {top_story["id"]}
    selected = [top_story]

    # 逐配额填充
    for content_type, quota, min_score in quotas:
        candidates = [
            a for a in articles
            if a["id"] not in used_ids
            and a["content_type"] == content_type
            and a["total_score"] >= min_score
        ]
        for art in candidates[:quota]:
            selected.append({**art, "slot": content_type})
            used_ids.add(art["id"])

    # 不足 10 条时，用保底阈值补充（任意类型）
    if len(selected) < TARGET_PER_BUCKET:
        remain = TARGET_PER_BUCKET - len(selected)
        fallback = [
            a for a in articles
            if a["id"] not in used_ids and a["total_score"] >= FALLBACK_MIN_SCORE
        ]
        for art in fallback[:remain]:
            selected.append({**art, "slot": "Fallback"})
            used_ids.add(art["id"])

    # 按分再次排序（TopStory 始终第一）
    top = [a for a in selected if a.get("slot") == "TopStory"]
    rest = sorted([a for a in selected if a.get("slot") != "TopStory"],
                  key=lambda a: a["total_score"], reverse=True)
    final = (top + rest)[:TARGET_PER_BUCKET]

    # 分配 display_id
    prefix = "AI-" if bucket_name == "ai" else ""
    for rank, art in enumerate(final, start=1):
        art["rank"] = rank
        art["display_id"] = f"{prefix}{rank}"

    log.info(f"[select] {bucket_name} 桶: {len(final)} 条 "
             f"（TopStory={final[0]['total_score']}分，min={final[-1]['total_score']}分）")

    if len(final) < TARGET_PER_BUCKET:
        log.warning(f"[select] {bucket_name} 桶仅 {len(final)} 条（目标10条），将在消息末注明")

    return final


# ── 主函数 ────────────────────────────────────────────────────────────────────

def run_select(date: str, dry_run: bool, input_file: str = "scored_articles.json",
               output_file: str = "daily_brief.json") -> dict:
    data = json.loads(Path(input_file).read_text(encoding="utf-8"))
    articles = data.get("articles", [])

    invest_pool = [a for a in articles if a.get("track") == "INV"]
    ai_pool = [a for a in articles if a.get("track") == "AI"]

    log.info(f"[select] 输入: INV={len(invest_pool)} AI={len(ai_pool)}")

    # 第一层：事件指纹去重（assets_affected 精确匹配）
    invest_pool, invest_dropped = _deduplicate_by_event(invest_pool)
    ai_pool, ai_dropped = _deduplicate_by_event(ai_pool)
    log.info(f"[select] 指纹去重后: INV={len(invest_pool)} (去除{len(invest_dropped)}篇) "
             f"AI={len(ai_pool)} (去除{len(ai_dropped)}篇)")

    # 第二层：事件簇去重（LLM 语义标签，捕捉同事件跨源/跨角度报道）
    invest_pool, invest_cluster_dropped = _deduplicate_by_cluster(invest_pool)
    ai_pool, ai_cluster_dropped = _deduplicate_by_cluster(ai_pool)
    log.info(f"[select] 簇去重后: INV={len(invest_pool)} (去除{len(invest_cluster_dropped)}篇) "
             f"AI={len(ai_pool)} (去除{len(ai_cluster_dropped)}篇)")

    invest_selected = _select_bucket(invest_pool, INVEST_QUOTAS, "invest")
    ai_selected = _select_bucket(ai_pool, AI_QUOTAS, "ai")

    output = {
        "date": date,
        "selected_at": datetime.now(timezone.utc).isoformat(),
        "summary": {
            "invest_count": len(invest_selected),
            "ai_count": len(ai_selected),
            "invest_short": len(invest_selected) < TARGET_PER_BUCKET,
            "ai_short": len(ai_selected) < TARGET_PER_BUCKET,
        },
        "buckets": {
            "invest": invest_selected,
            "ai": ai_selected,
        },
    }

    if output_file:
        Path(output_file).write_text(
            json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        log.info(f"[select] 投资桶={len(invest_selected)} AI桶={len(ai_selected)} → {output_file}")

    return {"status": "success", "count": len(invest_selected) + len(ai_selected)}


if __name__ == "__main__":
    import argparse
    import os
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

    result = run_select(date=args.date, dry_run=False,
                        input_file="scored_articles.json",
                        output_file="daily_brief.json")
    print(result)
