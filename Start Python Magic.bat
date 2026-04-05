@echo off
title Tailscale Magic - Python Launcher
echo [SYSTEM] Starting Tailscale Magic Environment...
cd /d "%~dp0"
python main.py
if %errorlevel% neq 0 (
    echo [ERROR] Python not found or crash detected.
    echo Make sure Python and requirements are installed.
    pause
)
pause
