@echo off
REM ============================================================
REM  IBKR Trading Performance Dashboard - launcher (Windows)
REM  Double-click this file to open the dashboard in your browser.
REM ============================================================
cd /d "%~dp0"

echo Checking dependencies...
python -m pip install -r requirements.txt --quiet

echo Starting dashboard...  (a browser tab will open)
echo To stop it, close this window.
python -m streamlit run app.py

pause
