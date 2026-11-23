@echo off
call "%~dp0_iniciar.bat" kit.revisar %*
if exist "%~dp03-RESULTADOS\panel.html" start "" "%~dp03-RESULTADOS\panel.html"
pause
