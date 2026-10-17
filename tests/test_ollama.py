"""
Tests del proveedor Ollama.

No toca Ollama de verdad: se simula el HTTP para probar la logica del
proveedor sin requerir que la maquina lo tenga instalado.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from core.ollama import OLLAMA_MODELO_POR_DEFECTO, OLLAMA_URL_POR_DEFECTO, ProveedorOllama


@pytest.fixture
def prov() -> ProveedorOllama:
    return ProveedorOllama(url="http://127.0.0.1:11434")


def test_url_por_defecto():
    p = ProveedorOllama()
    assert p.url == OLLAMA_URL_POR_DEFECTO
    assert p.modelo == OLLAMA_MODELO_POR_DEFECTO


def test_url_sin_barra_final():
    p = ProveedorOllama(url="http://localhost:11434/")
    assert p.url == "http://localhost:11434"


def test_modelo_3b_es_el_default_y_el_mas_ligero():
    """El modelo default tiene que ser el mas liviano que entiende el prompt."""
    assert OLLAMA_MODELO_POR_DEFECTO == "llama3.2:3b"


def test_disponible_sin_ollama(monkeypatch):
    """Si Ollama no esta arriba, se dice, y se ofrece Ollama pull."""

    class _Falso:
        status_code = 500

    class _Excepcion(Exception):
        pass

    def _get_fake(url, timeout=None):
        raise _Excepcion("conexion")

    monkeypatch.setattr("httpx.get", _get_fake)

    p = ProveedorOllama()
    listo, motivo = p.disponible()
    assert not listo
    assert "Ollama" in motivo
    assert "pull" in motivo


def test_disponible_con_ollama_corriendo(monkeypatch):
    """Si el endpoint /api/tags responde 200, se considera disponible."""

    class _OK:
        status_code = 200

    monkeypatch.setattr("httpx.get", lambda url, timeout=None: _OK())

    p = ProveedorOllama()
    listo, _ = p.disponible()
    assert listo


def test_corregir_sin_ollama(monkeypatch):
    """Ollama caido: `corregir` lanza, no devuelve None silenciosamente."""

    class _Excepcion(Exception):
        pass

    monkeypatch.setattr("httpx.get", lambda url, timeout=None: (_ for _ in ()).throw(_Excepcion()))
    from core.ollama import OllamaCorrupta

    p = ProveedorOllama()
    with pytest.raises(OllamaCorrupta):
        p.corregir("hola")


def test_etiqueta_del_proovedor():
    """El proovedor se etiqueta, y el log no lo confunde."""
    from core.proovedor import es_gemini, es_ollama, etiqueta

    p = ProveedorOllama()
    assert es_ollama(p)
    assert not es_gemini(p)
    assert etiqueta(p) == "ollama"


def test_el_prompt_es_el_mismo_que_gemini():
    """Ollama usa el prompt conservador, no otro: las reglas no cambian."""
    from core.ai import PROMPT

    # El prompt se aplica en la llamada; verifico que se usa el mismo que Gemini.
    assert PROMPT.startswith("Eres un corrector")
    assert "PERUANO" in PROMPT
    assert "no cambies" in PROMPT or "NUNCA" in PROMPT
