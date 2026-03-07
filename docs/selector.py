#!/usr/bin/env python3
"""
selector.py · Phase 3
事件级去重 + 配额筛选 → daily_brief.json

v3.0: 升级为事件指纹去重，解决同一事件多源重复问题
"""

import argparse
import json
import logging
from collections import defaultdict
from pathlib import Path

log = logging.getLogger("selector")

# ── 配额配置 ──────────────────────────────────────────────────────────────────

QUOTAS = {
    "invest": {
        "Breaking":  {"slots": 3, "min_score": 14},
        "Analysis":  {"slots": 3, "min_score": 15},
        "Opinion":   {"slots": 2, "min_score": 13},
        "Research":  {"slots": 1, "min_score": 12},
        "Official":  {"slots": 1, "min_score": 12},
        "News":      {"slots": 3, "min_score": 11},  # 兜底
        "_top_story": {"slots": 1, "min_score": 0},  # 当日最高分，不受配额限制
        "_total": 10,
        "_fallback_min_score": 10,  # 配额不足时降低门槛
    },
    "ai": {
        "Breaking":  {"slots": 2, "min_score": 14},
        "Analysis":  {"slots": 4, "min_score": 15},
        "Opinion":   {"slots": 2, "min_score": 13},
        "Research":  {"slots": 2, "min_score": 12},
        "Official":  {"slots": 1, "min_score": 12},
        "News":      {"slots": 2, "min_score": 11},  # 兜底
        "_top_story": {"slots": 1, "min_score": 0},
        "_total": 10,
        "_fallback_min_score": 10,
    },
}

# ── 事件指纹去重 ──────────────────────────────────────────────────────────────

def extract_event_fingerprint(article: dict) -> str:
    """
    提取文章事件指纹。
    
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


def deduplicate_by_event(articles: list, bucket: str) -> tuple[list, list]:
    """
    事件级去重。
    
    返回：(保留列表, 去重日志列表)
    
    逻辑：
    1. 相同事件指纹 → 只保留评分最高的一篇
    2. 空指纹文章 → 不参与去重，全部保留
    3. 被去重的文章记录到日志（用于调试和统计）
    """
    event_groups: dict[str, list] = defaultdict(list)
    no_dedup: list = []
    dropped_log: list = []
    
    for art in articles:
        fp = extract_event_fingerprint(art)
        if not fp:
            no_dedup.append(art)
        else:
            event_groups[fp].append(art)
    
    kept = list(no_dedup)
    
    for fp, group in event_groups.items():
        # 按总分降序
        group.sort(key=lambda x: x.get("total", 0), reverse=True)
        kept.append(group[0])
        
        for dropped in group[1:]:
            dropped_log.append({
                "title_zh":    dropped.get("title_zh", ""),
                "source":      dropped.get("source", ""),
                "total":       dropped.get("total", 0),
                "dedup_reason": f"same_event:{fp}",
                "kept_instead": group[0].get("title_zh", ""),
            })
            log.info(f"[Dedup] 去重丢弃：{dropped.get('title_zh','')} "
                     f"({dropped.get('source','')}, {dropped.get('total',0)}分) "
                     f"→ 保留：{group[0].get('title_zh','')}")
    
    return kept, dropped_log


# ── 配额筛选 ──────────────────────────────────────────────────────────────────

def select_by_quota(articles: list, bucket: str) -> list:
    """
    按配额从候选池中选出 Top 10（或更少）。
    
    逻辑：
    1. 先找 Top Story（当日最高分，跨类型）
    2. 按内容类型分配配额
    3. 配额不足时降低分数线至 fallback_min_score
    4. 按总分降序排列最终结果
    """
    if not articles:
        return []
    
    quota_cfg = QUOTAS[bucket]
    total_slots = quota_cfg["_total"]
    fallback_min = quota_cfg["_fallback_min_score"]
    
    # 按评分降序排列候选池
    pool = sorted(articles, key=lambda x: x.get("total", 0), reverse=True)
    
    selected = []
    selected_ids = set()
    
    # Step 1: Top Story（最高分那篇，无论类型）
    if pool:
        top = pool[0]
        selected.append(top)
        selected_ids.add(top.get("url", id(top)))
        log.info(f"[Select] Top Story: {top.get('title_zh','')} ({top.get('total',0)}分)")
    
    # Step 2: 按内容类型配额填充
    for ctype, cfg in quota_cfg.items():
        if ctype.startswith("_"):
            continue
        slots     = cfg["slots"]
        min_score = cfg["min_score"]
        
        count = 0
        for art in pool:
            if art.get("url", id(art)) in selected_ids:
                continue
            if art.get("content_type") == ctype and art.get("total", 0) >= min_score:
                selected.append(art)
                selected_ids.add(art.get("url", id(art)))
                count += 1
                if count >= slots:
                    break
    
    # Step 3: 如果还不够 total_slots，降低分数线补充
    if len(selected) < total_slots:
        for art in pool:
            if len(selected) >= total_slots:
                break
            uid = art.get("url", id(art))
            if uid not in selected_ids and art.get("total", 0) >= fallback_min:
                selected.append(art)
                selected_ids.add(uid)
                log.info(f"[Select] 降级补充: {art.get('title_zh','')} ({art.get('total',0)}分)")
    
    # 最终按评分降序排列
    selected.sort(key=lambda x: x.get("total", 0), reverse=True)
    
    # 添加序号
    for i, art in enumerate(selected, 1):
        if bucket == "ai":
            art["display_index"] = f"AI-{i}"
        else:
            art["display_index"] = str(i)
        art["bucket_index"] = i
    
    log.info(f"[Select] {bucket} 桶最终选出 {len(selected)} 篇")
    return selected


# ── 主函数 ────────────────────────────────────────────────────────────────────

def run(input_path: str, output_path: str):
    with open(input_path) as f:
        scored = json.load(f)
    
    # scored_articles.json 结构：{"invest": [...], "ai": [...]}
    invest_raw = scored.get("invest", [])
    ai_raw     = scored.get("ai", [])
    
    log.info(f"[Select] 输入: 投资桶 {len(invest_raw)} 篇, AI桶 {len(ai_raw)} 篇")
    
    # Phase A: 事件级去重
    invest_deduped, invest_dropped = deduplicate_by_event(invest_raw, "invest")
    ai_deduped,     ai_dropped     = deduplicate_by_event(ai_raw, "ai")
    
    log.info(f"[Select] 去重后: 投资桶 {len(invest_deduped)} 篇 (去除 {len(invest_dropped)} 篇), "
             f"AI桶 {len(ai_deduped)} 篇 (去除 {len(ai_dropped)} 篇)")
    
    # Phase B: 配额筛选
    invest_final = select_by_quota(invest_deduped, "invest")
    ai_final     = select_by_quota(ai_deduped, "ai")
    
    # 输出
    result = {
        "invest": invest_final,
        "ai":     ai_final,
        "meta": {
            "invest_candidates": len(invest_raw),
            "ai_candidates":     len(ai_raw),
            "invest_deduped":    len(invest_deduped),
            "ai_deduped":        len(ai_deduped),
            "invest_selected":   len(invest_final),
            "ai_selected":       len(ai_final),
            "dedup_log": {
                "invest_dropped": invest_dropped,
                "ai_dropped":     ai_dropped,
            },
        },
    }
    
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    
    log.info(f"[Select] 完成 → {output_path}")
    log.info(f"[Select] 最终: 投资桶 {len(invest_final)} 篇, AI桶 {len(ai_final)} 篇")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--input",  required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--log-level", default="INFO")
    args = parser.parse_args()
    
    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    )
    run(args.input, args.output)
