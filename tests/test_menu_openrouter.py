"""Tests honestos del menu de bandeja con OpenRouter (proxy local)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from core import bandeja, perfil

ORDEN = ["corregir", "deshacer", "rehacer"]


@pytest.fixture
def perfil_falso(tmp_path, monkeypatch):
    """Apunta el perfil a una carpeta temporal y la limpia al salir."""
    monkeypatch.setattr(perfil, "DIR_PERFIL", tmp_path)
    monkeypatch.setattr(perfil, "ARCHIVO_CONFIG", tmp_path / "config.json")
    return tmp_path


class _EstadoFalso:
    """Estado mínimo para construir el menu sin ventana ni atajos reales."""

    def resumen(self) -> str:
        return "Estado de prueba"

    def puede_deshacer(self) -> bool:
        return False

    def puede_rehacer(self) -> bool:
        return False


def _bandeja_con_perfil(perfil_falso: Path) -> bandeja.Bandeja:
    return bandeja.Bandeja(_EstadoFalso(), {})


def _texto_de_item(item) -> str:
    """pystray.MenuItem guarda el texto en .text (lambda para items de estado)."""
    return getattr(item, "text", str(item))


# --- Menu principal ------------------------------------------------------------

def test_menu_no_muestra_claves_viejas(perfil_falso: Path):
    """El menú no contiene 'Clave API Gemini...' ni 'Clave API NVIDIA...'."""
    b = _bandeja_con_perfil(perfil_falso)
    menu = b._construir()
    titulos = [_texto_de_item(i) for i in menu.items]
    assert not any("Clave API Gemini" in t for t in titulos), titulos
    assert not any("Clave API NVIDIA" in t for t in titulos), titulos


def test_menu_tiene_una_sola_entrada_openrouter(perfil_falso: Path):
    """El menú contiene exactamente UNA entrada con 'Clave API OpenRouter'."""
    b = _bandeja_con_perfil(perfil_falso)
    menu = b._construir()
    titulos = [_texto_de_item(i) for i in menu.items]
    hits = [t for t in titulos if "Clave API OpenRouter" in t]
    assert len(hits) == 1, hits


# --- Submenu de modelo ---------------------------------------------------------

def test_submenu_modelo_no_ofrece_nvidia_ni_gemini(perfil_falso: Path):
    """El submenú modelo no ofrece 'NVIDIA Ultra' ni 'Gemini'."""
    b = _bandeja_con_perfil(perfil_falso)
    item_modelo = next(
        i for i in b._construir().items if "Modelo de correccion" in _texto_de_item(i)
    )
    submenu = item_modelo.submenu
    textos = [_texto_de_item(i) for i in submenu.items]
    assert not any("NVIDIA Ultra" in t for t in textos), textos
    assert not any("Gemini" in t for t in textos), textos


def test_submenu_modelo_texto_contiene_nemotron(perfil_falso: Path, monkeypatch):
    """Su texto contiene nvidia/nemotron-3.5-super-vl:free."""
    monkeypatch.delenv("NIM_MODEL", raising=False)
    b = _bandeja_con_perfil(perfil_falso)
    item_modelo = next(
        i for i in b._construir().items if "Modelo de correccion" in _texto_de_item(i)
    )
    submenu = item_modelo.submenu
    radios = [i for i in submenu.items if getattr(i, "radio", False)]
    assert radios, "no hay radios"
    assert "nvidia/nemotron-3.5-super-vl:free" in _texto_de_item(radios[0])


def test_submenu_modelo_siempre_marcado(perfil_falso: Path):
    """La opción del submenú está siempre marcada (checked devuelve True)."""
    b = _bandeja_con_perfil(perfil_falso)
    item_modelo = next(
        i for i in b._construir().items if "Modelo de correccion" in _texto_de_item(i)
    )
    submenu = item_modelo.submenu
    radios = [i for i in submenu.items if getattr(i, "radio", False)]
    assert radios
    for radio in radios:
        assert radio.checked is True or radio.checked() is True


def test_submenu_modelo_persiste_auto(perfil_falso: Path, monkeypatch):
    """El callback del submenú persiste 'auto' en config.json."""
    b = _bandeja_con_perfil(perfil_falso)
    item_modelo = next(
        i for i in b._construir().items if "Modelo de correccion" in _texto_de_item(i)
    )
    submenu = item_modelo.submenu
    radios = [i for i in submenu.items if getattr(i, "radio", False)]
    assert radios
    accion = getattr(radios[0], "_action", None)
    assert accion is not None
    accion(radios[0])
    config = perfil.leer_config()
    assert config["modelo_ia"] == "auto"


# --- Guardar clave OpenRouter --------------------------------------------------

def _fake_input(monkeypatch, valor: str):
    """Monkeypatch de input para devolver `valor` (o EOF si es None)."""
    if valor is None:

        def _eof(*_):
            raise EOFError

        monkeypatch.setattr("builtins.input", _eof)
    else:
        monkeypatch.setattr("builtins.input", lambda *_args: valor)


def test_guardar_clave_nueva_actualiza_env_y_preserva_otras(
    perfil_falso: Path, monkeypatch
):
    """Guardar clave nueva actualiza OPENROUTER_API_KEY en .env y preserva otras líneas."""
    _fake_input(monkeypatch, "sk-or-clave-nueva-123")
    b = _bandeja_con_perfil(perfil_falso)

    env = perfil.DIR_PERFIL / ".env"
    env.write_text("OTRA_LINEA=valor\nGEMINI_API_KEY=abc\n", encoding="utf-8")

    b._configurar_clave_openrouter_en_consola()

    contenido = env.read_text(encoding="utf-8")
    assert "OPENROUTER_API_KEY=sk-or-clave-nueva-123" in contenido
    assert "OTRA_LINEA=valor" in contenido
    assert "GEMINI_API_KEY=abc" in contenido


def test_clave_igual_a_efectiva_no_reescribe(
    perfil_falso: Path, monkeypatch
):
    """Clave igual a la efectiva ⇒ no reescribe .env ni DPAPI."""
    _fake_input(monkeypatch, "sk-or-igual")
    b = _bandeja_con_perfil(perfil_falso)

    env = perfil.DIR_PERFIL / ".env"
    env.write_text("OPENROUTER_API_KEY=sk-or-igual\nOTRA=1\n", encoding="utf-8")
    antes = env.read_text(encoding="utf-8")

    llamadas = []

    def _falso_guardar(clave):
        llamadas.append(clave)

    monkeypatch.setattr(perfil, "guardar_clave_openrouter", _falso_guardar)
    monkeypatch.setattr(
        b, "_escribir_openrouter_env", lambda clave: llamadas.append(("env", clave))
    )

    b._configurar_clave_openrouter_en_consola()

    assert llamadas == [], llamadas
    assert env.read_text(encoding="utf-8") == antes


def test_enter_no_crea_nada(perfil_falso: Path, monkeypatch):
    """ENTER (cadena vacía) ⇒ no crea ni modifica nada."""
    _fake_input(monkeypatch, "")
    b = _bandeja_con_perfil(perfil_falso)

    env = perfil.DIR_PERFIL / ".env"
    env.write_text("OTRA=1\n", encoding="utf-8")
    antes = env.read_text(encoding="utf-8")

    llamadas = []
    monkeypatch.setattr(
        perfil, "guardar_clave_openrouter", lambda clave: llamadas.append(clave)
    )
    monkeypatch.setattr(
        b, "_escribir_openrouter_env", lambda clave: llamadas.append(("env", clave))
    )

    b._configurar_clave_openrouter_en_consola()

    assert llamadas == [], llamadas
    assert env.read_text(encoding="utf-8") == antes
    assert not perfil._archivo_clave_openrouter().exists()
