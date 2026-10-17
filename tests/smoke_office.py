"""
Prueba de humo de los adaptadores de Office (Word y Excel por COM).

Se sube unicamente si Office esta instalado. Si falta, la prueba se salta con
un aviso en vez de fallar.

    uv run python tests/smoke_office.py

Cubre las guardas que hacen falta por la semantica de Office:
- Excel no debe tocar celdas con formula ni valores no textuales.
- Word debe conservar los saltos de parrafo de la seleccion.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from core.config import Config
from core.engine import run_once
from core.logsetup import setup_logging
from core.winapi import user32

TEXTO = "El cliente pidio tres cajas"

log = setup_logging(verbose=True)


def _espera(hwnd: int, segundos: float = 2.0) -> bool:
    """Espera a que la ventana quede delante."""
    limite = time.time() + segundos
    while time.time() < limite:
        if user32.GetForegroundWindow() == hwnd:
            return True
        time.sleep(0.1)
    return False


def _probar_excel(cfg) -> int:
    import win32com.client as com

    fallos = 0
    app = com.Dispatch("Excel.Application")
    app.Visible = True
    libro = app.Workbooks.Add()
    hoja = libro.ActiveSheet

    def caso(
        nombre: str,
        valor,
        esperado,
        esperado_motivo: str | None = None,
        leer=None,
    ) -> None:
        """
        `leer` permite comprobar .Formula en vez de .Value: Excel EVALUA las
        formulas, asi que escribir '=CONCATENATE("a","b")' deja "ab" en .Value.
        """
        nonlocal fallos
        hoja.Range("A1").Value = valor
        app.ActiveWindow.Activate()
        hoja.Range("A1").Select()
        hwnd = int(app.Hwnd)
        user32.SetForegroundWindow(hwnd)
        _espera(hwnd)

        outcome = run_once(cfg, mode="mock", transform="wrap")
        time.sleep(0.4)
        actual = leer() if leer else hoja.Range("A1").Value
        log.info("%s -> resultado=%s  A1=%r", nombre, outcome.reason, actual)

        if actual != esperado:
            log.error("FALLO %s: se esperaba %r", nombre, esperado)
            fallos += 1
        elif esperado_motivo and outcome.reason != esperado_motivo:
            log.error(
                "FALLO %s: motivo esperado %s, obtenido %s",
                nombre,
                esperado_motivo,
                outcome.reason,
            )
            fallos += 1
        else:
            log.info("OK %s", nombre)

    log.info("=== Excel ===")
    caso("celda de texto", TEXTO, f"«{TEXTO}»", "escrito")
    caso(
        "celda con formula",
        '=CONCATENATE("a","b")',
        '=CONCATENATE("a","b")',
        "sin-seleccion",
        leer=lambda: hoja.Range("A1").Formula,
    )
    caso("celda numerica", 42, 42.0, "sin-seleccion")
    caso("celda vacia", "", None, "sin-seleccion")

    libro.Close(False)
    app.Quit()
    return fallos


def _probar_word(cfg) -> int:
    import win32com.client as com

    fallos = 0
    word = com.Dispatch("Word.Application")
    word.Visible = True
    doc = word.Documents.Add()

    def caso(nombre: str, texto: str, esperado: str) -> None:
        nonlocal fallos
        doc.Content.Text = texto
        doc.Activate()
        rng = doc.Content
        rng.Select()
        hwnd = int(word.ActiveWindow.Hwnd)
        user32.SetForegroundWindow(hwnd)
        _espera(hwnd)

        outcome = run_once(cfg, mode="mock", transform="wrap")
        time.sleep(0.4)
        actual = doc.Content.Text
        log.info("%s -> resultado=%s  texto=%r", nombre, outcome.reason, actual)

        if actual != esperado:
            log.error("FALLO %s: se esperaba %r", nombre, esperado)
            fallos += 1
        else:
            log.info("OK %s", nombre)

    log.info("=== Word ===")
    # El documento de Word siempre termina en \r; el corrector no debe crear
    # un parrafo extra al escribir.
    caso("parrafo simple", TEXTO, f"«{TEXTO}»\r")
    caso("dos parrafos", f"{TEXTO}\rSegunda linea", f"«{TEXTO}\rSegunda linea»\r")

    doc.Close(False)
    word.Quit()
    return 0 if fallos == 0 else fallos


def main() -> int:
    try:
        import win32com.client  # noqa: F401
    except ImportError:
        log.error("pywin32 no esta instalado")
        return 1

    cfg = Config.from_env()
    fallos = 0

    try:
        fallos += _probar_excel(cfg)
    except Exception:
        log.exception("Excel no disponible o fallo la prueba; se omite")

    try:
        fallos += _probar_word(cfg)
    except Exception:
        log.exception("Word no disponible o fallo la prueba; se omite")

    if fallos:
        log.error("=== %d prueba(s) de Office fallaron ===", fallos)
        return 1
    log.info("=== todas las pruebas de Office pasaron ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
