"""
Prueba de humo del atajo global.

Registra los tres atajos de verdad con RegisterHotKey y comprueba que:

1. se pueden registrar (no estan ocupados por otra app),
2. la pulsacion sintetica dispara la accion correcta,
3. cada accion se dispara una sola vez aunque se insista,
4. cerrar libera los atajos.

    uv run python tests/smoke_hotkey.py
"""

from __future__ import annotations

import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from core.hotkey import (
    MOD_CTRL,
    MOD_SHIFT,
    Atajo,
    EscuchaAtajos,
    describir_atajo,
    parsear_atajo,
)
from core.logsetup import setup_logging
from core.winapi import send_hotkey

log = setup_logging(verbose=False)

DISPAROS: list[str] = []
EVENTO = threading.Event()


def _al_presionar(accion: str) -> None:
    DISPAROS.append(accion)
    EVENTO.set()


def _esperar(accion: str, segundos: float = 3.0) -> bool:
    limite = time.time() + segundos
    while time.time() < limite:
        if accion in DISPAROS:
            return True
        time.sleep(0.05)
    return False


def main() -> int:
    fallos = 0

    # --- El parser entiende lo que la gente escribe --------------------------
    print("=== parser de atajos ===")
    casos = [
        ("CTRL+SHIFT+E", MOD_CTRL | MOD_SHIFT, ord("E"), "CTRL+SHIFT+E"),
        ("ctrl+shift+e", MOD_CTRL | MOD_SHIFT, ord("E"), "CTRL+SHIFT+E"),
        ("CTRL + SHIFT + E", MOD_CTRL | MOD_SHIFT, ord("E"), "CTRL+SHIFT+E"),
        ("ALT+F4", 0x0001, 0x73, "ALT+F4"),
        ("CTRL+1", MOD_CTRL, ord("1"), "CTRL+1"),
        ("WIN+E", 0x0008, ord("E"), "WIN+E"),
        ("CTRL+F5", MOD_CTRL, 0x74, "CTRL+F5"),
    ]
    for texto, mods, tecla, esperado in casos:
        a = parsear_atajo(texto)
        bien = a.modificadores == mods and a.tecla == tecla
        marca = "OK " if bien else "MAL"
        if not bien:
            fallos += 1
        print(f"  [{marca}] {texto!r:20} -> {describir_atajo(a)}")

    for malo in ("", "CTRL", "CTRL+NOTATECLA", "CTRL+A+B"):
        try:
            parsear_atajo(malo)
            print(f"  [MAL] {malo!r} deberia dar error")
            fallos += 1
        except ValueError:
            print(f"  [OK ] {malo!r} rechazado como corresponde")

    # --- Atajos repetidos ----------------------------------------------------
    print("\n=== deteccion de atajos repetidos ===")
    repetidos = {
        "corregir": parsear_atajo("CTRL+SHIFT+E"),
        "deshacer": parsear_atajo("CTRL+SHIFT+E"),
    }
    try:
        EscuchaAtajos(repetidos)._registrar()
        print("  [MAL] deberia rechazar dos atajos iguales")
        fallos += 1
    except OSError as exc:
        print(f"  [OK ] rechazados: {exc}")

    # --- Registro y disparo reales ------------------------------------------
    print("\n=== registro y disparo ===")
    atajos = {
        "corregir": parsear_atajo("CTRL+SHIFT+E"),
        "deshacer": parsear_atajo("CTRL+SHIFT+Z"),
        "rehacer": parsear_atajo("CTRL+SHIFT+R"),
    }
    escucha = EscuchaAtajos(atajos)

    hilo = threading.Thread(
        target=lambda: escucha.start(_al_presionar), name="escucha", daemon=True
    )
    hilo.start()
    time.sleep(1.0)

    if not hilo.is_alive():
        print("  FALLO: la escucha termino antes de tiempo (atajo ocupado?)")
        return 1

    for accion, combinacion in (
        ("corregir", ("E", MOD_CTRL | MOD_SHIFT)),
        ("deshacer", ("Z", MOD_CTRL | MOD_SHIFT)),
        ("rehacer", ("R", MOD_CTRL | MOD_SHIFT)),
    ):
        DISPAROS.clear()
        EVENTO.clear()
        send_hotkey(ord(combinacion[0]), combinacion[1])
        if _esperar(accion):
            print(f"  OK: {accion} -> {describir_atajo(atajos[accion])}")
        else:
            print(f"  FALLO: {accion} no llego")
            fallos += 1

    # --- Repetir no apila ---------------------------------------------------
    print("\n=== una accion a la vez ===")
    conteo: list[str] = []
    bloqueo = threading.Event()

    def _lento(accion: str) -> None:
        conteo.append(accion)
        bloqueo.set()
        time.sleep(1.2)

    escucha._al_presionar = _lento
    for _ in range(4):
        send_hotkey(ord("E"), MOD_CTRL | MOD_SHIFT)
        time.sleep(0.1)
    bloqueo.wait(3)
    time.sleep(1.6)
    total = len(conteo)
    escucha._al_presionar = _al_presionar
    bien = total == 1
    print(f"  {'OK ' if bien else 'MAL'} 4 pulsaciones rapidas -> {total} ejecucion(es)")
    if not bien:
        fallos += 1

    # --- Cierre limpio ------------------------------------------------------
    escucha.stop()
    hilo.join(timeout=3)
    if hilo.is_alive():
        print("  FALLO: el bucle de mensajes no cerro")
        fallos += 1
    else:
        print("  OK: cierre limpio")

    segundo = EscuchaAtajos({"corregir": Atajo(MOD_CTRL | MOD_SHIFT, ord("E"), "CTRL+SHIFT+E")})
    try:
        segundo._registrar()
        print("  OK: los atajos quedan libres tras cerrar")
        user32 = __import__("core.winapi", fromlist=["user32"])
        user32.user32.UnregisterHotKey(None, 0xB361)
    except OSError as exc:
        print(f"  FALLO: los atajos quedaron tomados: {exc}")
        fallos += 1

    print()
    if fallos:
        print(f"=== {fallos} verificacion(es) fallaron ===")
        return 1
    print("=== todas las pruebas del atajo pasaron ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
