@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv-course\Scripts\pythonw.exe" (
  echo The project Python environment is missing: .venv-course
  pause
  exit /b 1
)
if not exist "deploy\audio_console.py" (
  echo The audio console source is missing.
  pause
  exit /b 1
)
start "" "%~dp0.venv-course\Scripts\pythonw.exe" "%~dp0deploy\audio_console.py"
exit /b 0
