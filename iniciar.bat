@echo off
chcp 65001 >nul
setlocal

title g360-textofix - Corrector de texto

:: Lanzador unico del proyecto. Sincroniza dependencias y arranca.
:: PyInstaller / version portable se dejo para mas adelante: la Etapa 1
:: corre sobre Python y no lo necesita.

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

echo [G360] Iniciando corrector. Atajo: Ctrl+Shift+E
echo [G360] Ctrl+C para salir.
echo.
echo [G360] ETAPA 1: todavia NO corrige. Usa --mock-transform wrap para que
echo [G360] veas el texto encerrado en comillas y confirmes que funciona.
echo.

uv run python src\main.py --mock-transform wrap %*
if errorlevel 1 pause