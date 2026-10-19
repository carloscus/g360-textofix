"""
Tests del fallback nube -> nube.

Si el proveedor elegido (NVIDIA o Gemini) revienta al corregir (red,
cuota, clave invalida), el engine reintenta UNA vez con el otro. Si no
hay otro disponible, o si el segundo tambien revienta, se propaga el
fallo: mejor fallar que inventar.

Los tests patean `seleccion_proveedor` y `otra_nube`: sin eso, con una
clave real guardada llamarian a la API de verdad (lento, y gasta la
cuota del usuario).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import core.proovedor as prov_mod
from core.ai import CuotaAgotada


class _NIMRota:
    modelo = "meta/llama-3.2-90b-vision-instruct"

    def corregir(self, texto, evitando=None):
        raise CuotaAgotada("cuota agotada")

    def disponible(self):
        return True, ""


class _GeminiOK:
    modelo = "gemini-2.5-flash-lite"

    def corregir(self, texto, evitando=None):
        return "corregido por gemini"

    def disponible(self):
        return True, ""


class _GeminiRota:
    modelo = "gemini-2.5-flash-lite"

    def corregir(self, texto, evitando=None):
        raise CuotaAgotada("cuota agotada")

    def disponible(self):
        return True, ""


class _NimOK:
    modelo = "meta/llama-3.2-90b-vision-instruct"

    def corregir(self, texto, evitando=None):
        return "corregido por nvidia"

    def disponible(self):
        return True, ""


def _patear(monkeypatch, primario, otra):
    """Patea la seleccion y el fallback para no tocar la API real."""
    monkeypatch.setattr(prov_mod, "seleccion_proveedor", lambda: primario)
    monkeypatch.setattr(prov_mod, "otra_nube", lambda _prov: otra)


def test_nvidia_falla_y_reintenta_con_gemini(monkeypatch):
    from core import engine

    _patear(monkeypatch, _NIMRota(), _GeminiOK())

    resultado = engine.correct("hola", "ia", "roundtrip")

    assert resultado == "corregido por gemini"


def test_gemini_falla_y_reintenta_con_nvidia(monkeypatch):
    from core import engine

    _patear(monkeypatch, _GeminiRota(), _NimOK())

    resultado = engine.correct("hola", "ia", "roundtrip")

    assert resultado == "corregido por nvidia"


def test_sin_otra_nube_disponible_se_propaga(monkeypatch):
    """Si no hay segundo proveedor con clave, el fallo del primero sube."""
    from core import engine

    _patear(monkeypatch, _NIMRota(), None)

    with pytest.raises(CuotaAgotada):
        engine.correct("hola", "ia", "roundtrip")


def test_si_el_fallback_tambien_revienta_se_propaga(monkeypatch):
    from core import engine

    _patear(monkeypatch, _NIMRota(), _GeminiRota())

    with pytest.raises(CuotaAgotada):
        engine.correct("hola", "ia", "roundtrip")


def test_si_el_primario_no_falla_no_se_toca_el_fallback(monkeypatch):
    """El reintento es solo para fallos: un pedido normal no lo consulta."""
    from core import engine

    llamadas = []

    def _espia(_prov):
        llamadas.append(1)
        return _NimOK()

    monkeypatch.setattr(prov_mod, "seleccion_proveedor", lambda: _GeminiOK())
    monkeypatch.setattr(prov_mod, "otra_nube", _espia)

    resultado = engine.correct("hola", "ia", "roundtrip")

    assert resultado == "corregido por gemini"
    assert not llamadas, "el fallback se consulto sin que nadie fallara"


# --- otra_nube (la logica del fallback, sin patear) ---------------------------


def test_otra_nube_de_nim_busca_gemini(monkeypatch):
    from core.nvidia import ProveedorNIM

    class _GeminiFalso:
        def disponible(self):
            return True, ""

    monkeypatch.setattr(prov_mod, "_nuevo_gemini", lambda: _GeminiFalso())

    otra = prov_mod.otra_nube(ProveedorNIM(api_key="k"))

    assert isinstance(otra, _GeminiFalso)


def test_otra_nube_de_gemini_busca_nim_si_hay_clave(monkeypatch):
    from core.ai import CorrectorIA

    class _NimFalso:
        def disponible(self):
            return True, ""

    monkeypatch.setattr(prov_mod, "_nuevo_nim", lambda: _NimFalso())

    otra = prov_mod.otra_nube(CorrectorIA(api_key="k"))

    assert isinstance(otra, _NimFalso)


def test_otra_nube_sin_clave_del_otro_devuelve_none(monkeypatch):
    from core.ai import CorrectorIA

    class _NimSinClave:
        def disponible(self):
            return False, "falta la clave"

    monkeypatch.setattr(prov_mod, "_nuevo_nim", lambda: _NimSinClave())

    assert prov_mod.otra_nube(CorrectorIA(api_key="k")) is None
