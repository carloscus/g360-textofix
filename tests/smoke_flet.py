"""
Prueba end-to-end contra una app Flet real.

Flet usa Flutter, que se comporta de forma distinta a casi todo lo demas:

- no expone TextPattern (no hay forma de saber la seleccion),
- rechaza ValuePattern.SetValue() con "Unspecified error",
- ignora Ctrl+C y Ctrl+V sinteticos,
- ignora las teclas de navegacion (Home, End).

Pero SI responde a Ctrl+End, al Retroceso y a la escritura con
KEYEVENTF_UNICODE. Esta prueba levanta una app Flet minima y comprueba que el
ciclo completo funciona en ella.

    uv run --with flet python tests/smoke_flet.py

Si flet no esta disponible, la prueba se omite con un aviso.
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import uiautomation as auto
import win32gui
import win32process

from core.adapters import build_adapters, pick_adapter
from core.adapters.base import Capture
from core.config import Config
from core.engine import run_once
from core.logsetup import setup_logging
from core.winapi import foreground_context, user32

TITULO = "Prueba textofix"
INICIAL = "analizandodo una descuento comercial"
ESPERADO = "El cliente pidio tres cajas para el deposito"

APP = """
import flet as ft

def main(page: ft.Page):
    page.title = "Prueba textofix"
    page.add(ft.TextField(label="Antecedentes", value="{inicial}"))

ft.run(main)
"""


def _ventana_por_titulo(titulo: str) -> tuple[int, int]:
    encontrados = []

    def cb(hwnd, _):
        if win32gui.IsWindowVisible(hwnd) and win32gui.GetWindowText(hwnd).strip() == titulo:
            _, pid = win32process.GetWindowThreadProcessId(hwnd)
            encontrados.append((hwnd, pid))

    win32gui.EnumWindows(cb, None)
    return encontrados[0] if encontrados else (0, 0)


def _buscar_edit(control, profundidad: int = 0):
    if profundidad > 14:
        return None
    try:
        hijos = control.GetChildren()
    except Exception:
        return None
    for hijo in hijos:
        try:
            if hijo.ControlTypeName == "EditControl":
                return hijo
        except Exception:
            continue
        encontrado = _buscar_edit(hijo, profundidad + 1)
        if encontrado is not None:
            return encontrado
    return None


def _enfocar(hwnd: int) -> bool:
    user32.ShowWindow(hwnd, 9)
    for _ in range(5):
        user32.SetForegroundWindow(hwnd)
        time.sleep(0.4)
        if user32.GetForegroundWindow() == hwnd:
            return True
    return False


def main() -> int:
    log = setup_logging(verbose=False)

    try:
        import flet  # noqa: F401
    except ImportError:
        log.warning("flet no esta instalado. Ejecuta: uv run --with flet ...")
        return 0

    with tempfile.TemporaryDirectory() as tmp:
        ruta = Path(tmp) / "app.py"
        ruta.write_text(APP.format(inicial=INICIAL), encoding="utf-8")

        proc = subprocess.Popen([sys.executable, str(ruta)])
        hwnd = 0
        for _ in range(80):
            time.sleep(0.5)
            hwnd, _pid = _ventana_por_titulo(TITULO)
            if hwnd:
                break

        if not hwnd:
            log.error("no abrio la ventana de la app Flet")
            proc.terminate()
            return 1

        fallos = 0
        try:
            if not _enfocar(hwnd):
                log.error("no se pudo poner la app Flet en primer plano")
                return 1

            with auto.UIAutomationInitializerInThread():
                ctrl = _buscar_edit(auto.ControlFromHandle(hwnd))
                if ctrl is None:
                    log.error("no se encontro el campo de texto")
                    return 1

                patron = ctrl.GetPattern(auto.PatternId.ValuePattern)
                print(f"  valor inicial: {patron.Value!r}")

                # El usuario hace clic en el campo antes de usar el atajo. Sin
                # ese clic el framework no tiene el foco y no hay nada que leer.
                rect = ctrl.BoundingRectangle
                auto.Click((rect.left + rect.right) // 2, (rect.top + rect.bottom) // 2)
                time.sleep(0.6)

                # El ciclo completo del corrector, con wrap para que se vea.
                cfg = Config.from_env()
                outcome = run_once(cfg, mode="mock", transform="wrap")
                print(f"  resultado: {outcome.reason} (adaptador {outcome.adapter})")
                time.sleep(1.2)

                final = patron.Value
                print(f"  valor final : {final!r}")
                esperado = f"«{INICIAL}»"

                if outcome.reason != "escrito":
                    print(f"  FALLO: se esperaba 'escrito', hubo {outcome.reason}")
                    fallos += 1
                elif final != esperado:
                    print(f"  FALLO: se esperaba {esperado!r}")
                    fallos += 1
                else:
                    print("  OK: el ciclo completo funciona en Flutter/Flet")

                # Restaurar para dejar la app como estaba.
                adaptador = pick_adapter(build_adapters(cfg), foreground_context())
                adaptador.write(None, Capture(text=final, meta={"via": "uia-value"}), INICIAL)
                time.sleep(1.0)
                print(f"  restaurado  : {patron.Value!r}")
        finally:
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except Exception:
                proc.kill()

    print()
    if fallos:
        print(f"=== {fallos} verificacion(es) fallaron ===")
        return 1
    print("=== Flet/Flutter verificado ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
