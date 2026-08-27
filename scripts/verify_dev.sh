#!/usr/bin/env bash
# 使用 mock 模型启动后端和前端，用于端到端用户路径验证。

set -e

cd "$(dirname "$0")/.."

echo "=== DeepAgents Scaffold Verify Mode ==="
echo ""

# Clean previous development logs
if [ -d logs ]; then
    echo "[1/3] Cleaning previous development logs..."
    rm -f logs/*.log
fi

# Start backend with verification config
echo "[2/3] Starting FastAPI backend with config.verify.yaml on http://localhost:8000"
SCAFFOLD_CONFIG_PATH=config.verify.yaml PYTHONPATH=src uv run uvicorn scaffold.api.app:app --host 0.0.0.0 --port 8000 --reload &
BACKEND_PID=$!

# Start frontend
echo "[3/3] Starting Vite frontend on http://localhost:3002"
cd src/web
npm install --silent
npm run dev &
FRONTEND_PID=$!

cd ../..

echo ""
echo "Backend:  http://localhost:8000"
echo "Frontend: http://localhost:3002"
echo "Docs:     http://localhost:8000/docs"
echo ""
echo "Press Ctrl+C to stop both services."
echo ""

wait $BACKEND_PID $FRONTEND_PID
