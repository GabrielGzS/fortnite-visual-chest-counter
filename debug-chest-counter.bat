@echo off
setlocal
pushd "%~dp0" || exit /b 1
if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" -m fortnite_chest_counter.gui %*
) else (
    python -m fortnite_chest_counter.gui %*
)
set "result=%errorlevel%"
if not "%result%"=="0" pause
popd
exit /b %result%
