"""
Tests de la verificacion de API (`core.ping`).

El ping hace UNA llamada real por proveedor, pero estos tests nunca tocan
la red: se simula el proveedor con fakes, igual que el resto de la suite.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from core import ping


class _SinClave:
    def disponible(self):
        return False, "falta la clave de NVIDIA NIM"

    def corregir(self, texto):
        raise AssertionError("no deberia llamar sin clave")


class _Ok:
    def disponible(self):
        return True, ""

    def corregir(self, texto):
        return "hola."


class _Rota:
    def __init__(self, exc: Exception):
        self._exc = exc

    def disponible(self):
        return True, ""

    def corregir(self, texto):
        raise self._exc


class _SinTexto:
    def disponible(self):
        return True, ""

    def corregir(self, texto):
        return None


def test_sin_clave_no_llama_a_la_api():
    r = ping._verificar("nvidia", _SinClave())

    assert not r["ok"]
    assert r["detalle"] == "falta la clave de NVIDIA NIM"
    assert r["segundos"] == 0.0


def test_clave_ok():
    r = ping._verificar("gemini", _Ok())

    assert r["ok"]
    assert r["detalle"] == "clave y modelo OK"
    assert r["segundos"] >= 0.0


def test_401_se_traduce_como_clave_mala():
    r = ping._verificar("gemini", _Rota(RuntimeError("401 API_KEY_INVALID")))

    assert not r["ok"]
    assert "clave rechazada (401)" in r["detalle"]


def test_404_se_traduce_como_modelo_malo():
    r = ping._verificar("nvidia", _Rota(RuntimeError("404 NOT_FOUND model")))

    assert not r["ok"]
    assert "GEMINI_MODEL / NIM_MODEL" in r["detalle"]


def test_429_se_traduce_como_cuota():
    r = ping._verificar("gemini", _Rota(RuntimeError("429 RESOURCE_EXHAUSTED")))

    assert not r["ok"]
    assert "cuota agotada (429)" in r["detalle"]
    # La clave sirve: eso lo distingue de un 401.
    assert "la clave sirve" in r["detalle"]


def test_error_desconocico_no_se_traga():
    r = ping._verificar("nvidia", _Rota(ValueError("boom")))

    assert not r["ok"]
    assert "ValueError" in r["detalle"]
    assert "boom" in r["detalle"]


def test_respuesta_sin_texto_no_es_ok():
    r = ping._verificar("gemini", _SinTexto())

    assert not r["ok"]
    assert "sin texto" in r["detalle"]


def test_probar_todo_prueba_las_dos_nubes(monkeypatch):
    llamado = []

    monkeypatch.setattr(ping, "probar_nvidia", lambda: llamado.append("nvidia") or {"ok": True})
    monkeypatch.setattr(ping, "probar_gemini", lambda: llamado.append("gemini") or {"ok": False})

    resultados = ping.probar_todo()

    assert llamado == ["nvidia", "gemini"]
    assert len(resultados) == 2


def test_linea_y_sin_clave():
    buena = {"ok": True, "etiqueta": "nvidia", "detalle": "clave y modelo OK", "segundos": 1.25}
    assert "[OK" in ping.linea(buena)
    assert not ping.sin_clave(buena)

    sin = {
        "ok": False,
        "etiqueta": "gemini",
        "detalle": "falta la clave de Gemini",
        "segundos": 0.0,
    }
    assert ping.sin_clave(sin)


def test_imprimir_distingue_falta_de_clave_de_error(capsys):
    ping.imprimir(
        {"ok": False, "etiqueta": "gemini", "detalle": "falta la clave de Gemini", "segundos": 0.0}
    )
    assert "SIN CLAVE" in capsys.readouterr().out

    ping.imprimir(
        {"ok": False, "etiqueta": "gemini", "detalle": "clave rechazada (401)", "segundos": 0.4}
    )
    assert "FALLO" in capsys.readouterr().out


# --- Los detalles que solo se ven con la API real ----------------------------


def test_ping_de_cuota_no_espera():
    """reintentos=0: el 429 se reporta de una, sin dormir 120s como el corrector."""
    import time

    from core.ai import CorrectorIA, CuotaAgotada

    class _Modelos:
        def generate_content(self, **kwargs):
            raise RuntimeError("429 RESOURCE_EXHAUSTED")

    class _Cliente:
        models = _Modelos()

    prov = CorrectorIA(api_key="k", reintentos=0)
    inicio = time.monotonic()
    with pytest.raises(CuotaAgotada):
        prov._pedir(_Cliente(), None, "hola")
    assert time.monotonic() - inicio < 1.0, "el ping no puede dormirse"


def test_corrector_con_reintentos_sigue_siendo_el_default():
    """El corrector normal conserva sus 2 reintentos: solo el ping se apura."""
    from core.ai import CorrectorIA

    assert CorrectorIA(api_key="k").reintentos == 2
    assert CorrectorIA(api_key="k", reintentos=0).reintentos == 0


def test_diagnostico_mira_la_causa_envuelta_de_nim():
    """NIM envuelve el 401 real en un NIMCorrupta generico: hay que mirar la causa."""
    from core.nvidia import NIMCorrupta

    envuelta = NIMCorrupta("ningun modelo de NIM respondio (2 probados)")
    envuelta.__cause__ = RuntimeError("Client error '401 Unauthorized' for url")

    assert "clave rechazada (401)" in ping._diagnostico(envuelta)


def test_diagnostico_reconoce_cuota_por_el_mensaje_propio():
    """CuotaAgotada no trae el 429 en el texto, pero si la palabra 'cuota'."""
    from core.ai import CuotaAgotada

    mensaje = "Se agoto la cuota GRATUITA de Gemini (5 peticiones por minuto)."

    assert "la clave sirve" in ping._diagnostico(CuotaAgotada(mensaje))


def test_nim_401_corta_la_cadena_sin_gastar_el_respaldo():
    """Clave mala: el modelo de respaldo usa la misma, no se llama al segundo."""
    httpx = pytest.importorskip("httpx")
    from core.nvidia import NIMCorrupta, ProveedorNIM

    llamadas: list[str] = []

    class _HttpxFalso:
        TimeoutException = httpx.TimeoutException
        HTTPStatusError = httpx.HTTPStatusError

        @staticmethod
        def post(url, **kwargs):
            llamadas.append(url)
            req = httpx.Request("POST", url)
            raise httpx.HTTPStatusError(
                "401", request=req, response=httpx.Response(401, request=req)
            )

    prov = ProveedorNIM(api_key="mala", timeout_s=1)
    with pytest.raises(NIMCorrupta):
        prov._pedir(_HttpxFalso, "system", "hola")

    assert len(llamadas) == 1
