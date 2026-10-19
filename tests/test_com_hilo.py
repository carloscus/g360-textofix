"""
Tests del ciclo de COM en el hilo de atajos.

El bug que cubren: `UIAutomationInitializerInThread` inicializa COM en
__init__ y lo DES-inicializa en __del__ (comtypes.CoUninitialize). Si el
objeto se descarta tras crearlo, CPython lo recolecta al instante y el
hilo queda sin COM: de ahi el "CoInitialize has not been called" que
imprimia uiautomation en el primer atajo de cada arranque.
"""

from __future__ import annotations

import contextlib
import sys
import types
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from core.hotkey import EscuchaAtajos, parsear_atajo


def _escucha() -> EscuchaAtajos:
    return EscuchaAtajos({"corregir": parsear_atajo("CTRL+SHIFT+E")})


def test_el_initializer_de_com_se_guarda_vivo(monkeypatch):
    """La referencia vive en la instancia: si no, __del__ apaga COM ya."""
    modulo = types.ModuleType("uiautomation")

    class _Initializer:
        pass

    modulo.UIAutomationInitializerInThread = _Initializer
    monkeypatch.setitem(sys.modules, "uiautomation", modulo)

    escucha = _escucha()
    assert escucha._com is None

    escucha._inicializar_com()

    assert isinstance(escucha._com, _Initializer)


def test_sin_uiautomation_no_se_revienta(monkeypatch):
    """El arranque del hilo no depende de que el modulo exista."""
    monkeypatch.setitem(sys.modules, "uiautomation", None)  # ImportError

    escucha = _escucha()
    escucha._inicializar_com()

    assert escucha._com is None


def test_texto_en_pantalla_lee_dentro_de_com(monkeypatch):
    """La lectura para deshacer tambien vive dentro del contexto COM."""
    from core import engine

    entradas: list[str] = []

    class _Ctx:
        pass

    class _Adapter:
        def _texto_del_control(self):
            entradas.append("leido")
            return "hola"

    @contextlib.contextmanager
    def _com():
        entradas.append("com-entro")
        yield
        entradas.append("com-salio")

    monkeypatch.setattr(engine, "com_inicializado", _com)
    monkeypatch.setattr(engine, "foreground_context", lambda: _Ctx())
    monkeypatch.setattr(engine, "build_adapters", lambda _cfg: [])
    monkeypatch.setattr(engine, "pick_adapter", lambda _adapters, _ctx: _Adapter())

    assert engine.texto_en_pantalla() == "hola"
    assert entradas == ["com-entro", "leido", "com-salio"]


def test_texto_en_pantalla_sin_ventana_no_toca_com(monkeypatch):
    from core import engine

    llamado = []

    @contextlib.contextmanager
    def _com():
        llamado.append(1)
        yield

    monkeypatch.setattr(engine, "com_inicializado", _com)
    monkeypatch.setattr(engine, "foreground_context", lambda: None)

    assert engine.texto_en_pantalla() is None
    assert llamado == []
