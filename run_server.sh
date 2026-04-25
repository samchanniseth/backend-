#!/usr/bin/env bash
# run_server.sh — starts the SubtitleAI backend
set -e

echo "=== SubtitleAI Backend Startup ==="

# 1. Create venv if missing
if [ ! -d "venv" ]; then
    echo "[1/4] Creating virtual environment..."
    python3 -m venv venv
fi

# 2. Activate
source venv/bin/activate

# 3. Install deps
echo "[2/4] Installing dependencies..."
pip install --upgrade pip -q
pip install -r requirements.txt -q

# 4. Launch
echo "[3/4] Starting server on http://0.0.0.0:8000"
echo "[4/4] Press Ctrl+C to stop"
uvicorn server:app --host 0.0.0.0 --port 8000 --reload
