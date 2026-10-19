"""
Seleccion del proveedor de IA.

El usuario elige por `.env` o por la bandeja. El resto del corrector no
sabe que proveedor usa: solo llama `proovedor.corregir(texto)`.

Solo hay dos proveedores, ambos de nube (el texto SI sale de la maquina):

- Con clave de NIM, la nube grande manda (el cupo es mas generoso).
- Sin clave de NIM, Gemini con la suya.
- Sin ninguna clave, se pide al arrancar o se avisa.

Eso hace que el primer arranque del .exe no dependa de nada: si el usuario
solo tiene la clave de Gemini, sigue funcionando.
"""

from __future__ import annotations

import logging
import os
from typing import Protocol

from .logsetup import LOGGER_NAME
from .nvidia import MODELO_90B

log = logging.getLogger(LOGGER_NAME)


class ProveedorIA(Protocol):
    """Contrato minimo que el corrector necesita de cualquier proveedor."""

    def corregir(self, texto: str, evitando: str | None = None) -> str | None: ...
    def disponible(self) -> tuple[bool, str]: ...
    def probar(self, texto: str) -> dict: ...

    @property
    def api_key(self) -> str | None: ...


PROVEEDOR_GEMINI = "gemini"
PROVEEDOR_NIM = "nvidia"
# El 90b elegido a mano desde la bandeja (config.json -> modelo_ia).
PROVEEDOR_NIM_90B = "nvidia-90b"
# Ollama se retiro del proyecto; el valor queda solo para detectar el .env
# viejo y avisar, en vez de fallar en silencio.
PROVEEDOR_OLLAMA_LEGACY = "ollama"

# Las opciones del menu "Modelo de correccion" de la bandeja, en orden.
# (valor persistido, texto visible)
OPCIONES_MODELO = [
    ("auto", "Auto (NVIDIA nemotron-super)"),
    ("nvidia-90b", "NVIDIA 90b Vision"),
    ("gemini", "Gemini (nube Google)"),
]


def _eleccion_usuario() -> str:
    """
    La eleccion explicita del usuario, si la hay.

    La bandeja (config.json del perfil) manda sobre PROVEEDOR_IA del .env;
    "auto" no es una eleccion, deja pasar el .env y el autodetect.
    """
    from .perfil import leer_modelo_ia

    eleccion = leer_modelo_ia().strip().lower()
    if eleccion and eleccion != "auto":
        return eleccion
    return os.environ.get("PROVEEDOR_IA", "").strip().lower()


def seleccion_proveedor() -> ProveedorIA:
    """
    Devuelve el proveedor a usar.

    El orden de decicion:

    1. El usuario pidio explicitamente uno: en la bandeja (modelo_ia) o en
       PROVEEDOR_IA (.env). La bandeja manda.
    2. No pidio ninguno: la nube con clave disponible (NIM primero,
       Gemini despues).
    """
    elegido = _eleccion_usuario()

    if elegido == PROVEEDOR_OLLAMA_LEGACY:
        log.warning("PROVEEDOR_IA=ollama ya no se soporta: se usa el default de nube")
        return _nube_o_mock()

    if elegido == PROVEEDOR_NIM_90B:
        prov = _nuevo_nim(modelo=MODELO_90B)
        listo, motivo = prov.disponible()
        if not listo:
            log.warning("NVIDIA 90b no esta disponible: %s", motivo)
            return _nube_o_mock()
        log.info("proovedor: nvidia 90b por eleccion del usuario")
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

    # No se pidio nada explicito: NIM si hay clave, si no Gemini.
    return _nube_o_mock()


def _nuevo_nim(modelo: str | None = None) -> ProveedorIA:
    from .nvidia import ProveedorNIM

    return ProveedorNIM(modelo=modelo)


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


def otra_nube(prov: ProveedorIA) -> ProveedorIA | None:
    """
    El OTRO proveedor de nube, si esta disponible; si no, None.

    Es el reintento del fallback nube -> nube: si el proveedor elegido
    revienta (red, cuota, clave invalida), se intenta una vez con el otro.
    """
    if es_nim(prov):
        gemini = _nuevo_gemini()
        return gemini if gemini.disponible()[0] else None
    if es_gemini(prov):
        nim = _nuevo_nim()
        return nim if nim.disponible()[0] else None
    return None


# --- Utilidades ---------------------------------------------------------------


def es_gemini(prov: ProveedorIA) -> bool:
    from .ai import CorrectorIA

    return isinstance(prov, CorrectorIA)


def es_nim(prov: ProveedorIA) -> bool:
    from .nvidia import ProveedorNIM

    return isinstance(prov, ProveedorNIM)


def etiqueta(prov: ProveedorIA) -> str:
    """Etiqueta corta para el log. El proovedor en si no la sabe, pero
    para el log alcanza con el modulo en que vive."""
    from .ai import CorrectorIA
    from .nvidia import ProveedorNIM

    if isinstance(prov, ProveedorNIM):
        return "nvidia"
    if isinstance(prov, CorrectorIA):
        return "gemini"
    return type(prov).__module__
