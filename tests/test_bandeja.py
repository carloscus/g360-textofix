"""
Tests de la bandeja.

Solo la parte comprobable sin abrir ventanas: la construccion del menu y la
logica de eleccion de accion. El icono real se prueba a mano, porque un test
que abre bandeja deja iconos huérfanos en el escritorio del que lo ejecuta.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from core.bandeja import _elegir

ORDEN = ["corregir", "deshacer", "rehacer"]


def test_elegir_acepta_numero():
    assert _elegir(ORDEN, "2") == "deshacer"


def test_elegir_acepta_nombre_con_espacios_y_minusculas():
    assert _elegir(ORDEN, " DESHACER ") == "deshacer"


def test_elegir_numero_fuera_de_rango_devuelve_nada():
    assert _elegir(ORDEN, "0") is None
    assert _elegir(ORDEN, "4") is None
    assert _elegir(ORDEN, "99") is None


def test_elegir_texto_inexistente_devuelve_nada():
    assert _elegir(ORDEN, "xyz") is None
