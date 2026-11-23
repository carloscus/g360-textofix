"""
Tests de las guardas de validacion.

`guards.py` es modulo puro: estos tests corren en cualquier plataforma, sin
Windows. Es la red que impide que una respuesta del modelo pise texto ajeno.
"""

from __future__ import annotations

import pytest

from core.casos import TODOS
from core.guards import (
    CORTA,
    NUMERICO,
    PALABRA,
    PROTEGIDO,
    Diferencias,
    diferencias,
    extract_correos,
    extract_digits,
    extract_urls,
    normalize,
    presupuesto_palabras,
    tokens_lexicos,
    validate,
)

# --- Helpers -----------------------------------------------------------------


def ok(original: str, candidate: str) -> bool:
    return validate(original, candidate).ok


def changed(original: str, candidate: str) -> bool:
    return validate(original, candidate).changed


def reason(original: str, candidate: str) -> str:
    return validate(original, candidate).reason


# --- Rechazos basicos --------------------------------------------------------


def test_rechaza_seleccion_vacia():
    assert reason("", "algo") == "sin-seleccion"
    assert reason("   \n ", "algo") == "sin-seleccion"


def test_rechaza_respuesta_vacia():
    assert reason("hola", None) == "respuesta-vacia"
    assert reason("hola", "") == "respuesta-vacia"
    assert reason("hola", "   ") == "respuesta-vacia"


def test_rechaza_bloque_de_codigo():
    original = "el cliente pidio tres cajas"
    assert reason(original, "```\nel cliente pidio tres cajas\n```") == "formato-markdown"


@pytest.mark.parametrize(
    "preambulo",
    [
        "Aqui tienes la correccion: el cliente pidio tres cajas",
        "Corrección: el cliente pidió tres cajas",
        "Texto corregido: el cliente pidió tres cajas",
        "Respuesta: el cliente pidió tres cajas",
    ],
)
def test_rechaza_preambulos(preambulo):
    original = "el cliente pidio tres cajas"
    assert reason(original, preambulo) == "preambulo-en-respuesta"


def test_rechaza_parafrasis_larga():
    original = "el cliente pidio tres cajas"
    largo = (
        "El estimable cliente solicito la compra de tres cajas "
        "para su proyecto, segun consta en el requerimiento adjunto."
    )
    assert reason(original, largo) == "respuesta-demasiado-larga"


def test_rechaza_respuesta_muy_corta():
    original = "el cliente pidio tres cajas para el deposito de lima"
    assert reason(original, "tres cajas") == "respuesta-demasiado-corta"


# --- Guarda de cifras --------------------------------------------------------


def test_acepta_correccion_que_conserva_cifras():
    original = "el cliente pidio 3 cajas el 12/05"
    assert ok(original, "El cliente pidió 3 cajas el 12/05")


def test_rechaza_cifras_inventadas():
    original = "el cliente pidio 3 cajas"
    assert reason(original, "El cliente pidió 5 cajas") == "cifras-modificadas"


def test_rechaza_cifras_eliminadas():
    original = "pedido 42 unidades ref 7781"
    assert reason(original, "pedido unidades ref") == "cifras-modificadas"


def test_rechaza_cifras_reordenadas():
    original = "del 12 al 15 de mayo"
    assert reason(original, "del 15 al 12 de mayo") == "cifras-modificadas"


def test_extract_digits_conserva_orden():
    assert extract_digits("pedido 12 ref 34") == ("12", "34")
    assert extract_digits("sin numeros") == ()


# --- Idempotencia ------------------------------------------------------------


def test_texto_ya_correcto_no_cambia():
    texto = "El cliente pidió tres cajas."
    assert ok(texto, texto)
    assert not changed(texto, texto)
    assert reason(texto, texto) == "sin-cambios"


def test_falta_de_tilde_si_es_un_cambio():
    original = "El cliente pidio tres cajas."
    assert changed(original, "El cliente pidió tres cajas."), (
        "poner la tilde ES el cambio que buscamos, no una razon para rechazar"
    )


def test_no_cambia_por_mayusculas_ni_espacios():
    original = "el cliente pidió tres cajas"
    assert not changed(original, "  El cliente pidió tres cajas  ")


def test_normalize_ignora_tildes_no_ignora_palabras():
    # normalize NO borra tildes: "pidio" y "pidió" son distintos a proposito,
    # porque una correccion justamente puede consistir en poner la tilde.
    assert normalize("pidio") != normalize("pidió")
    assert normalize("  Hola   mundo ") == normalize("hola mundo")


