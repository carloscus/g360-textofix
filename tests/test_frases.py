"""
Bateria de frases: casos de prueba del corrector.

Los datos viven en `core/casos.py` porque los usa tambien la funcion
`--bateria`, que va incluida en el ejecutable. Aca solo se conectan con pytest.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from core.casos import (
    CORRECCIONES,
    INVARIANTES,
    TODOS,
    Caso,
    resumen,
)

__all__ = ["CORRECCIONES", "INVARIANTES", "TODOS", "Caso", "resumen"]


def test_la_bateria_tiene_casos_de_cada_tipo():
    """Una bateria vacia o de un solo tipo no mide nada."""
    assert len(CORRECCIONES) >= 10
    assert len(INVARIANTES) >= 10
    assert len(TODOS) == len(CORRECCIONES) + len(INVARIANTES)


def test_los_casos_de_correccion_tienen_un_error_real():
    """Si entrada y esperado son iguales, el caso no mide nada."""
    for caso in CORRECCIONES:
        assert caso.entrada != caso.esperado, (
            f"{caso.nombre}: la entrada ya era correcta, deberia ser invariante"
        )


def test_los_invariantes_no_cambian():
    for caso in INVARIANTES:
        assert caso.solo_puntuar, f"{caso.nombre}: deberia quedar sin cambios"


def test_no_hay_nombres_repetidos():
    nombres = [c.nombre for c in TODOS]
    assert len(nombres) == len(set(nombres))


def test_todo_invariante_cubre_vocabulario_peruano():
    """El vocabulario peruano es lo mas facil de romper: debe estar cubierto."""
    peru = [c.nombre for c in INVARIANTES if c.nombre.startswith("peru-")]
    assert len(peru) >= 5, f"solo hay {len(peru)} casos peru-"


def test_las_cifras_de_los_invariantes_estan_protegidas():
    """Las cifras son lo que mas daña si el modelo las toca."""
    con_cifras = [c for c in INVARIANTES if any(ch.isdigit() for ch in c.entrada)]
    assert len(con_cifras) >= 3
