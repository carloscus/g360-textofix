"""
Guardas de validacion de la correccion.

Modulo PURO: no importa nada de Windows ni de la red, para poder testearse
aislado. La idea es que el modelo nunca pueda pisar texto que no es suyo.

Ante cualquier duda se rechaza el texto y se conserva el original.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# Si la respuesta crece mas que esto, no es una correccion: es una reformulacion.
MAX_LENGTH_RATIO = 2.0

# Si se reduce mas que esto, se perdio contenido.
MIN_LENGTH_RATIO = 0.3

# Formato inesperado: el modelo se pudo haber colado un bloque de codigo.
_FENCE = "```"

# El modelo a veces responde con una introduccion en vez de solo el texto.
_PREAMBLES = (
    "aqui tienes",
    "aqui esta",
    "aquí está",
    "correccion",
    "corrección",
    "texto corregido",
    "version corregida",
    "versión corregida",
    "respuesta",
    "aclaracion",
    "aclaración",
    "clarification",
    "resultado",
)

# Frases de rechazo conversacional: el modelo chico a veces "charla" en vez
# de corregir ("Lo siento, pero no puedo cumplir con esa solicitud."). Esto
# NO es una correccion: si entra en el texto, pisa lo que el usuario escribio
# con una disculpa. Se busca en TODO el texto, no solo al principio, porque
# puede venir mezclada con el texto corregido.
_RECHAZOS_CONVERSACIONALES = (
    "lo siento",
    "perdón",
    "perdon,",
    "disculpa",
    "no puedo cumplir",
    "no puedo ayudar",
    "no puedo continuar",
    "como modelo de lenguaje",
    "como modelo de ia",
    "no tengo la capacidad",
)

_DIGITS = re.compile(r"\d+")
_WHITESPACE = re.compile(r"\s+")


def extract_digits(text: str) -> tuple[str, ...]:
    """Secuencia de numeros del texto, en orden. Base de la guarda de cifras."""
    return tuple(_DIGITS.findall(text))


def normalize(text: str) -> str:
    """Compara dos textos ignorando mayusculas, tildes menores y espacios."""
    stripped = _WHITESPACE.sub(" ", text).strip()
    return stripped.casefold()


def _looks_like_preamble(text: str) -> bool:
    head = normalize(text)[:60]
    return any(head.startswith(p) or head.startswith(p + ":") for p in _PREAMBLES)


@dataclass(frozen=True)
class Verdict:
    """Resultado de validar una correccion contra su original."""

    ok: bool
    changed: bool
    reason: str

    @property
    def should_write(self) -> bool:
        """Solo se escribe si la respuesta es valida Y aporta un cambio."""
        return self.ok and self.changed


def validate(original: str, candidate: str | None) -> Verdict:
    """
    Decide si `candidate` puede reemplazar a `original`.

    Ante la duda devuelve `ok=False`: el llamador conserva el original.
    """
    if not original or not original.strip():
        return Verdict(False, False, "sin-seleccion")

    if candidate is None or not candidate.strip():
        return Verdict(False, False, "respuesta-vacia")

    if _FENCE in candidate:
        return Verdict(False, False, "formato-markdown")

    if _looks_like_preamble(candidate):
        return Verdict(False, False, "preambulo-en-respuesta")

    # Rechazo conversacional en cualquier parte del texto: el modelo chico
    # puede mezclar una disculpa con el texto "corregido", y esa mezcla pasa
    # la guarda de longitud (una disculpa corta entra en el rango 30%-200%).
    # Solo cuenta si la frase NO estaba en el original: un correo legitimo
    # que dice 'lo siento por la demora' no se bloquea por corregirse.
    candidato_bajo = normalize(candidate)
    original_bajo = normalize(original)
    if any(
        frase in candidato_bajo and frase not in original_bajo
        for frase in _RECHAZOS_CONVERSACIONALES
    ):
        return Verdict(False, False, "respuesta-conversacional")

    ratio = len(candidate) / len(original)
    if ratio > MAX_LENGTH_RATIO:
        return Verdict(False, False, "respuesta-demasiado-larga")
    if ratio < MIN_LENGTH_RATIO:
        return Verdict(False, False, "respuesta-demasiado-corta")

    if extract_digits(original) != extract_digits(candidate):
        return Verdict(False, False, "cifras-modificadas")

    if normalize(original) == normalize(candidate):
        return Verdict(True, False, "sin-cambios")

    return Verdict(True, True, "ok")
