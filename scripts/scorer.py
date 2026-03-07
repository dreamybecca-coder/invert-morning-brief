#!/usr/bin/env python3
"""
Phase 2 · Scorer — 五维评分 + 分桶

输入:  raw_articles.json
输出:  scored_articles.json

评分 Prompt 来自 references/scoring.md，批次间隔 ≥ 3s，
401/429 指数退避重试（最多 3 次，30s/60s/120s）。
"""

import json
import logging
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

ROOT = Path(__file__).parent.parent
SCORING_MD = ROOT / "references" / "scoring.md"

log = logging.getLogger(__name__)

KIMI_BASE = "https://api.moonshot.cn/v1"
KIMI_MODEL = "moonshot-v1-8k"
BATCH_SIZE = 15
BATCH_INTERVAL = 3.0
MAX_RETRY = 3
RETRY_BACKOFF = [30, 60, 120]


# ── Prompt 提取 ───────────────────────────────────────────────────────────────

def _load_prompt_template() -> str:
    """从 scoring.md 的 PROMPT 代码块中提取模板文本"""
    text = SCORING_MD.read_text(encoding="utf-8")
    # 找到 ## PROMPT 部分
    start = text.find("## PROMPT")
    if start == -1:
        raise ValueError("scoring.md 中未找到 ## PROMPT 节")
    # 找第一个 ``` 代码块
    cb_start = text.find("```\n", start)
    if cb_start == -1:
        raise ValueError("scoring.md 中未找到 PROMPT 代码块")
    cb_start += 4  # 跳过 "```\n"
    cb_end = text.find("\n```", cb_start)
    if cb_end == -1:
        raise ValueError("scoring.md PROMPT 代码块未闭合")
    return text[cb_start:cb_end]


# ── LLM 调用 ──────────────────────────────────────────────────────────────────

