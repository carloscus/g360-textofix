"""
Atajo global con RegisterHotKey (API nativa, sin instalar hooks de teclado).

Ventajas frente a librerias como `keyboard` o `pynput`:
- No requiere permisos de administrador.
- No instala un hook global de teclado (WH_KEYBOARD_LL), que es lo que suele
  marcar los antivirus.
- `MOD_NOREPEAT` evita que se dispare en rafaga al mantener pulsado.

El precio es que necesita un bucle de mensajes, porque WM_HOTKEY se entrega a la
cola del hilo que registro el atajo. Ese bucle se aprovecha mas adelante para
la bandeja del sistema (Etapa 3).
"""

from __future__ import annotations

import ctypes
import logging
import threading
from collections.abc import Callable
from ctypes import wintypes

from .logsetup import LOGGER_NAME

log = logging.getLogger(LOGGER_NAME)

# `use_last_error` hace que ctypes.get_last_error() devuelva el codigo real.
user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.windll.kernel32

WM_HOTKEY = 0x0312
WM_QUIT = 0x0012
HOTKEY_ID = 0xB360

MOD_NOREPEAT = 0x4000

_MSG = wintypes.MSG


class HotkeyListener:
    """
    Escucha el atajo global.

    El trabajo se ejecuta en un hilo aparte para que el bucle de mensajes siga
    bombeando: una correccion que tarde (una llamada de red, en la Etapa 2) no
    puede congelar la escucha. Un cerrojo evita apilar correcciones si el
    atajo se repite.
    """

    def __init__(self, modifiers: int, virtual_key: int, label: str = ""):
        self.modifiers = modifiers
        self.virtual_key = virtual_key
        self.label = label
        self._thread_id: int | None = None
        self._on_hotkey: Callable[[], None] | None = None
        self._lock = threading.Lock()
        self._busy = False

    # --- API ----------------------------------------------------------------

    def start(self, on_hotkey: Callable[[], None]) -> None:
        """Registra el atajo y entra al bucle. Bloquea hasta `stop()`."""
        self._on_hotkey = on_hotkey
        self._thread_id = kernel32.GetCurrentThreadId()
        self._set_thread_name()

        flags = self.modifiers | MOD_NOREPEAT
        if not user32.RegisterHotKey(None, HOTKEY_ID, flags, self.virtual_key):
            error = ctypes.get_last_error()
            raise OSError(
                error,
                f"no se pudo registrar el atajo {self.label or hex(self.virtual_key)} "
                f"(error {error}). Puede que otra aplicacion ya lo este usando.",
            )

        log.info("atajo global registrado: %s", self.label)
        self._pump()

    def stop(self) -> None:
        """Cierra el bucle. Seguro de llamar desde otro hilo."""
        if self._thread_id is not None:
            user32.PostThreadMessageW(self._thread_id, WM_QUIT, 0, 0)

    # --- Interno ------------------------------------------------------------

    def _set_thread_name(self) -> None:
        """Nombre del hilo para poder identificarlo en el Administrador."""
        try:
            kernel32.SetThreadDescription(self._thread_id, "g360-textofix")
        except Exception:
            pass  # Windows anterior a 1607: no es critico.

    def _pump(self) -> None:
        msg = _MSG()
        while True:
            result = user32.GetMessageW(ctypes.byref(msg), None, 0, 0)
            if result in (0, -1):
                break
            if msg.message == WM_HOTKEY:
                self._fire()
                continue
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))

        log.info("bucle de mensajes cerrado")

    def _fire(self) -> None:
        """Dispara el atajo en un hilo, como mucho una correccion a la vez."""
        with self._lock:
            if self._busy:
                log.debug("correccion en curso: atajo ignorado")
                return
            self._busy = True

        worker = threading.Thread(
            target=self._run, name="textofix-trabajo", daemon=True
        )
        worker.start()

    def _run(self) -> None:
        try:
            if self._on_hotkey is not None:
                self._on_hotkey()
        except Exception:
            log.exception("fallo ejecutando la correccion")
        finally:
            with self._lock:
                self._busy = False
