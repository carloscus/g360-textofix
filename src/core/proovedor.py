"""
Seleccion del proveedor de IA.

El usuario elige por `.env` o por la bandeja. El resto del corrector no
sabe que proveedor usa: solo llama `proovedor.corregir(texto)`.

El default depende de que este disponible:

- Si Ollama esta corriendo con el modelo descargado, se usa Ollama:
  offline, sin cuota, privado.
- Si no, se usa Gemini: el original, por la nube.
- Ni Ollama ni Gemini: se arranca en modo mock y se avisa.

Eso hace que el primer arranque del .exe no dependa de nada: si el usuario
no tiene Ollama, sigue funcionando con la clave de Gemini.
"""

from __future__ import annotations

import logging
import os
from typing import Protocol

from .logsetup import LOGGER_NAME

log = logging.getLogger(LOGGER_NAME)


class ProveedorIA(Protocol):
    """Contrato minimo que el corrector necesita de cualquier proveedor."""

    def corregir(self, texto: str) -> str | None: ...
    def disponible(self) -> tuple[bool, str]: ...
    def probar(self, texto: str) -> dict: ...

    @property
    def api_key(self) -> str | None: ...


PROVEEDOR_GEMINI = "gemini"
PROVEEDOR_OLLAMA = "ollama"


def seleccion_proveedor() -> ProveedorIA:
    """
    Devuelve el proveedor a usar.

    El orden de decicion:

    1. El usuario pidio explicitamente uno en `PROVEEDOR_IA` (.env).
    2. No pidio ninguno: si Ollama esta arriba, va Ollama (offline, sin
       cuota, el texto no sale). Si no, Gemini (por la nube).
    """
    elegido = os.environ.get("PROVEEDOR_IA", "").strip().lower()

    if elegido == PROVEEDOR_OLLAMA:
        from .ollama import ProveedorOllama

        prov = ProveedorOllama()
        listo, motivo = prov.disponible()
        if not listo:
            log.warning("Ollama no esta disponible: %s", motivo)
            return _gemini_o_mock()
        log.info("proovedor: ollama local (%s)", prov.modelo)
        return prov

    if elegido == PROVEEDOR_GEMINI:
        prov = _gemini_o_mock()
        log.info("proovedor: gemini por la nube")
        return prov

    # No se pidio nada explicito: se mira Ollama primero y, si no esta,
    # se cae a Gemini. El usuario no tiene que configurar nada para que
    # funcione: si tiene Ollama, lo usa; si no, usa Gemini.
    from .ollama import ProveedorOllama

    ollama = ProveedorOllama()
    if ollama._ollama_arriba():
        log.info("Ollama detectado: se usa el proovedor local")
        return ollama
    log.info("Ollama no detectado: se usa Gemini por la nube")
    return _gemini_o_mock()


def _gemini_o_mock() -> ProveedorIA:
    """El proovedor Gemini. Si no hay clave ni dependencia, arranca en mock."""
    from .ai import CorrectorIA

    return CorrectorIA()


# --- Utilidades ---------------------------------------------------------------


def es_gemini(prov: ProveedorIA) -> bool:
    from .ai import CorrectorIA

    return isinstance(prov, CorrectorIA)


def es_ollama(prov: ProveedorIA) -> bool:
    from .ollama import ProveedorOllama

    return isinstance(prov, ProveedorOllama)


def etiqueta(prov: ProveedorIA) -> str:
    """Etiqueta corta para el log: 'gemini' o 'ollama'.
    El proovedor en si no la sabe, pero para el log alcanza con el modulo
    en que vive."""
    from .ai import CorrectorIA
    from .ollama import ProveedorOllama

    if isinstance(prov, CorrectorIA):
        return "gemini"
    if isinstance(prov, ProveedorOllama):
        return "ollama"
    return type(prov).__module__
