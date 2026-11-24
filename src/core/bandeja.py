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
    borrar_clave_openrouter,
    guardar_clave_api,
    guardar_clave_nim,
    guardar_clave_openrouter,
    hay_clave_api,
    iniciar_con_windows,
    leer_clave_api,
    leer_clave_nim,
    leer_clave_openrouter,
    quitar_inicio_con_windows,
    ruta_perfil,
    tiene_inicio_con_windows,
)
from .ping import probar_gemini, probar_nvidia
from .proovedor import modelo_openrouter_activo

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

    def texto_estado(self) -> str:
        """Texto del item de estado: 'Corrigiendo...' si hay una en curso,
        el resumen de lo contrario.

        Se lee en la misma instancia de Bandeja, asi refleja el estado vivo
        de la escucha (no un snapshot al construir el menu).
        """
        if self.escucha is not None and self.escucha.en_curso("corregir"):
            return "Corrigiendo..."
        return self.estado.resumen()

    def _item_estado(self) -> pystray.MenuItem:
        """
        Linea de estado, no pulsable.

        La funcion debe devolver TEXTO: si devolviera un MenuItem, pystray lo
        tomaria como un submenu y falla al construir el menu.
        """
        from .hotkey import ERROR_HOTKEY_ALREADY_REGISTERED

        faltantes = []
        if self.escucha is not None:
            faltantes = self.escucha.faltantes

        if faltantes:
            # 'Corrigiendo...' se evalua dinamicamente en cada acceso (no es un
            # snapshot al construir el menu), para que refleje el estado vivo
            # de la escucha incluso cuando hay atajos sin registrar.
            lineas_faltantes = [f"Atajos sin registrar ({len(faltantes)}):"]
            for f in faltantes:
                titulo = "OTRA APP" if f["es_conflicto_externo"] else "INTERNO"
                lineas_faltantes.append(f"  - {f['atajo']} ({titulo})")
            return pystray.MenuItem(
                lambda _i: "\n".join([self.texto_estado(), *lineas_faltantes]),
                None,
                enabled=False,
            )
        return pystray.MenuItem(lambda _item: self.texto_estado(), None, enabled=False)

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
            pystray.MenuItem(
                "Clave API OpenRouter...", self._configurar_clave_openrouter
            ),
            pystray.MenuItem("Modelo de correccion", self._submenu_modelo()),
            pystray.MenuItem("Estilo de correccion", self._submenu_estilo()),
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

    def _configurar_clave_openrouter(self, *_):
        """Pide la clave de OpenRouter por consola, la guarda y la deja en .env."""
        from .consola import cerrar_consola_propia, pedir_consola

        pedir_consola()
        try:
            self._configurar_clave_openrouter_en_consola()
        finally:
            cerrar_consola_propia()

    def _configurar_clave_openrouter_en_consola(self):
        print("\n[g360-textofix] Clave de la API de OpenRouter")
        print("Anotala en https://openrouter.ai/keys")
        print(f"Se guarda cifrada en: {ruta_perfil()}")
        actual = leer_clave_openrouter()
        if actual:
            print("Ya hay una clave guardada. Pega la nueva o ENTER para dejarla.")
        try:
            nueva = input("Clave (oculta no se puede: pegala con Ctrl+V): ").strip()
        except (EOFError, KeyboardInterrupt, OSError):
            print("\nCancelado.")
            return
        if not nueva:
            print("No se cambia nada.")
            return

        # Clave efectiva: la que ya esta en .env, o la guardada en DPAPI, o nada.
        efectiva = self._leer_openrouter_env() or leer_clave_openrouter() or ""
        if nueva == efectiva:
            print("La clave es igual a la ya configurada: no se reescribe nada.")
            return

        # 1. Guardar cifrada en DPAPI.
        try:
            guardar_clave_openrouter(nueva)
        except OSError as exc:
            print(f"No se pudo guardar: {exc}")
            self.refrescar()
            return

        # 2. Persistir OPENROUTER_API_KEY en el .env del perfil, preservando
        #    el resto de las lineas (crear archivo si no existe; nunca el repo).
        self._escribir_openrouter_env(nueva)

        print("Clave de OpenRouter guardada (cifrada) y dejada en .env del perfil.")
        print(
            "el proxy lee esa variable al arrancar -> reiniciá el proxy para aplicarla."
        )
        self.refrescar()

    # --- .env del perfil (clave OpenRouter para el proxy) ---------------------

    def _env_path(self) -> Path:
        """El .env del perfil: fuera del repo, en %APPDATA%/g360-textofix."""
        return ruta_perfil() / ".env"

    def _leer_openrouter_env(self) -> str | None:
        """Devuelve OPENROUTER_API_KEY del .env del perfil, o None."""
        ruta = self._env_path()
        if not ruta.exists():
            return None
        for linea in ruta.read_text(encoding="utf-8").splitlines():
            if linea.startswith("OPENROUTER_API_KEY="):
                return linea.split("=", 1)[1].strip()
        return None

    def _escribir_openrouter_env(self, clave: str) -> None:
        """Escribe OPENROUTER_API_KEY en el .env del perfil, preservando demas lineas.

        Crea el archivo si no existe. Nunca toca nada dentro del repo.
        """
        ruta = self._env_path()
        ruta.parent.mkdir(parents=True, exist_ok=True)
        lineas = []
        if ruta.exists():
            lineas = ruta.read_text(encoding="utf-8").splitlines()
        escritas = False
        nuevas = []
        for linea in lineas:
            if linea.startswith("OPENROUTER_API_KEY="):
                nuevas.append(f"OPENROUTER_API_KEY={clave}")
                escritas = True
            else:
                nuevas.append(linea)
        if not escritas:
            nuevas.append(f"OPENROUTER_API_KEY={clave}")
        ruta.write_text("\n".join(nuevas) + "\n", encoding="utf-8")
        log.info("OPENROUTER_API_KEY actualizada en el .env del perfil")

    def _submenu_modelo(self) -> pystray.Menu:
        """
        Una sola opcion de modelo para OpenRouter (proxy local), siempre marcada.

        No usa OPCIONES_MODELO: ese menu es de los proveedores de nube (NIM /
        Gemini). Cuando el proveedor real es OpenRouter via proxy local, el
        modelo es unico y viene de NIM_MODEL del entorno o del default.
        La callback persiste "auto" en config.json (la bandeja no elige modelo
        propio, deja pasar el proxy).
        """
        from .perfil import guardar_config, leer_config

        texto = f"OpenRouter ({modelo_openrouter_activo()})"

        def _elegir_auto(_item):
            config = leer_config()
            config["modelo_ia"] = "auto"
            guardar_config(config)
            log.info("modelo de correccion: auto (OpenRouter/proxy local)")
            self.refrescar()

        return pystray.Menu(
            pystray.MenuItem(
                texto,
                _elegir_auto,
                radio=True,
                checked=lambda _: True,
            )
        )

    def _submenu_estilo(self) -> pystray.Menu:
        """
        Las tres opciones de estilo de correccion, con radio y estado al dia.

        La fuente unica de los valores es `ai.OPCIONES_ESTILO` (auto, natural,
        estricto). La marca se re-lee al abrir el menu contra `estilo_activo()`
        (el modo EFECTIVO: config.json si es natural/estricto, si no TEXTOFIX_ESTILO
        del entorno, y por defecto "natural"), asi que "auto" + env marca
        correctamente el modo real que se va a aplicar.

        Incluye una nota visible aclarando que "Automatico" usa Humano salvo
        override de entorno.
        """
        from .ai import OPCIONES_ESTILO, estilo_activo

        activo = estilo_activo()

        def _marcado(valor: str):
            return lambda _item: activo == valor

        return pystray.Menu(
            pystray.MenuItem(
                "Nota: Automatico usa Humano salvo override de entorno",
                None,
                enabled=False,
            ),
            *[
                pystray.MenuItem(
                    texto,
                    lambda _item, _valor=valor: self._elegir_estilo(_valor),
                    radio=True,
                    checked=_marcado(valor),
                )
                for valor, texto in OPCIONES_ESTILO
            ],
        )

    def _elegir_estilo(self, valor: str, *_):
        """Persiste la eleccion de estilo en el perfil: aplica a la proxima
        correccion (la cache ya separa por estilo). No re-registra hotkeys,
        no reinicia."""
        from .perfil import guardar_config, leer_config

        config = leer_config()
        config["estilo"] = valor
        guardar_config(config)
        log.info("estilo de correccion elegido: %s", valor)
        self.refrescar()

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
            from .ping import linea, sin_clave

            print("Verificando con una llamada real...")
            resultado = probar(nueva)
            if sin_clave(resultado):
                print(f"[SIN CLAVE] No se pudo verificar: {resultado.get('etiqueta', '')}")
            else:
                etiqueta = linea(resultado)
                print(f"Verificación exitosa: {etiqueta}")
                print("La clave es válida y funcional.")
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


