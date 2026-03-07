#!/usr/bin/env python3
"""
fetcher.py · Phase 1
RSS 抓取 + 全文提取 + Hash 去重 → raw_articles.json

v3.0: 新增全文抓取（archive.ph 付费墙绕过 + 正文提取）
"""

import argparse
import hashlib
import json
import logging
import re
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

import feedparser
import requests

log = logging.getLogger("fetcher")

# ── 常量 ──────────────────────────────────────────────────────────────────────

FETCH_TIMEOUT      = 12    # RSS 抓取超时（秒）
FULLTEXT_TIMEOUT   = 8     # 全文抓取超时（秒）
BATCH_INTERVAL     = 0.5   # RSS 源间隔（秒）
HOURS_WINDOW       = 24    # 时效窗口（小时）
HASH_CACHE_FILE    = "url_hash_cache.json"
MAX_FULLTEXT_CHARS = 3000  # 全文截取上限

PAYWALL_DOMAINS = {
    "bloomberg.com", "ft.com", "wsj.com",
    "economist.com", "barrons.com", "theinformation.com",
}

TIER_LIMITS = {"S": 5, "A": 3, "B": 2, "C": 0}

# ── 时效过滤 ──────────────────────────────────────────────────────────────────

def is_within_window(published_str: str, hours: int = 24) -> bool:
    """判断文章是否在时效窗口内"""
    if not published_str:
        return True  # 无时间戳默认保留
    try:
        formats = [
            "%a, %d %b %Y %H:%M:%S %z",
            "%Y-%m-%dT%H:%M:%S%z",
            "%Y-%m-%dT%H:%M:%SZ",
        ]
        pub = None
        for fmt in formats:
            try:
                pub = datetime.strptime(published_str, fmt)
                break
            except ValueError:
                continue
        if pub is None:
            return True
        now = datetime.now(timezone.utc)
        if pub.tzinfo is None:
            pub = pub.replace(tzinfo=timezone.utc)
        return (now - pub) <= timedelta(hours=hours)
    except Exception:
        return True


# ── URL Hash 去重 ─────────────────────────────────────────────────────────────

def load_hash_cache(cache_file: str) -> set:
    """加载 48h 内的 URL hash 缓存"""
    try:
        with open(cache_file) as f:
            data = json.load(f)
        cutoff = datetime.now(timezone.utc) - timedelta(hours=48)
        valid = {k for k, ts in data.items()
                 if datetime.fromisoformat(ts) > cutoff}
        return valid
    except (FileNotFoundError, json.JSONDecodeError):
        return set()


def save_hash_cache(hashes: set, cache_file: str):
    """更新 hash 缓存（保留现有 + 新增）"""
    try:
        with open(cache_file) as f:
            existing = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        existing = {}
    now_str = datetime.now(timezone.utc).isoformat()
    for h in hashes:
        existing[h] = now_str
    with open(cache_file, "w") as f:
        json.dump(existing, f)


def url_hash(url: str) -> str:
    return hashlib.md5(url.strip().lower().encode()).hexdigest()


# ── 全文提取 ──────────────────────────────────────────────────────────────────

def extract_main_text(html: str) -> str:
    """从 HTML 中提取正文（简单版：去除标签，提取最长段落块）"""
    # 去除 script / style / nav
    html = re.sub(r'<(script|style|nav|header|footer)[^>]*>.*?</\1>', '', html,
                  flags=re.DOTALL | re.IGNORECASE)
    # 去除所有 HTML 标签
    text = re.sub(r'<[^>]+>', ' ', html)
    # 清理空白
    text = re.sub(r'\s+', ' ', text).strip()
    return text


