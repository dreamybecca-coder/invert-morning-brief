#!/usr/bin/env python3
"""
Phase 1 · Fetcher — 抓取文章

输入:  sources_status.json（recon 输出）
输出:  raw_articles.json
配额:  S层5条 / A层3条 / B层2条（每源）
时效:  24小时窗口
去重:  URL+标题 hash，48小时窗口
"""

import hashlib
import json
import logging
import os
import re
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from email.utils import parsedate_to_datetime

import feedparser
import requests

ROOT = Path(__file__).parent.parent
SOURCES_FILE = ROOT / "references" / "sources.json"
DEDUP_CACHE_FILE = ROOT / "dedup_cache.json"

log = logging.getLogger(__name__)

LOOKBACK_HOURS = 24
DEDUP_TTL_HOURS = 48
TIER_LIMITS = {"S": 5, "A": 3, "B": 2, "C": 0}
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; morning-brief/1.0; +https://invert.bot)"}

FULLTEXT_TIMEOUT = 8
MAX_FULLTEXT_CHARS = 3000
PAYWALL_DOMAINS = {
    "bloomberg.com", "wsj.com",
    "economist.com", "barrons.com", "theinformation.com",
    # ft.com 已移除：FT直接HTTP抓取可得全文，无需archive.ph
}


# ── 全文提取 ──────────────────────────────────────────────────────────────────

def _extract_main_text(html: str) -> str:
    """从 HTML 提取正文（去除 script/style/nav，清理标签和空白）"""
    html = re.sub(r'<(script|style|nav|header|footer)[^>]*>.*?</\1>', '',
                  html, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r'<[^>]+>', ' ', html)
    return re.sub(r'\s+', ' ', text).strip()


def _fetch_full_text(url: str, domain: str) -> tuple[str | None, bool]:
    """
    尝试获取文章全文。
    策略1：直接抓原 URL；策略2：付费域名尝试 archive.ph。
    返回 (text_or_None, is_full_text)
    """
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/121.0.0.0 Safari/537.36"
        )
    }
    # 策略1：直接抓
    try:
        resp = requests.get(url, headers=headers, timeout=FULLTEXT_TIMEOUT)
        if resp.status_code == 200:
            text = _extract_main_text(resp.text)
            if len(text) > 800:
                return text[:MAX_FULLTEXT_CHARS], True
    except Exception as e:
        log.debug(f"直接抓取失败 {url}: {e}")

    # 策略2：付费域名尝试 archive.ph
    if any(d in domain for d in PAYWALL_DOMAINS):
        try:
            resp = requests.get(f"https://archive.ph/{url}", headers=headers,
                                timeout=FULLTEXT_TIMEOUT)
            if resp.status_code == 200:
                text = _extract_main_text(resp.text)
                if len(text) > 800:
                    log.debug(f"archive.ph 成功: {url}")
                    return text[:MAX_FULLTEXT_CHARS], True
        except Exception as e:
            log.debug(f"archive.ph 失败 {url}: {e}")

    return None, False


def _fetch_full_texts(articles: list[dict]) -> list[dict]:
    """对所有文章顺序尝试全文抓取（失败不阻塞）"""
    for art in articles:
        try:
            text, is_full = _fetch_full_text(art["url"], art.get("domain", ""))
            if is_full and text:
                art["full_text"] = text
                art["has_full_text"] = True
                art["content_quality"] = "full_text"
                log.debug(f"全文获取成功: {art['title'][:40]}")
        except Exception as e:
            log.debug(f"全文获取异常 [{art.get('title','')[:40]}]: {e}")
        time.sleep(0.3)

    success = sum(1 for a in articles if a.get("has_full_text"))
    log.info(f"[Fetch] 全文获取: {success}/{len(articles)} 篇成功")
    return articles


# ── 去重缓存 ─────────────────────────────────────────────────────────────────

def _load_dedup_cache() -> dict[str, str]:
    """加载去重缓存，清理 48h 过期条目"""
    if not DEDUP_CACHE_FILE.exists():
        return {}
    try:
        cache: dict[str, str] = json.loads(DEDUP_CACHE_FILE.read_text(encoding="utf-8"))
        cutoff = datetime.now(timezone.utc) - timedelta(hours=DEDUP_TTL_HOURS)
        return {h: ts for h, ts in cache.items()
                if datetime.fromisoformat(ts) > cutoff}
    except Exception:
        return {}


def _save_dedup_cache(cache: dict[str, str]):
    DEDUP_CACHE_FILE.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")


def _article_hash(url: str, title: str) -> str:
    key = (url.strip() + "|" + title.strip()).encode("utf-8")
    return hashlib.sha256(key).hexdigest()[:24]


# ── 时间解析 ─────────────────────────────────────────────────────────────────

def _parse_published(entry) -> datetime | None:
    """从 feedparser entry 解析发布时间，返回 UTC datetime"""
    for attr in ("published_parsed", "updated_parsed", "created_parsed"):
        val = getattr(entry, attr, None)
        if val:
            try:
                import calendar
                ts = calendar.timegm(val)
                return datetime.fromtimestamp(ts, tz=timezone.utc)
            except Exception:
                pass
    # 尝试字符串解析
    for attr in ("published", "updated"):
        val = getattr(entry, attr, None)
        if val:
            try:
                return parsedate_to_datetime(val).astimezone(timezone.utc)
            except Exception:
                pass
    return None


# ── RSS 抓取 ─────────────────────────────────────────────────────────────────

