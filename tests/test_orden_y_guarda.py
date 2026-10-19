"""
Tests de la orden de proveedores y la guarda anti-disculpas.

Un modelo llego a escribir "Lo siento, pero no puedo cumplir..." en
lugar del texto del usuario, y esa mezcla pasaba la guarda de longitud
(una disculpa corta entra en el rango 30%-200%). Estos tests cubren las
dos defensas: la guarda que rechaza disculpas inventadas, y el orden de
proveedores (NIM primero, Gemini despues) que prioriza la nube con cupo
mas generoso.
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


def test_con_clave_nim_la_nube_manda(monkeypatch):
    """Si hay clave de NIM, NVIDIA va primero aunque tambien este Gemini."""
    import core.proovedor as prov_mod
    from core.nvidia import ProveedorNIM

    class _NIMFalso(ProveedorNIM):
        modelo = "meta/llama-3.2-90b-vision-instruct"

        def disponible(self):
            return True, ""

    monkeypatch.setattr(prov_mod, "_nuevo_nim", lambda: _NIMFalso())
    monkeypatch.delenv("PROVEEDOR_IA", raising=False)

    prov = prov_mod.seleccion_proveedor()
    assert prov_mod.etiqueta(prov) == "nvidia"


def test_sin_clave_nim_va_a_gemini(monkeypatch):
    """Sin clave de NIM, el default es Gemini con la suya."""
    import core.proovedor as prov_mod
    from core.nvidia import ProveedorNIM

    class _NIMSinClave(ProveedorNIM):
        def disponible(self):
            return False, "falta la clave"

    monkeypatch.setattr(prov_mod, "_nuevo_nim", lambda: _NIMSinClave())
    monkeypatch.delenv("PROVEEDOR_IA", raising=False)

    prov = prov_mod.seleccion_proveedor()
    assert prov_mod.etiqueta(prov) == "gemini"


def test_ollama_en_el_env_viejo_cae_al_default_de_nube(monkeypatch):
    """PROVEEDOR_IA=ollama ya no existe: no rompe, cae al default de nube."""
    import core.proovedor as prov_mod
    from core.nvidia import ProveedorNIM

    class _NIMFalso(ProveedorNIM):
        modelo = "meta/llama-3.2-90b-vision-instruct"

        def disponible(self):
            return True, ""

    monkeypatch.setattr(prov_mod, "_nuevo_nim", lambda: _NIMFalso())
    monkeypatch.setenv("PROVEEDOR_IA", "ollama")

    prov = prov_mod.seleccion_proveedor()
    assert prov_mod.etiqueta(prov) == "nvidia"


# --- Eleccion desde la bandeja (config.json -> modelo_ia) -------------------


def _perfil_con(monkeypatch, eleccion: str) -> None:
    from core import perfil

    monkeypatch.setattr(perfil, "leer_modelo_ia", lambda: eleccion)


def test_bandeja_90b_fuerza_el_90b(monkeypatch):
    """La opcion 'NVIDIA 90b' pide el 90b explicito, no el default."""
    import core.proovedor as prov_mod
    from core.nvidia import MODELO_90B

    class _NIMFalso:
        modelo = MODELO_90B

        def disponible(self):
            return True, ""

    llamado: dict = {}

    def _nuevo(modelo=None):
        llamado["modelo"] = modelo
        return _NIMFalso()

    monkeypatch.setattr(prov_mod, "_nuevo_nim", _nuevo)
    _perfil_con(monkeypatch, "nvidia-90b")
    monkeypatch.delenv("PROVEEDOR_IA", raising=False)

    prov = prov_mod.seleccion_proveedor()

    assert llamado["modelo"] == MODELO_90B
    assert prov is not None


def test_bandeja_manda_sobre_el_env(monkeypatch):
    """Si la bandeja eligio Gemini, un PROVEEDOR_IA del .env no lo pisa."""
    import core.proovedor as prov_mod

    toco_nim: list = []
    monkeypatch.setattr(prov_mod, "_nuevo_nim", lambda modelo=None: toco_nim.append(1))
    _perfil_con(monkeypatch, "gemini")
    monkeypatch.setenv("PROVEEDOR_IA", "nvidia")

    prov = prov_mod.seleccion_proveedor()

    assert prov_mod.etiqueta(prov) == "gemini"
    assert toco_nim == []  # ni siquiera se consulto NIM


def test_auto_deja_pasar_el_env(monkeypatch):
    """'auto' no es una eleccion: PROVEEDOR_IA del .env sigue mandando."""
    import core.proovedor as prov_mod
    from core.nvidia import ProveedorNIM

    class _NIMFalso(ProveedorNIM):
        modelo = "nvidia/nemotron-3-super-120b-a12b"

        def disponible(self):
            return True, ""

    monkeypatch.setattr(prov_mod, "_nuevo_nim", lambda modelo=None: _NIMFalso())
    _perfil_con(monkeypatch, "auto")
    monkeypatch.setenv("PROVEEDOR_IA", "nvidia")

    prov = prov_mod.seleccion_proveedor()
    assert prov_mod.etiqueta(prov) == "nvidia"


def test_el_menu_trae_las_tres_opciones():
    from core.perfil import CONFIG_POR_DEFECTO
    from core.proovedor import OPCIONES_MODELO

    assert [valor for valor, _ in OPCIONES_MODELO] == ["auto", "nvidia-90b", "gemini"]
    assert CONFIG_POR_DEFECTO["modelo_ia"] == "auto"


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
