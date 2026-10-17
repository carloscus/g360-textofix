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

# Acciones que el corrector escucha. Cada una tiene su propio atajo.
ACCIONES = ("corregir", "deshacer", "rehacer")

MOD_CTRL = 0x0002
MOD_SHIFT = 0x0004
MOD_ALT = 0x0001
MOD_WIN = 0x0008

_NOMBRES_MOD = {
    "CTRL": MOD_CTRL,
    "CONTROL": MOD_CTRL,
    "SHIFT": MOD_SHIFT,
    "ALT": MOD_ALT,
    "WIN": MOD_WIN,
    "META": MOD_WIN,
}
_NOMBRES_MOD_INV = {MOD_CTRL: "CTRL", MOD_SHIFT: "SHIFT", MOD_ALT: "ALT", MOD_WIN: "WIN"}


class AtajoInvalido(ValueError):
    """El texto del atajo no se pudo entender."""


class Atajo:
    """Una combinacion de modificadores y una tecla."""

    def __init__(self, modificadores: int, tecla: int, etiqueta: str = ""):
        self.modificadores = modificadores
        self.tecla = tecla
        self.etiqueta = etiqueta

    def __repr__(self) -> str:
        return f"Atajo({self.etiqueta!r})"

    def __eq__(self, otro) -> bool:
        return (
            isinstance(otro, Atajo)
            and self.modificadores == otro.modificadores
            and self.tecla == otro.tecla
        )


def _tecla_desde_nombre(nombre: str) -> int:
    n = nombre.strip().upper()
    if len(n) == 1 and ("A" <= n <= "Z" or "0" <= n <= "9"):
        return ord(n)
    if n.startswith("F") and n[1:].isdigit():
        numero = int(n[1:])
        if 1 <= numero <= 24:
            return 0x70 + numero - 1  # VK_F1 = 0x70
    especiales = {
        "SPACE": 0x20,
        "ESC": 0x1B,
        "ESCAPE": 0x1B,
        "ENTER": 0x0D,
        "RETURN": 0x0D,
        "TAB": 0x09,
        "INSERT": 0x2D,
        "DELETE": 0x2E,
        "HOME": 0x24,
        "END": 0x23,
        "PGUP": 0x21,
        "PGDN": 0x22,
    }
    if n in especiales:
        return especiales[n]
    raise AtajoInvalido(f"tecla desconocida: {nombre!r}")


# Inverso del mapa de teclas especiales, para poder volver a nombrarlas.
_ESPECIALES_INV = {
    "SPACE": 0x20,
    "ESC": 0x1B,
    "ENTER": 0x0D,
    "TAB": 0x09,
    "INSERT": 0x2D,
    "DELETE": 0x2E,
    "HOME": 0x24,
    "END": 0x23,
    "PGUP": 0x21,
    "PGDN": 0x22,
}


def parsear_atajo(texto: str) -> Atajo:
    """
    Convierte "CTRL+SHIFT+E" en modificadores y tecla.

    Si no se indica ningun modificador se asume CTRL, que es lo esperable en
    un corrector. Y un atajo de solo SHIFT no sirve porque Windows lo rechaza.
    """
    if not texto or not texto.strip():
        raise AtajoInvalido("atajo vacio")

    partes = [p for p in texto.replace(" ", "").split("+") if p]
    if not partes:
        raise AtajoInvalido(f"atajo sin parte valida: {texto!r}")

    modificadores = 0
    indice = 0
    while indice < len(partes) - 1:
        clave = partes[indice].upper()
        if clave not in _NOMBRES_MOD:
            break
        modificadores |= _NOMBRES_MOD[clave]
        indice += 1

    tecla = _tecla_desde_nombre(partes[indice])
    if indice < len(partes) - 1:
        raise AtajoInvalido(f"mas de una tecla en el atajo: {texto!r}")

    if modificadores == 0:
        modificadores = MOD_CTRL
    if modificadores == MOD_SHIFT:
        modificadores |= MOD_CTRL

    return Atajo(modificadores, tecla, texto.strip().upper())


def _nombre_de_tecla(tecla: int) -> str:
    """
    Nombre legible de una tecla.

    Hace falta el mapa explicito: el codigo virtual de F4 es 0x73, que en
    ASCII es la letra 's'. Sin esto, "ALT+F4" se mostraría como "ALT+s".
    """
    for nombre, codigo in _ESPECIALES_INV.items():
        if codigo == tecla:
            return nombre
    if 0x70 <= tecla <= 0x87:
        return f"F{tecla - 0x70 + 1}"
    if 0x20 <= tecla < 0x7F:
        return chr(tecla)
    return f"0x{tecla:02X}"


def describir_atajo(atajo: Atajo) -> str:
    partes = [v for k, v in sorted(_NOMBRES_MOD_INV.items()) if atajo.modificadores & k]
    return "+".join(partes + [_nombre_de_tecla(atajo.tecla)])


