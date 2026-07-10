#!/usr/bin/env bash
# 停止由 scripts/dev.sh 或 scripts/verify_dev.sh 启动的前后端服务。

set -e

cd "$(dirname "$0")/.."

echo "=== Stopping DeepAgents Scaffold services ==="

stop_port() {
    local port=$1
    local stopped=0

    if command -v fuser >/dev/null 2>&1; then
        fuser -k "${port}/tcp" >/dev/null 2>&1 || true
        stopped=1
    elif command -v lsof >/dev/null 2>&1; then
        local pids
        pids=$(lsof -ti:"${port}" 2>/dev/null || true)
        if [ -n "$pids" ]; then
            echo "$pids" | xargs -r kill 2>/dev/null || true
        fi
        stopped=1
    fi

    if [ "$stopped" -eq 0 ]; then
        echo "Warning: neither fuser nor lsof available; cannot stop port ${port} precisely."
    fi
}

stop_port 8000
stop_port 3000

# 兜底：停止后端 uvicorn（命令特征足够具体，不会误伤调用方 shell）
pkill -f "uvicorn scaffold.api.app:app" 2>/dev/null || true

echo "Services stopped."
