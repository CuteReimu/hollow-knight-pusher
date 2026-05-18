#!/usr/bin/env bash
# 启动脚本
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

# 使用 .env.prod（复制为 NoneBot2 默认读取的 .env）
if [ ! -f .env.prod ] && [ -f .env ]; then
  cp .env .env.prod
  echo "[info] 已将 .env 复制为 .env.prod，请按需修改后重新运行。"
  exit
fi

# 自动选择 python3 或 python
if command -v python3 &>/dev/null; then
  PYTHON=python3
else
  PYTHON=python
fi

# 设置生产环境标志并启动
ENVIRONMENT=prod "$PYTHON" bot.py