def fetch_full_text(url: str, domain: str) -> tuple[Optional[str], bool]:
    """
    尝试获取文章全文。
    
    返回：(text_or_None, is_full_text)
    
    策略：
    1. 直接抓原文 URL
    2. 如为付费域名或直抓内容太少，尝试 archive.ph
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
            text = extract_main_text(resp.text)
            if len(text) > 800:
                return text[:MAX_FULLTEXT_CHARS], True
    except Exception as e:
        log.debug(f"直接抓取失败 {url}: {e}")
    
    # 策略2：archive.ph（付费域名或直抓失败）
    if any(d in domain for d in PAYWALL_DOMAINS):
        try:
            archive_url = f"https://archive.ph/{url}"
            resp = requests.get(archive_url, headers=headers, timeout=FULLTEXT_TIMEOUT)
            if resp.status_code == 200:
                text = extract_main_text(resp.text)
                if len(text) > 800:
                    log.debug(f"archive.ph 成功: {url}")
                    return text[:MAX_FULLTEXT_CHARS], True
        except Exception as e:
            log.debug(f"archive.ph 失败 {url}: {e}")
    
    return None, False


# ── RSS 抓取主逻辑 ────────────────────────────────────────────────────────────

def fetch_source(source: dict, hours: int, seen_hashes: set) -> list:
    """抓取单个 RSS 源，返回文章列表"""
    url   = source.get("url", "")
    name  = source.get("name", url)
    tier  = source.get("tier", "B")
    limit = TIER_LIMITS.get(tier, 2)
    
    if limit == 0:
        return []
    
    try:
        feed    = feedparser.parse(url)
        entries = feed.entries
    except Exception as e:
        log.warning(f"RSS 解析失败 [{name}]: {e}")
        return []
    
    articles = []
    
    for entry in entries:
        if len(articles) >= limit:
            break
        
        article_url = entry.get("link", "")
        if not article_url:
            continue
        
        h = url_hash(article_url)
        if h in seen_hashes:
            log.debug(f"[Hash去重] {article_url}")
            continue
        
        pub_str = entry.get("published", entry.get("updated", ""))
        if not is_within_window(pub_str, hours):
            continue
        
        # 提取摘要
        summary = ""
        if hasattr(entry, "summary"):
            summary = re.sub(r'<[^>]+>', '', entry.summary).strip()
        elif hasattr(entry, "description"):
            summary = re.sub(r'<[^>]+>', '', entry.description).strip()
        summary = summary[:500]
        
        domain = article_url.split("/")[2] if "/" in article_url else ""
        
        article = {
            "title":        entry.get("title", ""),
            "url":          article_url,
            "source":       name,
            "source_tier":  tier,
            "published":    pub_str,
            "summary":      summary,
            "full_text":    summary,       # 默认降级为摘要
            "has_full_text": False,
            "content_quality": "summary_only",
            "domain":       domain,
            "hash":         h,
        }
        
        articles.append(article)
        seen_hashes.add(h)
    
    return articles


def fetch_full_texts(articles: list) -> list:
    """
    对所有文章尝试全文抓取（异步顺序执行，失败不阻塞）。
    实践中约 40-60% 成功率。
    """
    for art in articles:
        try:
            text, is_full = fetch_full_text(art["url"], art.get("domain", ""))
            if is_full and text:
                art["full_text"]       = text
                art["has_full_text"]   = True
                art["content_quality"] = "full_text"
                log.debug(f"全文获取成功: {art['title'][:40]}")
        except Exception as e:
            log.debug(f"全文获取异常 [{art['title'][:40]}]: {e}")
        time.sleep(0.3)   # 轻微间隔，避免 IP 被封
    
    success = sum(1 for a in articles if a["has_full_text"])
    log.info(f"[Fetch] 全文获取: {success}/{len(articles)} 篇成功")
    return articles


# ── 主入口 ────────────────────────────────────────────────────────────────────

def run(sources_file: str, status_file: str, hours: int, output_path: str):
    with open(sources_file) as f:
        sources = json.load(f)
    
    try:
        with open(status_file) as f:
            status = json.load(f)
        reachable_ids = {k for k, v in status.items() if v.get("reachable")}
    except (FileNotFoundError, json.JSONDecodeError):
        reachable_ids = None  # status 文件不存在时不过滤
    
    seen_hashes = load_hash_cache(HASH_CACHE_FILE)
    all_articles = []
    new_hashes = set()
    
    for source in sources:
        if reachable_ids is not None and source.get("id") not in reachable_ids:
            log.debug(f"跳过不可达源: {source.get('name','')}")
            continue
        
        articles = fetch_source(source, hours, seen_hashes)
        all_articles.extend(articles)
        new_hashes.update(a["hash"] for a in articles)
        time.sleep(BATCH_INTERVAL)
    
    log.info(f"[Fetch] RSS 抓取完成: {len(all_articles)} 篇原始文章")
    
    # 全文抓取
    all_articles = fetch_full_texts(all_articles)
    
    # 保存 hash 缓存
    save_hash_cache(new_hashes, HASH_CACHE_FILE)
    
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(all_articles, f, ensure_ascii=False, indent=2)
    
    log.info(f"[Fetch] 输出: {output_path} ({len(all_articles)} 篇)")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--sources",  required=True)
    parser.add_argument("--status",   default="sources_status.json")
    parser.add_argument("--hours",    type=int, default=24)
    parser.add_argument("--output",   required=True)
    parser.add_argument("--log-level", default="INFO")
    args = parser.parse_args()
    
    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    )
    run(args.sources, args.status, args.hours, args.output)
