#!/usr/bin/env python3
"""
validate.py · 环境与引用文件验证
用法：
  python scripts/validate.py --check-env
  python scripts/validate.py --check-refs
  python scripts/validate.py --check-all
"""

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
REFS = ROOT / "references"
EXAMPLES = ROOT / "examples"

REQUIRED_REFS = [
    "sources.json",
    "scoring.md",
    "domain-map.md",
    "output-format.md",
    "agent-compat.md",
]

REQUIRED_EXAMPLES = [
    "good-breaking.md",
    "good-analysis.md",
]

REQUIRED_ENV = [
    "TELEGRAM_BOT_TOKEN",
    "TELEGRAM_INVEST_CHAT_ID",
    "TELEGRAM_AI_CHAT_ID",
    "OBSIDIAN_VAULT_PATH",
]

LLM_ENV_OPTIONS = ["KIMI_API_KEY", "ANTHROPIC_API_KEY"]


def check_refs() -> bool:
    ok = True
    print("\n── References 检查 ─────────────────────────")
    for f in REQUIRED_REFS:
        path = REFS / f
        if path.exists():
            size = path.stat().st_size
            print(f"  ✅ {f} ({size} bytes)")
        else:
            print(f"  ❌ {f} 不存在")
            ok = False

    print("\n── Examples 检查 ───────────────────────────")
    for f in REQUIRED_EXAMPLES:
        path = EXAMPLES / f
        if path.exists():
            print(f"  ✅ {f}")
        else:
            print(f"  ❌ {f} 不存在")
            ok = False

    # 验证 sources.json 格式
    sources_path = REFS / "sources.json"
    if sources_path.exists():
        try:
            data = json.loads(sources_path.read_text())
            invest_total = sum(
                len(data["bucket_invest"].get(f"tier_{t}", []))
                for t in ["S", "A", "B", "C"]
            )
            ai_total = sum(
                len(data["bucket_ai"].get(f"tier_{t}", []))
                for t in ["S", "A", "B", "C"]
            )
            print(f"\n  sources.json: 投资桶 {invest_total} 源 | AI桶 {ai_total} 源 | 合计 {invest_total+ai_total} 源")
        except Exception as e:
            print(f"  ❌ sources.json 解析失败: {e}")
            ok = False

    return ok


def check_env() -> bool:
    # 尝试加载 .env
    env_file = ROOT / ".env"
    if env_file.exists():
        with open(env_file) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip())

    ok = True
    print("\n── 环境变量检查 ────────────────────────────")
    for k in REQUIRED_ENV:
        val = os.getenv(k)
        if val:
            masked = val[:4] + "***" + val[-4:] if len(val) > 8 else "***"
            print(f"  ✅ {k} = {masked}")
        else:
            print(f"  ❌ {k} 未设置")
            ok = False

    has_llm = any(os.getenv(k) for k in LLM_ENV_OPTIONS)
    if has_llm:
        found = [k for k in LLM_ENV_OPTIONS if os.getenv(k)]
        print(f"  ✅ LLM API Key: {found}")
    else:
        print(f"  ❌ LLM API Key 未设置（需要 {LLM_ENV_OPTIONS} 之一）")
        ok = False

    # 检查 Obsidian vault 路径是否存在
    vault = os.getenv("OBSIDIAN_VAULT_PATH")
    if vault:
        if Path(vault).exists():
            print(f"  ✅ Obsidian vault 路径存在: {vault}")
        else:
            print(f"  ⚠️  Obsidian vault 路径不存在（首次运行会自动创建子目录）: {vault}")

    return ok


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--check-env",  action="store_true")
    parser.add_argument("--check-refs", action="store_true")
    parser.add_argument("--check-all",  action="store_true")
    args = parser.parse_args()

    results = []
    if args.check_env or args.check_all:
        results.append(check_env())
    if args.check_refs or args.check_all:
        results.append(check_refs())

    if not results:
        parser.print_help()
        sys.exit(0)

    all_ok = all(results)
    print(f"\n{'✅ 全部通过' if all_ok else '❌ 存在问题，请修复后重试'}")
    sys.exit(0 if all_ok else 1)
