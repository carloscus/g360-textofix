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
# WM_APP + 1: mensaje privado para pedir un cambio de atajo desde otro hilo.
WM_CAMBIAR = 0x8001
HOTKEY_ID_BASE = 0xB360

MOD_NOREPEAT = 0x4000

_MSG = wintypes.MSG


def _numero_para(atajos: dict[str, Atajo], accion: str) -> int:
    """Numero de id que le toca a `accion`, estable aunque se cambie el orden."""
    orden = list(atajos)
    return orden.index(accion) + 1 if accion in orden else len(orden) + 1


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
        # Pedido de cambio de atajo encolado desde otro hilo; ver `cambiar`.
        self._pendiente: tuple | None = None
        # El initializer de COM del hilo: la referencia lo mantiene vivo
        # (su __del__ des-inicializa COM, ver `_inicializar_com`).
        self._com = None

    def etiquetas(self) -> dict[str, str]:
        return {accion: a.etiqueta or describir_atajo(a) for accion, a in self.atajos.items()}

    def cambiar(self, accion: str, nuevo: Atajo) -> tuple[bool, str]:
        """
        Cambia el atajo de UNA accion, en caliente: no hace falta reiniciar.

        Se ejecuta en el hilo del bucle de mensajes, y no en el que llama.
        RegisterHotKey con ventana nula ata el atajo al hilo que lo registra:
        si lo hiciera el hilo de la bandeja, Windows le enviaria el aviso a
        esa bandeja, que no bombea mensajes, y el atajo quedaria mudo.

        El registro nuevo se intenta ANTES de soltar el viejo, para que un
        atajo ocupado deje a la accion con su combinacion anterior en vez de
        sin asignar. Solo si el nuevo entra, se suelta el viejo.
        """
        if self._thread_id is None:
            return self._cambiar_en_este_hilo(accion, nuevo)

        resultado: dict[str, object] = {}
        listo = threading.Event()
        self._pendiente = (accion, nuevo, resultado, listo)

        if not user32.PostThreadMessageW(self._thread_id, WM_CAMBIAR, 0, 0):
            error = ctypes.get_last_error()
            log.warning("no se pudo encolar el cambio de atajo: error %s", error)
            self._pendiente = None
            return False, "no se pudo encolar el cambio"

        # Sin limite estricto: el bucle puede tardar si una accion larga esta
        # en curso. Un tope evita que la bandeja se quede colgada para siempre.
        if not listo.wait(timeout=10):
            self._pendiente = None
            return False, "se tardo demasiado en cambiar el atajo"

        self._pendiente = None
        return bool(resultado.get("ok")), str(resultado.get("motivo", ""))

    def _cambiar_en_este_hilo(self, accion: str, nuevo: Atajo) -> tuple[bool, str]:
        viejo = self.atajos.get(accion)
        if viejo is not None and viejo == nuevo:
            return True, "ya estaba asignado"

        id_viejo = self._id_de(accion)

        # Se suelta el viejo ANTES de registrar el nuevo, y no al reves.
        # Windows rechaza RegisterHotKey si el id ya esta tomado por este mismo
        # hilo, aunque la combinacion sea distinta: registrar primero y soltar
        # despues haria que todo cambio fallara siempre.
        # La ventana sin atajo dura microsegundos y no puede perder un aviso,
        # porque este hilo es el que bombearia ese aviso y ahora mismo esta aqui.
        if id_viejo is not None:
            user32.UnregisterHotKey(None, id_viejo)
            del self._ids[id_viejo]

        numero = _numero_para(self.atajos, accion)
        if not user32.RegisterHotKey(
            None, HOTKEY_ID_BASE + numero, nuevo.modificadores | MOD_NOREPEAT, nuevo.tecla
        ):
            error = ctypes.get_last_error()
            log.warning("no se pudo registrar %s: error %s", describir_atajo(nuevo), error)
            # El nuevo no entro: se restaura el viejo, que la accion no se
            # quede sin atajo por querer mejorarla.
            if viejo is not None and id_viejo is not None:
                if user32.RegisterHotKey(
                    None, id_viejo, viejo.modificadores | MOD_NOREPEAT, viejo.tecla
                ):
                    self._ids[id_viejo] = accion
                else:
                    log.error("no se pudo restaurar el atajo de %s", accion)
            return False, f"{describir_atajo(nuevo)} esta ocupado"

        self._ids[HOTKEY_ID_BASE + numero] = accion
        self.atajos[accion] = nuevo
        log.info("atajo %s -> %s", accion, describir_atajo(nuevo))
        return True, describir_atajo(nuevo)

    def _procesar_cambio(self) -> None:
        """Atiende el pedido de cambio en el hilo que si bombea mensajes."""
        pendiente = self._pendiente
        self._pendiente = None
        if pendiente is None:
            return
        accion, nuevo, resultado, listo = pendiente
        try:
            ok, motivo = self._cambiar_en_este_hilo(accion, nuevo)
        except Exception as exc:  # un fallo no debe dejar la bandeja esperando
            log.exception("fallo cambiando el atajo de %s", accion)
            ok, motivo = False, f"fallo inesperado: {exc}"
        resultado.update(ok=ok, motivo=motivo)
        listo.set()

    def _id_de(self, accion: str) -> int | None:
        for id_hotkey, a in self._ids.items():
            if a == accion:
                return id_hotkey
        return None

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

    def _inicializar_com(self) -> None:
        """
        COM una vez en este hilo: UI Automation es COM, y hay que
        inicializarlo por hilo. Sin esto, la primera lectura con UIA en el
        hilo del atajo fallaria con "CoInitialize has not been called".

        OJO con guardar la referencia: el initializer inicializa en __init__
        y DES-inicializa en __del__ (comtypes.CoUninitialize). Si el objeto
        se descarta, CPython lo recolecta al instante y COM queda apagado
        otra vez — exactamente el bug que imprimia el consejo de
        UIAutomationInitializerInThread en cada primer atajo.
        """
        try:
            import uiautomation as auto

            self._com = auto.UIAutomationInitializerInThread()
        except Exception:
            pass

    def _bucle(self) -> None:
        self._inicializar_com()

        msg = _MSG()
        while True:
            resultado = user32.GetMessageW(ctypes.byref(msg), None, 0, 0)
            if resultado in (0, -1):
                break
            if msg.message == WM_HOTKEY:
                self._disparar(self._ids.get(msg.wParam))
                continue
            if msg.message == WM_CAMBIAR:
                self._procesar_cambio()
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
