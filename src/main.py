#!/usr/bin/env python3
"""
g360-textofix - corrector de texto para Windows.

Etapa 1: atajo global, captura de la seleccion y reemplazo, sin IA.
Etapa 2 (pendiente de facturacion): correccion con Gemini.

Uso:
    uv run python src/main.py                                  # escucha el atajo
    uv run python src/main.py --once                           # una correccion y sale
    uv run python src/main.py --once --mock-transform wrap
    uv run python src/main.py --diagnostico                    # que ventana ve el corrector
"""

from __future__ import annotations

import argparse
import ctypes
import logging
import os
import sys

from core import feedback
from core.config import (
    Config,
    cargar_dotenv,
)
from core.engine import aplicar_texto, detect_context, run_once, texto_en_pantalla
from core.logsetup import LOGGER_NAME, setup_logging
from core.perfil import ruta_perfil

VERSION = "1.0.0"
APP_NAME = "g360-textofix"

# Modos de correccion: `mock` no usa IA, `ia` corrige con el proveedor
# de nube elegido (NVIDIA NIM o Gemini).
MODO_MOCK = "mock"
MODO_IA = "ia"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="g360-textofix",
        description=f"{APP_NAME} v{VERSION} - corrector de texto para Windows",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {VERSION}")

    parser.add_argument(
        "--once",
        action="store_true",
        help="Ejecuta una correccion sobre la seleccion actual y sale.",
    )
    parser.add_argument(
        "--modo",
        choices=("mock", "ia"),
        default="ia",
        help=(
            "mock: no usa IA, devuelve el texto igual (para probar la mecanica). "
            "ia: corrige de verdad con Gemini. Es el por defecto del .exe; "
            "solo queda mock cuando no hay clave."
        ),
    )
    parser.add_argument(
        "--bateria",
        action="store_true",
        help="Corrige la bateria de frases de prueba y muestra el resultado, sin escribir nada.",
    )
    parser.add_argument(
        "--probar-api",
        action="store_true",
        help=(
            "Verifica cada nube con UNA llamada minima (clave, modelo y red) "
            "e imprime el resultado. Sale 0 si al menos una quedo usable."
        ),
    )
    parser.add_argument(
        "--filtro",
        default="",
        help="Con --bateria, corre solo los casos cuyo nombre contenga este texto.",
    )
    parser.add_argument(
        "--pausa",
        type=float,
        default=0.0,
        help=(
            "Segundos de pausa entre casos de la bateria. En cuota gratuita "
            "(5 por minuto) convie poner 13 o mas."
        ),
    )
    parser.add_argument(
        "--mock-transform",
        choices=("roundtrip", "wrap"),
        default="roundtrip",
        help=(
            "roundtrip: devuelve el texto igual, prueba el ciclo completo. "
            "wrap: lo envuelve en «» para ver donde se escribio."
        ),
    )
    parser.add_argument(
        "--diagnostico",
        action="store_true",
        help="Informa que ventana esta en primer plano y que adaptador usaria.",
    )
    parser.add_argument(
        "--modelo",
        default=None,
        help=(
            "Modelo a usar sobre el default del proveedor elegido. Sin esto "
            "cada nube usa el suyo: GEMINI_MODEL (default gemini-2.5-flash-lite) "
            "o NIM_MODEL (default nvidia/nemotron-3-super-120b-a12b)."
        ),
    )
    parser.add_argument("--sin-sonido", action="store_true", help="Desactiva los tonos.")
    parser.add_argument("-v", "--verbose", action="store_true", help="Detalle en consola.")

    return parser.parse_args(argv)


def _install_console_handler(listener) -> None:
    """
    Cierra el bucle con Ctrl+C o al cerrar la consola.

    Sin esto, Ctrl+C no llegaria: el hilo principal esta bloqueado dentro de
    GetMessageW y no bombea senales de Python.
    """
    CTRL_C_EVENT = 0
    handler_type = ctypes.WINFUNCTYPE(ctypes.c_int, ctypes.c_ulong)

    @handler_type
    def _handler(event: int) -> int:
        if event in (CTRL_C_EVENT, 2):  # CTRL_C_EVENT, CTRL_CLOSE_EVENT
            listener.stop()
            return 1  # handled
        return 0

    # La referencia no puede morir mientras el handler este registrado.
    _install_console_handler._keepalive = _handler  # type: ignore[attr-defined]
    ctypes.WinDLL("kernel32", use_last_error=True).SetConsoleCtrlHandler(_handler, 1)


def _hay_alguna_clave() -> bool:
    """Si hay clave de Gemini o de NVIDIA, en el almacen o en el entorno."""
    from core.perfil import leer_clave_api, leer_clave_nim

    return bool(
        leer_clave_api()
        or os.environ.get("GEMINI_API_KEY")
        or leer_clave_nim()
        or os.environ.get("NIM_API_KEY")
    )