# --- Flujo completo -----------------------------------------------------------


def test_escritura_solo_cuando_valida_y_cambia():
    original = "el cliente pidio 3 cajas"
    veredicto = validate(original, "El cliente pidió 3 cajas")
    assert veredicto.should_write

    veredicto = validate(original, "el cliente pidio 3 cajas")
    assert not veredicto.should_write

    veredicto = validate(original, "El cliente pidió 9 cajas")
    assert not veredicto.should_write


def test_texto_largo_valido_se_acepta():
    original = "x" * 400
    assert ok(original, "X" * 400)


# --- Guardas de URLs y correos -----------------------------------------------


def test_acepta_url_intacta():
    original = "visita https://ejemplo.com/ayuda para mas info"
    assert ok(original, "Visita https://ejemplo.com/ayuda para más información.")


def test_rechaza_url_modificada():
    original = "revisa https://soporte.g360.pe/faq"
    assert reason(original, "Revisa https://g360.pe/soporte") == "urls-correos-modificados"


def test_acepta_correo_intacto():
    original = "escribir a ventas@g360.pe es rápido"
    assert ok(original, "Escribir a ventas@g360.pe es rápido.")


def test_rechaza_correo_modificado():
    original = "contactar a compras@proveedor.com.pe"
    assert reason(original, "Contactar a compras.proveedor@gmail.com") == "urls-correos-modificados"


def test_sin_urls_ni_correos_no_aplica_la_guarda():
    # Dos tuplas vacias: la guarda no activa, cualquier correccion ortografica
    # sigue pasando por las otras reglas.
    original = "el clima esta muy caluroso hoy"
    assert ok(original, "El clima está muy caluroso hoy.")


def test_extract_urls_conserva_patron():
    urls = extract_urls("ve http://a.com y https://b.org/doc.pdf")
    assert urls == ("http://a.com", "https://b.org/doc.pdf")
    assert extract_urls("sin enlaces") == ()


def test_extract_correos_conserva_patron():
    cs = extract_correos("mando a x.y@test.pe o z@dominio.com.uy")
    assert cs == ("x.y@test.pe", "z@dominio.com.uy")
    assert extract_correos("ningun contacto aqui") == ()


# --- Tabla de clases de tokens_lexicos --------------------------------------


@pytest.mark.parametrize(
    "texto,esperado",
    [
        ("Hola mundo", [("hola", PALABRA), ("mundo", PALABRA)]),
        ("a b", [("a", CORTA), ("b", CORTA)]),
        ("123 42", [("123", NUMERICO), ("42", NUMERICO)]),
        ("MAS", [("mas", PROTEGIDO)]),
        ("señor", [("senor", PALABRA)]),
        ("hola, mundo!", [("hola", PALABRA), ("mundo", PALABRA)]),
        ("9:30 am", [("9:30", NUMERICO), ("am", CORTA)]),
        ("12/05/2026", [("12/05/2026", NUMERICO)]),
        ("SKU-ABC-001", [("sku", NUMERICO), ("abc", NUMERICO), ("001", NUMERICO)]),
        ("abc123 def", [("abc123", NUMERICO), ("def", PALABRA)]),
        ("EE.UU. SKU-ABC", [("ee.uu", PROTEGIDO), ("sku", PROTEGIDO), ("abc", PROTEGIDO)]),
    ],
)
def test_tokens_lexicos_clases(texto, esperado):
    """tokens_lexicos normaliza (NFC+casefold+sin diacriticos), recorta
    puntuacion, separa guion interno y clasifica. NUMERICO y PROTEGIDO no
    cuentan para el presupuesto."""
    assert tokens_lexicos(texto) == esperado


def test_tokens_lexicos_nfc_equivalencia():
    """Un caracter compuesto y su forma descompuesta dan el mismo token."""
    compuesto = "caf\u00e9"      # e con tilde compuesta (U+00E9)
    descompuesto = "cafe\u0301"  # e + tilde combinante (U+0301)
    assert tokens_lexicos(compuesto) == tokens_lexicos(descompuesto)


# --- Tildes / mayusculas / puntuacion cuentan 0 cambios ---------------------