def _call_llm(prompt: str, api_key: str) -> dict | None:
    """调用 Kimi API，返回解析后的 JSON dict；失败返回 None"""
    payload = {
        "model": KIMI_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.1,
        "max_tokens": 700,
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    for attempt in range(MAX_RETRY + 1):
        try:
            resp = requests.post(
                f"{KIMI_BASE}/chat/completions",
                headers=headers,
                json=payload,
                timeout=30,
            )

            if resp.status_code == 401:
                wait = RETRY_BACKOFF[min(attempt, len(RETRY_BACKOFF) - 1)]
                log.warning(f"[scorer] 401 认证失败，等待 {wait}s 重试 ({attempt+1}/{MAX_RETRY})")
                if attempt < MAX_RETRY:
                    time.sleep(wait)
                    continue
                log.error("[scorer] 401 已达最大重试次数，跳过此批次")
                return None

            if resp.status_code == 429:
                wait = RETRY_BACKOFF[min(attempt, len(RETRY_BACKOFF) - 1)]
                log.warning(f"[scorer] 429 rate limit，退避 {wait}s ({attempt+1}/{MAX_RETRY})")
                if attempt < MAX_RETRY:
                    time.sleep(wait)
                    continue
                log.error("[scorer] 429 已达最大重试次数，跳过")
                return None

            resp.raise_for_status()
            content = resp.json()["choices"][0]["message"]["content"].strip()

            # 提取 JSON（LLM 有时包裹在 ```json ... ``` 里）
            json_match = re.search(r"\{.*\}", content, re.DOTALL)
            if not json_match:
                log.warning(f"[scorer] LLM 响应无 JSON: {content[:200]}")
                return None

            result = json.loads(json_match.group())
            return result

        except json.JSONDecodeError as e:
            log.warning(f"[scorer] JSON 解析失败: {e} | content: {content[:200]}")
            return None
        except requests.RequestException as e:
            wait = RETRY_BACKOFF[min(attempt, len(RETRY_BACKOFF) - 1)]
            log.warning(f"[scorer] 网络错误 attempt {attempt+1}: {e}，等待 {wait}s")
            if attempt < MAX_RETRY:
                time.sleep(wait)
            else:
                log.error(f"[scorer] 放弃: {e}")
                return None

    return None


def _score_article(article: dict, prompt_template: str, api_key: str) -> dict | None:
    """对单篇文章评分，返回 LLM 结果 dict"""
    # 优先用全文，fallback 到摘要（v3.0：全文感知评分）
    content = article.get("full_text") or article.get("summary", "（无摘要）")
    content_quality = "full_text" if article.get("has_full_text") else "summary_only"
    # 用手动 replace，避免 prompt 中的 JSON {} 被 .format() 误解析
    prompt = prompt_template \
        .replace("<<TITLE>>",           article.get("title", "")) \
        .replace("<<CONTENT>>",         content[:2000]) \
        .replace("<<SOURCE>>",          article.get("source_name", "")) \
        .replace("<<PUBLISHED>>",       article.get("published", "未知")) \
        .replace("<<CONTENT_QUALITY>>", content_quality)
    return _call_llm(prompt, api_key)


# ── 评分结果验证 ──────────────────────────────────────────────────────────────

def _validate_score(result: dict) -> bool:
    """基本格式校验"""
    required = ["track", "content_type", "scores", "total", "one_line"]
    if not all(k in result for k in required):
        return False
    if result["track"] not in ("AI", "INV", "DUAL", "X"):
        return False
    scores = result.get("scores", {})
    dims = ["market_impact", "information_edge", "causal_depth", "urgency", "source_authority"]
    if not all(d in scores for d in dims):
        return False
    return True


def _merge_score(article: dict, llm_result: dict) -> dict:
    """将 LLM 评分合并到文章 dict"""
    track = llm_result.get("track", "X")
    if track == "DUAL":
        track = "AI"  # AI 优先规则

    scores = llm_result.get("scores", {})
    total = llm_result.get("total", sum(scores.values()))

    return {
        **article,
        "track": track,
        "content_type": llm_result.get("content_type", "News"),
        "scores": scores,
        "total_score": total,
        "one_line": llm_result.get("one_line", "")[:30],
        "assets_affected": llm_result.get("assets_affected", [])[:3],
        "event_cluster": llm_result.get("event_cluster", "standalone").strip().lower()[:60],
        # 中文摘要字段（v2.1 新增）
        "title_zh": llm_result.get("title_zh", article.get("title", ""))[:35],
        "fact": llm_result.get("fact", "")[:50],
        "impact": llm_result.get("impact", "")[:50],
        "watch_next": llm_result.get("watch_next", "")[:40],
    }


# ── 主函数 ────────────────────────────────────────────────────────────────────

def run_score(date: str, dry_run: bool, input_file: str = "raw_articles.json",
              output_file: str = "scored_articles.json") -> dict:
    raw = json.loads(Path(input_file).read_text(encoding="utf-8"))
    articles = raw.get("articles", [])

    api_key = os.getenv("KIMI_API_KEY") or os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise EnvironmentError("缺少 KIMI_API_KEY 或 ANTHROPIC_API_KEY")

    prompt_template = _load_prompt_template()

    scored: list[dict] = []
    skipped = 0

    log.info(f"[scorer] 开始评分 {len(articles)} 篇文章（批次={BATCH_SIZE}，间隔={BATCH_INTERVAL}s）")

    for i, article in enumerate(articles):
        if i > 0 and i % BATCH_SIZE == 0:
            log.info(f"[scorer] 批次间隔 {BATCH_INTERVAL}s（已处理 {i}/{len(articles)}）")
            time.sleep(BATCH_INTERVAL)

        llm_result = _score_article(article, prompt_template, api_key)

        if llm_result is None or not _validate_score(llm_result):
            log.warning(f"[scorer] 跳过（评分失败）: {article.get('title', '')[:50]}")
            skipped += 1
            continue

        merged = _merge_score(article, llm_result)
        if merged["track"] == "X" or merged["total_score"] < 10:
            log.debug(f"[scorer] 丢弃（低分/无关）: {article.get('title', '')[:40]}")
            continue

        scored.append(merged)
        log.debug(f"[scorer] ✓ {merged['track']} {merged['total_score']}分 | {article.get('title','')[:40]}")

    ai_count = sum(1 for a in scored if a["track"] == "AI")
    inv_count = sum(1 for a in scored if a["track"] == "INV")
    log.info(f"[scorer] 完成: AI桶 {ai_count} 篇 | 投资桶 {inv_count} 篇 | 跳过 {skipped} 篇")

    output = {
        "date": date,
        "scored_at": datetime.now(timezone.utc).isoformat(),
        "summary": {"ai": ai_count, "invest": inv_count, "skipped": skipped},
        "articles": scored,
    }

    if output_file:
        Path(output_file).write_text(
            json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        log.info(f"[scorer] → {output_file}")

    return {"status": "success", "count": len(scored)}


if __name__ == "__main__":
    import argparse
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
    parser.add_argument("--test", action="store_true")
    args = parser.parse_args()

    result = run_score(date=args.date, dry_run=False,
                       input_file="raw_articles.json",
                       output_file="scored_articles.json")
    print(result)
