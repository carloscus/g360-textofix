"""
Bateria de frases para medir el corrector (plan, seccion 5).

Estos casos NO se ejecutan contra un modelo en la Etapa 1: no hay IA todavia.
Sirven como criterio de aceptacion fijo para la Etapa 2, de modo que el
comportamiento se pueda comparar antes y despues de cambiar el prompt o el
modelo.

Cada caso dice que se espera del corrector. `solo_puntuar` marca las frases
que ya estan correctas y por lo tanto no deben cambiar.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Caso:
    nombre: str
    entrada: str
    esperado: str
    nota: str = ""

    @property
    def solo_puntuar(self) -> bool:
        """El texto ya es correcto: el corrector no debe tocarlo."""
        return self.entrada == self.esperado


# --- Correcciones tipicas ----------------------------------------------------

CORRECCIONES = [
    Caso(
        "tilde-acentos",
        "El cliente pidio tres cajas",
        "El cliente pidió tres cajas",
    ),
    Caso(
        "mayuscula-inicial",
        "enviamos la cotizacion hoy",
        "Enviamos la cotización hoy",
    ),
    Caso(
        "puntuacion-final",
        "Gracias por su atencion",
        "Gracias por su atención.",
    ),
    Caso(
        "tilde-e",
        "El senor quiere mas informacion",
        "El señor quiere más información",
    ),
    Caso(
        "tilde-o",
        "La informacion llego tarde",
        "La información llegó tarde",
    ),
    Caso(
        "tilde-u",
        "El numero de serie es unico",
        "El número de serie es único",
    ),
    Caso(
        "tilde-n",
        "El ano pasado fue mejor",
        "El año pasado fue mejor",
    ),
    Caso(
        "tilde-i",
        "Hubo mas errores de los esperados",
        "Hubo más errores de los esperados",
    ),
    Caso(
        "tilde-a",
        "Solo falta validar el analisis",
        "Sólo falta validar el análisis",
    ),
]

# --- Que NO deben cambiar ----------------------------------------------------

INVARIANTES = [
    Caso(
        "sin-cambios-1", "El cliente pidió tres cajas.", "El cliente pidió tres cajas."
    ),
    Caso("sin-cambios-2", "Gracias por su atención.", "Gracias por su atención."),
    Caso(
        "sin-cambios-cifras",
        "Pedido 42 unidades, referencia 7781, fecha 12/05/2026.",
        "Pedido 42 unidades, referencia 7781, fecha 12/05/2026.",
        nota="Las cifras deben sobrevivir intactas.",
    ),
    Caso(
        "sin-cambios-marca",
        "Cipsa S.A.C. - Lima, Peru",
        "Cipsa S.A.C. - Lima, Peru",
        nota="Nombres propios y simbolos no se tocan.",
    ),
    Caso(
        "sin-cambios-codigo",
        "SKU-ABC-001 / SKU-ABC-002",
        "SKU-ABC-001 / SKU-ABC-002",
        nota="Codigos internos intactos.",
    ),
    Caso(
        "sin-cambios-url",
        "Ver https://intranet.cipsa.com.pe/pedidos/7781",
        "Ver https://intranet.cipsa.com.pe/pedidos/7781",
        nota="Las URL no se reescriben.",
    ),
    Caso(
        "sin-cambios-formato",
        "| Codigo | Cantidad |",
        "| Codigo | Cantidad |",
        nota="Tablas y pipes: el corrector no es un formateador.",
    ),
]

TODOS = CORRECCIONES + INVARIANTES


def resumen() -> dict[str, int]:
    return {
        "correcciones": len(CORRECCIONES),
        "invariantes": len(INVARIANTES),
        "total": len(TODOS),
    }
