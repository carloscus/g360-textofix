"""
Tests de la orden de proveedores y la guarda anti-disculpas.

El 3B local llego a escribir "Lo siento, pero no puedo cumplir..." en
lugar del texto del usuario, y esa mezcla pasaba la guarda de longitud
(una disculpa corta entra en el rango 30%-200%). Estos tests cubren las
dos defensas: la guarda que rechaza disculpas inventadas, y el orden de
proveedores que prioriza la nube confiable sobre el local veloz.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from core.guards import validate

# --- Guarda anti-disculpas ---------------------------------------------------


def test_disculpa_inventada_se_rechaza():
    """'Lo siento, no puedo...' NO es una correccion: se rechaza."""
    v = validate(
        "El cliente pidio tres cajas",
        "Lo siento, pero no puedo cumplir con esa solicitud.",
    )
    assert not v.ok
    assert v.reason == "respuesta-conversacional"


def test_disculpa_mezclada_con_texto_se_rechaza():
    """El modelo puede mezclar la disculpa con texto 'corregido'."""
    v = validate(
        "El cliente pidio tres cajas de combustible ayer por la tarde",
        "El cliente pidió tres cajas de combustible. Lo siento, no puedo ayudar más.",
    )
    assert not v.ok
    assert v.reason == "respuesta-conversacional"


def test_disculpa_que_estaba_en_el_original_se_permite():
    """Un correo legitimo que ya decía 'lo siento' no se bloquea."""
    original = "Lo siento por la demora en responder su consulta del pedido"
    corregido = "Lo siento por la demora en responder su consulta del pedido."
    v = validate(original, corregido)
    assert v.ok


def test_variedad_de_rechazos_se_detecta():
    casos = [
        "Disculpa, no entendi el texto",
        "Como modelo de lenguaje no puedo hacerlo",
        "No puedo continuar con esta solicitud",
    ]
    for respuesta in casos:
        v = validate("El cliente pidio tres cajas", respuesta)
        assert not v.ok, f"debio rechazar: {respuesta!r}"


# --- Orden de proveedores ----------------------------------------------------


def test_con_clave_nim_la_nube_manda(monkeypatch, tmp_path):
    """Si hay clave de NIM guardada, la nube va primero (el local es opt-in)."""
    import core.proovedor as prov_mod
    from core.nvidia import ProveedorNIM
    from core.ollama import ProveedorOllama

    class _NIMFalso(ProveedorNIM):
        modelo = "meta/llama-3.2-90b-vision-instruct"

        def disponible(self):
            return True, ""

    class _OllamaFalso(ProveedorOllama):
        def _ollama_arriba(self):
            return True  # Ollama corriendo, pero la nube manda igual

    monkeypatch.setattr(prov_mod, "_nuevo_nim", lambda: _NIMFalso())
    monkeypatch.setattr(prov_mod, "_nuevo_ollama", lambda: _OllamaFalso())
    monkeypatch.delenv("PROVEEDOR_IA", raising=False)

    prov = prov_mod.seleccion_proveedor()
    assert prov_mod.etiqueta(prov) == "nvidia"


def test_sin_clave_nim_ollama_manda(monkeypatch):
    """Sin clave de NIM, el local sigue siendo el default."""
    import core.proovedor as prov_mod
    from core.ollama import ProveedorOllama

    class _NIMSinClave:
        modelo = "meta/llama-3.2-90b-vision-instruct"

        def disponible(self):
            return False, "falta la clave"

    class _OllamaFalso(ProveedorOllama):
        def _ollama_arriba(self):
            return True

    monkeypatch.setattr(prov_mod, "_nuevo_nim", lambda: _NIMSinClave())
    monkeypatch.setattr(prov_mod, "_nuevo_ollama", lambda: _OllamaFalso())
    monkeypatch.delenv("PROVEEDOR_IA", raising=False)

    prov = prov_mod.seleccion_proveedor()
    assert prov_mod.etiqueta(prov) == "ollama"


def test_ollama_optin_explicito(monkeypatch):
    """PROVEEDOR_IA=ollama fuerza el local aunque haya clave de NIM."""
    import core.proovedor as prov_mod
    from core.ollama import ProveedorOllama

    class _NIMFalso:
        modelo = "meta/llama-3.2-90b-vision-instruct"

        def disponible(self):
            return True, ""

    class _OllamaFalso(ProveedorOllama):
        modelo = "llama3.2:3b"

        def disponible(self):
            return True, ""

        def _ollama_arriba(self):
            return True

    monkeypatch.setattr(prov_mod, "_nuevo_nim", lambda: _NIMFalso())
    monkeypatch.setattr(prov_mod, "_nuevo_ollama", lambda: _OllamaFalso())
    monkeypatch.setenv("PROVEEDOR_IA", "ollama")

    prov = prov_mod.seleccion_proveedor()
    assert prov_mod.etiqueta(prov) == "ollama"


# --- Guarda de salto de pagina -----------------------------------------------
# En Word, un salto de pagina (Ctrl+Enter) es un caracter \x0c invisible que
# viaja dentro del texto seleccionado. Verificado con Word real: si el modelo
# lo elimina, el documento pierde la pagina en silencio (2 paginas -> 1) y
# ninguna otra guarda lo nota.


def test_salto_de_pagina_perdido_se_rechaza():
    original = "Primera pagina\r" + chr(12) + "\rSegunda pagina"
    candidato = "Primera pagina\r\rSegunda pagina"  # el modelo se comio el salto
    v = validate(original, candidato)
    assert not v.ok
    assert v.reason == "salto-de-pagina-perdido"


def test_salto_de_pagina_preservado_se_permite():
    original = "Primera pagina con errorr\r" + chr(12) + "\rSegunda pagina"
    candidato = "Primera pagina con error.\r" + chr(12) + "\rSegunda pagina"
    v = validate(original, candidato)
    assert v.ok


def test_sin_saltos_de_pagina_no_afecta():
    """Un texto normal (sin saltos de pagina) no toca esta guarda."""
    v = validate("El cliente pidio tres cajas", "El cliente pidió tres cajas.")
    assert v.ok
