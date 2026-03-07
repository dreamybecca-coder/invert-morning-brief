# Agent 兼容性映射表 v1.0

> 此文件解决不同 Agent 运行环境的工具调用差异。
> 主 SKILL.md 使用标准接口，各 Agent 按此表映射到实际调用方式。

---

## 标准接口（工具无关）

```bash
# 日常运行（由 cron 或 Agent 触发）
python run_morning_brief.py --date today

# 干跑测试（不推送，不写 Obsidian）
python run_morning_brief.py --dry-run --date today

# 单 Phase 调试
python run_morning_brief.py --phase recon|fetch|score|select|push

# 环境验证
python scripts/validate.py --check-refs
python scripts/validate.py --check-env
```

---

## OpenClaw 映射

OpenClaw 使用 `[tool: bash]` 执行 shell 命令，`[tool: file_write]` 写入文件系统。

```yaml
# OpenClaw 日常触发（每日 08:30 cron）
trigger_type: cron
cron_expression: "30 8 * * *"
command: |
  cd {PROJECT_ROOT} && python run_morning_brief.py --date today
tool: bash

# OpenClaw 写入 Obsidian
tool: file_write
path_env: OBSIDIAN_VAULT_PATH
note: "Obsidian vault 路径必须在 .env 中配置为绝对路径"

# OpenClaw 接收 Telegram 深挖指令
tool: telegram_listener
pattern: "^深挖 (AI-\d+|\d+)( (AI-\d+|\d+))*$"
on_match: "python deep_dive.py --ids {matched_ids} --vault $OBSIDIAN_VAULT_PATH"
note: "此触发逻辑属于 Skill 2，此处仅为接口约定"
```

---

## Claude Code 映射

Claude Code 直接在 terminal 执行标准接口命令。

```bash
# 首次构建和测试
cd morning-brief-skill
cp .env.example .env         # 填入 API keys
pip install -r requirements.txt

# 验证环境
python scripts/validate.py --check-env

# 全链路测试（dry-run）
python run_morning_brief.py --dry-run --date today

# 正式部署 cron（macOS）
crontab -e
# 添加：30 8 * * * cd {PROJECT_ROOT} && python run_morning_brief.py --date today >> logs/cron.log 2>&1
```

---

## 通用 Agent / 未来兼容

若未来接入其他 Agent（如 n8n / Dify / 自定义 Agent），可通过 REST API 调用：

```bash
# 启动本地 API 服务（可选，不影响 cron 直接调用）
python api_server.py --port 8765
```

```http
# 触发日报
POST http://localhost:8765/brief/run
Content-Type: application/json
{"date": "today", "dry_run": false}

# 查询今日简报状态
GET http://localhost:8765/brief/status?date=today

# 触发深挖（Skill 2 入口）
POST http://localhost:8765/brief/deep-dive
{"ids": ["AI-3", "AI-7"], "vault_path": "/path/to/obsidian"}
```

REST API 封装是可选模块，不影响主 pipeline 的 cron 运行。

---

## 环境变量清单 (.env.example)

```bash
# LLM API（二选一）
KIMI_API_KEY=sk-xxx
ANTHROPIC_API_KEY=sk-ant-xxx

# Telegram
TELEGRAM_BOT_TOKEN=xxx:xxx
TELEGRAM_INVEST_CHAT_ID=-100xxxxxxxx   # 投资桶频道
TELEGRAM_AI_CHAT_ID=-100xxxxxxxx       # AI桶频道

# Obsidian
OBSIDIAN_VAULT_PATH=/Users/rebecca/obsidian-vault

# 可选：付费源认证
THE_INFORMATION_COOKIE=xxx
SEMIANALYSIS_COOKIE=xxx

# 运行参数
BRIEF_LOOKBACK_HOURS=24
BRIEF_MAX_INVEST=10
BRIEF_MAX_AI=10
LOG_LEVEL=INFO
```
