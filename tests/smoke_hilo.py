"""
Regresion: la correccion debe funcionar desde un hilo de trabajo.

UI Automation es COM, y COM se inicializa POR HILO. El atajo global dispara la
correccion en un hilo de trabajo para no congelar el bucle de mensajes, asi que
si ese hilo no inicializa COM, UIA falla con:

    [WinError -2147221008] CoInitialize has not been called

y el corrector se queda sin poder leer la seleccion. Esta prueba ejecuta el
ciclo completo desde un hilo, que es exactamente el escenario que rompia.

    uv run python tests/smoke_hilo.py
"""

from __future__ import annotations

import io
import sys
import threading
from contextlib import redirect_stdout
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import smoke_win32_edit as H

from core.config import Config
from core.engine import run_once
from core.logsetup import setup_logging

EM_SETSEL = 0x00B1
TEXTO = "El cliente pidio tres cajas"

log = setup_logging(verbose=False)


def main() -> int:
    H._ocultar_consola()
    ventana = H._Ventana()
    ventana.abrir()
    fallos = 0

    try:
        cfg = Config.from_env()
        resultado: dict = {}

        def desde_hilo() -> None:
            """Reproduce como lo invoca el atajo global."""
            # uiautomation imprime su error a stdout, asi que se captura.
            buffer = io.StringIO()
            with redirect_stdout(buffer):
                outcome = run_once(cfg, mode="mock", transform="wrap")
            resultado["outcome"] = outcome
            resultado["stdout"] = buffer.getvalue()

        H._poner_texto(ventana.edit, TEXTO)
        H._enfocar(ventana)
        H.user32.SendMessageW(ventana.edit, EM_SETSEL, 0, -1)

        hilo = threading.Thread(target=desde_hilo, name="prueba-hilo")
        hilo.start()
        hilo.join(timeout=30)

        if hilo.is_alive():
            print("  FALLO: el hilo se quedo colgado")
            return 1

        outcome = resultado.get("outcome")
        capturado = resultado.get("stdout", "")

        if "CoInitialize has not been called" in capturado:
            print("  FALLO: UIA fallo por COM sin inicializar en el hilo")
            print(capturado[:400])
            fallos += 1
        else:
            print("  OK: sin error de COM en el hilo de trabajo")

        if outcome is None:
            print("  FALLO: el hilo no devolvio resultado")
            fallos += 1
        else:
            print(f"  resultado desde el hilo: {outcome.reason}")
            if outcome.reason != "escrito":
                print("  FALLO: se esperaba 'escrito'")
                fallos += 1

        texto = H._texto(ventana.edit)
        print(f"  documento ahora: {texto!r}")
        if texto != f"«{TEXTO}»":
            print("  FALLO: el texto no se reemplazo")
            fallos += 1
        else:
            print("  OK: el ciclo completo funciona desde un hilo de trabajo")
    finally:
        ventana.cerrar()

    print()
    if fallos:
        print(f"=== {fallos} verificacion(es) fallaron ===")
        return 1
    print("=== la correccion en hilo de trabajo funciona ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
