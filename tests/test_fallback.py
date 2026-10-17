"""
Tests de la caida local -> nube.

Si el proovedor local (Ollama) revienta al corregir, el engine cae a la
nube (NIM o Gemini, el que tenga clave) en el mismo pedido. Si el
proovedor original ya era nube y revienta, no se reintenta: se propaga.

Los tests patean `seleccion_nube`: con la clave de NIM guardada en DPAPI,
el proovedor de nube real es NVIDIA, y un test que no lo patee llamaria
a la API de verdad (lento, y gasta la cuota del usuario).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import core.proovedor as prov_mod
from core.ai import CuotaAgotada
from core.ollama import ProveedorOllama


def _patear_nube(monkeypatch, salida):
    """Patea `seleccion_nube` para que la caida no llame a la API real."""

    class _NubeFalsa:
        modelo = "falso"

        def corregir(self, texto):
            return salida

        def disponible(self):
            return True, ""

    monkeypatch.setattr(prov_mod, "seleccion_nube", lambda: _NubeFalsa())


def _ollama_roto(monkeypatch) -> ProveedorOllama:
    """`seleccion_proveedor` devuelve Ollama que revienta al corregir."""
    import httpx

    class _Ollama(ProveedorOllama):
        def corregir(self, texto):
            raise httpx.HTTPStatusError(
                "404", request=httpx.Request("POST", "http://127.0.0.1:11434/api/chat")
            )

    monkeypatch.setattr(prov_mod, "seleccion_proveedor", lambda: _Ollama(modelo="llama3.2:3b"))
    return _Ollama(modelo="llama3.2:3b")


def test_ollama_falla_y_cae_a_la_nube(monkeypatch):
    from core import engine

    _ollama_roto(monkeypatch)
    _patear_nube(monkeypatch, "El cliente pidió tres cajas.")

    resultado = engine.correct("El cliente pidio tres cajas", "ia", "roundtrip")

    assert resultado == "El cliente pidió tres cajas."


def test_gemini_roto_se_propaga_sin_reintentar(monkeypatch):
    """Si el proovedor original es nube y revienta, no se reintenta: se propaga."""

    class _GeminiRoto:
        modelo = "gemini-2.5-flash-lite"

        def corregir(self, texto):
            raise CuotaAgotada("cuota agotada")

        def disponible(self):
            return True, ""

    monkeypatch.setattr(prov_mod, "seleccion_proveedor", lambda: _GeminiRoto())

    from core import engine

    with pytest.raises(CuotaAgotada):
        engine.correct("hola", "ia", "roundtrip")


def test_la_caida_pide_seleccion_nube(monkeypatch):
    """La caida va por `seleccion_nube`, no por un proovedor fijo."""
    from core import engine

    llamadas = []

    def _espia():
        llamadas.append(1)
        return _NubeContada()

    class _NubeContada:
        modelo = "falso"

        def corregir(self, texto):
            return "corregido"

        def disponible(self):
            return True, ""

    monkeypatch.setattr(prov_mod, "seleccion_nube", _espia)
    _ollama_roto(monkeypatch)

    resultado = engine.correct("hola", "ia", "roundtrip")

    assert resultado == "corregido"
    assert llamadas, "la caida no consulto a seleccion_nube"
