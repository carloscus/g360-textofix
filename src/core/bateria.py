"""
Bateria de frases contra el modelo real.

No toca ninguna pantalla ni escribe en ninguna aplicacion: solo llama al
proovedor elegido (NVIDIA o Gemini, el que tenga clave) y muestra
el antes y el despues. Sirve para medir el prompt antes de confiar en el
corrector con texto real.

    uv run python src/main.py --bateria          # todas (estricta, canónica)
    uv run python src/main.py --bateria --natural # modo humano ligero
    uv run python src/main.py --bateria tilde    # solo las que coinciden
"""

from __future__ import annotations

import time

from .ai import CuotaAgotada
from .casos import CASOS_NATURALES
from .guards import (
    Diferencias,
    PALABRA,
    CORTA,
    diferencias,
    presupuesto_palabras,
    tokens_lexicos,
    validate,
)
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


# --- Bucle compartido ---------------------------------------------------------
# `ejecutar` (estricta) y `ejecutar_natural` comparten el mismo bucle de casos:
# la diferencia es el estilo que se le pasa a `validate` y el reporte de cada
# caso. Extraerlo en una funcion pequena evita duplicar el loop y sus bordes
# (cuota, sin texto, pausa, resumen final).


def _bucle_casos(
    casos: list,
    filtro: str,
    pausa: float,
    titulo: str,
    estilo: str,
    evaluar_caso,
) -> int:
    """Ejecuta una bateria de casos sobre el proveedor elegido.

    `evaluar_caso(salida, caso) -> (marca, lineas_extra)` imprime lo que corresponda
    para cada modo (estricto o natural) sin que el bucle sepa de cada uno.
    """
    corrector = seleccion_proveedor()

    listo, motivo = corrector.disponible()
    if not listo:
        print(f"No se puede probar: {motivo}")
        print("Claves: revisa el .env (GEMINI_API_KEY / NIM_API_KEY) y corré: uv sync --extra ai")
        return 1

    casos = [c for c in casos if filtro in c.nombre]
    if not casos:
        print(f"Ningun caso coincide con {filtro!r}")
        return 1

    modelo = getattr(corrector, "modelo", "desconocido")
    print(f"Provevedor: {type(corrector).__module__.split('.')[-1]}  modelo: {modelo}")
    print(f"Modo: {titulo}  casos: {len(casos)}")
    if pausa:
        print(f"Pausa entre casos: {pausa}s")
    print()

    aciertos = 0
    sin_texto = 0
    rechazados = 0
    exceden_presupuesto = 0

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

        marca, extra = evaluar_caso(salida, caso, estilo)
        if "RECHAZADO" in marca:
            rechazados += 1
        if "reescritura-agresiva" in marca:
            exceden_presupuesto += 1
        if extra:
            for linea in extra:
                print(f"    {linea}")

        print(f"[{marca}] {caso.nombre}")
        print(f"    antes   : {caso.entrada!r}")
        print(f"    modelo  : {salida!r}")
        if caso.nota:
            print(f"    nota    : {caso.nota}")

        if pausa and indice < len(casos) - 1:
            time.sleep(pausa)

    total = len(casos)
    print(f"\n{'=' * 60}")
    print(f"modo       : {titulo}")
    print(f"casos      : {total}")
    print(f"rechazados : {rechazados}")
    print(f"sin texto  : {sin_texto}")
    if estilo == "natural":
        print(f"exceden presupuesto: {exceden_presupuesto}")
    return 0


def ejecutar(filtro: str = "", pausa: float = 0.0) -> int:
    """Bateria estricta (canónica). Pasa estilo="estricto" a validate."""

    def evaluar(salida: str, caso, estilo: str) -> tuple[str, list[str]]:
        from .casos import TODOS  # evita import circular en modulo
        origen = next((c for c in TODOS if c.nombre == caso.nombre), None)
        esperado = origen.esperado if origen is not None else None
        veredicto = validate(caso.entrada, salida, estilo="estricto")
        marca = "OK " if (esperado is not None and _mismo_texto(salida, esperado)) else "DIF"
        if not veredicto.ok:
            marca = f"RECHAZADO({veredicto.reason})"
        if origen is not None and origen.solo_puntuar and not _mismo_texto(salida, origen.entrada):
            marca += " TOCO UN TEXTO QUE YA ESTA BIEN"
        extra = []
        if not (esperado is not None and _mismo_texto(salida, esperado)):
            extra.append(f"esperado: {esperado!r}")
        return marca, extra

    return _bucle_casos(
        casos_disponibles(), filtro, pausa, "estricta (canónica)", "estricto", evaluar
    )


def ejecutar_natural(filtro: str = "", pausa: float = 0.0) -> int:
    """Bateria en modo humano ligero (natural).

    La naturalidad/neutralidad NO es determinista: por cada caso se imprime una
    checklist cualitativa ("¿suena natural?", "¿neutral de registro?",
    "¿conserva ideas?") para que el operador la complete. Lo que sí se evalúa
    de forma determinista: validate(entrada, salida, estilo="natural").ok, las
    cadenas de debe_contener presentes, ninguna de no_debe_contener, y se
    reporta diferencias.total vs presupuesto_palabras.
    """
    from .casos import CASOS_NATURALES

    print("=== MODO HUMANO LIGERO (natural) ===")
    print("La naturalidad y neutralidad NO son deterministas.")
    print("Por cada caso se imprime una checklist cualitativa para que el operador")
    print("la complete a mano. Solo se valida determinísticamente:")
    print("  - validate(entrada, salida, estilo='natural').ok")
    print("  - cada cadena de debe_contener está presente")
    print("  - ninguna cadena de no_debe_contener está presente")
    print("  - diferencias.total vs presupuesto_palabras (se reporta, no se rechaza)")
    print()

    def evaluar(salida: str, caso, estilo: str) -> tuple[str, list[str]]:
        veredicto = validate(caso.entrada, salida, estilo="natural")
        diff = diferencias(caso.entrada, salida)
        n = sum(1 for _, c in tokens_lexicos(caso.entrada) if c in (PALABRA, CORTA))
        presupuesto = presupuesto_palabras(n)
        marca = "OK " if veredicto.ok else f"RECHAZADO({veredicto.reason})"
        extra = [
            f"presupuesto: {diff.total}/{presupuesto} palabras cambiadas",
            "  ¿suena natural? [ ]   ¿neutral de registro? [ ]   ¿conserva ideas? [ ]",
        ]
        # debe_contener / no_debe_contener son deterministas: se chequean y se reportan.
        falta = [s for s in caso.debe_contener if s not in salida]
        sobra = [s for s in caso.no_debe_contener if s in salida]
        if falta:
            extra.append(f"  FALTA debe_contener: {falta!r}")
        if sobra:
            extra.append(f"  SOBRA no_debe_contener: {sobra!r}")
        return marca, extra

    return _bucle_casos(
        CASOS_NATURALES, filtro, pausa, "humano ligero (natural)", "natural", evaluar
    )
