"""
Seleccion del proveedor de IA.

El usuario elige por `.env` o por la bandeja. El resto del corrector no
sabe que proveedor usa: solo llama `proovedor.corregir(texto)`.

El default depende de que este disponible:

- Con clave de NIM, la nube grande manda (el 3B local a veces "charla").
- Sin clave de NIM, Ollama local si esta corriendo (offline, sin cuota).
- Sin NIM ni Ollama, Gemini; sin nada, modo mock y aviso.

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
PROVEEDOR_NIM = "nvidia"


def seleccion_proveedor() -> ProveedorIA:
    """
    Devuelve el proveedor a usar.

    El orden de decicion:

    1. El usuario pidio explicitamente uno en `PROVEEDOR_IA` (.env).
    2. No pidio ninguno: si Ollama esta arriba, va Ollama (offline, sin
       cuota, el texto no sale). Si no, el proveedor de nube con clave
       disponible (NIM primero, Gemini despues).
    """
    elegido = os.environ.get("PROVEEDOR_IA", "").strip().lower()

    if elegido == PROVEEDOR_OLLAMA:
        prov = _nuevo_ollama()
        listo, motivo = prov.disponible()
        if not listo:
            log.warning("Ollama no esta disponible: %s", motivo)
            return _nube_o_mock()
        log.info("proovedor: ollama local (%s)", prov.modelo)
        return prov

    if elegido == PROVEEDOR_NIM:
        prov = _nuevo_nim()
        listo, motivo = prov.disponible()
        if not listo:
            log.warning("NVIDIA NIM no esta disponible: %s", motivo)
            return _nube_o_mock()
        log.info("proovedor: nvidia NIM por la nube (%s)", prov.modelo)
        return prov

    if elegido == PROVEEDOR_GEMINI:
        prov = _nuevo_gemini()
        log.info("proovedor: gemini por la nube")
        return prov

    # No se pidio nada explicito. El orden lo dicta la confiabilidad, no la
    # velocidad: el 3B local es rapido pero a veces "charla" y hasta llego a
    # escribir una disculpa en lugar del texto. Si hay clave de NIM, la nube
    # grande manda; el local queda como opt-in con PROVEEDOR_IA=ollama.
    nim = _nuevo_nim()
    if nim.disponible()[0]:
        log.info("clave de NIM disponible: se usa la nube (%s)", nim.modelo)
        return nim
    log.info("sin clave de NIM: se prueba Ollama local")
    ollama = _nuevo_ollama()
    if ollama._ollama_arriba():
        log.info("Ollama detectado: se usa el proovedor local")
        return ollama
    log.info("Ollama no detectado: se usa el proovedor de nube")
    return _nube_o_mock()


def _nuevo_ollama() -> ProveedorIA:
    from .ollama import ProveedorOllama

    return ProveedorOllama()


def _nuevo_nim() -> ProveedorIA:
    from .nvidia import ProveedorNIM

    return ProveedorNIM()


def _nuevo_gemini() -> ProveedorIA:
    from .ai import CorrectorIA

    return CorrectorIA()


def _nube_o_mock() -> ProveedorIA:
    """
    El proovedor de nube, con el que tenga clave.

    NVIDIA NIM tiene el cupo mas generoso y un modelo grande que respeta
    el prompt conservador, asi que va primero. Gemini queda como la
    caida si no hay clave de NIM.
    """
    nim = _nuevo_nim()
    listo, motivo = nim.disponible()
    if listo:
        log.info("proovedor de nube: nvidia NIM (%s)", nim.modelo)
        return nim
    log.info("sin clave de NIM (%s): se usa Gemini", motivo)
    return _nuevo_gemini()


def seleccion_nube() -> ProveedorIA:
    """
    El proovedor de nube para la caida: NVIDIA NIM si tiene clave, si no
    Gemini. Se usa cuando el proovedor local reviento o cuando las
    guardas rechazaron la correccion local.
    """
    nim = _nuevo_nim()
    listo, motivo = nim.disponible()
    if listo:
        return nim
    log.debug("sin clave de NIM para la caida: %s", motivo)
    return _nuevo_gemini()


# --- Utilidades ---------------------------------------------------------------


def es_gemini(prov: ProveedorIA) -> bool:
    from .ai import CorrectorIA

    return isinstance(prov, CorrectorIA)


def es_ollama(prov: ProveedorIA) -> bool:
    from .ollama import ProveedorOllama

    return isinstance(prov, ProveedorOllama)


def es_nim(prov: ProveedorIA) -> bool:
    from .nvidia import ProveedorNIM

    return isinstance(prov, ProveedorNIM)


def etiqueta(prov: ProveedorIA) -> str:
    """Etiqueta corta para el log. El proovedor en si no la sabe, pero
    para el log alcanza con el modulo en que vive."""
    from .ai import CorrectorIA
    from .nvidia import ProveedorNIM
    from .ollama import ProveedorOllama

    if isinstance(prov, ProveedorNIM):
        return "nvidia"
    if isinstance(prov, CorrectorIA):
        return "gemini"
    if isinstance(prov, ProveedorOllama):
        return "ollama"
    return type(prov).__module__
