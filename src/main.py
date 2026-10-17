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
import sys
from pathlib import Path

from core import feedback
from core.config import (
    MOD_CONTROL,
    MOD_NOREPEAT,
    MOD_SHIFT,
    VK_E,
    Config,
    Hotkey,
    cargar_dotenv,
)
from core.engine import detect_context, run_once
from core.hotkey import HotkeyListener
from core.logsetup import setup_logging

VERSION = "1.0.0"
APP_NAME = "g360-textofix"

# Modos de correccion: `mock` no usa IA, `ia` llama a Gemini.
MODO_MOCK = "mock"
MODO_IA = "ia"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="g360-textofix",
        description=f"{APP_NAME} v{VERSION} - corrector de texto para Windows (Etapa 1)",
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
        default="mock",
        help=(
            "mock: no usa IA, devuelve el texto igual (para probar la mecanica). "
            "ia: corrige de verdad con Gemini (Etapa 2)."
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
    parser.add_argument("--sin-sonido", action="store_true", help="Desactiva los tonos.")
    parser.add_argument("-v", "--verbose", action="store_true", help="Detalle en consola.")

    return parser.parse_args(argv)


def _install_console_handler(listener: HotkeyListener) -> None:
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


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    cargar_dotenv()
    cfg = Config.from_env()
    log = setup_logging(verbose=args.verbose or cfg.verbose)

    if args.sin_sonido:
        feedback.set_muted(True)

    if args.bateria:
        cargar_dotenv()
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tests"))
        from core.bateria import ejecutar

        return ejecutar(args.filtro)

    if args.diagnostico:
        log.info("diagnostico: ventana activa en primer plano")
        detect_context()
        return 0

    modo = args.modo

    if modo == MODO_IA:
        from core.ai import CorrectorIA

        listo, motivo = CorrectorIA().disponible()
        if not listo:
            log.error("modo IA no disponible: %s", motivo)
            return 3

    if args.once:
        outcome = run_once(cfg, mode=modo, transform=args.mock_transform)
        log.info("resultado=%s adaptador=%s", outcome.reason, outcome.adapter or "-")
        return 0 if outcome.ok else 1

    if not cfg.enabled:
        log.warning("desactivado por configuracion (TEXTOFIX_ENABLED=0)")
        return 0

    hotkey = Hotkey(
        modifiers=MOD_CONTROL | MOD_SHIFT | MOD_NOREPEAT,
        virtual_key=VK_E,
        label="Ctrl+Shift+E",
    )
    listener = HotkeyListener(hotkey.modifiers, hotkey.virtual_key, hotkey.label)
    _install_console_handler(listener)

    log.info("%s v%s escuchando %s (Ctrl+C para salir)", APP_NAME, VERSION, hotkey.label)

    # Aviso honesto sobre que se esta haciendo: en modo mock el texto vuelve
    # igual y no se ve nada, lo que parece un fallo pero no lo es.
    if modo == MODO_IA:
        log.info("MODO IA: se corrige con Gemini. Cada correccion consume cuota.")
    elif args.mock_transform == "wrap":
        log.info(
            "MODO DEMO: el texto se devuelve entre comillas angulares, para que "
            "veas donde se escribio. No se corrige todavia."
        )
    else:
        log.warning(
            "MODO SIMULADO: el texto se devuelve SIN corregir, asi que no se ve "
            "ningun cambio. Para comprobar que funciona: --mock-transform wrap. "
            "Para corregir de verdad: --modo ia"
        )

    try:
        listener.start(lambda: run_once(cfg, mode=modo, transform=args.mock_transform))
    except OSError as exc:
        log.error("%s", exc)
        return 2
    except KeyboardInterrupt:
        log.info("interrumpido")

    log.info("adios")
    return 0


if __name__ == "__main__":
    sys.exit(main())
