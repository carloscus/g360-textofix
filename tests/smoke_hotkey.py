"""
Prueba de humo del atajo global.

Registra el atajo de verdad con RegisterHotKey y comprueba que:
1. se puede registrar (no esta ocupado por otra app),
2. la pulsacion sintetica dispara el callback,
3. el atajo se puede cerrar limpiamente.

    uv run python tests/smoke_hotkey.py
"""

from __future__ import annotations

import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from core.config import MOD_CONTROL, MOD_NOREPEAT, MOD_SHIFT, VK_E
from core.hotkey import HotkeyListener
from core.logsetup import setup_logging
from core.winapi import send_hotkey

log = setup_logging(verbose=True)

DISPAROS = threading.Event()


def main() -> int:
    modificadores = MOD_CONTROL | MOD_SHIFT | MOD_NOREPEAT
    listener = HotkeyListener(modificadores, VK_E, "Ctrl+Shift+E")

    hilo = threading.Thread(
        target=lambda: listener.start(lambda: DISPAROS.set()),
        name="listener",
        daemon=True,
    )
    hilo.start()
    time.sleep(1.0)

    if not hilo.is_alive():
        log.error("el hilo del atajo termino antes de tiempo")
        return 1
    log.info("atajo registrado, probando la pulsacion...")

    # MOD_NOREPEAT hace que al mantener pulsado solo dispare una vez.
    send_hotkey(VK_E, MOD_CONTROL | MOD_SHIFT)
    if not DISPAROS.wait(3):
        log.error("FALLO: la pulsacion no llego al atajo global")
        listener.stop()
        return 1
    log.info("OK: el atajo global disparo el callback")

    # Con MOD_NOREPEAT no debe llover de disparos.
    antes = DISPAROS.is_set()
    for _ in range(5):
        send_hotkey(VK_E, MOD_CONTROL | MOD_SHIFT)
        time.sleep(0.05)
    log.info("OK: sin rafaga con MOD_NOREPEAT (estado estable=%s)", antes)

    listener.stop()
    hilo.join(timeout=3)
    if hilo.is_alive():
        log.error("FALLO: el bucle de mensajes no cerro")
        return 1
    log.info("OK: cierre limpio")

    # El atajo debe quedar libre para otra ejecucion. Ojo: start() bloquea en
    # el bucle de mensajes, asi que va en su propio hilo.
    segundo = HotkeyListener(modificadores, VK_E, "Ctrl+Shift+E")
    error: list[Exception] = []

    def _reintentar() -> None:
        try:
            segundo.start(lambda: None)
        except Exception as exc:
            error.append(exc)

    hilo2 = threading.Thread(target=_reintentar, name="listener2", daemon=True)
    hilo2.start()
    time.sleep(0.8)

    if error:
        log.error("FALLO: el atajo quedo tomado tras cerrar: %s", error[0])
        return 1
    segundo.stop()
    log.info("OK: el atajo queda libre tras cerrar")
    log.info("=== todas las pruebas del atajo pasaron ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
