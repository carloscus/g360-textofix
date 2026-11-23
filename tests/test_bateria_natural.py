"""
Tests de la bateria en modo natural (humano ligero).

Offline: usan un proveedor fake, sin red. Validan que `ejecutar_natural` llama a
`validate(..., estilo="natural")`, reporte `debe_contener` / `no_debe_contener`,
y que `CASOS_NATURALES` cumple el contrato (10-12 casos, >=3 por registro).
"""

from __future__ import annotations

from core.bateria import ejecutar_natural
from core.casos import CASOS_NATURALES, CasoNatural


class _ProvFake:
    """Proveedor fake: devuelve el texto igual salvo que se indique otra salida."""

    def __init__(self, salida: str | None = None):
        self.salida = salida
        self.corregir_llamado_con: list[str] = []
        self.modelo = "fake-modelo"

    def disponible(self):
        return True, ""

    def corregir(self, texto: str, evitando: str | None = None):
        self.corregir_llamado_con.append(texto)
        return self.salida if self.salida is not None else texto

    def probar(self, texto: str):
        return {"original": texto, "corregido": self.corregir(texto)}

    @property
    def api_key(self):
        return None


def test_casos_naturales_contrato():
    """CASOS_NATURALES: 10-12 casos, al menos 3 por registro, sin nombres repetidos."""
    assert 10 <= len(CASOS_NATURALES) <= 12, len(CASOS_NATURALES)
    por_registro: dict[str, int] = {}
    for c in CASOS_NATURALES:
        por_registro[c.registro] = por_registro.get(c.registro, 0) + 1
    for registro in ("formal", "informal", "neutro"):
        assert por_registro.get(registro, 0) >= 3, (
            f"registro {registro}: {por_registro.get(registro, 0)}"
        )
    nombres = [c.nombre for c in CASOS_NATURALES]
    assert len(nombres) == len(set(nombres)), "nombres repetidos"
    for c in CASOS_NATURALES:
        assert isinstance(c, CasoNatural)
        assert c.registro in ("formal", "informal", "neutro")


def test_ejecutar_natural_texto_igual_reporta_ok(monkeypatch, capsys):
    """Si el fake devuelve el texto igual, validate ok y se imprime presupuesto."""
    prov = _ProvFake()
    monkeypatch.setattr("core.bateria.seleccion_proveedor", lambda: prov)
    rc = ejecutar_natural("texto-neutro")
    assert rc == 0
    salida = capsys.readouterr().out
    assert "humano ligero (natural)" in salida
    assert "texto-neutro" in salida
    assert "presupuesto:" in salida
    assert "¿suena natural?" in salida
    assert prov.corregir_llamado_con == ["el reporte esta listo para revisar y hay que enviarlo hoy mismo"]


def test_ejecutar_natural_reporta_falta_debe_contener(monkeypatch, capsys):
    """Si falta una cadena de debe_contener, se reporta en el extra del caso."""
    prov = _ProvFake("otra cosa totalmente distinta")
    monkeypatch.setattr("core.bateria.seleccion_proveedor", lambda: prov)
    rc = ejecutar_natural("cifras-y-moneda")
    assert rc == 0
    salida = capsys.readouterr().out
    assert "FALTA debe_contener" in salida
    assert "S/ 1,250.00" in salida