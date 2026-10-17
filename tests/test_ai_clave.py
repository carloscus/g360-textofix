"""
Tests del orden en que `CorrectorIA` busca la clave.

El orden es la parte importante: el almacén cifrado de Windows manda sobre
`.env`. Si alguien cambió la clave desde la bandeja, un `.env` olvidado al
lado no puede seguir mandando.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from core.ai import CorrectorIA

CLAVE_ALMACEN = "clave-del-almacen-cifrado"
CLAVE_ENTORNO = "clave-del-entorno"


@pytest.fixture
def perfil_vacio(tmp_path, monkeypatch) -> None:
    """El almacén cifrado no tiene nada, y el entorno tampoco."""
    from core import perfil

    monkeypatch.setattr(perfil, "DIR_PERFIL", tmp_path)
    monkeypatch.setattr(perfil, "ARCHIVO_CONFIG", tmp_path / "config.json")
    monkeypatch.setattr(perfil, "ARCHIVO_CLAVE", tmp_path / "clave.dat")
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)


def _almacen_con(monkeypatch, clave: str | None) -> None:
    """Finge el almacén cifrado sin tocar DPAPI de verdad."""
    monkeypatch.setattr("core.ai._clave_almacenada", lambda: clave)


def _revienta_lectura(monkeypatch) -> None:
    """
    Hace que la lectura del almacén reviente de verdad.

    Se patea `perfil.leer_clave_api` y no `ai._clave_almacenada`: la guarda que
    tolera el fallo vive dentro de `_clave_almacenada`, así que reemplazarla
    desaparecería justo lo que se quiere probar.
    """

    def _revienta():
        raise OSError("perfil ilegible")

    monkeypatch.setattr("core.perfil.leer_clave_api", _revienta)


# --- Orden de búsqueda -------------------------------------------------------


def test_sin_nada_no_esta_disponible(perfil_vacio):
    listo, motivo = CorrectorIA().disponible()
    assert not listo
    assert "clave" in motivo


def test_la_clave_del_entorno_sirve(perfil_vacio, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", CLAVE_ENTORNO)
    _almacen_con(monkeypatch, None)

    assert CorrectorIA().api_key == CLAVE_ENTORNO


def test_el_almacen_manda_sobre_el_entorno(perfil_vacio, monkeypatch):
    """Un .env olvidado no debe pisar lo que el usuario guardó en la bandeja."""
    monkeypatch.setenv("GEMINI_API_KEY", CLAVE_ENTORNO)
    _almacen_con(monkeypatch, CLAVE_ALMACEN)

    assert CorrectorIA().api_key == CLAVE_ALMACEN


def test_la_clave_dada_explicitamente_manda_sobre_todo(perfil_vacio, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", CLAVE_ENTORNO)
    _almacen_con(monkeypatch, CLAVE_ALMACEN)

    assert CorrectorIA(api_key="explicita").api_key == "explicita"


def test_un_almacen_ilegible_no_tumba_el_corrector(perfil_vacio, monkeypatch):
    """Si el perfil no se puede leer, se sigue buscando en el entorno."""
    monkeypatch.setenv("GEMINI_API_KEY", CLAVE_ENTORNO)
    _revienta_lectura(monkeypatch)

    assert CorrectorIA().api_key == CLAVE_ENTORNO


def test_un_almacen_ilegible_sin_entorno_no_esta_disponible(perfil_vacio, monkeypatch):
    _revienta_lectura(monkeypatch)

    listo, motivo = CorrectorIA().disponible()
    assert not listo
    assert "clave" in motivo


# --- La clave jamas llega al log ---------------------------------------------


def test_repr_de_corrector_no_filtra_la_clave():
    """Un repr que muestre la clave termina en un log por descuido."""
    c = CorrectorIA(api_key="AIza-super-secreta")

    assert "AIza-super-secreta" not in repr(c)
    assert "AIza-super-secreta" not in str(c)
