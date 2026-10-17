"""
Tests del búfer de deshacer/rehacer.

Es logica pura, sin Windows: se prueban los casos que en la vida real estan
documentados, en particular los dos que importan.

- No se puede deshacer en una aplicacion que no es donde se corrigio.
- Si el usuario edito el texto despues, deshacer deja de aplicar.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from core.estado import MOTIVOS, Correccion, Estado

ORIGINAL = "El cliente pidio tres cajas"
CORREGIDO = "El cliente pidió tres cajas."


@pytest.fixture
def estado() -> Estado:
    e = Estado(activo=True, modo="ia")
    e.registrar_correccion(
        Correccion(proceso="notepad.exe", original=ORIGINAL, corregido=CORREGIDO)
    )
    return e


# --- Consulta ----------------------------------------------------------------


def test_fresco_no_tiene_nada_que_deshacer():
    e = Estado()
    assert not e.puede_deshacer()
    assert not e.puede_rehacer()
    texto, motivo = e.preparar_deshacer("notepad.exe")
    assert texto is None
    assert motivo == MOTIVOS["nunca-corregido"]


def test_tras_corregir_se_puede_deshacer(estado: Estado):
    assert estado.puede_deshacer()
    assert not estado.puede_rehacer()


# --- Ciclos basicos ----------------------------------------------------------


def test_deshacer_devuelve_el_original(estado: Estado):
    texto, motivo = estado.preparar_deshacer("notepad.exe")
    assert texto == ORIGINAL
    assert motivo == MOTIVOS["ok"]
    assert not estado.puede_deshacer()
    assert estado.puede_rehacer()


def test_rehacer_vuelve_al_corregido(estado: Estado):
    estado.preparar_deshacer("notepad.exe")
    texto, _ = estado.preparar_rehacer("notepad.exe")
    assert texto == CORREGIDO
    assert estado.puede_deshacer()


def test_dos_veces_deshacer_solo_deshace_una_vez(estado: Estado):
    estado.preparar_deshacer("notepad.exe")
    texto, motivo = estado.preparar_deshacer("notepad.exe")
    assert texto is None
    assert motivo == MOTIVOS["nada-que-deshacer"]


def test_rehacer_sin_deshacer_no_hace_nada(estado: Estado):
    texto, motivo = estado.preparar_rehacer("notepad.exe")
    assert texto is None
    assert motivo == MOTIVOS["nada-que-rehacer"]


# --- Seguridad ---------------------------------------------------------------


def test_no_deshacer_en_otra_aplicacion(estado: Estado):
    texto, motivo = estado.preparar_deshacer("excel.exe")
    assert texto is None
    assert motivo == MOTIVOS["app-cambiada"]


def test_tras_no_deshacer_en_otra_app_sigue_pudiendo(estado: Estado):
    estado.preparar_deshacer("excel.exe")
    texto, _ = estado.preparar_deshacer("notepad.exe")
    assert texto == ORIGINAL


def test_si_el_usuario_edita_se_invalida(estado: Estado):
    estado.comprobar_cambio("el usuario escribio otra cosa")
    texto, motivo = estado.preparar_deshacer("notepad.exe")
    assert texto is None
    assert motivo == MOTIVOS["nunca-corregido"]


def test_si_el_texto_sigue_igual_no_se_invalida(estado: Estado):
    estado.comprobar_cambio(CORREGIDO)
    texto, _ = estado.preparar_deshacer("notepad.exe")
    assert texto == ORIGINAL


def test_tras_deshacer_el_texto_es_el_original(estado: Estado):
    estado.preparar_deshacer("notepad.exe")
    # El usuario no toco nada: el texto en pantalla es el original.
    estado.comprobar_cambio(ORIGINAL)
    texto, _ = estado.preparar_rehacer("notepad.exe")
    assert texto == CORREGIDO


def test_si_la_escritura_falla_se_revierte_el_estado(estado: Estado):
    """Si no se pudo escribir, el búfer no debe creer que si."""
    estado.preparar_deshacer("notepad.exe")
    estado.revertir_preparacion()
    # Como no se escribio nada, se puede volver a deshacer.
    texto, motivo = estado.preparar_deshacer("notepad.exe")
    assert texto == ORIGINAL
    assert motivo == MOTIVOS["ok"]


# --- Vista para la bandeja ---------------------------------------------------


def test_resumen_muestra_el_estado():
    assert "Demo" in Estado(modo="mock").resumen()
    assert "IA" in Estado(modo="ia").resumen()
    assert Estado(activo=False).resumen() == "Inactivo"
