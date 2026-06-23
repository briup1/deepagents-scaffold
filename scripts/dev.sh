#!/usr/bin/env bash
# Start backend and frontend in development mode.

set -e

cd "$(dirname "$0")/.."

echo "=== DeepAgents Scaffold Dev Mode ==="
echo ""

# Start backend in background
echo "[1/2] Starting FastAPI backend on http://localhost:8000"
PYTHONPATH=src uvicorn scaffold.api.app:app --host 0.0.0.0 --port 8000 --reload &
BACKEND_PID=$!

# Start frontend
echo "[2/2] Starting Vite frontend on http://localhost:3000"
cd src/web
npm install --silent 2>/dev/null || true
npm run dev &
FRONTEND_PID=$!

cd ../..

echo ""
echo "Backend:  http://localhost:8000"
echo "Frontend: http://localhost:3000"
echo "Docs:     http://localhost:8000/docs"
echo ""
echo "Press Ctrl+C to stop both services."
echo ""

wait $BACKEND_PID $FRONTEND_PID