def _tener_estado_clave_gemini() -> tuple[bool, str]:
    """Retorna (tiene_clave, descripcion) del estado de la clave Gemini.

    Retorna:
        (True, "configurada") - Hay clave en .env/DPAPI
        (True, "ok") - Clave válida y funciona
        (False, "no-configurada") - No hay clave configurada
        (False, "inválida") - Hay clave pero no funciona
    """
    clave = leer_clave_api()
    if not clave:
        return False, "no-configurada"

    # Probar la clave
    try:
        resultado = probar_gemini(clave)
        if resultado["ok"]:
            return True, "configurada"
        else:
            return False, f"inválida: {resultado['detalle']}"
    except Exception as e:
        return False, f"error: {str(e)[:50]}"


def _tener_estado_clave_nim() -> tuple[bool, str]:
    """Retorna (tiene_clave, descripcion) del estado de la clave NVIDIA NIM.

    Igual que la anterior pero para NIM.
    """
    clave = leer_clave_nim()
    if not clave:
        return False, "no-configurada"

    try:
        resultado = probar_nvidia(clave)
        if resultado["ok"]:
            return True, "configurada"
        else:
            return False, f"inválida: {resultado['detalle']}"
    except Exception as e:
        return False, f"error: {str(e)[:50]}"


def clave_configurada() -> bool:
    return hay_clave_api()
