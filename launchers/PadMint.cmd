@echo off
rem PadMint for Windows. Double-click to start; Python is included.
cd /d "%~dp0"
rem Opened straight from the ZIP, Windows copies only this file to a temporary folder.
if not exist "%~dp0python\python.exe" (
  echo PadMint has to be unzipped first.
  echo Right-click the PadMint ZIP, choose Extract All, open the new folder, then double-click the PadMint file.
  echo.
  pause
  exit /b 1
)
"%~dp0python\python.exe" -m padmint %*
echo.
pause