@pytest.mark.parametrize("caso", [c for c in TODOS if c.nombre.startswith("tilde-")])
def test_sola_tilde_no_cuenta_cambio(caso):
    """Una correccion de sola tilde/mayuscula/puntuacion cuenta 0 cambios:
    tokens_lexicos ya normalizo tildes y mayusculas y recorto puntuacion, por
    eso senor->señor, mas->más, etc. no aparecen como no-equal."""
    diff = diferencias(caso.entrada, caso.esperado)
    assert diff.total == 0, f"{caso.nombre}: {diff}"


def test_diferencias_tilde_e_o_u():
    """Casos explicitos de tilde-e, tilde-o, tilde-u: 0 cambios."""
    pares = [
        ("El senor quiere mas informacion", "El señor quiere más información"),
        ("La informacion llego tarde", "La información llegó tarde"),
        ("El numero de serie es unico", "El número de serie es único"),
    ]
    for original, candidato in pares:
        assert diferencias(original, candidato).total == 0


# --- Formula difflib (documentada en guards.py) ----------------------------


@pytest.mark.parametrize(
    "original,candidato,esperado",
    [
        # solo sustituciones del mismo tamaño
        ("hola mundo", "hola mundo", Diferencias(0, 0, 0)),
        ("uno dos", "uno tres", Diferencias(1, 0, 0)),
        # insercion: una palabra mas en el candidato
        ("hola mundo", "hola cruel mundo", Diferencias(0, 1, 0)),
        # borrado: una palabra menos en el candidato
        ("hola cruel mundo", "hola mundo", Diferencias(0, 0, 1)),
        # mezcla: reemplazo + insercion + borrado
        ("a b c", "a x b y c", Diferencias(0, 2, 0)),
    ],
)
def test_formula_diferencias(original, candidato, esperado):
    """Por opcode no-equal con tamaños a,b: sustituidas += min(a,b); el
    remanente va a borradas (a>b) o insertadas (b>a). cambios = sust+ins+del."""
    diff = diferencias(original, candidato)
    assert diff == esperado, f"{original!r} -> {candidato!r}: {diff} != {esperado}"
    assert diff.total == esperado.total


def test_sola_tilde_no_cuenta_en_diferencias():
    """La tilde no cuenta como cambio: pidio->pidió es Diferencias(0,0,0)."""
    assert diferencias("el cliente pidio tres cajas", "el cliente pidió tres cajas") == Diferencias(0, 0, 0)


def test_cifras_modificadas_se_rechazan_en_validate():
    """Un cambio de cifra se detecta con extract_digits antes del presupuesto."""
    original = "el cliente pidio tres cajas"
    candidato = "el cliente pidió 3 cajas"
    v = validate(original, candidato, estilo="natural")
    assert v.reason == "cifras-modificadas"


# --- presupuesto_palabras: piso / 20% / tope ------------------------------


@pytest.mark.parametrize(
    "n,esperado",
    [
        (1, 2),   # piso
        (2, 2),   # piso
        (5, 2),   # round(1.0)=1 -> piso 2
        (10, 2),  # round(2.0)=2
        (25, 5),  # round(5.0)=5
        (50, 10), # round(10.0)=10
        (60, 12), # round(12.0)=12 (tope)
        (100, 12),# round(20.0)=20 -> tope 12
    ],
)
def test_presupuesto_palabras(n, esperado):
    assert presupuesto_palabras(n) == esperado


# --- Par agresivo: rechazado SOLO con estilo="natural" ---------------------


def test_par_agresivo_solo_en_natural():
    original = "El cliente pidio tres cajas para el deposito de lima"
    candidato = "El estimable cliente solicito la compra de tres cajas para su proyecto"
    # Con estilo None o "estricto" no hay presupuesto: se acepta (si pasa el
    # resto de guardas; aca solo chequeamos que no sea reescritura-agresiva).
    for estilo in (None, "estricto"):
        v = validate(original, candidato, estilo=estilo)
        assert v.reason != "reescritura-agresiva", estilo
    # Con estilo="natural" se rechaza por exceder el presupuesto.
    v = validate(original, candidato, estilo="natural")
    assert v.reason == "reescritura-agresiva"


# --- Todos los pares de casos.TODOS pasan en natural y estricto ------------


@pytest.mark.parametrize("caso", TODOS)
def test_todos_los_casos_pasan_en_ambos_modos(caso):
    """Ningun par de casos.TODOS se rechaza por presupuesto, ni en natural
    ni en estricto (los cambios de tilde cuentan 0)."""
    for estilo in (None, "estricto", "natural"):
        v = validate(caso.entrada, caso.esperado, estilo=estilo)
        assert v.ok, f"{caso.nombre} [{estilo}]: {v.reason}"
