@echo off
cd /d "%~dp0"
if exist "dist\0.7.2\ToolVH\ToolVH.exe" (
    start "" "dist\0.7.2\ToolVH\ToolVH.exe" %*
    exit /b
)
if exist ".venv\Scripts\pythonw.exe" (
    start "" ".venv\Scripts\pythonw.exe" launcher.py %*
    exit /b
)
echo Please install requirements.txt or build ToolVH with Build.ps1.
pause
