# -*- mode: python ; coding: utf-8 -*-
"""
Empaquetado con PyInstaller para distribuir g360-textofix a otros usuarios.

Cada usuario recibe un unico .exe y pone SU propia clave API desde la bandeja.
El ejecutable NO lleva ninguna clave dentro: una clave embebida en un binario
se puede extraer, y ademas seria la misma para todos.
"""

import sys
from pathlib import Path

# Rutas del proyecto
RAIZ = Path(SPECPATH).resolve()          # noqa: F821  (definido por PyInstaller)
SRC = RAIZ / "src"

# `main.py` espera ejecutarse con src/ en sys.path (hace imports de `core`).
sys.path.insert(0, str(SRC))

# Dependencias que PyInstaller no detecta solas porque se importan en vivo
# dentro de funciones: la IA se importa perezoso en core/ai.py.
hidden = [
    "core",
    "core.casos",
    "core.bateria",
    "core.ai",
    "google.genai",
    "google.genai.types",
    "uiautomation",
    "win32clipboard",
    "win32com.client",
    "pythoncom",
    "pywintypes",
]

# uiautomation trae DLLs propias que hay que asegurar.
binarios = []
dlls = SRC / "uiautomation"
for nombre in ("UIAutomationCore.dll",):
    cand = dlls / nombre
    if cand.exists():
        binarios.append((str(cand), "."))
if not binarios:
    # pywin32 / uiautomation estan en el site-packages del venv de uv.
    import importlib.util
    spec = importlib.util.find_spec("uiautomation")
    if spec is None:
        raise SystemExit(
            "uiautomation no esta en el entorno. "
            "Corre primero: uv sync --extra ai --extra pack"
        )
    base = Path(spec.origin).resolve().parent
    for cand in base.glob("*.dll"):
        binarios.append((str(cand), "."))

a = Analysis(
    [str(SRC / "main.py")],
    pathex=[str(SRC)],
    binaries=binarios,
    # assets/ entero: icono de bandeja (ruta_icono) y sonidos (feedback).
    datas=[(str(RAIZ / "assets"), "assets")],
    hiddenimports=hidden,
    hookspath=[],
    runtime_hooks=[],
    excludes=["tkinter", "matplotlib", "notebook", "IPython", "pytest"],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="g360-textofix",
    icon=str(RAIZ / "assets" / "g360-textofix.ico"),
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,  # arranca en segundo plano; la consola la crea el propio
    # programa cuando pide algo (core/consola.py). Desde un terminal,
    # --probar-api y --bateria imprimen ahi (AttachConsole).
    disable_windowed_traceback=False,
)