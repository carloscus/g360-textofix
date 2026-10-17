"""
Adaptador de Microsoft Excel via COM.

Excel no tiene "texto seleccionado" como tal: lo que hay es una celda activa.
Por eso este adaptador trabaja a nivel de celda y aplica guardas que el resto
no necesita:

- Si la celda contiene una formula, NO se toca. Sobrescribirla con texto
  destruiria la logica de la hoja.
- Si el valor no es texto (numero, fecha, error), no se toca. Este corrector
  corrige ortografia, no numeros.
- Si la seleccion abarca varias celdas, solo se actúa sobre la celda activa,
  que es la que el usuario considera selection.
"""

from __future__ import annotations

import logging

import win32com.client

from ..logsetup import LOGGER_NAME
from .base import Capture

log = logging.getLogger(LOGGER_NAME)

PROCESS = "excel.exe"


def _address(cell) -> str:
    """
    Referencia de la celda sin signos de dolar: "A1".

    `Range.Address` es una propiedad parametrizada: segun como se resuelva el
    despacho COM puede came como cadena ("$A$1") o como metodo. Se cubre ambos
    casos porque fallar aqui haria que no se pudiera validar la seleccion antes
    de escribir.
    """
    try:
        crudo = cell.Address
    except Exception:
        return ""
    if callable(crudo):
        try:
            crudo = crudo(False, False)
        except Exception:
            return ""
    return str(crudo).replace("$", "").upper()


class ExcelAdapter:
    name = "excel"

    def matches(self, ctx) -> bool:
        return ctx.process.lower() == PROCESS

    def _app(self):
        return win32com.client.GetActiveObject("Excel.Application")

    def read(self, ctx) -> Capture | None:
        xl = self._app()
        cell = xl.ActiveCell

        formula = cell.Formula
        if isinstance(formula, str) and formula.startswith("="):
            log.info("excel: celda con formula, se omite")
            return None

        value = cell.Value
        if not isinstance(value, str):
            # Numero, fecha, booleano o error: fuera del alcance de un
            # corrector ortografico.
            return None

        if not value.strip():
            return None

        meta = {"app": "excel", "address": _address(cell)}
        return Capture(text=value, suffix="", meta=meta)

    def write(self, ctx, capture: Capture, text: str) -> None:
        xl = self._app()
        cell = xl.ActiveCell

        # Se revalida justo antes de escribir: entre la lectura y la escritura
        # el usuario pudo mover la seleccion o cambiar la celda.
        formula = cell.Formula
        if isinstance(formula, str) and formula.startswith("="):
            raise PermissionError("la celda paso a contener una formula")

        if _address(cell) != capture.meta.get("address"):
            raise PermissionError("la seleccion cambio antes de escribir")

        if xl.ActiveSheet.ProtectContents:
            raise PermissionError("la hoja esta protegida")

        # Escribir .Value conserva el formato de celda y la fuente: el valor
        # sigue siendo texto, asi que no se pierde maquetacion.
        cell.Value = text
        log.debug("excel: escritura aplicada")

    def release(self, capture: Capture) -> None:
        """Excel se lee y escribe por COM: el portapapeles no interviene."""
        return
