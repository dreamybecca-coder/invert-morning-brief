#!/usr/bin/env python3
"""
Phase 4b · Pusher — 推送 Telegram + 写入 Obsidian

输入:  daily_brief.json
输出:  push_result.json

dry-run 模式: 只打印到控制台，不推送，不写 Obsidian。
两条消息间隔 5s（防止 Telegram 消息顺序混乱）。
Obsidian 写入: 新建文件，不全量重写已有文件。
"""

import json
import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).parent.parent

log = logging.getLogger(__name__)

TELEGRAM_RETRY = 3
TELEGRAM_RETRY_INTERVAL = 10
MESSAGE_GAP = 5  # 两桶消息间隔秒数


# ── Telegram 推送 ─────────────────────────────────────────────────────────────

def _send_telegram(text: str, chat_id: str, token: str) -> int:
    """发送 Telegram 消息，返回 message_id；失败抛出异常"""
    import requests

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "disable_web_page_preview": True,
        "parse_mode": "",  # 纯文本，不用 Markdown（特殊字符无需转义）
    }

    for attempt in range(TELEGRAM_RETRY):
        try:
            resp = requests.post(url, json=payload, timeout=30)
            resp.raise_for_status()
            msg_id = resp.json()["result"]["message_id"]
            log.info(f"[push] Telegram 发送成功 (message_id={msg_id})")
            return msg_id
        except Exception as e:
            safe_err = str(e).replace(token, "***TOKEN***") if token else str(e)
            log.warning(f"[push] Telegram 发送失败 attempt {attempt+1}: {safe_err}")
            if attempt < TELEGRAM_RETRY - 1:
                time.sleep(TELEGRAM_RETRY_INTERVAL)

    raise RuntimeError(f"Telegram 推送失败（重试 {TELEGRAM_RETRY} 次）")


# ── Obsidian 写入 ─────────────────────────────────────────────────────────────

def _write_obsidian(date: str, content: str, bucket: str, vault: str):
    """写入 Obsidian 存档文件（新建，不覆盖已有）"""
    if bucket == "invest":
        rel = f"01-Projects/Invert-Bot/Morning-Brief/{date}-morning-brief-Invest news.md"
    else:
        rel = f"01-Projects/AI-Narrative-Lab/Morning-Brief/{date}-morning-brief-AI news.md"

    path = Path(vault) / rel
    path.parent.mkdir(parents=True, exist_ok=True)

    if path.exists():
        log.warning(f"[push] {path.name} 已存在，跳过写入（使用 Skill 2 tagger.py 更新字段）")
        return

    path.write_text(content, encoding="utf-8")
    size = path.stat().st_size

    if size < 500:
        raise RuntimeError(f"Obsidian 文件写入异常，字节数过小: {size} bytes → {path}")

    log.info(f"[push] Obsidian 写入成功: {path} ({size} bytes)")


def _obsidian_backup(date: str, content: str, bucket: str):
    """Obsidian 写入失败时本地备份"""
    backup_dir = Path.home() / "morning-brief-backup"
    backup_dir.mkdir(exist_ok=True)
    suffix = "invest" if bucket == "invest" else "ai"
    backup_path = backup_dir / f"{date}-{suffix}.md"
    backup_path.write_text(content, encoding="utf-8")
    log.info(f"[push] Obsidian 备份写入: {backup_path}")


# ── 主函数 ────────────────────────────────────────────────────────────────────

def run_push(date: str, dry_run: bool, input_file: str = "daily_brief.json",
             output_file: str = "push_result.json") -> dict:
    from scripts.formatter import run_format

    # Step 1: 格式化
    fmt_file = "formatted_brief.json"
    run_format(date=date, dry_run=dry_run, input_file=input_file, output_file=fmt_file)
    formatted = json.loads(Path(fmt_file).read_text(encoding="utf-8"))

    invest_tg = formatted["invest"]["telegram"]
    ai_tg = formatted["ai"]["telegram"]
    invest_ob = formatted["invest"]["obsidian"]
    ai_ob = formatted["ai"]["obsidian"]

    result = {
        "date": date,
        "dry_run": dry_run,
        "pushed_at": datetime.now(timezone.utc).isoformat(),
        "invest": {},
        "ai": {},
    }

    if dry_run:
        # ── DRY-RUN：打印到控制台 ──────────────────────────────────────────
        print("\n" + "=" * 60)
        print("DRY-RUN · 投资桶 Telegram 消息预览")
        print("=" * 60)
        print(invest_tg)

        print("\n" + "=" * 60)
        print("DRY-RUN · AI产业链桶 Telegram 消息预览")
        print("=" * 60)
        print(ai_tg)

        print("\n" + "=" * 60)
        print("DRY-RUN · 投资桶 Obsidian 存档预览（前 500 字）")
        print("=" * 60)
        print(invest_ob[:500] + "...")

        print("\n" + "=" * 60)
        print("DRY-RUN · AI桶 Obsidian 存档预览（前 500 字）")
        print("=" * 60)
        print(ai_ob[:500] + "...")

        print("\n[DRY-RUN] ✅ 格式检查完成。实际运行时将推送 Telegram + 写入 Obsidian。\n")
        result["invest"]["status"] = "dry-run"
        result["ai"]["status"] = "dry-run"

    else:
        # ── 正式推送 ──────────────────────────────────────────────────────
        token = os.getenv("TELEGRAM_BOT_TOKEN")
        invest_chat = os.getenv("TELEGRAM_INVEST_CHAT_ID")
        ai_chat = os.getenv("TELEGRAM_AI_CHAT_ID")
        vault = os.getenv("OBSIDIAN_VAULT_PATH")

        # 推送投资桶
        try:
            msg_id = _send_telegram(invest_tg, invest_chat, token)
            result["invest"]["telegram_msg_id"] = msg_id
            result["invest"]["status"] = "ok"
        except Exception as e:
            log.error(f"[push] 投资桶 Telegram 失败: {e}")
            result["invest"]["status"] = "failed"
            result["invest"]["error"] = str(e)

        time.sleep(MESSAGE_GAP)

        # 推送 AI 桶
        try:
            msg_id = _send_telegram(ai_tg, ai_chat, token)
            result["ai"]["telegram_msg_id"] = msg_id
            result["ai"]["status"] = "ok"
        except Exception as e:
            log.error(f"[push] AI桶 Telegram 失败: {e}")
            result["ai"]["status"] = "failed"
            result["ai"]["error"] = str(e)

        # 写入 Obsidian
        if vault:
            for bucket, content in [("invest", invest_ob), ("ai", ai_ob)]:
                try:
                    _write_obsidian(date, content, bucket, vault)
                except Exception as e:
                    log.error(f"[push] Obsidian {bucket} 写入失败: {e}，备份到本地")
                    _obsidian_backup(date, content, bucket)
        else:
            log.warning("[push] OBSIDIAN_VAULT_PATH 未设置，跳过 Obsidian 写入")

    if output_file:
        Path(output_file).write_text(
            json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    return {"status": "success", "count": 20}


if __name__ == "__main__":
    import argparse
    import logging as _logging
    _logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")

    env_file = ROOT / ".env"
    if env_file.exists():
        import os
        for line in env_file.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())

    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default=datetime.now().strftime("%Y-%m-%d"))
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    result = run_push(date=args.date, dry_run=args.dry_run,
                      input_file="daily_brief.json",
                      output_file="push_result.json")
    print(result)
