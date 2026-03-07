#!/usr/bin/env python3
"""
Phase 0 · Recon — 检查 RSS 源可达性

输入: 无（直接读 references/sources.json）
输出: sources_status.json
"""

import json
import logging
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).parent.parent
SOURCES_FILE = ROOT / "references" / "sources.json"

log = logging.getLogger(__name__)

TIMEOUT = 10
SKIP_ACCESS_METHODS = {"telegram_channel"}


def _check_url(url: str) -> tuple[bool, str]:
    """检查 URL 可达性，返回 (ok, error_msg)"""
    import requests

    headers = {"User-Agent": "Mozilla/5.0 (compatible; morning-brief/1.0; +https://invert.bot)"}
    try:
        resp = requests.head(url, timeout=TIMEOUT, allow_redirects=True, headers=headers)
        if resp.status_code < 400:
            return True, ""
        # HEAD 返回 4xx，尝试 GET（部分服务器不支持 HEAD）
        if resp.status_code in (405, 403):
            resp2 = requests.get(url, timeout=TIMEOUT, allow_redirects=True,
                                 headers=headers, stream=True)
            resp2.close()
            return resp2.status_code < 400, f"GET {resp2.status_code}"
        return False, f"HTTP {resp.status_code}"
    except Exception as e:
        # HEAD 失败，直接 GET
        try:
            import requests as req2
            resp = req2.get(url, timeout=TIMEOUT, allow_redirects=True,
                            headers=headers, stream=True)
            resp.close()
            return resp.status_code < 400, f"GET {resp.status_code}"
        except Exception as e2:
            return False, str(e2)[:120]


def _collect_sources(sources_data: dict) -> list[dict]:
    """从 sources.json 收集所有需要检查的源（跳过 tier_C 和 telegram 接入）"""
    result = []
    seen_ids: set[str] = set()

    for bucket_key in ["bucket_invest", "bucket_ai"]:
        bucket_name = "invest" if "invest" in bucket_key else "ai"
        bucket = sources_data.get(bucket_key, {})

        for tier_key in ["tier_S", "tier_A", "tier_B"]:
            for src in bucket.get(tier_key, []):
                if src.get("access_method") in SKIP_ACCESS_METHODS:
                    log.debug(f"[recon] 跳过 telegram 接入源: {src['id']}")
                    continue
                if src["id"] in seen_ids:
                    continue
                seen_ids.add(src["id"])
                result.append({**src, "source_bucket": bucket_name})

    return result


def run_recon(date: str, dry_run: bool, input_file=None, output_file: str = "sources_status.json") -> dict:
    sources_data = json.loads(SOURCES_FILE.read_text(encoding="utf-8"))
    sources = _collect_sources(sources_data)

    status: dict[str, dict] = {}
    reachable = 0

    log.info(f"[recon] 开始检查 {len(sources)} 个源")

    for src in sources:
        url = src["url"]
        if "TODAY" in url:
            url = url.replace("TODAY", datetime.now().strftime("%Y-%m-%d"))

        ok, err = _check_url(url)
        status[src["id"]] = {
            "name": src["name"],
            "url": url,
            "source_bucket": src["source_bucket"],
            "tier": src.get("tier", "?"),
            "reachable": ok,
            "error": err,
            "checked_at": datetime.now(timezone.utc).isoformat(),
        }
        if ok:
            reachable += 1
        icon = "✅" if ok else "❌"
        log.info(f"[recon] {icon} {src['id']}" + (f" ({err})" if err else ""))

    output = {
        "date": date,
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "sources": status,
        "summary": {
            "total": len(sources),
            "reachable": reachable,
            "unreachable": len(sources) - reachable,
        },
    }

    if output_file:
        Path(output_file).write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
        log.info(f"[recon] {reachable}/{len(sources)} 可达 → {output_file}")

    return {"status": "success", "count": reachable}


if __name__ == "__main__":
    import argparse
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")

    # 加载 .env
    env_file = ROOT / ".env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())

    parser = argparse.ArgumentParser()
    parser.add_argument("--check-all", action="store_true")
    parser.add_argument("--date", default=datetime.now().strftime("%Y-%m-%d"))
    args = parser.parse_args()

    result = run_recon(date=args.date, dry_run=False,
                       output_file="sources_status.json")
    print(result)
