"""
Prueba de humo contra una aplicacion real: el Bloc de notas.

Cubre lo que el control EDIT de `smoke_win32_edit.py` no cubre: una app
moderna de verdad.

    uv run python tests/smoke_notepad.py

Sobre las selecciones parciales: no se prueban aqui. Fijarlas requiere teclas de
navegacion (Home, Shift+Flecha) y se comprobo que las teclas SIN modificador no
llegan de forma fiable al Bloc de notas de Windows 11, aunque los atajos con
Ctrl si lleguen. El caso de seleccion parcial se valida de forma determinista en
`smoke_win32_edit.py`, que controla la seleccion por mensaje.
"""

from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import uiautomation as auto
import win32gui
import win32process

from core.config import Config
from core.engine import run_once
from core.logsetup import setup_logging
from core.winapi import send_ctrl, user32

TEXTO = "El cliente pidio tres cajas"

VK_A = 0x41
SW_RESTORE = 9

log = setup_logging(verbose=True)


def _ventana_de(pid: int) -> int:
    """HWND visible del proceso dado. Se busca por pid y no por titulo, porque
    el titulo del Bloc de notas cambia con el idioma del sistema."""
    encontrados = []

    def cb(hwnd, _):
        if not win32gui.IsWindowVisible(hwnd):
            return
        _, wpid = win32process.GetWindowThreadProcessId(hwnd)
        if wpid == pid and win32gui.GetWindowText(hwnd):
            encontrados.append(hwnd)

    win32gui.EnumWindows(cb, None)
    return encontrados[0] if encontrados else 0


def _editor(hwnd: int):
    for ctrl in auto.ControlFromHandle(hwnd).GetChildren():
        if ctrl.ControlTypeName == "EditControl":
            return ctrl
    return None


def _texto(hwnd: int) -> str:
    ctrl = _editor(hwnd)
    if ctrl is None:
        return ""
    patron = ctrl.GetPattern(auto.PatternId.ValuePattern)
    return (patron.Value or "") if patron is not None else ""


def _poner_texto(hwnd: int, texto: str) -> None:
    _editor(hwnd).GetPattern(auto.PatternId.ValuePattern).SetValue(texto)
    time.sleep(0.3)


def main() -> int:
    proc = subprocess.Popen(["notepad.exe"])
    hwnd = 0
    for _ in range(40):
        time.sleep(0.25)
        hwnd = _ventana_de(proc.pid)
        if hwnd:
            break

    if not hwnd:
        log.error("no aparecio la ventana del Bloc de notas")
        proc.terminate()
        return 1

    fallos = 0
    try:
        user32.ShowWindow(hwnd, SW_RESTORE)
        user32.SetForegroundWindow(hwnd)
        time.sleep(0.8)

        cfg = Config.from_env()

        log.info("=== Bloc de notas: seleccionar todo ===")
        _poner_texto(hwnd, TEXTO)
        user32.SetForegroundWindow(hwnd)
        time.sleep(0.5)
        send_ctrl(VK_A)
        time.sleep(0.5)

        outcome = run_once(cfg, mode="mock", transform="wrap")
        log.info("resultado=%s adaptador=%s", outcome.reason, outcome.adapter)
        time.sleep(0.6)
        texto = _texto(hwnd)
        log.info("documento ahora: %r", texto)

        if texto != f"«{TEXTO}»":
            log.error("FALLO: se esperaba el documento entrecomillado")
            fallos += 1
        else:
            log.info("OK: ciclo completo en una app real")

        log.info("=== Bloc de notas: cursor sin seleccion ===")
        _poner_texto(hwnd, TEXTO)
        user32.SetForegroundWindow(hwnd)
        time.sleep(0.6)

        outcome = run_once(cfg, mode="mock", transform="wrap")
        log.info("resultado=%s adaptador=%s", outcome.reason, outcome.adapter)
        time.sleep(0.5)
        texto = _texto(hwnd)

        if texto != TEXTO:
            log.error("FALLO: el documento no debio cambiar, ahora es %r", texto)
            fallos += 1
        else:
            log.info("OK: sin seleccion no se modifica nada")
    finally:
        proc.terminate()

    if fallos:
        log.error("=== %d prueba(s) fallaron ===", fallos)
        return 1
    log.info("=== todas las pruebas del Bloc de notas pasaron ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
