"""
Bandeja del sistema.

Menu corto a proposito: estado, deshacer/rehacer, cambiar atajo, claves de API
(Gemini y NVIDIA), inicio automatico y salir. Nada mas, porque una bandeja con
veinte opciones es una bandeja que nadie usa.

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
    guardar_clave_nim,
    hay_clave_api,
    iniciar_con_windows,
    leer_clave_api,
    leer_clave_nim,
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


def _elegir(orden: list[str], texto: str) -> str | None:
    """Acepta tanto el numero (1, 2, 3) como el nombre de la accion."""
    limpio = texto.strip().lower()
    if limpio.isdigit():
        indice = int(limpio) - 1
        return orden[indice] if 0 <= indice < len(orden) else None
    return next((a for a in orden if a.lower() == limpio), None)


class Bandeja:
    """Icono de la bandeja con el menu del corrector."""

    def __init__(self, estado, acciones: dict, al_cerrar=None, escucha=None):
        self.estado = estado
        self.acciones = acciones  # {"corregir": fn, "deshacer": fn, ...}
        self.al_cerrar = al_cerrar
        self.escucha = escucha  # EscuchaAtajos, para re-registrar en caliente
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
            pystray.MenuItem("Clave API Gemini...", self._configurar_clave),
            pystray.MenuItem("Clave API NVIDIA...", self._configurar_clave_nim),
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
        from .ping import probar_gemini

        self._pedir_clave(
            "Gemini",
            "https://aistudio.google.com/apikey",
            leer_clave_api,
            guardar_clave_api,
            probar=probar_gemini,
        )

    def _configurar_clave_nim(self, *_):
        from .ping import probar_nvidia

        self._pedir_clave(
            "NVIDIA NIM",
            "https://build.nvidia.com (Generate API Key)",
            leer_clave_nim,
            guardar_clave_nim,
            probar=probar_nvidia,
        )

    def _pedir_clave(self, nombre: str, donde: str, leer, guardar, probar=None):
        """Pide una clave por consola, la guarda cifrada (DPAPI) y la verifica."""
        from .consola import cerrar_consola_propia, pedir_consola

        pedir_consola()
        try:
            self._pedir_clave_en_consola(nombre, donde, leer, guardar, probar)
        finally:
            # La consola propia se cierra con Enter al terminar; la de
            # origen (terminal, desarrollo) no se toca.
            cerrar_consola_propia()

    def _pedir_clave_en_consola(self, nombre, donde, leer, guardar, probar):
        print(f"\n[g360-textofix] Clave de la API de {nombre}")
        print(f"Pedila en {donde}")
        print(f"Se guarda cifrada en: {ruta_perfil()}")
        actual = leer()
        if actual:
            print("Ya hay una clave guardada. Pega la nueva o ENTER para dejarla.")
        try:
            nueva = input("Clave (oculta no se puede: pegala con Ctrl+V): ").strip()
        except (EOFError, KeyboardInterrupt, OSError):
            print("\nCancelado.")
            return
        if not nueva:
            print("Se deja la clave como estaba.")
            return
        try:
            guardar(nueva)
            print("Clave guardada (cifrada).")
        except OSError as exc:
            print(f"No se pudo guardar: {exc}")
            self.refrescar()
            return
        if probar is not None:
            # Una llamada minima ahora, no en la primera correccion: una clave
            # mala se entiende aqui, con el diagnostico (401, 404, 429).
            from .ping import imprimir

            print("Verificando con una llamada real...")
            imprimir(probar(nueva))
        self.refrescar()

    def _cambiar_atajo(self, *_):
        """
        Cambia un atajo: lo re-registra YA y lo guarda en el perfil.

        Re-registrar en caliente en vez de pedir un reinicio es la diferencia
        entre que alguien cambie el atajo y que lo deje como estaba.
        """
        from .consola import cerrar_consola_propia, pedir_consola

        pedir_consola()
        try:
            self._cambiar_atajo_en_consola()
        finally:
            cerrar_consola_propia()

    def _cambiar_atajo_en_consola(self):
        from .hotkey import AtajoInvalido, describir_atajo, parsear_atajo
        from .perfil import guardar_atajo

        if self.escucha is None:
            print("\n[g360-textofix] Los atajos no se pueden cambiar en caliente.")
            return

        actuales = self.escucha.etiquetas()
        registrados = self.escucha.atajos
        if not actuales:
            print("\n[g360-textofix] No hay ningun atajo registrado.")
            return

        print("\n[g360-textofix] Atajos actuales")
        orden = list(actuales)
        for i, accion in enumerate(orden, start=1):
            print(f"  {i}. {accion:9} {actuales[accion]}")

        print("\nQue accion queres cambiar? (numero, o ENTER para cancelar)")
        try:
            eleccion = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nCancelado.")
            return
        if not eleccion:
            return

        accion = _elegir(orden, eleccion)
        if accion is None:
            print("Ese numero no existe.")
            return

        print(f"\nNuevo atajo para {accion} ({actuales[accion]}).")
        print("Formato: CTRL+SHIFT+E  (CTRL, ALT, SHIFT, WIN + letra, digito o F1-F24)")
        try:
            respuesta = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nCancelado.")
            return
        if not respuesta:
            return

        try:
            atajo = parsear_atajo(respuesta)
        except AtajoInvalido as exc:
            print(f"No se entiende: {exc}")
            return

        # No se puede repetir un atajo que otra accion ya tenga: Windows no lo
        # aceptaria y el usuario quedaria sin saber cual de las dos manda.
        repetido = next(
            (a for a, t in registrados.items() if a != accion and t == atajo),
            None,
        )
        if repetido is not None:
            print(f"Ya lo usa {repetido} ({actuales[repetido]}). Elegi otra combinacion.")
            return

        listo, motivo = self.escucha.cambiar(accion, atajo)
        if not listo:
            print(f"No se pudo cambiar: {motivo}. Se deja {actuales[accion]}.")
            return

        normalizado = describir_atajo(atajo)
        try:
            guardar_atajo(accion, normalizado)
            print(f"{accion}: {normalizado}. Guardado y activo.")
        except OSError as exc:
            print(f"{accion}: {normalizado} activo, pero no se pudo guardar: {exc}")

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
