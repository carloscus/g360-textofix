"""Tests honestos de la etiqueta visible OpenRouter (Nemotron).

La clave interna sigue siendo "nvidia": solo cambia lo que se muestra al
usuario cuando NIM_URL apunta al proxy local.
"""

from __future__ import annotations

from core import estado
from core.latencia import LATENCIA_TRACKER
from core import ping
from core.proovedor import etiqueta_visible


def test_etiqueta_visible_openrouter_when_nim_url_loopback(monkeypatch):
    monkeypatch.setenv(
        "NIM_URL", "http://127.0.0.1:8002/v1/chat/completions"
    )
    assert etiqueta_visible("nvidia") == "OpenRouter (Nemotron)"


def test_etiqueta_visible_sin_nim_url(monkeypatch):
    monkeypatch.delenv("NIM_URL", raising=False)
    assert etiqueta_visible("nvidia") == "nvidia"


def test_etiqueta_visible_url_real_de_nvidia(monkeypatch):
    monkeypatch.setenv("NIM_URL", "https://integrate.api.nvidia.com/v1/chat/completions")
    assert etiqueta_visible("nvidia") == "nvidia"


def test_resumen_con_historial_muestra_openrouter_y_promedio_ok(monkeypatch):
    monkeypatch.setenv(
        "NIM_URL", "http://127.0.0.1:8002/v1/chat/completions"
    )
    LATENCIA_TRACKER._historial.clear()
    LATENCIA_TRACKER.registrar("nvidia", 1.2)
    e = estado.Estado(activo=True, modo="ia")
    try:
        resumen = e.resumen()
    finally:
        LATENCIA_TRACKER._historial.clear()
    assert "OpenRouter (Nemotron)" in resumen
    assert "1,2s" in resumen or "1.2s" in resumen


def test_resumen_sin_historial_terminan_en_guion(monkeypatch):
    monkeypatch.delenv("NIM_URL", raising=False)
    LATENCIA_TRACKER._historial.clear()
    e = estado.Estado(activo=True, modo="ia")
    resumen = e.resumen()
    assert resumen == "Activo · Modo IA · —"
    assert "OpenRouter" not in resumen


def test_linea_ping_muestra_openrouter_con_loopback(monkeypatch):
    monkeypatch.setenv(
        "NIM_URL", "http://127.0.0.1:8002/v1/chat/completions"
    )
    resultado = {
        "etiqueta": "nvidia",
        "ok": True,
        "detalle": "clave y modelo OK",
        "segundos": 0.9,
    }
    linea = ping.linea(resultado)
    assert "OpenRouter (Nemotron)" in linea
    assert resultado["etiqueta"] == "nvidia"


def test_texto_de_prueba_no_es_hola_y_tiene_commu():
    assert ping.TEXTO_DE_PRUEBA != "hola"
    assert "commu" in ping.TEXTO_DE_PRUEBA
