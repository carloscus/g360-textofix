"""Tests de `core.logsetup`.

La regression clave: `refrescar_streams()` no debe invocar `setStream()`
sobre un stream cerrado (eso lanza ValueError en Python 3.14). El test usa
un archivo REAL de disco cerrado, no StringIO, porque con StringIO cerrado
no falla.
"""

from __future__ import annotations

import logging
import sys
import tempfile
from pathlib import Path

from core.logsetup import LOGGER_NAME, refrescar_streams


def _handler_sobre_archivo_cerrado():
    """Devuelve un StreamHandler cuyo stream es un archivo real cerrado."""
    fd, path = tempfile.mkstemp(suffix=".log")
    archivo = open(fd, "w", encoding="utf-8")
    archivo.close()  # simulamos el stream muerto despues de cerrar consola
    handler = logging.StreamHandler(archivo)
    return handler, path


def test_refrescar_streams_no_revienta_con_stream_cerrado(monkeypatch):
    """Previo al fix: ValueError. Posterior al fix: no lanza."""
    handler, path = _handler_sobre_archivo_cerrado()
    try:
        logger = logging.getLogger(LOGGER_NAME)
        monkeypatch.setattr(logger, "handlers", [handler])

        refrescar_streams()

        assert handler.stream is sys.stderr
    finally:
        Path(path).unlink(missing_ok=True)


def test_refrescar_streams_apunta_a_stderr_vigente(monkeypatch):
    """El handler queda apuntando al sys.stderr actual."""
    handler, path = _handler_sobre_archivo_cerrado()
    try:
        logger = logging.getLogger(LOGGER_NAME)
        monkeypatch.setattr(logger, "handlers", [handler])

        refrescar_streams()

        assert handler.stream is sys.stderr
    finally:
        Path(path).unlink(missing_ok=True)
