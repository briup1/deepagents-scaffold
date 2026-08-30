#!/usr/bin/env bash
# Start backend and frontend in development mode.

set -e

cd "$(dirname "$0")/.."

echo "=== DeepAgents Scaffold Dev Mode ==="
echo ""

# Clean previous development logs for a focused debugging session
if [ -d logs ]; then
    echo "[1/3] Cleaning previous development logs..."
    rm -f logs/*.log
fi

# Start backend in background
echo "[2/3] Starting FastAPI backend on http://localhost:8000"
PYTHONPATH=src uv run uvicorn scaffold.api.app:app --host 0.0.0.0 --port 8000 --reload --reload-dir src/scaffold &
BACKEND_PID=$!

# Start frontend
echo "[3/3] Starting Vite frontend on http://localhost:3002"
cd src/web
npm install --silent 2>/dev/null || true
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
