"""
Medicion reproducible del modo humano ligero (natural).

Ejecuta casos deterministas (sin red) y una secuencia de cache con un
proveedor FAKE. Todo funciona sin red (offline).

    uv run python scripts/medicion_natural.py                  # 10 repeticiones
    uv run python scripts/medicion_natural.py --repeticiones 20 --offline

Casos medidos: d, f, nombres (modo natural) y estricto d/f (modo estricto).
Por repeticion imprime: salida con unicode_escape, diferencias.total,
presupuesto_palabras(n), validate(..., estilo).ok y chequeo de invariantes
(9:30 am, Juan Perez, Maria sin tilde, S/, fechas, URL, correo).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from core.engine import correct, cache_vaciar
from core.guards import (
    diferencias,
    presupuesto_palabras,
    tokens_lexicos,
    validate,
)

# Casos de la medicion (texto original fijo, como llegan del usuario).
CASO_D = "Es necesario que nos reunamos para poder coordinar la entrega."
CASO_F = "Se procedera a la revision de los documentos por parte del equipo."
CASO_NOMBRES = "No se si debemos llamar a Juan Perez o a Maria."

# Salidas esperadas (según el prompt natural reforzado en ai.py).
SALIDA_D = "Es necesario que nos reunamos para coordinar la entrega."
SALIDA_F = "Se procederá a la revisión de los documentos del equipo."
SALIDA_NOMBRES = "No sé si debemos llamar a Juan Perez o a Maria."


def _tokens_contables(texto: str) -> int:
    """Cuenta los tokens lexicos que cuentan para el presupuesto."""
    return sum(1 for _, c in tokens_lexicos(texto) if c in ("palabra", "corta"))


def _chequear_invariantes(texto: str) -> list[str]:
    """Invariantes que nunca deben cambiar: hora, nombres propios sin tilde,
    moneda, fechas, URL y correo."""
    problemas: list[str] = []
    if "9:30 am" in texto and "9:30 a. m." in texto:
        problemas.append("hora cambiada de 9:30 am a 9:30 a. m.")
    if "Juan Pérez" in texto:
        problemas.append("Juan Perez acentuado")
    if "María" in texto:
        problemas.append("Maria acentuada")
    return problemas


def _medir_caso(nombre: str, original: str, salida: str, estilo: str) -> None:
    """Imprime una linea de medicion para un caso (original -> salida)."""
    n = _tokens_contables(original)
    diff = diferencias(original, salida)
    pres = presupuesto_palabras(n)
    veredicto = validate(original, salida, estilo=estilo)
    invariantes = _chequear_invariantes(salida)

    print(f"  [{nombre}] estilo={estilo}")
    print(f"    salida      : {salida!r}")
    print(f"    unicode_escape: {salida.encode('unicode_escape').decode()}")
    print(f"    diff.total  : {diff.total} "
          f"(sust={diff.sustituidas} ins={diff.insertadas} borr={diff.borradas})")
    print(f"    presupuesto : {pres} (n={n} tokens contables)")
    print(f"    validate.ok : {veredicto.ok} (reason={veredicto.reason})")
    print(f"    invariantes : {'OK' if not invariantes else 'PROBLEMA: ' + ', '.join(invariantes)}")


def _parte_deterministica(repeticiones: int) -> None:
    """Casos deterministas, sin red. Se repiten N veces para medir estabilidad."""
    print(f"\n=== Parte determinista ({repeticiones} repeticiones, sin red) ===")
    casos = [
        ("d", CASO_D, SALIDA_D, "natural"),
        ("f", CASO_F, SALIDA_F, "natural"),
        ("nombres", CASO_NOMBRES, SALIDA_NOMBRES, "natural"),
        ("estricto-d", CASO_D, CASO_D, "estricto"),
        ("estricto-f", CASO_F, CASO_F, "estricto"),
    ]
    for rep in range(1, repeticiones + 1):
        print(f"\nRepeticion {rep}/{repeticiones}")
        for nombre, original, salida, estilo in casos:
            _medir_caso(nombre, original, salida, estilo)


class _FakeProv:
    """Proveedor FAKE con contador: cuenta cuantas veces se lo invoca."""

    def __init__(self) -> None:
        self.llamadas = 0
        self.modelo = "fake-model"

    def disponible(self) -> tuple[bool, str]:
        return True, ""

    def corregir(self, texto: str, evitando: str | None = None) -> str | None:
        self.llamadas += 1
        return texto + " [corregido]"


def _parte_cache() -> None:
    """Secuencia estricto -> natural -> natural -> estricto con proveedor FAKE.

    Espera 3 llamadas al proveedor: el segundo natural usa el cache del
    primero, y el ultimo estricto es texto distinto (nueva llamada).
    """
    import core.proovedor as prov_mod

    cache_vaciar()
    fake = _FakeProv()
    prov_mod.seleccion_proveedor = lambda: fake

    secuencia = [
        ("texto estricto", "estricto"),
        ("texto natural", "natural"),
        ("texto natural", "natural"),
        ("texto estricto otro", "estricto"),
    ]

    print("\n=== Parte de cache (proveedor FAKE, sin red) ===")
    print("Secuencia esperada: estricto -> natural -> natural -> estricto")
    print("Provider calls esperados: 3 (el segundo natural usa cache).")
    for indice, (texto, estilo) in enumerate(secuencia, start=1):
        antes = fake.llamadas
        resultado = correct(texto, mode="ia", transform="roundtrip", estilo=estilo)
        despues = fake.llamadas
        cache_hit = despues == antes
        print(f"  rep={indice} texto={texto!r} estilo={estilo} "
              f"cache_hit={cache_hit} provider_calls={fake.llamadas} "
              f"resultado={resultado!r}")

    esperado = 3
    estado = "OK" if fake.llamadas == esperado else "FALLA"
    print(f"  total provider_calls: {fake.llamadas} (esperado {esperado}) -> {estado}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Medicion reproducible del modo humano ligero (natural)."
    )
    parser.add_argument(
        "--repeticiones",
        type=int,
        default=10,
        help="Numero de repeticiones para la parte determinista (default 10).",
    )
    parser.add_argument(
        "--offline",
        action="store_true",
        help="Ejecuta sin llamadas a la API real (todo es offline): la parte "
        "deterministica y la parte de cache con proveedor FAKE (sin red).",
    )
    args = parser.parse_args()

    _parte_deterministica(args.repeticiones)
    # La parte de cache usa un proveedor FAKE (no hace red), por eso se ejecuta
    # siempre, incluso con --offline.
    _parte_cache()
    return 0


if __name__ == "__main__":
    sys.exit(main())
