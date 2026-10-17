"""
Comparar modelos locales con los mismos 26 casos de la bateria.

Salida: una tabla en consola. No escribe en ninguna pantalla: solo mide la
calidad de cada modelo contra el conjunto de frases del proyecto.

    uv run python tools/comparar_modelos.py
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from core.casos import TODOS
from core.guards import validate
from core.ollama import ProveedorOllama

MODELOS = [
    ("llama3.2:3b", "ligero, 3B"),
    ("llama3:8b", "mas capaz, 8B de la familia previa"),
    ("qwen3:8b", "multilingue, primera opcion de la sugerencia"),
    ("gemma3:4b", "IT cuantizada, alternativa"),
]


def _sin_cierre(texto: str) -> str:
    return " ".join(texto.split()).rstrip(".").strip()


def correccion_buena(entrada: str, salida: str, esperado: str) -> str:
    """Etiqueta de un solo caso: OK, DIF, RECHAZADO, o SIN TEXTO."""
    if salida is None:
        return "SIN TEXTO"
    veredicto = validate(entrada, salida)
    if not veredicto.ok:
        return f"RECHAZADO({veredicto.reason})"
    if _sin_cierre(salida) == _sin_cierre(esperado):
        return "OK"
    return "DIF"


def medir(prov: ProveedorOllama, casos: list) -> tuple[dict, float]:
    resumen = {c.nombre: None for c in casos}
    tiempos: list[float] = []
    for caso in casos:
        t0 = time.monotonic()
        salida = prov.corregir(caso.entrada)
        dt = time.monotonic() - t0
        tiempos.append(dt)
        resumen[caso.nombre] = correccion_buena(caso.entrada, salida, caso.esperado)
        time.sleep(0.2)  # no se abusa del CPU
    return resumen, (sum(tiempos) / len(tiempos) if tiempos else 0.0)


def main() -> int:
    casos = TODOS
    print(f"{len(casos)} casos de la bateria")
    print()

    # Solo se mide un modelo si se le pide: todos o uno.
    solo = sys.argv[1] if len(sys.argv) > 1 else ""

    for nombre, nota in MODELOS:
        if solo and solo not in nombre:
            continue
        print(f"=== {nombre}  ({nota}) ===")
        prov = ProveedorOllama(modelo=nombre)
        listo, motivo = prov.disponible()
        if not listo:
            print(f"  no disponible: {motivo}")
            print(f"  descargalo con: ollama pull {nombre}")
            print()
            continue

        print("  cargando modelo (warm-up)...")
        prov.corregir("hola")
        resumen, lat = medir(prov, casos)

        ok = sum(1 for v in resumen.values() if v == "OK")
        dif = sum(1 for v in resumen.values() if v == "DIF")
        rech = sum(1 for v in resumen.values() if v and v.startswith("RECHAZADO"))
        sin = sum(1 for v in resumen.values() if v == "SIN TEXTO")

        print(f"  exactos  : {ok}/{len(casos)}")
        print(f"  distintos: {dif}")
        print(f"  rechazados: {rech}")
        print(f"  sin texto : {sin}")
        print(f"  latencia media: {lat:.1f}s (incluye cold start)")
        print()
        for caso in casos:
            resultado = resumen[caso.nombre]
            print(f"    [{resultado:22}] {caso.nombre:30} {caso.entrada[:40]!r}")
        print()

    return 0


if __name__ == "__main__":
    sys.exit(main())
