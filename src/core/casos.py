"""
Casos de la bateria de frases.

Viven en `core` y no en `tests` porque los usa la FUNCION `--bateria`, que
va incluida en el ejecutable. Si vivieran en los tests, el .exe no tendria con
que medir el prompt.

`tests/test_frases.py` los importa desde aca.
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
    # --- Contexto de correo de trabajo peruano ---
    Caso(
        "correo-apertura",
        "Estimado senor nos dirigimos a usted para confirmar la entrega",
        "Estimado señor, nos dirigimos a usted para confirmar la entrega",
        nota="Tilde en 'señor' y coma tras el vocativo.",
    ),
    Caso(
        "correo-closure",
        "Quedamos a la espera de su confirmacion Cordialmente",
        "Quedamos a la espera de su confirmación. Cordialmente.",
        nota="Tilde y punto antes del cierre.",
    ),
    Caso(
        "correo-cantidad",
        "Adjuntamos 3 facturas por un total de S/ 4,500.00",
        "Adjuntamos 3 facturas por un total de S/ 4,500.00.",
        nota="Solo el punto final: las cifras no se tocan.",
    ),
]

# --- Que NO deben cambiar ----------------------------------------------------

INVARIANTES = [
    # --- Vocabulario peruano: es correcto y no se toca (regla 6 del prompt) ---
    Caso(
        "peru-computadora",
        "Le enviamos la computadora con el informe adjunto",
        "Le enviamos la computadora con el informe adjunto",
        nota="'computadora' es espanol peruano correcto, no es 'ordenador'.",
    ),
    Caso(
        "peru-combustible",
        "El precio del combustible subió esta semana",
        "El precio del combustible subió esta semana",
        nota="'combustible' es peruano correcto, no es 'gasolina'.",
    ),
    Caso(
        "peru-celular",
        "Le escribo a su celular para confirmar",
        "Le escribo a su celular para confirmar",
        nota="'celular' es peruano correcto, no es 'movil'.",
    ),
    Caso(
        "peru-moneda",
        "El monto total es S/ 1,250.00 por lote",
        "El monto total es S/ 1,250.00 por lote",
        nota="No se toca el formato de la moneda ni el separador de miles.",
    ),
    Caso(
        "peru-fecha",
        "La reunión es el 12/05/2026 en la oficina de Lima",
        "La reunión es el 12/05/2026 en la oficina de Lima",
        nota="No se cambia ni el orden ni las cifras de la fecha.",
    ),
    Caso(
        "peru-registro",
        "Estimado cliente, nos referimos a su pedido N° 7781",
        "Estimado cliente, nos referimos a su pedido N° 7781",
        nota="Un correo formal no se informaliza.",
    ),
    Caso("sin-cambios-1", "El cliente pidió tres cajas.", "El cliente pidió tres cajas."),
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
