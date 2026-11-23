"""
Guardas de validacion de la correccion.

Modulo PURO: no importa nada de Windows ni de la red, para poder testearse
aislado. La idea es que el modelo nunca pueda pisar texto que no es suyo.

Ante cualquier duda se rechaza el texto y se conserva el original.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

import difflib

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
# URLs con esquema (http/https/ftp) y correos. El prompt ya pide no tocarlos;
# esta guarda es la red de atras: si la respuesta los cambio, no se escribe.
_URLS = re.compile(r"https?://\S+|ftp://\S+")
_CORREOS = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")

# --- Presupuesto de cambios (modo natural) ----------------------------------

# Un guion interno separa dos tokens lexicos ("bien-estar" -> "bien", "estar").
_GUION_INTERNO = re.compile(r"(?<=[a-z0-9])-(?=[a-z0-9])")
# Caracteres de puntuacion que se recortan de los bordes de cada token.
_PUNTUACION_BORDES = ".,;:!?¿¡\"'()[]{}«»…–—-"

# Clasificacion de un token lexico contable.
PALABRA = "palabra"
CORTA = "corta"
NUMERICO = "numerico"
PROTEGIDO = "protegido"


def _quitar_diacriticos(texto: str) -> str:
    """Devuelve el texto sin tildes ni otros signos diacriticos.

    Se normaliza a NFC primero para que un caracter compuesto y su equivalente
    descompuesto mapeen al mismo token (p.ej. "e\u0301" == "e" tras quitar
    diacriticos), y luego a NFD para descartar las marcas combinantes.
    """
    normalizado = unicodedata.normalize("NFC", texto)
    normalizado = unicodedata.normalize("NFD", normalizado)
    return "".join(c for c in normalizado if unicodedata.category(c) != "Mn")


def _es_sigla_original(raw: str) -> bool:
    """True si `raw` (ya recortado de puntuacion de bordes) es una sigla/codigo
    en mayusculas: se evalua ANTES del casefold para que PROTEGIDO siga siendo
    detectable. Una palabra con guion como "SKU-ABC-001" se trata como una
    sola palabra original: si la original es mayuscula larga, todos sus
    sub-tokens quedan protegidos."""
    token = raw.strip(_PUNTUACION_BORDES)
    partes = [p for p in token.split() if p]
    # Una sola parte, mayuscula larga y con mas de 2 caracteres: sigla protegida.
    return len(partes) == 1 and partes[0].isupper() and len(partes[0]) > 2


def _tiene_digito(raw: str) -> bool:
    """True si la palabra original (antes de separar por guion) contiene
    cualquier digito. Se usa para clasificar a TODOS los sub-tokens como
    NUMERICO, de modo que "9:30", "12/05" y "abc123" no cuenten para el
    presupuesto."""
    return any(c.isdigit() for c in raw)


def tokens_lexicos(texto: str) -> list[tuple[str, str]]:
    """
    Tokeniza un texto en pares (token, clase).

    Proceso: NFC + casefold + quitar diacritics, recortar puntuacion de los
    bordes, separar guion interno, descartar vacios. Clasifica cada token en
    PALABRA, CORTA (<=2 caracteres), NUMERICO o PROTEGIDO. NUMERICO y
    PROTEGIDO NO cuentan para el presupuesto de cambios.

    La clase se determina sobre la PALABRA ORIGINAL (antes de separar por
    guion interno): si la original contiene cualquier digito, todos sus
    sub-tokens son NUMERICO; si la original es una sigla mayuscula larga, todos
    sus sub-tokens son PROTEGIDO. Así "SKU-ABC-001" queda entero protegido y
    "9:30" / "12/05" no cuentan como palabras cambiadas.
    """
    resultado: list[tuple[str, str]] = []
    for raw in _WHITESPACE.split(texto):
        # El token devuelto va normalizado (minusculas, sin diacriticos).
        norm = _quitar_diacriticos(raw.casefold()).strip(_PUNTUACION_BORDES)
        norm = _GUION_INTERNO.sub(" ", norm)
        # La clase se decide sobre el original (antes de casefold y guion).
        es_sigla = _es_sigla_original(raw)
        tiene_digito = _tiene_digito(raw)
        for sub in norm.split():
            if not sub:
                continue
            if tiene_digito:
                # Cualquier digito en la original: numerico, no cuenta.
                clase = NUMERICO
            elif es_sigla:
                # Sigla/codigo en mayusculas: protegido, no cuenta.
                clase = PROTEGIDO
            elif len(sub) <= 2:
                clase = CORTA
            else:
                clase = PALABRA
            resultado.append((sub, clase))
    return resultado


def _tokens_contables(texto: str) -> list[str]:
    """Solo los tokens lexicos que cuentan (PALABRA y CORTA)."""
    return [tok for tok, clase in tokens_lexicos(texto) if clase in (PALABRA, CORTA)]


@dataclass(frozen=True)
class Diferencias:
    """Resultado de comparar dos textos a nivel de tokens lexicos contables."""

    sustituidas: int = 0
    insertadas: int = 0
    borradas: int = 0

    @property
    def total(self) -> int:
        """cambios = sustituidas + insertadas + borradas."""
        return self.sustituidas + self.insertadas + self.borradas


def diferencias(original: str, candidato: str) -> Diferencias:
    """
    Compara `original` y `candidato` con difflib.SequenceMatcher sobre los
    tokens lexicos contables de cada uno.

    Por opcode no-equal con tamaños a (del original) y b (del candidato):
    - sustituidas += min(a, b)
    - el remanente va a borradas (a > b) o insertadas (b > a)

    Documentado con comentario: así una palabra que cambia de forma pero no
    de "rol" (p.ej. "senor" vs "señor", que tras normalizar son iguales)
    cuenta 0, y una palabra de más cuenta 1 inserción.
    """
    a_tokens = _tokens_contables(original)
    b_tokens = _tokens_contables(candidato)

    sustituidas = 0
    insertadas = 0
    borradas = 0

    for opcode, i1, i2, j1, j2 in difflib.SequenceMatcher(
        None, a_tokens, b_tokens, autojunk=False
    ).get_opcodes():
        a = i2 - i1  # tokens del original en este bloque
        b = j2 - j1  # tokens del candidato en este bloque
        if opcode == "equal":
            continue
        if opcode == "replace":
            sustituidas += min(a, b)
            if a > b:
                borradas += a - b
            elif b > a:
                insertadas += b - a
        elif opcode == "delete":
            borradas += a
        elif opcode == "insert":
            insertadas += b

    return Diferencias(sustituidas=sustituidas, insertadas=insertadas, borradas=borradas)


def presupuesto_palabras(n: int) -> int:
    """
    Presupuesto de palabras cambiadas para un original de `n` tokens contables.

    Fórmula: min(12, max(2, round(0.20 * n))). Pisos de 2, tope de 12, y el
    20 % del original como punto medio.
    """
    return min(12, max(2, round(0.20 * n)))


def _excede_presupuesto(original: str, candidato: str) -> bool:
    """
    True si el candidato supera el presupuesto de cambios del original.

    Una correccion de sola tilde/mayuscula/puntuacion cuenta 0 cambios porque
    tokens_lexicos ya normalizo tildes y mayusculas y recorto puntuacion: esos
    pares de tokens son iguales y no aparecen como no-equal en el SequenceMatcher.
    """
    n = len(_tokens_contables(original))
    if n == 0:
        return False
    diff = diferencias(original, candidato)
    return diff.total > presupuesto_palabras(n)


def extract_digits(text: str) -> tuple[str, ...]:
    """Secuencia de numeros del texto, en orden. Base de la guarda de cifras."""
    return tuple(_DIGITS.findall(text))


def extract_urls(text: str) -> tuple[str, ...]:
    """Secuencia de URLs con esquema del texto, en orden (patron extract_digits)."""
    return tuple(_URLS.findall(text))


def extract_correos(text: str) -> tuple[str, ...]:
    """Secuencia de correos del texto, en orden (patron extract_digits)."""
    return tuple(_CORREOS.findall(text))


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


def validate(
    original: str, candidate: str | None, estilo: str | None = None
) -> Verdict:
    """
    Decide si `candidate` puede reemplazar a `original`.

    Ante la duda devuelve `ok=False`: el llamador conserva el original.

    `estilo` ("natural" | "estricto" | None) solo activa el presupuesto de
    cambios cuando vale "natural". Con None o "estricto" el comportamiento es
    byte-idéntico al de antes. "auto" se normaliza a estilo_activo() en el
    llamador, no acá: guards no importa ai (usa el literal "natural").
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

    # URLs y correos: el modelo a veces los "corrige" (parte un enlace, toca
    # un dominio). Si el original los tenia y la secuencia difiere, no se
    # escribe. Un original sin ellos produce dos tuplas vacias y no aplica.
    # Si el original tenia una URL ya rota, el rechazo es conservador a
    # proposito: ante la duda, no se escribe.
    if extract_urls(original) != extract_urls(candidate) or extract_correos(
        original
    ) != extract_correos(candidate):
        return Verdict(False, False, "urls-correos-modificados")

    # Salto de pagina (Ctrl+Enter en Word, un caracter \x0c invisible que
    # viaja dentro del texto seleccionado). Una correccion legitima nunca
    # quita uno: si el modelo lo normalizo, el documento pierde la pagina
    # en silencio y ninguna otra guarda lo nota.
    if original.count(chr(12)) > candidate.count(chr(12)):
        return Verdict(False, False, "salto-de-pagina-perdido")

    # Modo natural: presupuesto de cambios (1-2 palabras por frase, tope 12).
    # Una sola tilde/mayuscula/puntuacion cuenta 0 cambios. Esta rama va
    # DESPUES del salto de pagina y ANTES de sin-cambios.
    if estilo == "natural" and _excede_presupuesto(original, candidate):
        return Verdict(False, False, "reescritura-agresiva")

    if normalize(original) == normalize(candidate):
        return Verdict(True, False, "sin-cambios")

    return Verdict(True, True, "ok")
