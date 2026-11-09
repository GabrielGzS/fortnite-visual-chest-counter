@echo off
setlocal
cd /d "%~dp0" || exit /b 1
if not exist ".venv\Scripts\pythonw.exe" (
    echo Set up the local Python environment first. See Development in README.md.
    pause
    exit /b 1
)
start "" "%~dp0.venv\Scripts\pythonw.exe" -m fortnite_chest_counter.gui
