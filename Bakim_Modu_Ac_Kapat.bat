@echo off
chcp 65001 >nul
powershell -ExecutionPolicy Bypass -File "%~dp0set_maintenance.ps1" -State toggle
pause