# `use_last_error` hace que ctypes.get_last_error() devuelva el codigo real.
user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.windll.kernel32

WM_HOTKEY = 0x0312
WM_QUIT = 0x0012
HOTKEY_ID_BASE = 0xB360

MOD_NOREPEAT = 0x4000

_MSG = wintypes.MSG


class EscuchaAtajos:
    """
    Escucha varios atajos globales en un solo bucle de mensajes.

    Cada accion (corregir, deshacer, rehacer) tiene su combinacion. El trabajo
    se ejecuta en un hilo aparte para que el bucle siga bombeando: una
    correccion que tarde (una llamada de red) no puede congelar la escucha. Un
    cerrojo evita apilar trabajo si se repite el atajo.
    """

    def __init__(self, atajos: dict[str, Atajo]):
        self.atajos = atajos
        self._thread_id: int | None = None
        self._ids: dict[int, str] = {}
        self._lock = threading.Lock()
        self._ocupado = set()
        self._al_presionar: Callable[[str], None] | None = None

    def etiquetas(self) -> dict[str, str]:
        return {accion: a.etiqueta or describir_atajo(a) for accion, a in self.atajos.items()}

    # --- API ----------------------------------------------------------------

    def start(self, al_presionar: Callable[[str], None]) -> None:
        """Registra los atajos y entra al bucle. Bloquea hasta `stop()`."""
        self._al_presionar = al_presionar
        self._thread_id = kernel32.GetCurrentThreadId()

        self._registrar()
        self._bucle()

    def stop(self) -> None:
        """Cierra el bucle. Seguro de llamar desde otro hilo."""
        if self._thread_id is not None:
            user32.PostThreadMessageW(self._thread_id, WM_QUIT, 0, 0)

    # --- Interno ------------------------------------------------------------

    def _registrar(self) -> None:
        """
        Registra uno por uno. Un atajo ocupado no impide registrar los otros.

        Si algo falla a medias se liberan los ya registrados: dejarlos tomados
        haria que un segundo intento fallara por un atajo que en realidad este
        proceso ya libero.
        """
        self._ids.clear()
        try:
            self._registrar_uno()
        except Exception:
            self._desregistrar()
            raise

        if not self._ids:
            self._desregistrar()
            raise OSError(
                0,
                "No se pudo registrar ningun atajo. Casi seguro hay otra "
                "instancia del corrector abierta: cierrala con Ctrl+C.",
            )

    def _desregistrar(self) -> None:
        """Libera los atajos que registro esta escucha."""
        for id_hotkey in self._ids:
            user32.UnregisterHotKey(None, id_hotkey)
        self._ids.clear()

    def _registrar_uno(self) -> None:
        vistos: dict[tuple[int, int], str] = {}
        for numero, (accion, atajo) in enumerate(self.atajos.items(), start=1):
            clave = (atajo.modificadores, atajo.tecla)
            if clave in vistos:
                raise OSError(
                    0,
                    f"el atajo de {accion} es el mismo que el de {vistos[clave]} "
                    f"({describir_atajo(atajo)})",
                )
            vistos[clave] = accion

            id_hotkey = HOTKEY_ID_BASE + numero
            if not user32.RegisterHotKey(
                None, id_hotkey, atajo.modificadores | MOD_NOREPEAT, atajo.tecla
            ):
                error = ctypes.get_last_error()
                log.warning(
                    "no se pudo registrar el atajo de %s (%s): error %s",
                    accion,
                    describir_atajo(atajo),
                    error,
                )
                continue
            self._ids[id_hotkey] = accion
            log.info("atajo %s -> %s", accion, describir_atajo(atajo))

    def _bucle(self) -> None:
        msg = _MSG()
        while True:
            resultado = user32.GetMessageW(ctypes.byref(msg), None, 0, 0)
            if resultado in (0, -1):
                break
            if msg.message == WM_HOTKEY:
                self._disparar(self._ids.get(msg.wParam))
                continue
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))

        log.info("bucle de mensajes cerrado")

    def _disparar(self, accion: str | None) -> None:
        """Ejecuta la accion en un hilo, una vez por accion."""
        if accion is None:
            return
        with self._lock:
            if accion in self._ocupado:
                log.debug("%s en curso: atajo ignorado", accion)
                return
            self._ocupado.add(accion)

        threading.Thread(
            target=self._ejecutar,
            args=(accion,),
            name=f"textofix-{accion}",
            daemon=True,
        ).start()

    def _ejecutar(self, accion: str) -> None:
        try:
            if self._al_presionar is not None:
                self._al_presionar(accion)
        except Exception:
            log.exception("fallo ejecutando %s", accion)
        finally:
            with self._lock:
                self._ocupado.discard(accion)


# Se conserva el nombre viejo: lo usa la prueba de humo del atajo.
HOTKEY_ID = HOTKEY_ID_BASE