def _fetch_rss(src: dict, cutoff: datetime, cache: dict[str, str], limit: int) -> list[dict]:
    """抓取单个 RSS 源，返回原始文章列表"""
    url = src["url"]
    if "TODAY" in url:
        url = url.replace("TODAY", datetime.now().strftime("%Y-%m-%d"))

    cookies = {}
    if src.get("id") == "the-information" and os.getenv("THE_INFORMATION_COOKIE"):
        cookies["cookie"] = os.getenv("THE_INFORMATION_COOKIE")
    elif src.get("id") == "semianalysis" and os.getenv("SEMIANALYSIS_COOKIE"):
        cookies["cookie"] = os.getenv("SEMIANALYSIS_COOKIE")

    try:
        feed = feedparser.parse(url, request_headers=HEADERS)
    except Exception as e:
        log.warning(f"[fetch] {src['id']} 解析失败: {e}")
        return []

    if feed.bozo and not feed.entries:
        log.warning(f"[fetch] {src['id']} feed 无法解析 (bozo={feed.bozo_exception})")
        return []

    articles = []
    for entry in feed.entries:
        if len(articles) >= limit:
            break

        title = getattr(entry, "title", "").strip()
        link = getattr(entry, "link", "").strip()
        if not title or not link:
            continue

        pub = _parse_published(entry)
        if pub is None:
            # 无时间信息，默认视为今天
            pub = datetime.now(timezone.utc)
        if pub < cutoff:
            continue

        # 去重
        h = _article_hash(link, title)
        if h in cache:
            log.debug(f"[fetch] 去重跳过: {title[:40]}")
            continue

        summary = (getattr(entry, "summary", "") or
                   getattr(entry, "description", "") or "").strip()
        # 清理 HTML 标签
        summary = re.sub(r"<[^>]+>", " ", summary).strip()
        summary = re.sub(r"\s+", " ", summary)[:800]

        domain = link.split("/")[2] if link.count("/") >= 2 else ""

        art = {
            "id": h,
            "title": title[:200],
            "url": link[:500],
            "source_id": src["id"],
            "source_name": src["name"],
            "source_bucket": src["source_bucket"],
            "tier": src.get("tier", "?"),
            "summary": summary,
            "full_text": summary,          # 默认降级为摘要，全文成功后覆盖
            "has_full_text": False,
            "content_quality": "summary_only",
            "domain": domain,
            "published": pub.isoformat(),
            "content_type_hints": src.get("content_types", []),
            "industry_layer": src.get("industry_layer"),
            "paywall": src.get("requires_auth", False),
            "fetched_at": datetime.now(timezone.utc).isoformat(),
        }
        articles.append(art)
        cache[h] = datetime.now(timezone.utc).isoformat()

    log.info(f"[fetch] {src['id']}: {len(articles)} 篇（今日）")
    return articles


# ── 主函数 ───────────────────────────────────────────────────────────────────

def run_fetch(date: str, dry_run: bool, input_file: str = "sources_status.json",
              output_file: str = "raw_articles.json") -> dict:
    # 读 recon 状态
    if not input_file or not Path(input_file).exists():
        raise FileNotFoundError(f"sources_status.json 不存在，请先运行 Phase 0 recon")
    status_data = json.loads(Path(input_file).read_text(encoding="utf-8"))
    reachable_ids = {sid for sid, info in status_data.get("sources", {}).items()
                     if info.get("reachable")}

    # 读源定义
    sources_data = json.loads(SOURCES_FILE.read_text(encoding="utf-8"))
    fetch_limits = sources_data["_meta"]["fetch_limits"]

    # 去重缓存
    cache = _load_dedup_cache()

    cutoff = datetime.now(timezone.utc) - timedelta(hours=LOOKBACK_HOURS)
    all_articles: list[dict] = []

    for bucket_key in ["bucket_invest", "bucket_ai"]:
        bucket_name = "invest" if "invest" in bucket_key else "ai"
        bucket = sources_data.get(bucket_key, {})

        for tier_key in ["tier_S", "tier_A", "tier_B"]:
            tier = tier_key.split("_")[1]
            limit = fetch_limits.get(tier, 0)
            if limit == 0:
                continue

            for src in bucket.get(tier_key, []):
                if src.get("access_method") == "telegram_channel":
                    log.debug(f"[fetch] 跳过 telegram 源: {src['id']}")
                    continue
                if src["id"] not in reachable_ids:
                    log.debug(f"[fetch] 跳过不可达源: {src['id']}")
                    continue

                arts = _fetch_rss(
                    {**src, "source_bucket": bucket_name},
                    cutoff, cache, limit
                )
                all_articles.extend(arts)

    log.info(f"[fetch] RSS 抓取完成: {len(all_articles)} 篇")

    # 全文抓取（在保存前）
    all_articles = _fetch_full_texts(all_articles)

    _save_dedup_cache(cache)

    count = len(all_articles)
    if count < 20:
        log.warning(f"[fetch] 仅抓到 {count} 篇，低于 20 篇建议阈值")

    output = {
        "date": date,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "total": count,
        "articles": all_articles,
    }

    if output_file:
        Path(output_file).write_text(
            json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        log.info(f"[fetch] 共抓取 {count} 篇 → {output_file}")

    return {"status": "success" if count >= 20 else "warning", "count": count}


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
    parser.add_argument("--source", help="测试单源")
    args = parser.parse_args()

    result = run_fetch(date=args.date, dry_run=False,
                       input_file="sources_status.json",
                       output_file="raw_articles.json")
    print(result)
