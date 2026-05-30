@echo off
setlocal

pushd "%~dp0" >nul 2>&1
if errorlevel 1 (
  echo.
  echo BrightToDo failed to locate the project directory.
  pause
  exit /b 1
)

if not exist ".\scripts\start_dev.ps1" (
  echo.
  echo BrightToDo startup script not found: .\scripts\start_dev.ps1
  popd >nul 2>&1
  pause
  exit /b 1
)

powershell -NoProfile -ExecutionPolicy Bypass -File ".\scripts\start_dev.ps1" %*
set "START_EXIT_CODE=%ERRORLEVEL%"

popd >nul 2>&1

if not "%START_EXIT_CODE%"=="0" (
  echo.
  echo BrightToDo failed to start. See the messages above.
  pause
)

exit /b %START_EXIT_CODE%
