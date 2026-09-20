@echo off
setlocal
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" "jamal_dashboard_launcher_v25.py"
  goto done
)
py -3 -c "import sys; sys.exit(sys.version_info < (3, 11))" >nul 2>&1
if not errorlevel 1 (
  py -3 "jamal_dashboard_launcher_v25.py"
  goto done
)
python -c "import sys; sys.exit(sys.version_info < (3, 11))" >nul 2>&1
if not errorlevel 1 (
  python "jamal_dashboard_launcher_v25.py"
  goto done
)
if exist "%USERPROFILE%\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" (
  "%USERPROFILE%\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" "jamal_dashboard_launcher_v25.py"
  goto done
)
echo Python was not found. Install Python 3.12 and follow QUICK_START.txt.
:done
pause
