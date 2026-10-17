"""
Bandeja del sistema.

Menu corto a proposito: estado, deshacer/rehacer, cambiar atajo, clave de API,
inicio automatico y salir. Nada mas, porque una bandeja con veinte opciones es
una bandeja que nadie usa.

pystray corre su propio bucle, asi que se arranca "detached": el hilo principal
queda libre para el bucle de mensajes de los atajos, que es el que de verdad
necesita bombear.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

import pystray
from PIL import Image

from .logsetup import LOGGER_NAME
from .perfil import (
    guardar_clave_api,
    hay_clave_api,
    iniciar_con_windows,
    leer_clave_api,
    quitar_inicio_con_windows,
    ruta_perfil,
    tiene_inicio_con_windows,
)

log = logging.getLogger(LOGGER_NAME)

NOMBRE_ICONO = "g360-textofix.ico"


def ruta_icono() -> Path | None:
    """
    Busca el icono, tanto en desarrollo como dentro del .exe.

    PyInstaller extrae los datos a una carpeta temporal y publica la ruta en
    sys._MEIPASS; sin eso, el icono no se encontraria dentro del ejecutable.
    """
    base = getattr(sys, "_MEIPASS", None)
    candidatas = []
    if base:
        candidatas.append(Path(base) / "assets" / NOMBRE_ICONO)
    candidatas.append(Path(__file__).resolve().parents[2] / "assets" / NOMBRE_ICONO)
    candidatas.append(Path(__file__).resolve().parents[1] / "assets" / NOMBRE_ICONO)

    for ruta in candidatas:
        if ruta.exists():
            return ruta
    return None


def imagen_icono() -> Image.Image:
    """Carga el icono, o uno de reserva si no se encuentra."""
    ruta = ruta_icono()
    if ruta is not None:
        try:
            return Image.open(ruta)
        except Exception as exc:
            log.warning("no se pudo abrir el icono %s: %s", ruta, exc)
    # Reserva: un cuadrado oscuro con la barra verde, para que la bandeja
    # nunca quede con un icono vacio.
    return Image.new("RGB", (32, 32), (11, 18, 32))


class Bandeja:
    """Icono de la bandeja con el menu del corrector."""

    def __init__(self, estado, acciones: dict, al_cerrar=None):
        self.estado = estado
        self.acciones = acciones  # {"corregir": fn, "deshacer": fn, ...}
        self.al_cerrar = al_cerrar
        self._icono = None

    # --- Menu ---------------------------------------------------------------

    def _item_estado(self) -> pystray.MenuItem:
        """
        Linea de estado, no pulsable.

        La funcion debe devolver TEXTO: si devolviera un MenuItem, pystray lo
        tomaria como un submenu y falla al construir el menu.
        """
        return pystray.MenuItem(lambda _item: self.estado.resumen(), None, enabled=False)

    def _construir(self):
        e = self.estado

        return pystray.Menu(
            self._item_estado(),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(
                "Deshacer correccion",
                lambda *_: self._invocar("deshacer"),
                enabled=lambda _: e.puede_deshacer(),
            ),
            pystray.MenuItem(
                "Rehacer correccion",
                lambda *_: self._invocar("rehacer"),
                enabled=lambda _: e.puede_rehacer(),
            ),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Cambiar atajo...", self._cambiar_atajo),
            pystray.MenuItem("Configurar clave API...", self._configurar_clave),
            pystray.MenuItem(
                "Iniciar con Windows",
                self._alternar_autostart,
                checked=lambda _: tiene_inicio_con_windows(),
            ),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Salir", self.salir),
        )

    def _invocar(self, accion: str) -> None:
        funcion = self.acciones.get(accion)
        if funcion is None:
            return
        try:
            funcion()
        except Exception:
            log.exception("fallo ejecutando %s desde la bandeja", accion)
        self.refrescar()

    def refrescar(self) -> None:
        """Vuelve a pintar el menu, para que los estados deshabilitadosòn al día."""
        if self._icono is not None:
            try:
                self._icono.update_menu()
            except Exception:
                pass

    # --- Acciones del menu --------------------------------------------------

    def _alternar_autostart(self, *_):
        if tiene_inicio_con_windows():
            quitar_inicio_con_windows()
        else:
            iniciar_con_windows()
        self.refrescar()

    def _configurar_clave(self, *_):
        print("\n[g360-textofix] Clave de la API de Gemini")
        print(f"Se guarda cifrada en: {ruta_perfil()}")
        actual = leer_clave_api()
        if actual:
            print("Ya hay una clave guardada. Pega la nueva o ENTER para dejarla.")
        try:
            nueva = input("Clave (oculta no se puede: pegala con Ctrl+V): ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nCancelado.")
            return
        if not nueva:
            print("Se deja la clave como estaba.")
            return
        try:
            guardar_clave_api(nueva)
            print("Clave guardada (cifrada).")
        except OSError as exc:
            print(f"No se pudo guardar: {exc}")
        self.refrescar()

    def _cambiar_atajo(self, *_):
        from .hotkey import AtajoInvalido, parsear_atajo

        print("\n[g360-textofix] Atajos")
        print("Formato: CTRL+SHIFT+E  (CTRL, ALT, SHIFT, WIN + letra, digito o F1-F24)")
        print("ENTER para dejar todo como estaba.")
        try:
            respuesta = input("Nuevo atajo: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nCancelado.")
            return
        if not respuesta:
            return
        try:
            parsear_atajo(respuesta)
        except AtajoInvalido as exc:
            print(f"No se entiende: {exc}")
            return
        print(f"Atajo: {respuesta.upper()}")
        print("Guardalo en el perfil para que persista.")
        self.refrescar()

    def salir(self, *_) -> None:
        log.info("saliendo desde la bandeja")
        if self.al_cerrar is not None:
            self.al_cerrar()
        if self._icono is not None:
            self._icono.stop()

    # --- Arranque -----------------------------------------------------------

    def iniciar(self) -> pystray.Icon:
        self._icono = pystray.Icon(
            "g360-textofix",
            imagen_icono(),
            self.estado.resumen(),
            menu=self._construir(),
        )
        # Detached: el bucle de pystray va en otro hilo y deja libre el
        # principal para el bucle de mensajes de los atajos.
        self._icono.run_detached()
        log.info("bandeja del sistema iniciada (perfil: %s)", ruta_perfil())
        return self._icono

    def icono_activo(self) -> bool:
        return self._icono is not None and getattr(self._icono, "visible", True)


def hay_icono_disponible() -> bool:
    return ruta_icono() is not None


def clave_configurada() -> bool:
    return hay_clave_api()
