@echo off
rem Runs start_demo.ps1 without changing the PowerShell execution policy (Windows blocks .ps1 files by default).
rem Example:  scripts\start_demo.cmd -Capture
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0start_demo.ps1" %*
