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


def setup_logging(verbose: bool = False) -> logging.Logger:
    logger = logging.getLogger(LOGGER_NAME)
    if logger.handlers:
        return logger

    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(
        logging.Formatter("%(asctime)s  %(levelname)-7s %(message)s", "%H:%M:%S")
    )
    logger.addHandler(handler)
    logger.setLevel(logging.DEBUG if verbose else logging.INFO)
    # Sin propagacion: el texto no debe terminar en logs de terceros.
    logger.propagate = False
    return logger


def describe(text: str | None) -> str:
    """
    Resumen seguro de un texto para loguear.

    Ej: `len=42 sha=3f9a1c2b`. No permite reconstruir el texto original.
    """
    if text is None:
        return "len=0 sha=-"
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()[:8]
    return f"len={len(text)} sha={digest}"
