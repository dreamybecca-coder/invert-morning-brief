#!/usr/bin/env python3
"""
Phase 5 · Logger — 日志归档

输入:  daily_brief.json（+ sources_status.json）
输出:  {VAULT}/00-Inbox/_Processed/brief-log-YYYY-MM-DD.json

dry-run 模式: 只打印日志内容，不写 Obsidian。
"""

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).parent.parent

log = logging.getLogger(__name__)


def run_log(date: str, dry_run: bool, input_file: str = "daily_brief.json",
            output_file=None) -> dict:
    # 读 daily_brief
    brief = {}
    if input_file and Path(input_file).exists():
        try:
            brief = json.loads(Path(input_file).read_text(encoding="utf-8"))
        except Exception:
            pass

    # 读 sources_status
    source_summary = {}
    if Path("sources_status.json").exists():
        try:
            st = json.loads(Path("sources_status.json").read_text(encoding="utf-8"))
            source_summary = st.get("summary", {})
        except Exception:
            pass

    # 读 push_result
    push_result = {}
    if Path("push_result.json").exists():
        try:
            push_result = json.loads(Path("push_result.json").read_text(encoding="utf-8"))
        except Exception:
            pass

    invest_articles = brief.get("buckets", {}).get("invest", [])
    ai_articles = brief.get("buckets", {}).get("ai", [])

    log_data = {
        "date": date,
        "run_at": datetime.now(timezone.utc).isoformat(),
        "dry_run": dry_run,
        "sources": source_summary,
        "articles": {
            "invest_count": len(invest_articles),
            "ai_count": len(ai_articles),
            "invest_scores": [a.get("total_score") for a in invest_articles],
            "ai_scores": [a.get("total_score") for a in ai_articles],
        },
        "push": {
            "invest_status": push_result.get("invest", {}).get("status", "unknown"),
            "ai_status": push_result.get("ai", {}).get("status", "unknown"),
        },
        "status": "success",
    }

    if dry_run:
        print("\n[DRY-RUN] 日志摘要:")
        print(json.dumps(log_data, ensure_ascii=False, indent=2))
    else:
        vault = os.getenv("OBSIDIAN_VAULT_PATH")
        if vault:
            log_path = (Path(vault) / "00-Inbox" / "_Processed"
                        / f"brief-log-{date}.json")
            log_path.parent.mkdir(parents=True, exist_ok=True)
            log_path.write_text(
                json.dumps(log_data, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            log.info(f"[logger] 日志写入: {log_path}")
        else:
            log.warning("[logger] OBSIDIAN_VAULT_PATH 未设置，跳过日志归档")

    return {"status": "success", "count": 1}


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
    args = parser.parse_args()

    result = run_log(date=args.date, dry_run=False)
    print(result)
