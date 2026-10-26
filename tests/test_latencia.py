"""
Tests del tracker de latencia (`core.latencia`).

Cubre el historial movil, el promedio, la alerta de lento y el resumen
para la bandeja. El singleton `LATENCIA_TRACKER` se crea en el modulo y
no se comparte entre tests (cada test recibe una instancia nueva).
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from core.latencia import LATENCIA_TRACKER, LatencyTracker


def _nuevo_tracker() -> LatencyTracker:
    """Un tracker sin datos previos para pruebas aisladas."""
    return LatencyTracker(window=3)


# --- Registro y promedio -----------------------------------------------------


def test_sin_datos_promedio_es_none():
    t = _nuevo_tracker()
    assert t.promedio("nvidia") is None
    assert t.promedio("gemini") is None


def test_el_primer_registro_da_ese_valor():
    t = _nuevo_tracker()
    t.registrar("nvidia", 1.5)
    assert t.promedio("nvidia") == 1.5
    assert t.promedio("gemini") is None


def test_el_promedio_acumula_multiples_registros():
    t = _nuevo_tracker()
    t.registrar("nvidia", 1.0)
    t.registrar("nvidia", 3.0)
    t.registrar("nvidia", 2.0)
    assert t.promedio("nvidia") == 2.0


def test_el_historial_rolling_window_recorta():
    """Con window=3, el cuarto valor descarta al primero."""
    t = _nuevo_tracker()
    t.registrar("nvidia", 1.0)
    t.registrar("nvidia", 2.0)
    t.registrar("nvidia", 3.0)
    t.registrar("nvidia", 4.0)  # descarta el 1.0

    # promedio de [2.0, 3.0, 4.0] = 3.0
    assert t.promedio("nvidia") == 3.0


def test_cada_proveedor_tiene_historial_separado():
    t = _nuevo_tracker()
    t.registrar("nvidia", 1.0)
    t.registrar("gemini", 5.0)

    assert t.promedio("nvidia") == 1.0
    assert t.promedio("gemini") == 5.0


# --- es_lento ----------------------------------------------------------------


def test_no_es_lento_por_defecto():
    t = _nuevo_tracker()
    assert not t.es_lento("nvidia")


def test_no_es_lento_si_promedio_bajo():
    t = _nuevo_tracker()
    t.registrar("nvidia", 1.0)
    t.registrar("nvidia", 2.0)
    assert not t.es_lento("nvidia")


def test_es_lento_cuando_promedio_supera_umbral():
    t = _nuevo_tracker()
    # UMBRAL_LENTO_S = 8.0
    t.registrar("nvidia", 9.0)
    t.registrar("nvidia", 10.0)
    assert t.es_lento("nvidia")


def test_no_es_lento_con_promedio_en_el_limite():
    t = _nuevo_tracker()
    t.registrar("nvidia", 7.0)
    t.registrar("nvidia", 8.0)
    assert not t.es_lento("nvidia")  # 7.5 < 8.0


# --- ultimo_provedor ----------------------------------------------------------


def test_sin_datos_ultimo_es_none():
    assert _nuevo_tracker().ultimo_provedor() is None


def test_ultimo_provedor_es_el_con_mas_registros():
    t = _nuevo_tracker()
    t.registrar("nvidia", 1.0)
    t.registrar("gemini", 2.0)
    t.registrar("gemini", 3.0)
    # gemini tiene 2, nvidia tiene 1
    assert t.ultimo_provedor() == "gemini"

    t.registrar("nvidia", 1.5)
    assert t.ultimo_provedor() == "nvidia"  # ahora empate 2-2, cualquiera vale


# --- resumen para bandeja ----------------------------------------------------


def test_resumen_sin_datos_vacio():
    t = _nuevo_tracker()
    assert t.resumen("nvidia") == ""


def test_resumen_muestra_promedio():
    t = _nuevo_tracker()
    t.registrar("gemini", 3.4)
    assert t.resumen("gemini") == "gemini 3.4s"


def test_resumen_muestra_alerta_de_lento():
    t = _nuevo_tracker()
    t.registrar("nvidia", 9.0)
    assert t.resumen("nvidia") == "nvidia 9.0s (lent@)"


def test_resumen_no_muestra_alerta_si_no_es_lento():
    t = _nuevo_tracker()
    t.registrar("nvidia", 1.2)
    assert t.resumen("nvidia") == "nvidia 1.2s"


# --- Singleton (no se comparten datos entre tests) --------------------------


def test_singleton_existe_y_es_instancia():
    assert isinstance(LATENCIA_TRACKER, LatencyTracker)
