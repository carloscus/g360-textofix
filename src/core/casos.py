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
        "commodo-typo",
        "El cliente encontro un commodo en el contrato",
        "El cliente encontró un comodato en el contrato",
        "Doble-consonante: 'commodo' no existe en espanol. Se escribe "
        "'comodato' (o, segun el contexto, 'comodidad').",
    ),
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
    Caso(
        "correo-breve-typo",
        (
            "Se envia esta solicitud aolicitando su aprobacion y habilitacion "
            "del cliente para proceder con las atenciones y mercaderia e a "
            "enviar segun lo solicitado por el cliente en su peduidoi de "
            "campana que tienbe letras de anticipo y pendientes por entregar"
        ),
        (
            "Se envía esta solicitud solicitando su aprobación y habilitación "
            "del cliente para proceder con las atenciones y mercadería a "
            "enviar según lo solicitado por el cliente en su pedido de "
            "campaña que tiene letras de anticipo y pendientes por entregar."
        ),
        nota=(
            "Correo breve real: 6 typos mezclados (aolicitando, peduidoi, "
            "tienbe, una 'e' suelta, tildes). Los modelos chicos suelen "
            "'charlar' aca; el 90b lo corrige completo."
        ),
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


# --- Casos del "modo humano ligero" (natural) --------------------------------

# Estos casos NO se mezclan con `casos.TODOS` (que tiene expectativa exacta):
# la naturalidad no es determinista. Cada caso trae `debe_contener` / no_debe_contener
# para lo que sí se puede afirmar de forma determinista (datos, URLs, cifras,
# nombres), y deja la naturalidad a una checklist cualitativa que completa el
# operador (ver `bateria.ejecutar_natural`).


@dataclass(frozen=True)
class CasoNatural:
    nombre: str
    entrada: str
    # "formal", "informal" o "neutro": registro del original.
    registro: str
    # Frases que SIEMPRE deben seguir estando (datos, URLs, cifras, nombres).
    debe_contener: tuple[str, ...] = ()
    # Frases que NUNCA deben aparecer (no se inventan, no se eliminan).
    no_debe_contener: tuple[str, ...] = ()
    nota: str = ""


CASOS_NATURALES = [
    CasoNatural(
        "correo-formal-largo",
        (
            "Estimado señor cliente, nos dirigimos a usted para confirmar la "
            "entrega de la mercadería pactada para el 12/05/2026. Quedamos a la "
            "espera de su confirmación y le enviamos la factura en formato PDF. "
            "Cualquier consulta, escribanos a ventas@cipsa.com.pe o llámenos al "
            "celular 987 654 321. Cordialmente, área de ventas."
        ),
        "formal",
        debe_contener=(
            "Estimado señor cliente",
            "12/05/2026",
            "ventas@cipsa.com.pe",
            "celular",
            "Cordialmente",
        ),
        no_debe_contener=("ordenador", "movil", "autobus"),
        nota="Correo formal largo: solo ortografía y puntuación, sin informalizar.",
    ),
    CasoNatural(
        "mensaje-informal-corto",
        "hola chau te mando la info pa el cliente lunes nomas",
        "informal",
        debe_contener=("lunes", "cliente"),
        no_debe_contener=("estimado", "cordialmente"),
        nota="Mensaje informal corto: se ordena sin enfriar el tono.",
    ),
    CasoNatural(
        "texto-neutro",
        "el reporte esta listo para revisar y hay que enviarlo hoy mismo",
        "neutro",
        debe_contener=("reporte", "hoy mismo"),
        nota="Texto neutro: tono conversacional, ni formal ni coloquial.",
    ),
    CasoNatural(
        "typos-basicos",
        "el cliente pidio tres cajas y la factura",
        "neutro",
        debe_contener=("cliente", "cajas", "factura"),
        nota="Typos sencillos (pidio -> pidió).",
    ),
    CasoNatural(
        "cifras-y-moneda",
        "el monto total es S/ 1,250.00 por lote y el 12/05/2026 se paga",
        "formal",
        debe_contener=("S/ 1,250.00", "12/05/2026", "lote"),
        nota="Cifras y moneda peruana intactas.",
    ),
    CasoNatural(
        "hora-y-abreviaturas",
        "la reunion empieza a las 9:30 am en la oficina de Lima",
        "informal",
        debe_contener=("9:30 am", "Lima"),
        no_debe_contener=("9:30 a. m.", "a.m."),
        nota="Horas y abreviaturas intactas (regla 8 del prompt).",
    ),
    CasoNatural(
        "nombres-propuios",
        "escribi a Juan Perez y Maria para confirmar la reunion",
        "informal",
        debe_contener=("Juan Perez", "Maria"),
        no_debe_contener=("Juan Pérez", "María"),
        nota="Nombres propios sin tilde, intactos (decision de estilo, no error).",
    ),
    CasoNatural(
        "url-y-correo",
        "ver https://intranet.cipsa.com.pe/pedidos/7781 y escribir a soporte@cipsa.pe",
        "neutro",
        debe_contener=("https://intranet.cipsa.com.pe/pedidos/7781", "soporte@cipsa.pe"),
        nota="URLs y correos intactos.",
    ),
    CasoNatural(
        "vocabulario-peruano",
        "le enviamos la computadora y el celular con el combustible",
        "formal",
        debe_contener=("computadora", "celular", "combustible"),
        no_debe_contener=("ordenador", "movil", "gasolina"),
        nota="Vocabulario peruano correcto, sin variantes regionales.",
    ),
    CasoNatural(
        "parrafo-multi-frase",
        (
            "Buenos dias. El reporte de marzo esta listo y lo enviamos hoy. "
            "Hay que revisar las cifras antes de firmar. Gracias por su atencion."
        ),
        "formal",
        debe_contener=("reporte", "marzo", "cifras", "Gracias"),
        nota="Parrafo multi-frase para medir el presupuesto de palabras (1-2 por frase).",
    ),
]


def resumen() -> dict[str, int]:
    return {
        "correcciones": len(CORRECCIONES),
        "invariantes": len(INVARIANTES),
        "total": len(TODOS),
        "casos_naturales": len(CASOS_NATURALES),
    }
