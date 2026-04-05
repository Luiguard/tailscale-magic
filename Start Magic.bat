@echo off
title Magic Hub
cd /d "%~dp0"

echo.
echo  ========================================
echo   Magic Hub v2.0 - Starting...
echo  ========================================
echo.

:: Check if Python is available
where python >nul 2>&1
if %errorlevel% neq 0 (
    echo  [FEHLER] Python nicht gefunden!
    echo  Bitte installiere Python von https://python.org
    pause
    exit /b 1
)

:: Install dependencies if needed
if exist "requirements.txt" (
    echo  [INFO] Pruefe Abhaengigkeiten...
    python -m pip install -r requirements.txt --quiet 2>nul
)

:: Kill any old instance on port 8080
for /f "tokens=5" %%a in ('netstat -ano ^| findstr :8080 ^| findstr LISTENING 2^>nul') do (
    taskkill /PID %%a /F >nul 2>&1
)

echo.
echo  [OK] Starte Magic Hub...
echo  Dashboard: http://127.0.0.1:8080
echo.
echo  Druecke Ctrl+C zum Beenden.
echo  ========================================
echo.

python main.py

if %errorlevel% neq 0 (
    echo.
    echo  [FEHLER] Magic Hub ist abgestuerzt.
    echo  Pruefe: magic_debug.log
    pause
)
