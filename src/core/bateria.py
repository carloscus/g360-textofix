"""
Bateria de frases contra el modelo real.

No toca ninguna pantalla ni escribe en ninguna aplicacion: solo llama al
proovedor elegido (NVIDIA o Gemini, el que tenga clave) y muestra
el antes y el despues. Sirve para medir el prompt antes de confiar en el
corrector con texto real.

    uv run python src/main.py --bateria          # todas
    uv run python src/main.py --bateria tilde    # solo las que coinciden
"""

from __future__ import annotations

import time

from .ai import CuotaAgotada
from .guards import validate
from .proovedor import seleccion_proveedor


def _mismo_texto(a: str, b: str) -> bool:
    """
    Compara ignorando el punto final.

    Anadir el punto de cierre a una frase es una correccion legitima, asi que
    el modelo no debe punished por ello. Lo demas sigue teniendo que coincidir
    exactamente.
    """
    return _sin_cierre(a) == _sin_cierre(b)


def _sin_cierre(texto: str) -> str:
    return " ".join(texto.split()).rstrip(".").strip()


def casos_disponibles():
    """Los casos de la bateria. Viven en core, no en tests, para que el .exe
    los tenga disponibles."""
    from .casos import TODOS

    return TODOS


def ejecutar(filtro: str = "", pausa: float = 0.0) -> int:
    corrector = seleccion_proveedor()

    listo, motivo = corrector.disponible()
    if not listo:
        print(f"No se puede probar: {motivo}")
        print("Claves: revisa el .env (GEMINI_API_KEY / NIM_API_KEY) y corré: uv sync --extra ai")
        return 1

    casos = [c for c in casos_disponibles() if filtro in c.nombre]
    if not casos:
        print(f"Ningun caso coincide con {filtro!r}")
        return 1

    modelo = getattr(corrector, "modelo", "desconocido")
    print(f"Provevedor: {type(corrector).__module__.split('.')[-1]}  modelo: {modelo}")
    print(f"Casos: {len(casos)}")
    if pausa:
        print(f"Pausa entre casos: {pausa}s")
    print()

    aciertos = 0
    sin_texto = 0
    rechazados = 0

    for indice, caso in enumerate(casos):
        try:
            salida = corrector.corregir(caso.entrada)
        except CuotaAgotada as exc:
            print(f"\n[CUOTA] {caso.nombre}: {exc}")
            print(f"\nCasos ejecutados: {indice + 1}/{len(casos)}")
            return 4
        except Exception as exc:
            print(f"[ERROR] {caso.nombre}: {type(exc).__name__}: {exc}")
            sin_texto += 1
            continue

        if salida is None:
            print(f"[SIN TEXTO] {caso.nombre}")
            sin_texto += 1
            continue

        veredicto = validate(caso.entrada, salida)
        if _mismo_texto(salida, caso.esperado):
            marca, aciertos = "OK ", aciertos + 1
        else:
            marca = "DIF"

        if not veredicto.ok:
            marca = f"RECHAZADO({veredicto.reason})"
            rechazados += 1
        if caso.solo_puntuar and not _mismo_texto(salida, caso.entrada):
            marca += " TOCO UN TEXTO QUE YA ESTA BIEN"

        print(f"[{marca}] {caso.nombre}")
        print(f"    antes   : {caso.entrada!r}")
        print(f"    modelo  : {salida!r}")
        if not _mismo_texto(salida, caso.esperado):
            print(f"    esperado: {caso.esperado!r}")
        if caso.nota:
            print(f"    nota    : {caso.nota}")

        if pausa and indice < len(casos) - 1:
            time.sleep(pausa)

    total = len(casos)
    print(f"\n{'=' * 60}")
    print(f"exactos    : {aciertos}/{total}")
    print(f"sin texto  : {sin_texto}")
    print(f"rechazados : {rechazados}")
    return 0
