"""
Prueba del ultimo recurso: corregir el campo ENTERO.

Se llego a este camino porque en Flutter (Flet) no hay ninguna forma de saber
que selecciono el usuario: no expone TextPattern y no responde al Ctrl+C
sintetico. Ahi la unica opcion es leer el valor completo, corregirlo entero y
escribirlo entero.

Esta prueba NO usa Flet (arrancaria una app de escritorio pesada). Usa un
control EDIT de Win32 real y ejercita el mismo codigo:

- la escritura por ValuePattern sobre el control enfocado,
- la guarda que se niega a tocar campos de varias lineas.

    uv run python tests/smoke_campo_entero.py
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))


import smoke_win32_edit as H

from core.adapters import build_adapters, pick_adapter
from core.adapters.base import Capture
from core.config import Config
from core.logsetup import setup_logging
from core.winapi import foreground_context

log = setup_logging(verbose=False)

TEXTO = "analizandodo una descuento comercial"
MULTILINEA = "primera linea\nsegunda linea"


def _adaptador():
    ctx = foreground_context()
    return pick_adapter(build_adapters(Config.from_env()), ctx)


def main() -> int:
    H._ocultar_consola()
    ventana = H._Ventana()
    ventana.abrir()
    fallos = 0

    try:
        # --- 1. Escritura del campo completo por ValuePattern ---------------
        log.info("=== escribir el campo entero ===")
        H._poner_texto(ventana.edit, TEXTO)
        H._enfocar(ventana)

        adaptador = _adaptador()
        if adaptador is None:
            print("  FALLO: no se encontro adaptador")
            return 1

        capture = Capture(text=TEXTO, meta={"via": "uia-value"})
        adaptador.write(None, capture, f"«{TEXTO}»")
        time.sleep(0.5)

        texto = H._texto(ventana.edit)
        print(f"  documento ahora: {texto!r}")
        if texto != f"«{TEXTO}»":
            print("  FALLO: el campo entero no se reescribio")
            fallos += 1
        else:
            print("  OK: el campo entero se reescribio por ValuePattern")

        # --- 2. La guarda se niega con texto multilinea ---------------------
        log.info("=== guarda de campo multilinea ===")
        H._poner_texto(ventana.edit, MULTILINEA)
        H._enfocar(ventana)
        time.sleep(0.3)

        adaptador = _adaptador()
        captura = adaptador._read_valor_entero(foreground_context())
        if captura is not None:
            print("  FALLO: se acepto un campo multilinea (SetValue lo aplanaria)")
            fallos += 1
        else:
            print("  OK: el campo multilinea se rechaza y queda intacto")
            print(f"  documento sigue: {H._texto(ventana.edit)!r}")
    finally:
        ventana.cerrar()

    print()
    if fallos:
        print(f"=== {fallos} verificacion(es) fallaron ===")
        return 1
    print("=== correccion de campo entero verificada ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
