"""
Prueba de humo en un navegador.

Abre Chrome con un perfil AISLADO en una carpeta temporal (no toca ni el perfil
real del usuario ni otros navegadores abiertos) sobre una pagina local con un
<textarea> y un <div contenteditable>, que son los dos casos tipicos de edicion
en una pagina web.

    uv run python tests/smoke_navegador.py

Cierra Chrome al terminar.
"""

from __future__ import annotations

import shutil
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

CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
PERFIL = Path.home() / "AppData" / "Local" / "Temp" / "opencode" / "chrome-textofix"
PAGINA = PERFIL / "prueba.html"

TEXTO = "El cliente pidio tres cajas"
VK_A = 0x41

HTML = f"""<!doctype html>
<html lang="es"><head><meta charset="utf-8"><title>Prueba textofix</title></head>
<body style="font:16px sans-serif;padding:20px">
  <h1>Prueba g360-textofix</h1>
  <p>Campo textarea:</p>
  <textarea id="ta" style="width:520px;height:80px">{TEXTO}</textarea>
  <p>Editable contenteditable:</p>
  <div id="ce" contenteditable="true"
       style="width:520px;height:80px;border:1px solid #6b7280">{TEXTO}</div>
</body></html>"""

log = setup_logging(verbose=True)


def _ventana_de(pid: int) -> int:
    encontrados = []

    def cb(hwnd, _):
        if not win32gui.IsWindowVisible(hwnd):
            return
        _, wpid = win32process.GetWindowThreadProcessId(hwnd)
        if wpid == pid and win32gui.GetWindowText(hwnd):
            encontrados.append(hwnd)

    win32gui.EnumWindows(cb, None)
    return encontrados[0] if encontrados else 0


def _buscar(ctrl, automation_id: str, profundidad: int = 0):
    """
    Busca un control por AutomationId recorriendo el arbol.

    uiautomation no trae GetDescendants, asi que el recorrido es a mano.
    """
    if profundidad > 14:
        return None
    try:
        hijos = ctrl.GetChildren()
    except Exception:
        return None

    for hijo in hijos:
        try:
            if hijo.AutomationId == automation_id:
                return hijo
        except Exception:
            continue
        encontrado = _buscar(hijo, automation_id, profundidad + 1)
        if encontrado is not None:
            return encontrado
    return None


def _por_id(hwnd: int, automation_id: str):
    return _buscar(auto.ControlFromHandle(hwnd), automation_id)


def _valor(ctrl) -> str:
    """Texto del control. Los contenteditable no tienen ValuePattern."""
    patron = ctrl.GetPattern(auto.PatternId.ValuePattern)
    if patron is not None:
        return patron.Value or ""
    texto = ctrl.GetPattern(auto.PatternId.TextPattern)
    if texto is not None:
        try:
            return texto.DocumentRange.GetText(-1) or ""
        except Exception:
            return ""
    return ""


def _reiniciar(hwnd: int) -> None:
    """Recarga la pagina para volver al texto original (contenteditable no
    admite SetValue)."""
    user32.SetForegroundWindow(hwnd)
    time.sleep(0.4)
    send_ctrl(0x52)  # Ctrl+R
    time.sleep(1.5)


def main() -> int:
    if not Path(CHROME).exists():
        log.warning("Chrome no esta instalado: se omite")
        return 0

    PERFIL.mkdir(parents=True, exist_ok=True)
    PAGINA.write_text(HTML, encoding="utf-8")

    proc = subprocess.Popen(
        [
            CHROME,
            f"--user-data-dir={PERFIL}",
            "--no-first-run",
            "--no-default-browser-check",
            "--disable-features=Translate,OptimizationHints",
            f"file:///{PAGINA.as_posix()}",
        ]
    )

    hwnd = 0
    for _ in range(60):
        time.sleep(0.25)
        hwnd = _ventana_de(proc.pid)
        if hwnd:
            break

    if not hwnd:
        log.error("no aparecio la ventana de Chrome")
        proc.terminate()
        return 1

    fallos = 0
    try:
        user32.ShowWindow(hwnd, 9)
        user32.SetForegroundWindow(hwnd)
        time.sleep(1.5)

        cfg = Config.from_env()

        for etiqueta, automation_id in (("textarea", "ta"), ("contenteditable", "ce")):
            log.info("=== Chrome: %s ===", etiqueta)
            ctrl = _por_id(hwnd, automation_id)
            if ctrl is None:
                log.error("no se encontro el control %s", automation_id)
                fallos += 1
                continue

            # Restablecer el contenido antes de cada caso. El textarea admite
            # SetValue; el contenteditable hay que recargarlo.
            _reiniciar(hwnd)
            ctrl = _por_id(hwnd, automation_id)
            if ctrl is None:
                log.error("no se encontro el control %s", automation_id)
                fallos += 1
                continue

            user32.SetForegroundWindow(hwnd)
            time.sleep(0.5)

            ctrl.SetFocus()
            time.sleep(0.4)
            send_ctrl(VK_A)  # seleccionar todo dentro del control
            time.sleep(0.6)

            outcome = run_once(cfg, mode="mock", transform="wrap")
            log.info("resultado=%s adaptador=%s", outcome.reason, outcome.adapter)
            time.sleep(0.6)

            actual = _valor(ctrl)
            log.info("valor ahora: %r", actual)

            if actual != f"«{TEXTO}»":
                log.error("FALLO %s: se esperaba el valor entrecomillado", etiqueta)
                fallos += 1
            else:
                log.info("OK %s", etiqueta)
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except Exception:
            proc.kill()
        shutil.rmtree(PERFIL, ignore_errors=True)

    if fallos:
        log.error("=== %d prueba(s) de navegador fallaron ===", fallos)
        return 1
    log.info("=== todas las pruebas de navegador pasaron ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
