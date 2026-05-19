@echo off
setlocal

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\start_dev.ps1" %*

if errorlevel 1 (
  echo.
  echo BrightToDo failed to start. See the messages above.
  pause
)
