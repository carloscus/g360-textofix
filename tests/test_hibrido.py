"""
Tests del flujo hibrido local -> nube.

Cuando el proveedor local (Ollama) es rechazado por las guardas, el
corrector reintenta por la nube en el mismo pedido. Si la nube tampoco
confía, se deja el original.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import core.proovedor as prov_mod
from core import engine
from core.engine import _reintentar_por_nube, _usaba_local


def test_modo_ia_marca_local_si_es_ollama(monkeypatch):
    """Si el proovedor es Ollama, `_usaba_local` queda en True para el ciclo."""
    import core.proovedor as prov_mod
    from core.ollama import ProveedorOllama

    ollama = ProveedorOllama(modelo="llama3.2:3b")
    monkeypatch.setattr(prov_mod, "seleccion_proveedor", lambda: ollama)

    engine._local_en_ultimo_pedido = False
    from core.proovedor import es_ollama

    prov = prov_mod.seleccion_proveedor()
    engine._local_en_ultimo_pedido = es_ollama(prov)

    assert _usaba_local()


def test_modo_ia_no_marca_local_si_es_gemini(monkeypatch):
    """Si el proovedor es Gemini, no se reintenta: ya es la nube."""
    import core.ai
    import core.proovedor as prov_mod

    gemini = core.ai.CorrectorIA()
    monkeypatch.setattr(prov_mod, "seleccion_proveedor", lambda: gemini)

    engine._local_en_ultimo_pedido = False
    from core.proovedor import es_ollama

    prov = prov_mod.seleccion_proveedor()
    engine._local_en_ultimo_pedido = es_ollama(prov)

    assert not _usaba_local()


def _falsa_capture(texto: str):
    class _Cap:
        def __init__(self, t):
            self.text = t

    return _Cap(texto)


def _falso_adapter():
    class _Ad:
        name = "generic"

        def write(self, ctx, capture, texto):
            capture.escrito = texto

        def release(self, capture):
            pass

    return _Ad()


def test_nube_que_confia_escribe(monkeypatch):
    """La nube devuelve un texto que pasa las guardas: se escribe."""

    class _NubeOK:
        modelo = "falso"

        def corregir(self, texto):
            return "El cliente pidió tres cajas."

        def disponible(self):
            return True, ""

    monkeypatch.setattr(prov_mod, "seleccion_nube", lambda: _NubeOK())

    adapter = _falso_adapter()
    capture = _falsa_capture("El cliente pidio tres cajas")
    outcome = _reintentar_por_nube(adapter, None, None, capture, "ia", "roundtrip", None)

    assert outcome.ok
    assert outcome.reason == "escrito"
    assert capture.escrito == "El cliente pidió tres cajas."


def test_nube_que_no_confia_no_escribe(monkeypatch):
    """La nube devolvió texto que no pasa las guardas: no se pisa nada."""

    class _NubeRoto:
        modelo = "falso"

        def corregir(self, texto):
            # Acorta a la mitad: la guarda lo rechaza
            return "El cliente"

        def disponible(self):
            return True, ""

    monkeypatch.setattr(prov_mod, "seleccion_nube", lambda: _NubeRoto())

    adapter = _falso_adapter()
    capture = _falsa_capture("El cliente pidio tres cajas de combustible")
    outcome = _reintentar_por_nube(adapter, None, None, capture, "ia", "roundtrip", None)

    assert not outcome.ok
    # No escribio nada
    assert not hasattr(capture, "escrito")


def test_nube_sin_respuesta_no_escribe(monkeypatch):
    """La nube devuelve None: no se pisa nada, se deja el original."""

    class _NubeNada:
        modelo = "falso"

        def corregir(self, texto):
            return None

        def disponible(self):
            return True, ""

    monkeypatch.setattr(prov_mod, "seleccion_nube", lambda: _NubeNada())

    adapter = _falso_adapter()
    capture = _falsa_capture("hola mundo con error")
    outcome = _reintentar_por_nube(adapter, None, None, capture, "ia", "roundtrip", None)

    assert not outcome.ok
    assert outcome.reason == "sin-respuesta-nube"
    assert not hasattr(capture, "escrito")
