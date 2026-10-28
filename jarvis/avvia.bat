@echo off
title Jarvis
cd /d "%~dp0"
where py >nul 2>nul
if %errorlevel%==0 (
    py -3 jarvis.py
) else (
    python jarvis.py
)
pause
