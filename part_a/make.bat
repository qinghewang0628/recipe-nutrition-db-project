@echo off
REM Cross-platform `make` shim for Windows CMD / PowerShell.
REM Lets you literally type `make seed` without installing GNU make.
chcp 65001 >nul
set PYTHONIOENCODING=utf-8
python "%~dp0make.py" %*
exit /b %ERRORLEVEL%
