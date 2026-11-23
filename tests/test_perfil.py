"""
Tests del perfil: atajos y configuracion.

Se manipulan las rutas de la carpeta de perfil para no tocar el `%APPDATA%`
real: un test que escriba en el perfil del usuario deja basura en la maquina.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from core import perfil


@pytest.fixture
def perfil_falso(tmp_path, monkeypatch) -> Path:
    """Apunta el perfil a una carpeta temporal y la limpia al salir."""
    monkeypatch.setattr(perfil, "DIR_PERFIL", tmp_path)
    monkeypatch.setattr(perfil, "ARCHIVO_CONFIG", tmp_path / "config.json")
    return tmp_path


# --- Atajos ------------------------------------------------------------------
# Cambiar un atajo sirve de poco si se pierde al reiniciar.


def test_guardar_atajo_persiste_en_el_perfil(perfil_falso: Path):
    perfil.guardar_atajo("deshacer", "CTRL+ALT+D")

    config = perfil.leer_config()
    assert config["hotkey_deshacer"] == "CTRL+ALT+D"
    # Las otras dos no se tocan.
    assert config["hotkey_corregir"] == "CTRL+ALT+SHIFT+E"
    assert config["hotkey_rehacer"] == "CTRL+SHIFT+R"


def test_guardar_atajo_normaliza_a_mayusculas(perfil_falso: Path):
    perfil.guardar_atajo("rehacer", "ctrl+shift+r")

    assert perfil.leer_config()["hotkey_rehacer"] == "CTRL+SHIFT+R"


def test_guardar_atajo_con_accion_desconocida_no_crea_archivo(perfil_falso: Path):
    perfil.guardar_atajo("inventada", "CTRL+X")

    assert not (perfil_falso / "config.json").exists()


def test_atajos_por_defecto_estan_completos():
    """Si falta un atajo en el config, el default tiene que taparlo."""
    config = perfil.leer_config()

    assert config["hotkey_corregir"]
    assert config["hotkey_deshacer"]
    assert config["hotkey_rehacer"]
    # Y los tres tienen que ser distintos: Windows no registra duplicados.
    assert len({config[k] for k in config if k.startswith("hotkey_")}) == 3


# --- Estilo ------------------------------------------------------------------
# `leer_estilo()` devuelve el estilo guardado: auto | natural | estricto.


def test_leer_estilo_default_es_auto(perfil_falso: Path):
    """Sin config.json, el default es 'auto'."""
    assert perfil.leer_estilo() == "auto"


def test_leer_estilo_roundtrip(perfil_falso: Path):
    """Lo que se guarda se lee igual (y no pierde otras claves)."""
    perfil.guardar_config({"estilo": "natural", "hotkey_corregir": "CTRL+ALT+E"})
    assert perfil.leer_estilo() == "natural"
    config = perfil.leer_config()
    assert config["hotkey_corregir"] == "CTRL+ALT+E"
    assert config["hotkey_deshacer"] == "CTRL+SHIFT+Z"


def test_leer_estilo_valor_invalido_cae_a_auto(perfil_falso: Path):
    """Cualquier valor distinto de auto|natural|estricto devuelve 'auto'."""
    (perfil_falso / "config.json").write_text('{"estilo": "inventado"}', encoding="utf-8")
    assert perfil.leer_estilo() == "auto"


def test_leer_estilo_config_sin_clave_devuelve_auto(perfil_falso: Path):
    """Config sin la clave 'estilo' devuelve 'auto'."""
    (perfil_falso / "config.json").write_text('{"activo": true}', encoding="utf-8")
    assert perfil.leer_estilo() == "auto"