def _pedir_claves() -> bool:
    """
    Pide por consola las claves que falten. Devuelve si quedo algo usable.

    Autodetect primero (.env, entorno, almacen cifrado) y solo si NO hay
    ninguna clave se abre la consola. Cualquier ENTER omite una clave: con
    una sola alcanza para que el corrector funcione.
    """
    from core.perfil import guardar_clave_api, guardar_clave_nim, leer_clave_api, leer_clave_nim
    from core.ping import imprimir, probar_gemini, probar_nvidia

    print("\n[g360-textofix] No se detecto ninguna clave de API.")
    print("Las dos son opcionales: con una alcanza. ENTER para omitir.\n")

    if not leer_clave_api():
        print("[1/2] Gemini: pedila en https://aistudio.google.com/apikey")
        print(f"Se guarda cifrada en: {ruta_perfil()}")
        try:
            clave = input("Clave Gemini (pegala con Ctrl+V): ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nCancelado.")
            return False
        if clave:
            try:
                guardar_clave_api(clave)
                print("Clave de Gemini guardada (cifrada). Verificando...")
                imprimir(probar_gemini(clave))
                print()
            except OSError as exc:
                print(f"No se pudo guardar la clave de Gemini: {exc}\n")

    if not leer_clave_nim():
        print("[2/2] NVIDIA NIM: pedila en https://build.nvidia.com (Generate API Key)")
        try:
            clave = input("Clave NVIDIA (pegala con Ctrl+V): ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nCancelado.")
            return False
        if clave:
            try:
                guardar_clave_nim(clave)
                print("Clave de NVIDIA guardada (cifrada). Verificando...")
                imprimir(probar_nvidia(clave))
            except OSError as exc:
                print(f"No se pudo guardar la clave de NVIDIA: {exc}")

    return True


def _asegurar_clave() -> bool:
    """
    Comprueba que haya un proveedor de IA disponible, y pide las claves si no.

    El orden es: autodetect (.env, entorno, almacen cifrado de Windows) y,
    solo si no hay NINGUNA clave, un prompt de consola con las dos. Si la
    clave ya existe pero falta la dependencia, pedir clave no arregla nada:
    se avisa y se sigue.
    """
    from core.proovedor import seleccion_proveedor

    log = logging.getLogger(LOGGER_NAME)

    prov = seleccion_proveedor()
    listo, motivo = prov.disponible()
    if listo:
        log.info("proveedor listo")
        return True

    if _hay_alguna_clave():
        log.error("modo IA no disponible: %s", motivo)
        return False

    # Sin clave y sin quien pueda escribirla (exe lanzado sin consola): se
    # avisa. El menu de la bandeja sigue siendo la via para configurarla.
    if sys.stdin is None or sys.stdin.closed or not sys.stdin.isatty():
        log.error("falta la clave de alguna API y no hay consola para pedirla")
        return False

    if not _pedir_claves():
        return False

    listo, motivo = seleccion_proveedor().disponible()
    if not listo:
        log.error("modo IA no disponible: %s", motivo)
        return False
    log.info("proveedor listo")
    return True


