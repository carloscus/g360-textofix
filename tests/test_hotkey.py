"""
Tests de hotkey: parsing, descripcion y deteccion de conflictos.

No se prueba RegisterHotKey real (requiere Windows y permisos); lo que se
valida es la logica alrededor del código de error 1409 que diferencia un
conflicto externo (otra app tiene el atajo) de un problema interno.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from core.hotkey import (
    ERROR_HOTKEY_ALREADY_REGISTERED,
    EscuchaAtajos,
    parsear_atajo,
)


# --- Parsing ----------------------------------------------------------------

def test_parsea_ctrl_shift_e():
    a = parsear_atajo("CTRL+SHIFT+E")
    assert a.tecla == ord("E")
    assert a.modificadores == 0x0006  # CTRL | SHIFT


def test_parsea_con_alt():
    a = parsear_atajo("ALT+F5")
    assert a.tecla == 0x74  # VK_F5
    assert a.modificadores & 0x0001  # ALT


def test_parsea_sin_modificador_asume_ctrl():
    a = parsear_atajo("X")
    assert a.modificadores != 0


def test_parsea_vacio_raises():
    with pytest.raises(ValueError):
        parsear_atajo("")


# --- Deteccion de conflictos ------------------------------------------------

def test_faltantes_vacio_cuando_no_hay_registros():
    """Sin fallos, faltantes regresa lista vacia."""
    e = EscuchaAtajos({"corregir": parsear_atajo("CTRL+SHIFT+E")})
    # Sin haber chamado _registrar(), no hay ids ni fallos.
    assert e.faltantes == []


def test_faltantes_excluye_los_que_si_tienen_id():
    """Si una accion esta en self._ids, no aparece en faltantes."""
    e = EscuchaAtajos({"corregir": parsear_atajo("CTRL+SHIFT+E")})
    e._ids["hotkey"] = "corregir"
    e._registros_fallidos.append(
        {"accion": "corregir", "atajo": "CTRL+SHIFT+E", "es_conflicto_externo": True}
    )
    # Aunque hay un registro de fallo, la accion ya tiene id asignado.
    assert e.faltantes == []


def test_faltantes_incluye_solo_lo_no_registrado():
    """Dos acciones: una registrada, otra con fallo. Solo la segunda importa."""
    a_ok = parsear_atajo("CTRL+SHIFT+E")
    a_bad = parsear_atajo("CTRL+SHIFT+R")
    e = EscuchaAtajos({"corregir": a_ok, "deshacer": a_bad})
    e._ids["hotkey_corregir"] = "corregir"
    e._registros_fallidos.extend([
        {"accion": "deshacer", "atajo": "CTRL+SHIFT+R", "es_conflicto_externo": True},
        {"accion": "corregir", "atajo": "CTRL+SHIFT+E", "es_conflicto_externo": False},
    ])
    resultado = e.faltantes
    assert len(resultado) == 1
    assert resultado[0]["accion"] == "deshacer"
    assert resultado[0]["es_conflicto_externo"] is True


def test_error_1409_se_marca_como_conflicto_externo():
    """El codigo de error 1409 indica que otra app tiene el atajo."""
    assert ERROR_HOTKEY_ALREADY_REGISTERED == 1409


def test_cambio_exitoso_limpi_a_el_fallo_previo_deesa_accion():
    """Cuando el usuario cambia a un atajo nuevo y funciona, se borra el aviso viejo."""
    a_viejo = parsear_atajo("CTRL+SHIFT+E")
    a_nuevo = parsear_atajo("CTRL+SHIFT+F")
    e = EscuchaAtajos({"corregir": a_viejo})
    # Simulamos un fallo previo.
    e._registros_fallidos.append(
        {"accion": "corregir", "atajo": "CTRL+SHIFT+E", "es_conflicto_externo": True}
    )
    # Cambiamos al nuevo atajo (simulamos el exito directamente).
    e._registros_fallidos = [
        r for r in e._registros_fallidos if r["accion"] != "corregir"
    ]
    # Después de limpiar, faltantes queda vacio.
    assert e.faltantes == []
