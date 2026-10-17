"""
Prueba de privacidad: el texto del usuario no debe filtrarse.

Verifica tres cosas que el plan promete:

1. Los logs NO contienen el texto corregido (solo longitud y hash).
2. Tras una correccion, el portapapeles del usuario queda como estaba.
3. No se crea ningun archivo de log en disco.

    uv run python tests/smoke_privacidad.py
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import smoke_win32_edit as H

from core.config import Config
from core.engine import run_once
from core.logsetup import setup_logging
from core.winapi import clipboard_read, clipboard_write

# Cadenas que jamas deberian aparecer en un log ni quedar como "contenido".
SEGREDO_DOC = "ZQXJ-SECRETO-DOCUMENTO-7412"
SEGREDO_CLIP = "ZQXJ-SECRETO-PORTAPAPELES-9134"

EM_SETSEL = 0x00B1


class _CapturaLogs(logging.Handler):
    """Guarda todos los mensajes de log para poder inspeccionarlos."""

    def __init__(self) -> None:
        super().__init__()
        self.mensajes: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.mensajes.append(record.getMessage())


def main() -> int:
    H._ocultar_consola()

    # Log a memoria: asi se puede comprobar que el texto no aparece.
    captura = _CapturaLogs()
    log = setup_logging(verbose=True)
    log.handlers = [captura]
    log.addHandler(captura)
    log.propagate = False

    ventana = H._Ventana()
    ventana.abrir()
    fallos = 0

    try:
        cfg = Config.from_env()

        # --- 1. Correccion sin cambios: el portapapeles no debe tocarse -----
        H._poner_texto(ventana.edit, SEGREDO_DOC)
        clipboard_write(SEGREDO_CLIP)
        H._enfocar(ventana)
        H.user32.SendMessageW(ventana.edit, EM_SETSEL, 0, -1)

        log.info(">>> inicio de la correccion")
        outcome = run_once(cfg, mode="mock", transform="roundtrip")
        log.info("<<< fin de la correccion (resultado=%s)", outcome.reason)
        print(f"  resultado: {outcome.reason}")

        texto_logs = "\n".join(captura.mensajes)
        print("  --- mensajes de log ---")
        for m in captura.mensajes:
            print(f"    {m}")

        if SEGREDO_DOC in texto_logs:
            print("  FALLO: el texto del documento aparece en los logs")
            fallos += 1
        else:
            print("  OK: el texto del documento NO aparece en los logs")

        if SEGREDO_CLIP in texto_logs:
            print("  FALLO: el contenido previo del portapapeles aparece en los logs")
            fallos += 1
        else:
            print("  OK: el portapapeles previo NO aparece en los logs")

        actual = clipboard_read()
        if actual != SEGREDO_CLIP:
            print(f"  FALLO: el portapapeles cambio -> {actual!r}")
            fallos += 1
        else:
            print("  OK: el portapapeles quedo intacto")

        # --- 2. Correccion con escritura: tambien debe restaurarse ---------
        H._poner_texto(ventana.edit, SEGREDO_DOC)
        clipboard_write(SEGREDO_CLIP)
        H._enfocar(ventana)
        H.user32.SendMessageW(ventana.edit, EM_SETSEL, 0, -1)

        captura.mensajes.clear()
        outcome = run_once(cfg, mode="mock", transform="wrap")
        print(f"  resultado (con escritura): {outcome.reason}")

        if outcome.reason == "escrito":
            if SEGREDO_DOC in "\n".join(captura.mensajes):
                print("  FALLO: el texto aparece en los logs tras escribir")
                fallos += 1
            else:
                print("  OK: sin texto en los logs tras escribir")

            actual = clipboard_read()
            if actual != SEGREDO_CLIP:
                print(f"  FALLO: el portapapeles no se restored -> {actual!r}")
                fallos += 1
            else:
                print("  OK: el portapapeles quedo intacto tras escribir")

        # --- 3. No se debe crear ningun archivo de log ---------------------
        raiz = Path(__file__).resolve().parents[1]
        logs_en_disco = [p for p in raiz.rglob("*.log") if ".venv" not in p.parts]
        if logs_en_disco:
            print(f"  FALLO: se crearon archivos de log: {logs_en_disco}")
            fallos += 1
        else:
            print("  OK: no se creo ningun archivo de log")
    finally:
        ventana.cerrar()

    print()
    if fallos:
        print(f"=== {fallos} verificacion(es) de privacidad fallaron ===")
        return 1
    print("=== privacidad verificada ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
