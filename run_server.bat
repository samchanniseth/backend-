@echo off
echo === SubtitleAI Backend Startup ===

if not exist venv (
    echo [1/4] Creating virtual environment...
    python -m venv venv
)

echo [2/4] Activating venv...
call venv\Scripts\activate.bat

echo [3/4] Installing dependencies...
pip install --upgrade pip -q
pip install -r requirements.txt -q

echo [4/4] Starting server on http://0.0.0.0:8000 ...
uvicorn server:app --host 0.0.0.0 --port 8000 --reload
pause
