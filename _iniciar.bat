@echo off
rem Prepara Python y ejecuta el modulo indicado en %1
chcp 65001 >nul
cd /d "%~dp0"
set "PY="
rem Preferir versiones con paquetes ya compilados para copy-spotter
for %%V in (3.12 3.11 3.13 3.10) do if not defined PY py -%%V -c "1" >nul 2>nul && set "PY=py -%%V"
if not defined PY where py >nul 2>nul && set "PY=py -3"
if not defined PY where python >nul 2>nul && set "PY=python"
if not defined PY (
  echo No se encontro Python. Instalalo desde https://www.python.org/downloads/ marcando "Add Python to PATH".
  pause & exit /b 1
)
if not exist ".venv\Scripts\python.exe" (
  echo Preparando el entorno por primera vez...
  %PY% -m venv .venv || (echo No se pudo crear el entorno. & pause & exit /b 1)
)
rem Reinstala si requirements.txt cambio desde la ultima instalacion
fc /b requirements.txt ".venv\.instalado" >nul 2>nul || (
  echo Instalando dependencias...
  ".venv\Scripts\python.exe" -m pip install -q --disable-pip-version-check -r requirements.txt || (echo Fallo la instalacion. Revisa tu conexion. & pause & exit /b 1)
  copy /y requirements.txt ".venv\.instalado" >nul
)
".venv\Scripts\python.exe" -m %*
