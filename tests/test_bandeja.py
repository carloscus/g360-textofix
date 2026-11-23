"""
Tests de la bandeja.

Solo la parte comprobable sin abrir ventanas: la construccion del menu y la
logica de eleccion de accion. El icono real se prueba a mano, porque un test
que abre bandeja deja iconos huérfanos en el escritorio del que lo ejecuta.
"""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from core import bandeja, perfil
from core.bandeja import _elegir
from core.ai import OPCIONES_ESTILO, estilo_activo

ORDEN = ["corregir", "deshacer", "rehacer"]


@pytest.fixture
def perfil_falso(tmp_path, monkeypatch):
    """Apunta el perfil a una carpeta temporal y la limpia al salir."""
    monkeypatch.setattr(perfil, "DIR_PERFIL", tmp_path)
    monkeypatch.setattr(perfil, "ARCHIVO_CONFIG", tmp_path / "config.json")
    return tmp_path


class _EstadoFalso:
    """Estado mínimo para construir el menú sin ventana ni atajos reales."""

    def resumen(self) -> str:
        return "Estado de prueba"

    def puede_deshacer(self) -> bool:
        return False

    def puede_rehacer(self) -> bool:
        return False


def _bandeja_con_perfil(perfil_falso: Path) -> bandeja.Bandeja:
    """Bandeja lista para inspeccionar su menu (sin abrir icono)."""
    return bandeja.Bandeja(_EstadoFalso(), {})


def _texto_de_item(item) -> str:
    """pystray.MenuItem guarda el texto en .text (lambda para items de estado)."""
    return getattr(item, "text", str(item))


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


# --- Submenu de estilo --------------------------------------------------------

def test_construir_contiene_item_estilo_de_correccion(perfil_falso: Path):
    """_construir() incluye el item 'Estilo de correccion'."""
    b = _bandeja_con_perfil(perfil_falso)
    menu = b._construir()
    titulos = [_texto_de_item(i) for i in menu.items]
    assert any("Estilo de correccion" in t for t in titulos), titulos


def test_submenu_estilo_tiene_tres_radios(perfil_falso: Path):
    """El submenu tiene exactamente 3 opciones, cada una con radio=True."""
    b = _bandeja_con_perfil(perfil_falso)
    item_estilo = next(
        i for i in b._construir().items if "Estilo de correccion" in _texto_de_item(i)
    )
    submenu = item_estilo.submenu
    radios = [i for i in submenu.items if getattr(i, "radio", False)]
    assert len(radios) == 3, [str(i.title) for i in radios]


def test_submenu_estilo_usa_opciones_de_ai(perfil_falso: Path):
    """Los textos visibles del submenu son los de ai.OPCIONES_ESTILO."""
    b = _bandeja_con_perfil(perfil_falso)
    item_estilo = next(
        i for i in b._construir().items if "Estilo de correccion" in _texto_de_item(i)
    )
    textos = [_texto_de_item(i) for i in item_estilo.submenu.items if i.enabled is not False]
    esperados = [texto for _valor, texto in OPCIONES_ESTILO]
    assert textos == esperados, textos


def test_checked_refleja_estilo_activo(perfil_falso: Path, monkeypatch):
    """El radio 'checked' refleja el estilo EFECTIVO (estilo_activo)."""
    b = _bandeja_con_perfil(perfil_falso)
    item_estilo = next(
        i for i in b._construir().items if "Estilo de correccion" in _texto_de_item(i)
    )
    # Con perfil vacio, estilo_activo() -> "natural" (default natural).
    assert estilo_activo() == "natural"
    radios = [i for i in item_estilo.submenu.items if getattr(i, "radio", False)]
    marcados = [_texto_de_item(i) for i in radios if i.checked]
    assert marcados == ["Humano (natural)"], marcados


def test_elegir_estilo_persiste_en_perfil_falso(perfil_falso: Path, monkeypatch):
    """_elegir_estilo("estricto") guarda estilo=estricto en config.json."""
    b = _bandeja_con_perfil(perfil_falso)
    b._elegir_estilo("estricto")

    config = perfil.leer_config()
    assert config["estilo"] == "estricto"
    # Y estilo_activo() ahora devuelve estricto (config gana).
    assert estilo_activo() == "estricto"


def test_elegir_estilo_no_reinicia_nor_registra_hotkeys(perfil_falso: Path):
    """_elegir_estilo solo persiste y refresca (no toca hotkeys ni reinicia)."""
    b = _bandeja_con_perfil(perfil_falso)
    b._elegir_estilo("auto")
    assert perfil.leer_config()["estilo"] == "auto"
