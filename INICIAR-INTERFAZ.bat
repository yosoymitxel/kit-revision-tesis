@echo off
rem Inicia el servidor del Centro de Control y abre la interfaz web
chcp 65001 >nul
call "%~dp0_iniciar.bat" kit.servidor
pause
