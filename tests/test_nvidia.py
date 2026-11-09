"""
Tests de ProveedorNIM (src/core/nvidia.py).

Cubre keep-alive del cliente httpx, temperature 0.1, max_tokens dinamico
(max/limite), el envoltorio <<<TEXTO>>> en el mensaje user, y la cadena de
respaldo cuando el principal da timeout.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pytest
import httpx


# Respuesta simulada de NIM que responde al metodo json() tal como lo espera
# el helper interno `_contenido`: busca `choices -> message -> content`.
class FakeResponse:
    status_code = 200

    def __init__(self, content: str):
        self._content = content
        # Requiere un request fake para HTTPStatusError.
        self.request = MagicMock()

    def json(self):
        return {
            "choices": [{"message": {"content": self._content}}],
        }

    def raise_for_status(self):
        pass


@pytest.fixture(autouse=True)
def _reset_cliente():
    """Resetear el cliente compartido despues de cada test para evitar
    contaminacion entre tests que usan httpx real o falso."""
    from core import nvidia

    nvidia._cliente_http = None
    yield
    nvidia._cliente_http = None


# --- Keep-alive (item 1) -----------------------------------------------------


def test_client_se_reusa_entre_llamadas(monkeypatch):
    """El cliente se crea una sola vez: dos correcciones comparten instancia."""
    from core import nvidia as nmod
    from core.nvidia import ProveedorNIM

    clientes_vistos: list = []

    class TrackingClient:
        def __init__(self):
            clientes_vistos.append(self)

        def post(self, url, headers=None, json=None, timeout=None):
            return FakeResponse("resuelta")

    # El spy debe devolver SIEMPRE la misma instancia (keep-alive).
    shared = TrackingClient()

    def spy(httpx_mod):
        return shared

    monkeypatch.setattr(nmod, "_obtener_cliente", spy)

    prov = ProveedorNIM(api_key="klave")
    prov.corregir("hola mundo")
    prov.corregir("otro texto")

    assert len(clientes_vistos) == 1, "el cliente deberia crearse UNA sola vez"


# --- Temperature y max_tokens (item 2) ---------------------------------------


def test_temperature_0_1(monkeypatch):
    """Un corrector es determinista: temperature 0.1, no 0.5."""
    from core import nvidia as nmod
    from core.nvidia import ProveedorNIM

    body_capturado: list = []

    class SpyClient:
        def post(self, url, headers=None, json=None, timeout=None):
            body_capturado.append(json)
            return FakeResponse("ok")

    monkeypatch.setattr(nmod, "_obtener_cliente", lambda httpx_mod: SpyClient())

    prov = ProveedorNIM(api_key="klave")
    prov.corregir("palabra mal escrita")

    assert len(body_capturado) >= 1
    assert body_capturado[0]["temperature"] == 0.1, "el corrector no es creativo: temperature 0.1"


def test_max_tokens_minimo_para_texto_corto(monkeypatch):
    """Para textos cortos (<~150 chars) el tope minimo debe mantenerse en 500."""
    from core import nvidia as nmod
    from core.nvidia import ProveedorNIM

    body_capturado: list = []

    class SpyClient:
        def post(self, url, headers=None, json=None, timeout=None):
            body_capturado.append(json)
            return FakeResponse("ok")

    monkeypatch.setattr(nmod, "_obtener_cliente", lambda httpx_mod: SpyClient())

    prov = ProveedorNIM(api_key="klave")
    prov.corregir("abc")  # 3 chars -> max(500, min(206, 4000)) = 500

    assert len(body_capturado) >= 1
    assert body_capturado[0]["max_tokens"] == 500, (
        "texto corto: max_tokens debe respetar el minimo de 500"
    )


def test_max_tokens_limite_superior_4000(monkeypatch):
    """Textos muy largos no deben exceder los 4000 tokens ni pasarlos al modelo."""
    from core import nvidia as nmod
    from core.nvidia import ProveedorNIM

    body_capturado: list = []

    class SpyClient:
        def post(self, url, headers=None, json=None, timeout=None):
            body_capturado.append(json)
            return FakeResponse("ok")

    monkeypatch.setattr(nmod, "_obtener_cliente", lambda httpx_mod: SpyClient())

    largo = "x " * 3000  # ~6000 chars => 6000*2+200 = 12200, capped a 4000
    prov = ProveedorNIM(api_key="klave")
    prov.corregir(largo)

    assert len(body_capturado) >= 1
    assert body_capturado[0]["max_tokens"] == 4000, (
        "texto muy largo: max_tokens no debe exceder el cap de 4000"
    )


def test_max_tokens_real_en_request(monkeypatch):
    """Verificar que el JSON enviado al modelo refleja el calculo dinamico."""
    from core import nvidia as nmod
    from core.nvidia import ProveedorNIM

    body_capturado: list = []

    class SpyClient:
        def post(self, url, headers=None, json=None, timeout=None):
            body_capturado.append(json)
            return FakeResponse("ok")

    monkeypatch.setattr(nmod, "_obtener_cliente", lambda httpx_mod: SpyClient())

    prov = ProveedorNIM(api_key="klave")
    prov.corregir("abc")  # 3 chars -> max(500, min(206, 4000)) = 500

    assert len(body_capturado) >= 1
    assert body_capturado[0]["max_tokens"] == 500


# --- Envoltorio <<<TEXTO>>> (item 5 lado NIM) ---------------------------------


def test_mensaje_user_envuelto_en_marcadores(monkeypatch):
    from core.ai import MARCA_FIN, MARCA_INICIO
    from core import nvidia as nmod
    from core.nvidia import ProveedorNIM

    mensajes_recibidos: list = []

    class SpyClient:
        def post(self, url, headers=None, json=None, timeout=None):
            mensajes_recibidos.extend(json.get("messages", []))
            return FakeResponse("x")

    monkeypatch.setattr(nmod, "_obtener_cliente", lambda httpx_mod: SpyClient())

    prov = ProveedorNIM(api_key="klave")
    prov.corregir("mi texto")

    user_msg = [m for m in mensajes_recibidos if m.get("role") == "user"]
    assert len(user_msg) >= 1, "no se encontro mensaje user"
    contenido = user_msg[0]["content"]
    assert contenido.startswith(MARCA_INICIO), f"contenido no inicia con marcadores: {contenido!r}"
    assert contenido.endswith(MARCA_FIN), f"contenido no termina con marcadores: {contenido!r}"
    assert "mi texto" in contenido


# --- Cadena de respaldo (timeout) --------------------------------------------


def test_pasaa_al_respaldo_cuando_timeout(monkeypatch):
    from core import nvidia as nmod
    from core.nvidia import MODELO_90B, ProveedorNIM

    llamadas: list = []

    class TimeoutClient:
        call_count = 0

        def post(self, url, headers=None, json=None, timeout=None):
            self.call_count += 1
            llamadas.append(json.get("model"))
            # Solo el PRIMERO falla con timeout; el segundo debe responder.
            if self.call_count == 1:
                raise httpx.TimeoutException("timed out")
            return FakeResponse("segunda respuesta")

    # El cliente se crea UNA sola vez y se reutiliza (keep-alive).
    shared = TimeoutClient()

    def spy(httpx_mod):
        return shared

    monkeypatch.setattr(nmod, "_obtener_cliente", spy)

    prov = ProveedorNIM(api_key="klave")
    resultado = prov.corregir("algo")
    assert resultado == "segunda respuesta"
    # El primer modelo falló, el segundo debió ser llamado.
    assert MODELO_90B in llamadas
    # Deben haberse hecho 2 llamadas (uno por cada modelo).
    assert len(llamadas) == 2


def test_clave_mala_no_llama_al_respaldo():
    """Clave invalida (401): corta la cadena inmediatamente."""
    from core import nvidia as nmod
    from core.nvidia import MODELO_POR_DEFECTO, NIMCorrupta, ProveedorNIM

    llamadas: list = []

    class ErrorClient:
        def post(self, url, headers=None, json=None, timeout=None):
            llamadas.append(json.get("model"))
            req = httpx.Request("POST", url)
            raise httpx.HTTPStatusError(
                "401", request=req, response=httpx.Response(401, request=req)
            )

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(nmod, "_obtener_cliente", lambda httpx_mod: ErrorClient())
    try:
        prov = ProveedorNIM(api_key="mala")
        with pytest.raises(NIMCorrupta):
            prov.corregir("algo")
        assert len(llamadas) == 1, "clave mala: no debe probar el respaldo"
        assert MODELO_POR_DEFECTO in llamadas
    finally:
        monkeypatch.undo()
