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
from requests.adapters import HTTPAdapter

ROOT = Path(__file__).parent.parent
SCORING_MD = ROOT / "references" / "scoring.md"

log = logging.getLogger(__name__)

KIMI_BASE = "https://api.moonshot.cn/v1"
KIMI_MODEL = "moonshot-v1-8k"
BATCH_SIZE = 15
MAX_RETRY = 3
RETRY_BACKOFF_STATUS = [20, 40, 80]
RETRY_BACKOFF_NETWORK = [5, 15, 30]
REQUEST_TIMEOUT = 30
REQUEST_INTERVAL_DEFAULT = 1.2
MAX_SCORE_SECONDS_DEFAULT = 1200
MAX_CONSECUTIVE_FAILURES_DEFAULT = 8

AI_KEYWORDS = {
    "ai", "model", "llm", "gpu", "npu", "chip", "hbm", "datacenter", "data center",
    "openai", "anthropic", "deepmind", "deepseek", "xai", "semiconductor", "inference",
    "training", "compute", "agent", "robot", "automation", "nvidia", "tsmc",
}
INVEST_KEYWORDS = {
    "fed", "rates", "inflation", "treasury", "stocks", "market", "economy", "oil",
    "gold", "bond", "tariff", "gdp", "earnings", "ipo", "sec", "dollar",
}
BREAKING_KEYWORDS = {"breaking", "just in", "live", "urgent"}
RESEARCH_KEYWORDS = {"research", "report", "paper", "study", "arxiv"}
OPINION_KEYWORDS = {"opinion", "commentary", "view", "analysis"}
HIGH_IMPACT_KEYWORDS = {
    "fed", "tariff", "war", "oil", "chip", "gpu", "model", "datacenter", "earnings",
    "rate", "inflation", "export control", "regulation", "policy",
}
OFFICIAL_SOURCE_IDS = {"fed-announcements", "sec-edgar", "sec-edgar-ai", "anthropic-blog", "openai-blog", "deepmind-blog"}
ANALYSIS_SOURCE_IDS = {
    "the-information", "ft-economy", "economist-finance", "semianalysis",
    "mit-tech-review", "wolf-street", "fabricated-knowledge", "one-useful-thing",
    "interconnects", "gary-marcus", "chinai-newsletter",
}
SOURCE_AUTHORITY = {
    "bloomberg-markets": 4,
    "reuters-business": 4,
    "ft-economy": 4,
    "fed-announcements": 4,
    "anthropic-blog": 4,
    "openai-blog": 4,
    "deepmind-blog": 4,
    "the-information": 3,
    "semianalysis": 3,
    "economist-finance": 3,
    "mit-tech-review": 3,
    "ieee-spectrum-ai": 4,
    "wired-ai": 2,
    "wolf-street": 2,
    "36kr-invest": 2,
    "politico-ai": 2,
    "utility-dive": 2,
}
ASSET_PATTERNS = [
    ("nvidia", "Nvidia"),
    ("openai", "OpenAI"),
    ("anthropic", "Anthropic"),
    ("deepmind", "DeepMind"),
    ("deepseek", "DeepSeek"),
    ("xai", "xAI"),
    ("microsoft", "Microsoft"),
    ("google", "Google"),
    ("amazon", "Amazon"),
    ("meta", "Meta"),
    ("apple", "Apple"),
    ("amd", "AMD"),
    ("tsmc", "TSMC"),
    ("oracle", "Oracle"),
    ("tesla", "Tesla"),
    ("fed", "Fed"),
    ("treasury", "US Treasuries"),
    ("oil", "Oil"),
    ("gold", "Gold"),
    ("bitcoin", "Bitcoin"),
]


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


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except ValueError:
        return default


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


