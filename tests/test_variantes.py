"""
Tests del ciclo de variantes: mismo atajo, otra correccion.

Cada variante es una llamada de red pedida solo cuando el usuario insiste
sobre el texto ya corregido. Lo que se cubre aca: el prompt de variante,
el paso de `evitando` por engine/proveedores, y que una variante igual a
la existente NO pise el texto.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from core import engine
from core import proovedor as prov_mod
from core.config import Config


def test_prompt_variante_agrega_la_instruccion():
    from core.ai import PROMPT, prompt_variante

    p = prompt_variante("El cliente pidio.")

    assert p.startswith(PROMPT)
    assert "El cliente pidio." in p
    assert "OTRA correccion" in p


def test_nvidia_con_evitando_usa_el_prompt_de_variante(monkeypatch):
    from core.nvidia import ProveedorNIM

    llamado: dict = {}
    prov = ProveedorNIM(api_key="k")
    monkeypatch.setattr(
        prov, "_pedir", lambda _h, prompt, _t: llamado.update(prompt=prompt) or "saludo"
    )

    salida = prov.corregir("hola", evitando="hola.")

    assert salida == "saludo"
    assert "OTRA correccion" in llamado["prompt"]
    assert "hola." in llamado["prompt"]


def test_gemini_con_evitando_usa_el_prompt_de_variante(monkeypatch):
    from core.ai import CorrectorIA

    recibido: dict = {}

    class _Respuesta:
        text = "saludo"

    class _Modelos:
        def generate_content(self, **kwargs):
            recibido.update(kwargs)
            return _Respuesta()

    class _Cliente:
        models = _Modelos()

    prov = CorrectorIA(api_key="k")
    monkeypatch.setattr(prov, "_obtener_cliente", lambda: _Cliente())

    salida = prov.corregir("hola", evitando="hola.")

    assert salida == "saludo"
    assert "OTRA correccion" in recibido["contents"]
    assert recibido["contents"].endswith("hola")


def test_correct_pasa_el_evitando_al_proveedor(monkeypatch):
    class _Prov:
        modelo = "x"

        def corregir(self, texto, evitando=None):
            return f"{texto}|{evitando}"

    monkeypatch.setattr(prov_mod, "seleccion_proveedor", lambda: _Prov())

    assert engine.correct("hola", "ia", "roundtrip", evitando="hola.") == "hola|hola."


def test_el_fallback_tambien_recibe_el_evitando(monkeypatch):
    class _Roto:
        modelo = "x"

        def corregir(self, texto, evitando=None):
            raise RuntimeError("boom")

    class _Buena:
        modelo = "y"

        def corregir(self, texto, evitando=None):
            return f"variante de {evitando}"

    monkeypatch.setattr(prov_mod, "seleccion_proveedor", lambda: _Roto())
    monkeypatch.setattr(prov_mod, "otra_nube", lambda _p: _Buena())

    assert engine.correct("hola", "ia", "roundtrip", evitando="hola.") == "variante de hola."


def test_variante_igual_no_pisa_el_texto(monkeypatch):
    """Si el modelo devuelve lo mismo que ya esta puesto, no se escribe nada."""
    escrituras: list = []
    tonos: list = []

    class _Adapter:
        name = "fake"

        def write(self, _ctx, _capture, texto):
            escrituras.append(texto)

    class _Feedback:
        @staticmethod
        def ok():
            tonos.append("ok")

        @staticmethod
        def error():
            tonos.append("error")

        @staticmethod
        def no_selection():
            tonos.append("sin")

    class _Capture:
        text = "ya corregido."

    monkeypatch.setattr(engine, "correct", lambda *_a, **_k: "ya corregido.")
    monkeypatch.setattr(engine, "feedback", _Feedback)

    outcome = engine._corregir_y_escribir(
        _Adapter(),
        object(),
        Config.from_env(),
        _Capture(),
        "ia",
        "roundtrip",
        None,
        evitando="ya corregido.",
    )

    assert outcome.reason == "variante-igual"
    assert escrituras == []  # el texto del usuario queda como estaba
    assert tonos == ["sin"]
