@echo off
REM Start all campus-notice services and open the unified admin UI.
cd /d "%~dp0"
python "%~dp0qq-service\launch.py"
if errorlevel 1 pause
