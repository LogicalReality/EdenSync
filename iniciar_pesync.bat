@echo off
title PESync - Ejecutando...
cd /d "%~dp0"

:: Verificar si existe el entorno virtual
if exist .venv\Scripts\python.exe (
    echo Iniciando PESync usando el entorno virtual...
    .venv\Scripts\python.exe main.py
) else (
    echo [ERROR] No se encontro el entorno virtual ['.venv'].
    echo Asegurate de haber instalado las dependencias requeridas.
)

:: Pausa final por si ocurre un error catastrófico no atrapado
pause
