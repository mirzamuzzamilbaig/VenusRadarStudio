@echo off
title VenusRadarStudio Launcher
echo.
echo  ====================================================
echo     ^🪐  VenusRadarStudio v1.0 — Starting...
echo  ====================================================
echo.

cd /d "%~dp0"

:: Install dependencies
echo  [1/2] Installing Python dependencies...
pip install flask flask-cors numpy scipy Pillow matplotlib --quiet --disable-pip-version-check

echo  [2/2] Starting Flask server...
echo.
echo  Open your browser at:  http://localhost:5000
echo.
echo  Press CTRL+C to stop the server.
echo.

python app\main.py

pause
