"""
Tests de las guardas de validacion.

`guards.py` es modulo puro: estos tests corren en cualquier plataforma, sin
Windows. Es la red que impide que una respuesta del modelo pise texto ajeno.
"""

from __future__ import annotations

import pytest

from core.guards import extract_correos, extract_digits, extract_urls, normalize, validate

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
