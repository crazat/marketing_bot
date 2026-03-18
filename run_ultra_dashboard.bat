@echo off
chcp 65001 > nul
echo 🧠 Starting Kyurim Marketing OS v6.0 (ULTRA THINKING)...
echo ------------------------------------------------
cd /d "%~dp0"
python -m streamlit run dashboard_ultra.py
if errorlevel 1 (
    echo.
    echo ❌ Program exited with error code %errorlevel%.
    pause
)
