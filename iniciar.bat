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

if exist ".env" (
    echo [G360] Modo IA: corrige de verdad con Gemini.
    uv sync --extra ai --quiet
    uv run python src\main.py --modo ia %*
) else (
    echo [G360] ETAPA 1: todavia NO corrige. Falta el archivo .env con la clave.
    echo [G360] Copia .env.example a .env, pega tu GEMINI_API_KEY y vuelve a ejecutar.
    echo [G360] Mientras tanto, modo demo: el texto se devuelve entre comillas.
    echo.
    uv run python src\main.py --mock-transform wrap %*
)
if errorlevel 1 pause