@echo off
chcp 65001 >nul
setlocal

title g360-textofix - Corrector de texto

:: Lanzador unico del proyecto. Sincroniza dependencias y arranca.
:: Si ya tenes el .exe, no hace falta: ese va solo.

where uv >nul 2>&1
if errorlevel 1 (
    echo [AVISO] uv no esta instalado.
    echo Ejecuta primero setup.bat, o instalalo desde https://github.com/astral-sh/uv
    pause
    exit /b 1
)

echo [G360] Sincronizando dependencias...
uv sync
if errorlevel 1 (
    echo [ERROR] No se pudieron instalar las dependencias.
    pause
    exit /b 1
)

echo [G360] Iniciando corrector. Atajos: Ctrl+Shift+E / Z / R
echo [G360] La primera vez te pide la clave de Gemini y la guarda cifrada.
echo [G360] Ctrl+C para salir.
echo.
uv sync --extra ai --quiet
uv run python src\main.py --modo ia %*
if errorlevel 1 pause