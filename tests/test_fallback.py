"""
Tests del fallback Ollama -> Gemini.

Si Ollama cae (404, timeout, modelo ausente), el corrector cae a Gemini
en el mismo pedido. Si el proovedor original es Gemini y revienta, no se
reintenta: se propaga.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import core.ai as ai_mod
from core.ai import CuotaAgotada
from core.ollama import ProveedorOllama


def _ollama_roto(monkeypatch) -> ProveedorOllama:
    """`seleccion_proveedor` devuelve Ollama que reviento al corregir."""
    import httpx

    def _corregir_roto(self, texto):
        raise httpx.HTTPStatusError(
            "404", request=httpx.Request("POST", "http://127.0.0.1:11434/api/chat")
        )

    class _Ollama(ProveedorOllama):
        def corregir(self, texto):
            _corregir_roto(self, texto)

    # Pateo la seleccion: se devuelve el roto.
    import core.proovedor as prov_mod
    monkeypatch.setattr(prov_mod, "seleccion_proveedor", lambda: _Ollama(modelo="llama3.2:3b"))
    return _Ollama(modelo="llama3.2:3b")


def _gemini_ok(monkeypatch, salida: str):
    """Patea `CorrectorIA` para que devuelva `salida` sin tocar la red."""

    class _Gemini:
        def __init__(self, modelo=None, **_):
            self.modelo = modelo

        def corregir(self, texto):
            return salida

    monkeypatch.setattr(ai_mod, "CorrectorIA", _Gemini)
    return _Gemini


def test_ollama_falla_y_cae_a_gemini(monkeypatch):
    from core import engine

    _ollama_roto(monkeypatch)
    _gemini_ok(monkeypatch, "El cliente pidi\u00f3 tres cajas.")

    resultado = engine.correct("El cliente pidio tres cajas", "ia", "roundtrip")

    assert resultado == "El cliente pidi\u00f3 tres cajas."


def test_gemini_no_se_caede_a_gemini(monkeypatch):
    """Si el proovedor original es Gemini y revienta, se propaga."""

    class _GeminiRoto:
        def __init__(self, modelo=None, **_):
            pass

        def corregir(self, texto):
            raise CuotaAgotada("cuota agotada")

    monkeypatch.setattr(ai_mod, "CorrectorIA", _GeminiRoto)

    # seleccion_proveedor devuelve Gemini (el roto)
    import core.proovedor as prov_mod
    monkeypatch.setattr(
        prov_mod, "seleccion_proveedor", lambda: ai_mod.CorrectorIA()
    )

    from core import engine

    with pytest.raises(CuotaAgotada):
        engine.correct("hola", "ia", "roundtrip")
