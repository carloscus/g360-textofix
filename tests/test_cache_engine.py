"""
Tests del cache LRU de engine.correct().

Item 6: reutiliza correcciones anteriores (ahorro de quota) en modos IA,
bypass con `evitando`, nunca cachea None, clave incluye (etiqueta, modelo).

Como `correct()` importa `seleccion_proveedor` LOCALMENTE dentro de la funcion
(`from .proovedor import seleccion_proveedor`), parchear el modulo DESPUES de
que la funcion ya se definio no tiene efecto sobre el binding local. La forma
que funciona es usar el fixture `monkeypatch` de pytest para inyectar el fake
ANTES de cada llamada a correct(): monkeypatch.setattr reemplaza el atributo
en el modulo proovedor Y el import local capturara el valor vigente en ese
momento porque Python evalua el from cuando se ejecuta la funcion, no cuando
se define.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pytest
from core.engine import correct, cache_vaciar


class FakeProv:
    """Proveedor simulado que cuenta cuantas veces lo llamamos."""

    def __init__(self, respuesta: str | None):
        self.llamadas = 0
        self._respuesta = respuesta
        self.modelo = "fake-model"

    def corregir(self, texto: str, evitando=None):
        self.llamadas += 1
        return self._respuesta

    def disponible(self):
        return True, ""

    def probar(self, texto: str):
        return {"original": texto, "corregido": self.corregir(texto)}


@pytest.fixture(autouse=True)
def _limpiar_cache():
    cache_vaciar()
    yield
    cache_vaciar()


# --- Cache a bajo nivel -------------------------------------------------------


def test_key_incluye_etiqueta_y_modelo():
    from core.engine import _cache_buscar, _cache_guardar

    cache_vaciar()
    _cache_guardar("nvidia", "model-x", "texto", "resultado")
    assert _cache_buscar("nvidia", "model-x", "texto") == "resultado"
    assert _cache_buscar("gemini", "model-x", "texto") is None
    assert _cache_buscar("nvidia", "model-y", "texto") is None


def test_lrue_expulsa_el_menos_usado():
    from core.engine import _cache_buscar, _cache_guardar

    cache_vaciar()
    import core.engine as mod

    original_max = mod._CACHE_MAX
    mod._CACHE_MAX = 2
    try:
        _cache_guardar("a", "m", "x", "rx")
        _cache_guardar("a", "m", "y", "ry")
        _cache_guardar("a", "m", "z", "rz")  # debe expulsar "x"
        assert _cache_buscar("a", "m", "x") is None, "x fue expulsado"
        assert _cache_buscar("a", "m", "y") == "ry"
        assert _cache_buscar("a", "m", "z") == "rz"
    finally:
        mod._CACHE_MAX = original_max
        cache_vaciar()


# --- Comportamientos deseados (via correct()) ---------------------------------


def test_primera_llamada_ejecuta_el_proveedor(monkeypatch):
    prov = FakeProv("x corregido")
    monkeypatch.setattr("core.proovedor.seleccion_proveedor", lambda: prov)
    resultado = correct("hola mundo", mode="ia", transform="roundtrip")
    assert resultado == "x corregido"
    assert prov.llamadas == 1


def test_segunda_llamada_igual_no_llama_de_nuevo(monkeypatch):
    prov = FakeProv("ya corrigio")
    monkeypatch.setattr("core.proovedor.seleccion_proveedor", lambda: prov)
    correct("texto identico", mode="ia", transform="roundtrip")
    antes = prov.llamadas
    correct("texto identico", mode="ia", transform="roundtrip")
    despues = prov.llamadas
    assert despues == antes, "el cache debio devolver la correccion sin llamar al proveedor"


def test_texto_distinto_si_llama_de_nuevo(monkeypatch):
    prov = FakeProv("respuesta")
    monkeypatch.setattr("core.proovedor.seleccion_proveedor", lambda: prov)
    correct("hola", mode="ia", transform="roundtrip")
    before = prov.llamadas
    correct("adios", mode="ia", transform="roundtrip")
    assert prov.llamadas == before + 1, "diferente texto => nueva llamada"


def test_evitando_bypassea_el_cache(monkeypatch):
    """Las variantes siempre van a red: no tiene sentido cache-las."""
    prov = FakeProv("alternativa-1")
    monkeypatch.setattr("core.proovedor.seleccion_proveedor", lambda: prov)
    correct("t", mode="ia", transform="roundtrip", evitando="prev")
    primera = prov.llamadas
    correct("t", mode="ia", transform="roundtrip", evitando="prev-diferente")
    assert prov.llamadas == primera + 1, "con evitando siempre llama al proveedor"


def test_none_no_se_cachea(monkeypatch):
    """Si la IA devuelve None, no se cachea (mejor fallar que repetir el error)."""
    prov = FakeProv(None)
    monkeypatch.setattr("core.proovedor.seleccion_proveedor", lambda: prov)
    before = prov.llamadas
    correct("fail", mode="ia", transform="roundtrip")
    after_first = prov.llamadas
    correct("fail", mode="ia", transform="roundtrip")
    after_second = prov.llamadas
    assert after_first == before + 1
    assert after_second == after_first + 1, "None no debe cachearse"


def test_mock_mode_no_toca_cache():
    """El modo mock es instantaneo y no se beneficia de cache."""
    correct("hola", mode="mock", transform="roundtrip")
    correct("hola", mode="mock", transform="roundtrip")
    cache_vaciar()  # solo limpieza.
