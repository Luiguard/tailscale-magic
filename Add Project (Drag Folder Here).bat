@echo off
setlocal
echo =======================================================
echo          TAILSCALE MAGIC : PROJECT REGISTER
echo =======================================================
echo.

set "PROJ_FOLDER=%~1"

if "%PROJ_FOLDER%"=="" (
    echo [HINT] You can also drag-and-drop a folder onto this script.
    set /p "PROJ_FOLDER=Enter Project Folder Path: "
)

:: Clear quotes
set PROJ_FOLDER=%PROJ_FOLDER:"=%

if not exist "%PROJ_FOLDER%" (
    echo [ERROR] Folder "%PROJ_FOLDER%" does not exist.
    pause
    exit /b
)

set /p "VIRTUAL_PATH=Enter Public Path (e.g. /NLP or /schule): "

echo.
echo [SYSTEM] Registering %PROJ_FOLDER% at %VIRTUAL_PATH%...
echo.

"%~dp0dist\TailscaleMagic.exe" --add "%PROJ_FOLDER%" "%VIRTUAL_PATH%"

echo.
echo =======================================================
echo [DONE] The project has been registered. 
echo It will start automatically in the background.
echo =======================================================
echo.
pause
