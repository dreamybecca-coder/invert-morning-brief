#!/usr/bin/env python3
"""
morning-brief · 主入口
用法：python run_morning_brief.py [--date today] [--dry-run] [--phase PHASE]

此脚本是各 Phase 脚本的编排器。
每个 Phase 的业务逻辑在 scripts/ 目录下的独立脚本中。
"""

import argparse
import json
import logging
import os
import sys
from datetime import datetime
from pathlib import Path


def _load_dotenv():
    """加载 .env 文件（项目根目录）"""
    env_file = Path(__file__).parent / ".env"
    if env_file.exists():
        with open(env_file) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip())


def check_env():
    """先加载 .env，再校验必需变量"""
    _load_dotenv()

    required = [
        "TELEGRAM_BOT_TOKEN",
        "TELEGRAM_INVEST_CHAT_ID",
        "TELEGRAM_AI_CHAT_ID",
        "OBSIDIAN_VAULT_PATH",
    ]
    llm_keys = ["KIMI_API_KEY", "ANTHROPIC_API_KEY"]

    missing = [k for k in required if not os.getenv(k)]
    has_llm = any(os.getenv(k) for k in llm_keys)

    if missing:
        print(f"[ERROR] 缺少环境变量: {missing}")
        print("请检查 .env 文件，参考 references/agent-compat.md")
        sys.exit(1)
    if not has_llm:
        print(f"[ERROR] 需要至少一个 LLM API Key: {llm_keys}")
        sys.exit(1)


# ── 主流程 ───────────────────────────────────────────────────────────────────
def run(date_str: str, dry_run: bool, phase: str | None):
    from scripts.recon import run_recon
    from scripts.fetcher import run_fetch
    from scripts.scorer import run_score
    from scripts.selector import run_select
    from scripts.pusher import run_push
    from scripts.logger import run_log

    log = logging.getLogger("morning-brief")
    start_time = datetime.now()
    state = {"date": date_str, "dry_run": dry_run, "errors": []}

    # (fn, required_input_file_or_None, output_file)
    phases = {
        "recon":  (run_recon,  None,                   "sources_status.json"),
        "fetch":  (run_fetch,  "sources_status.json",  "raw_articles.json"),
        "score":  (run_score,  "raw_articles.json",    "scored_articles.json"),
        "select": (run_select, "scored_articles.json", "daily_brief.json"),
        "push":   (run_push,   "daily_brief.json",     "push_result.json"),
        "log":    (run_log,    "daily_brief.json",     None),
    }

    run_targets = list(phases.keys()) if not phase else [phase]

    for p in run_targets:
        fn, required_file, output_file = phases[p]
        log.info(f"[Phase:{p}] 开始")

        if required_file and not Path(required_file).exists():
            log.error(f"[Phase:{p}] 输入文件不存在: {required_file}")
            state["errors"].append(f"{p}: missing {required_file}")
            _send_alert(f"morning-brief [{date_str}] Phase {p} 失败：{required_file} 不存在", dry_run)
            break

        try:
            result = fn(
                date=date_str,
                dry_run=dry_run,
                input_file=required_file,
                output_file=output_file,
            )
            log.info(f"[Phase:{p}] 完成 → {result}")
        except Exception as e:
            log.exception(f"[Phase:{p}] 异常: {e}")
            state["errors"].append(f"{p}: {str(e)}")
            _send_alert(f"morning-brief [{date_str}] Phase {p} 异常：{e}", dry_run)
            if p in ("push",):
                break

    state["duration_seconds"] = (datetime.now() - start_time).seconds
    state["status"] = "success" if not state["errors"] else "partial"
    log.info(f"[Done] {state['status']} in {state['duration_seconds']}s | errors={state['errors']}")
    return state


def _send_alert(message: str, dry_run: bool):
    """推送运行告警至 Telegram（不影响主流程）"""
    if dry_run:
        print(f"[DRY-RUN ALERT] {message}")
        return
    try:
        import requests
        token = os.getenv("TELEGRAM_BOT_TOKEN")
        chat_id = os.getenv("TELEGRAM_INVEST_CHAT_ID")
        requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat_id, "text": f"⚠️ {message}"},
            timeout=10,
        )
    except Exception:
        pass


# ── CLI ──────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    # 确保工作目录是项目根目录（cron 运行时 CWD 可能不正确）
    os.chdir(Path(__file__).parent)

    parser = argparse.ArgumentParser(description="morning-brief 日报 Pipeline")
    parser.add_argument("--date",      default="today", help="日期，默认 today")
    parser.add_argument("--dry-run",   action="store_true", help="不推送，不写 Obsidian")
    parser.add_argument("--phase",     choices=["recon", "fetch", "score", "select", "push", "log"],
                        help="仅运行指定 Phase（调试用）")
    parser.add_argument("--log-level", default="INFO")
    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    )

    check_env()

    date_str = datetime.now().strftime("%Y-%m-%d") if args.date == "today" else args.date

    state = run(date_str=date_str, dry_run=args.dry_run, phase=args.phase)
    sys.exit(0 if state["status"] == "success" else 1)
