@echo off
chcp 65001 >nul
setlocal

title g360-textofix - Corrector de texto

:: Lanzador del proyecto en modo desarrollo: sincroniza dependencias y
:: arranca con el codigo de src/. Para uso diario, el .exe de dist/ va
:: solo y no necesita uv.
::
:: OJO: correr solo UNA instancia. El .exe y este .bat usan los mismos
:: atajos (Ctrl+Shift+E/Z/R): el segundo en arrancar falla con error 1409.

where uv >nul 2>&1
if errorlevel 1 (
    echo [AVISO] uv no esta instalado.
    echo Ejecuta primero setup.bat, o instalalo desde https://github.com/astral-sh/uv
    pause
    exit /b 1
)

echo [G360] Sincronizando dependencias...
:: El extra ai trae google-genai (Gemini) y httpx (NVIDIA NIM).
uv sync --extra ai
if errorlevel 1 (
    echo [ERROR] No se pudieron instalar las dependencias.
    pause
    exit /b 1
)

echo.
echo [G360] Atajos: Ctrl+Shift+E corregir / Z deshacer / R rehacer.
echo [G360] Correccion: nube, NVIDIA NIM si hay clave, si no Gemini;
echo [G360] si una falla, reintenta con la otra en el mismo pedido.
echo [G360] Si los atajos no registran (error 1409), hay OTRA instancia
echo [G360] corriendo: cerrala primero.
echo [G360] Ctrl+C para salir.
echo.
uv run python src\main.py --modo ia %*
if errorlevel 1 pause
