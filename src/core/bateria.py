"""
Bateria de frases contra el modelo real.

No toca ninguna pantalla ni escribe en ninguna aplicacion: solo llama a Gemini
y muestra el antes y el despues. Sirve para medir el prompt antes de confiar en
el corrector con texto real.

    uv run python src/main.py --bateria          # todas
    uv run python src/main.py --bateria tilde    # solo las que coinciden
"""

from __future__ import annotations

from .ai import CorrectorIA
from .guards import validate


def casos_disponibles():
    """Los casos de `tests/test_frases.py`, sin importar un modulo de tests."""
    from test_frases import TODOS

    return TODOS


def ejecutar(filtro: str = "") -> int:
    corrector = CorrectorIA()

    listo, motivo = corrector.disponible()
    if not listo:
        print(f"No se puede probar: {motivo}")
        print("Revisa .env (puedes copiar .env.example) y corre: uv sync --extra ai")
        return 1

    casos = [c for c in casos_disponibles() if filtro in c.nombre]
    if not casos:
        print(f"Ningun caso coincide con {filtro!r}")
        return 1

    print(f"Modelo: {corrector.modelo}")
    print(f"Casos: {len(casos)}\n")

    aciertos = 0
    sin_texto = 0
    rechazados = 0

    for caso in casos:
        try:
            salida = corrector.corregir(caso.entrada)
        except Exception as exc:
            print(f"[ERROR] {caso.nombre}: {exc}")
            sin_texto += 1
            continue

        if salida is None:
            print(f"[SIN TEXTO] {caso.nombre}")
            sin_texto += 1
            continue

        veredicto = validate(caso.entrada, salida)
        if salida == caso.esperado:
            marca, aciertos = "OK ", aciertos + 1
        else:
            marca = "DIF"

        if not veredicto.ok:
            marca = f"RECHAZADO({veredicto.reason})"
            rechazados += 1
        if caso.solo_puntuar and salida != caso.entrada:
            marca += " TOCO UN TEXTO QUE YA ESTA BIEN"

        print(f"[{marca}] {caso.nombre}")
        print(f"    antes   : {caso.entrada!r}")
        print(f"    modelo  : {salida!r}")
        if salida != caso.esperado:
            print(f"    esperado: {caso.esperado!r}")
        if caso.nota:
            print(f"    nota    : {caso.nota}")

    total = len(casos)
    print(f"\n{'=' * 60}")
    print(f"exactos    : {aciertos}/{total}")
    print(f"sin texto  : {sin_texto}")
    print(f"rechazados : {rechazados}")
    return 0
