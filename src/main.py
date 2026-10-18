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

# Modos de correccion: `mock` no usa IA, `ia` llama a Gemini.
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
            "Modelo de Gemini a usar (default: gemini-2.5-flash-lite, el mas rapido). "
            "Opciones de la capa gratuita: gemini-2.5-flash-lite, gemini-2.5-flash, "
            "gemini-2.0-flash, gemini-1.5-flash."
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


def _asegurar_clave() -> bool:
    """
    Comprueba que haya un proveedor de IA disponible, y pide la clave si hace falta.

    Solo hay que pedir la clave cuando se usa Gemini. Ollama es local y no
    necesita clave: si el modelo no esta descargado, se pide que lo haga con
    `ollama pull`.
    """
    from core.perfil import guardar_clave_api, hay_clave_api, leer_clave_api
    from core.proovedor import es_gemini, seleccion_proveedor

    log = logging.getLogger(LOGGER_NAME)

    prov = seleccion_proveedor()
    listo, motivo = prov.disponible()
    if listo:
        log.info("proovedor listo")
        return True

    # Ollama no esta arriba o no tiene el modelo: se pide que lo descargue una vez.
    # No se pide clave.
    if not es_gemini(prov):
        log.error(
            "Ollama no disponible: %s. Descargalo de ollama.com y ejecuta: ollama pull llama3.2:3b",
            motivo,
        )
        return False

    # Gemini sin clave. Solo se puede pedir si hay quien pueda escribirla.
    if "falta la clave" not in motivo or hay_clave_api() or sys.stdin is None or sys.stdin.closed:
        log.error("modo IA no disponible: %s", motivo)
        return False

    if not sys.stdin.isatty():
        log.error("modo IA no disponible: %s", motivo)
        return False

    print("\n[g360-textofix] Falta la clave de la API de Gemini.")
    print("Pedila en https://aistudio.google.com/apikey y pegala abajo.")
    print(f"Se guarda cifrada en: {ruta_perfil()}\n")
    try:
        clave = input("Clave (pegala con Ctrl+V): ").strip()
    except (EOFError, KeyboardInterrupt):
        print("\nCancelado.")
        return False

    if not clave:
        log.error("no se ingreso clave: modo IA no disponible")
        return False

    try:
        guardar_clave_api(clave)
    except OSError as exc:
        log.error("no se pudo guardar la clave: %s", exc)
        return False

    log.info("clave guardada cifrada en el perfil")
    from core.ai import CorrectorIA

    return CorrectorIA(api_key=leer_clave_api()).disponible()[0]


def _clavedisponible() -> bool:
    """Si hay un proveedor de IA disponible (Ollama o Gemini)."""
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
            modelo=args.modelo or os.environ.get("GEMINI_MODEL") or None,
        )
        log.info("resultado=%s adaptador=%s", outcome.reason, outcome.adapter or "-")
        return 0 if outcome.ok else 1

    if not cfg.enabled:
        log.warning("desactivado por configuracion (TEXTOFIX_ENABLED=0)")
        return 0

    # Un .exe sin clave no debe arrancar roto: baja a mock y avisa claro.
    # El .bat ya trae la clave, pero el .exe de otro usuario puede no tenerla.
    if modo == MODO_IA and not _clavedisponible():
        log.warning("no hay clave de Gemini: se arranca en modo simulado")
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
            modelo=args.modelo or os.environ.get("GEMINI_MODEL") or None,
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
        # El proovedor es Ollama o Gemini: se mira en el log, no se asume.
        from core.proovedor import etiqueta as _etiqueta_prov
        from core.proovedor import seleccion_proveedor

        _prov = _etiqueta_prov(seleccion_proveedor())
        if _prov == "ollama":
            log.info("MODO IA local: corrige con Ollama, sin cuota, sin red.")
        elif _prov == "nvidia":
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