def _clavedisponible() -> bool:
    """Si hay un proveedor de IA disponible (NVIDIA o Gemini)."""
    from core.proovedor import seleccion_proveedor

    listo, _ = seleccion_proveedor().disponible()
    return listo


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    cargar_dotenv()
    cfg = Config.from_env()
    log = setup_logging(verbose=args.verbose or cfg.verbose)

    if args.sin_sonido:
        feedback.set_muted(True)

    if args.bateria:
        cargar_dotenv()
        from core.bateria import ejecutar

        return ejecutar(args.filtro, args.pausa)

    if args.probar_api:
        from core.ping import imprimir, probar_todo

        print("\n[g360-textofix] Verificacion de la API (1 llamada minima por proveedor)\n")
        resultados = probar_todo()
        for r in resultados:
            imprimir(r)
        if any(r["ok"] for r in resultados):
            return 0
        print("\nNingun proveedor quedo usable: revisa las claves o el .env.")
        return 1

    if args.diagnostico:
        log.info("diagnostico: ventana activa en primer plano")
        detect_context()
        return 0

    modo = args.modo

    if modo == MODO_IA and not _asegurar_clave():
        return 3

    if args.once:
        outcome = run_once(
            cfg,
            mode=modo,
            transform=args.mock_transform,
            modelo=args.modelo or None,
        )
        log.info("resultado=%s adaptador=%s", outcome.reason, outcome.adapter or "-")
        return 0 if outcome.ok else 1

    if not cfg.enabled:
        log.warning("desactivado por configuracion (TEXTOFIX_ENABLED=0)")
        return 0

    # Un .exe sin clave no debe arrancar roto: baja a mock y avisa claro.
    # El .bat ya trae la clave, pero el .exe de otro usuario puede no tenerla.
    if modo == MODO_IA and not _clavedisponible():
        log.warning("no hay clave de ninguna API: se arranca en modo simulado")
        modo = MODO_MOCK

    from core.bandeja import Bandeja
    from core.estado import Correccion, Estado
    from core.hotkey import AtajoInvalido, EscuchaAtajos, parsear_atajo
    from core.perfil import leer_config
    from core.winapi import foreground_context

    perfil = leer_config()

    # --- Atajos ---------------------------------------------------------------
    textos = {
        "corregir": perfil.get("hotkey_corregir", "CTRL+SHIFT+E"),
        "deshacer": perfil.get("hotkey_deshacer", "CTRL+SHIFT+Z"),
        "rehacer": perfil.get("hotkey_rehacer", "CTRL+SHIFT+R"),
    }
    atajos = {}
    for accion, texto in textos.items():
        try:
            atajos[accion] = parsear_atajo(texto)
        except AtajoInvalido as exc:
            log.error("el atajo de %s es invalido (%s); se deja sin asignar", accion, exc)

    estado = Estado(activo=perfil.get("activo", True), modo=modo)
    escucha = EscuchaAtajos(atajos)
    _install_console_handler(escucha)

    # --- Acciones -------------------------------------------------------------
    def _proceso_actual() -> str:
        ctx = foreground_context()
        return ctx.process.lower() if ctx else ""

    def _registrar_si_tocaron() -> None:
        estado.comprobar_cambio(texto_en_pantalla())

    def accion_corregir() -> None:
        if not estado.activo:
            log.info("corrector desactivado")
            feedback.no_selection()
            bandeja.refrescar()
            return
        _registrar_si_tocaron()
        outcome = run_once(
            cfg,
            mode=modo,
            transform=args.mock_transform,
            modelo=args.modelo or None,
            al_corregir=lambda o, c, p: estado.registrar_correccion(
                Correccion(proceso=p, original=o, corregido=c)
            ),
        )
        if not outcome.ok:
            log.info("sin correccion que deshacer: %s", outcome.reason)
        bandeja.refrescar()

    def _deshacer_rehacer(al_deshacer: bool) -> None:
        proceso = _proceso_actual()
        _registrar_si_tocaron()

        preparar = estado.preparar_deshacer if al_deshacer else estado.preparar_rehacer
        texto, motivo = preparar(proceso)

        if texto is None:
            log.info("no se %s: %s", "deshizo" if al_deshacer else "rehizo", motivo)
            feedback.error()
            bandeja.refrescar()
            return

        outcome = aplicar_texto(texto)
        if not outcome.ok:
            # No se escribio: el bucle no debe creer que si.
            estado.revertir_preparacion()
        bandeja.refrescar()

    acciones = {
        "corregir": accion_corregir,
        "deshacer": lambda: _deshacer_rehacer(True),
        "rehacer": lambda: _deshacer_rehacer(False),
        "salir": escucha.stop,
    }

    bandeja = Bandeja(estado, acciones, escucha=escucha)
    bandeja.iniciar()

    etiquetas = escucha.etiquetas()
    log.info("%s v%s", APP_NAME, VERSION)
    log.info("  corregir : %s", etiquetas.get("corregir", "-"))
    log.info("  deshacer : %s", etiquetas.get("deshacer", "-"))
    log.info("  rehacer  : %s", etiquetas.get("rehacer", "-"))
    log.info("  bandeja activa. Ctrl+C para salir.")

    if modo == MODO_IA:
        from core.proovedor import etiqueta as _etiqueta_prov
        from core.proovedor import seleccion_proveedor

        _prov = _etiqueta_prov(seleccion_proveedor())
        if _prov == "nvidia":
            log.info("MODO IA nube NVIDIA: 90b local-remoto, sin limite de cuota.")
        else:
            log.info("MODO IA por la nube: se corrige con Gemini (5 pedidos/min en cuota gratis).")
    else:
        log.warning(
            "MODO SIMULADO: el texto se devuelve SIN corregir. Para corregir de verdad: --modo ia"
        )

    try:
        escucha.start(lambda accion: acciones.get(accion, lambda: None)())
    except OSError as exc:
        log.error("%s", exc)
        return 2
    except KeyboardInterrupt:
        log.info("interrumpido")

    log.info("adios")
    return 0


if __name__ == "__main__":
    sys.exit(main())