def _env_flag(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in {"1", "true", "yes", "on"}


def _heuristic_assets(article: dict) -> list[str]:
    text = " ".join([
        article.get("title", ""),
        article.get("summary", ""),
        article.get("full_text", ""),
    ]).lower()
    assets: list[str] = []
    for needle, label in ASSET_PATTERNS:
        if needle in text and label not in assets:
            assets.append(label)
        if len(assets) >= 3:
            break
    return assets


def _heuristic_track(article: dict) -> str:
    bucket = article.get("source_bucket")
    if bucket == "invest":
        return "INV"
    if bucket == "ai":
        return "AI"

    text = " ".join([
        article.get("title", ""),
        article.get("summary", ""),
        article.get("full_text", ""),
    ]).lower()
    if any(k in text for k in AI_KEYWORDS):
        return "AI"
    if any(k in text for k in INVEST_KEYWORDS):
        return "INV"
    return "X"


def _heuristic_content_type(article: dict) -> str:
    text = " ".join([
        article.get("title", ""),
        article.get("summary", ""),
        article.get("full_text", ""),
    ]).lower()
    source_id = article.get("source_id", "")
    if source_id in OFFICIAL_SOURCE_IDS:
        return "Official"
    if any(k in text for k in BREAKING_KEYWORDS):
        return "Breaking"
    if any(k in text for k in RESEARCH_KEYWORDS):
        return "Research"
    if source_id in ANALYSIS_SOURCE_IDS or (article.get("has_full_text") and len(article.get("full_text", "")) > 1800):
        return "Analysis"
    if any(k in text for k in OPINION_KEYWORDS):
        return "Opinion"
    return "News"


def _heuristic_title(article: dict) -> str:
    title = (article.get("title") or "").strip()
    if not title:
        return "（无标题）"
    return title[:40]


def _heuristic_snippet(article: dict, limit: int = 70) -> str:
    source = (article.get("summary") or article.get("full_text") or "").strip()
    source = re.sub(r"\s+", " ", source)
    if not source:
        return "摘要信息有限，建议阅读原文。"
    return source[:limit]


def _heuristic_event_cluster(article: dict, assets: list[str]) -> str:
    if len(assets) >= 2:
        parts = [re.sub(r"[^a-z0-9]+", "-", asset.lower()).strip("-") for asset in assets[:3]]
        parts = [p for p in parts if p]
        if parts:
            return "-".join(parts[:3])
    return "standalone"


def _heuristic_result(article: dict) -> dict:
    text = " ".join([
        article.get("title", ""),
        article.get("summary", ""),
        article.get("full_text", ""),
    ]).lower()
    track = _heuristic_track(article)
    content_type = _heuristic_content_type(article)
    authority = SOURCE_AUTHORITY.get(article.get("source_id", ""), 2)

    market_impact = 1
    if article.get("tier") == "S":
        market_impact += 1
    if track == "AI":
        market_impact += 1
    if any(k in text for k in HIGH_IMPACT_KEYWORDS):
        market_impact += 1
    market_impact = min(4, market_impact)

    information_edge = min(4, max(1, authority))

    causal_depth = 1
    if article.get("has_full_text"):
        causal_depth += 1
    if content_type in {"Analysis", "Research", "Official"}:
        causal_depth += 1
    if len(article.get("full_text", "")) > 1800:
        causal_depth += 1
    causal_depth = min(4, causal_depth)

    urgency = 2
    if content_type == "Breaking":
        urgency = 4
    elif content_type in {"News", "Official"}:
        urgency = 3

    source_authority = authority

    scores = {
        "market_impact": market_impact,
        "information_edge": information_edge,
        "causal_depth": causal_depth,
        "urgency": urgency,
        "source_authority": source_authority,
    }
    total = sum(scores.values())
    assets = _heuristic_assets(article)
    title_zh = _heuristic_title(article)
    bucket_label = "AI产业链" if track == "AI" else "宏观与市场"
    fact_snippet = _heuristic_snippet(article, 90)

    return {
        "track": track,
        "content_type": content_type,
        "scores": scores,
        "total": total,
        "title_zh": title_zh,
        "one_line": f"{bucket_label}重点跟踪，建议纳入今日观察。",
        "fact": f"原文摘要：{fact_snippet}",
        "impact": "可能影响相关板块、公司估值与市场风险偏好。",
        "watch_next": "继续关注后续官方披露、公司公告与价格反馈。",
        "assets_affected": assets,
        "event_cluster": _heuristic_event_cluster(article, assets),
    }


def _new_session() -> requests.Session:
    """为每次 LLM 调用创建短生命周期 Session，避免复用损坏连接"""
    session = requests.Session()
    adapter = HTTPAdapter(pool_connections=1, pool_maxsize=1, max_retries=0)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    session.headers.update({
        "User-Agent": "morning-brief/1.0",
        "Connection": "close",
    })
    return session


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
        session = _new_session()
        content = ""
        try:
            resp = session.post(
                f"{KIMI_BASE}/chat/completions",
                headers=headers,
                json=payload,
                timeout=REQUEST_TIMEOUT,
            )

            if resp.status_code == 401:
                wait = RETRY_BACKOFF_STATUS[min(attempt, len(RETRY_BACKOFF_STATUS) - 1)]
                log.warning(f"[scorer] 401 认证失败，等待 {wait}s 重试 ({attempt+1}/{MAX_RETRY})")
                if attempt < MAX_RETRY:
                    time.sleep(wait)
                    continue
                log.error("[scorer] 401 已达最大重试次数，跳过此批次")
                return None

            if resp.status_code == 429:
                wait = RETRY_BACKOFF_STATUS[min(attempt, len(RETRY_BACKOFF_STATUS) - 1)]
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
            wait = RETRY_BACKOFF_NETWORK[min(attempt, len(RETRY_BACKOFF_NETWORK) - 1)]
            log.warning(f"[scorer] 网络错误 attempt {attempt+1}: {e}，等待 {wait}s")
            if attempt < MAX_RETRY:
                time.sleep(wait)
            else:
                log.error(f"[scorer] 放弃: {e}")
                return None
        finally:
            session.close()

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

    force_heuristic = _env_flag("BRIEF_FORCE_HEURISTIC_SCORING")
    allow_heuristic_fallback = _env_flag("BRIEF_ALLOW_HEURISTIC_FALLBACK")

    api_key = os.getenv("KIMI_API_KEY") or os.getenv("ANTHROPIC_API_KEY")
    if not api_key and not force_heuristic:
        raise EnvironmentError("缺少 KIMI_API_KEY 或 ANTHROPIC_API_KEY")

    prompt_template = _load_prompt_template()
    request_interval = max(0.0, _env_float("KIMI_REQUEST_INTERVAL", REQUEST_INTERVAL_DEFAULT))
    max_score_seconds = max(60, _env_int("BRIEF_MAX_SCORE_SECONDS", MAX_SCORE_SECONDS_DEFAULT))
    max_consecutive_failures = max(1, _env_int("BRIEF_MAX_CONSECUTIVE_SCORE_ERRORS", MAX_CONSECUTIVE_FAILURES_DEFAULT))

    scored: list[dict] = []
    skipped = 0
    heuristic_used = 0
    consecutive_failures = 0
    stopped_early = False
    started_at = time.monotonic()

    log.info(
        f"[scorer] 开始评分 {len(articles)} 篇文章 "
        f"（节流={request_interval}s，单次超时={REQUEST_TIMEOUT}s，预算={max_score_seconds}s，"
        f"fallback={'on' if allow_heuristic_fallback or force_heuristic else 'off'}）"
    )

    for i, article in enumerate(articles):
        if time.monotonic() - started_at >= max_score_seconds:
            stopped_early = True
            log.error(f"[scorer] 达到评分时间预算 {max_score_seconds}s，提前结束并保留已成功结果")
            break
        if i > 0 and not force_heuristic:
            time.sleep(request_interval)
        if i > 0 and i % BATCH_SIZE == 0:
            log.info(f"[scorer] 进度 {i}/{len(articles)}")

        llm_result = None
        if force_heuristic:
            llm_result = _heuristic_result(article)
            heuristic_used += 1
        else:
            llm_result = _score_article(article, prompt_template, api_key)
            if (llm_result is None or not _validate_score(llm_result)) and allow_heuristic_fallback:
                log.warning(f"[scorer] 启用启发式降级: {article.get('title', '')[:50]}")
                llm_result = _heuristic_result(article)
                heuristic_used += 1

        if llm_result is None or not _validate_score(llm_result):
            log.warning(f"[scorer] 跳过（评分失败）: {article.get('title', '')[:50]}")
            skipped += 1
            consecutive_failures += 1
            if consecutive_failures >= max_consecutive_failures and scored:
                stopped_early = True
                log.error(
                    f"[scorer] 连续失败达到 {consecutive_failures} 次，提前结束评分并保留已成功结果"
                )
                break
            continue

        consecutive_failures = 0
        merged = _merge_score(article, llm_result)
        if merged["track"] == "X" or merged["total_score"] < 10:
            log.debug(f"[scorer] 丢弃（低分/无关）: {article.get('title', '')[:40]}")
            continue

        scored.append(merged)
        log.debug(f"[scorer] ✓ {merged['track']} {merged['total_score']}分 | {article.get('title','')[:40]}")

    ai_count = sum(1 for a in scored if a["track"] == "AI")
    inv_count = sum(1 for a in scored if a["track"] == "INV")
    log.info(
        f"[scorer] 完成: AI桶 {ai_count} 篇 | 投资桶 {inv_count} 篇 | "
        f"跳过 {skipped} 篇 | 启发式 {heuristic_used} 篇"
    )

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

    status = "success"
    if stopped_early or skipped >= max(5, len(articles) // 3) or heuristic_used > 0:
        status = "warning"

    return {"status": status, "count": len(scored), "skipped": skipped, "heuristic_used": heuristic_used}


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
