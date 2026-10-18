"""
Logging sin contenido.

El corrector maneja texto que puede ser confidencial, asi que los logs NUNCA
guardan el texto: solo longitud, hash y resultado. Tampoco escribe a archivo
por defecto, para que no quede copia en disco.
"""

from __future__ import annotations

import hashlib
import logging
import sys

LOGGER_NAME = "g360.textofix"


class Nulo:
    """
    Salida inerte: a donde van print y logs cuando NO hay consola.

    El .exe arranca en segundo plano (sin ventana); hasta que se cree una
    consola bajo demanda, la salida tiene que ir a algun lado que no sea
    None (None reventaria print y el StreamHandler).
    """

    encoding = "utf-8"

    def write(self, texto: str) -> int:
        return len(texto)

    def flush(self) -> None:
        pass

    def isatty(self) -> bool:
        return False


def setup_logging(verbose: bool = False) -> logging.Logger:
    logger = logging.getLogger(LOGGER_NAME)
    if logger.handlers:
        return logger

    handler = logging.StreamHandler(sys.stderr if sys.stderr is not None else Nulo())
    handler.setFormatter(logging.Formatter("%(asctime)s  %(levelname)-7s %(message)s", "%H:%M:%S"))
    logger.addHandler(handler)
    logger.setLevel(logging.DEBUG if verbose else logging.INFO)
    # Sin propagacion: el texto no debe terminar en logs de terceros.
    logger.propagate = False
    return logger


def refrescar_streams() -> None:
    """
    Re-apunta el handler al stderr actual.

    Se llama tras crear o liberar una consola: el handler quedo apuntando al
    stream viejo (inerte o cerrado) y sin esto los logs posteriores se
    perderian o reventarian.
    """
    logger = logging.getLogger(LOGGER_NAME)
    destino = sys.stderr if sys.stderr is not None else Nulo()
    for handler in logger.handlers:
        if isinstance(handler, logging.StreamHandler):
            handler.setStream(destino)


def describe(text: str | None) -> str:
    """
    Resumen seguro de un texto para loguear.

    Ej: `len=42 sha=3f9a1c2b`. No permite reconstruir el texto original.
    """
    if text is None:
        return "len=0 sha=-"
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()[:8]
    return f"len={len(text)} sha={digest}"
