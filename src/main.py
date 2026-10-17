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

from core import feedback
from core.config import MOD_CONTROL, MOD_NOREPEAT, MOD_SHIFT, VK_E, Config, Hotkey
from core.engine import detect_context, run_once
from core.hotkey import HotkeyListener
from core.logsetup import setup_logging

VERSION = "1.0.0"
APP_NAME = "g360-textofix"

# En la Etapa 1 el unico modo de correccion es el simulado.
MODO_ETAPA_1 = "mock"


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
        "--sin-sonido", action="store_true", help="Desactiva los tonos."
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="Detalle en consola."
    )

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
    cfg = Config.from_env()
    log = setup_logging(verbose=args.verbose or cfg.verbose)

    if args.sin_sonido:
        feedback.set_muted(True)

    if args.diagnostico:
        log.info("diagnostico: ventana activa en primer plano")
        detect_context()
        return 0

    if args.once:
        outcome = run_once(cfg, mode=MODO_ETAPA_1, transform=args.mock_transform)
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

    log.info(
        "%s v%s escuchando %s (Ctrl+C para salir)", APP_NAME, VERSION, hotkey.label
    )

    try:
        listener.start(
            lambda: run_once(cfg, mode=MODO_ETAPA_1, transform=args.mock_transform)
        )
    except OSError as exc:
        log.error("%s", exc)
        return 2
    except KeyboardInterrupt:
        log.info("interrumpido")

    log.info("adios")
    return 0


if __name__ == "__main__":
    sys.exit(main())
