@echo off
rem PadMint for Windows. Double-click to start; Python is included.
cd /d "%~dp0"
"%~dp0python\python.exe" -m padmint %*
echo.
pause
