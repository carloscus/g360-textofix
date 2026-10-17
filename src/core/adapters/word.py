"""
Adaptador de Microsoft Word via COM.

Word expone `Selection.Range`, que lee exactamente lo seleccionado y respeta
parrafos, formato y control de cambios. UIA sobre Word es mas lento y fragil,
asi que para Word se usa COM.

 detalle: `Range.Text` incluye los saltos de parrafo que forman parte de la
seleccion. Si al escribir no se reponen, el documento pierde parrafos.
"""

from __future__ import annotations

import logging

import win32com.client

from ..logsetup import LOGGER_NAME
from .base import Capture

log = logging.getLogger(LOGGER_NAME)

PROCESS = "winword.exe"


class WordAdapter:
    name = "word"

    def matches(self, ctx) -> bool:
        return ctx.process.lower() == PROCESS

    def _app(self):
        """Conexion a la instancia de Word ya abierta (no la lanza nueva)."""
        return win32com.client.GetActiveObject("Word.Application")

    def read(self, ctx) -> Capture | None:
        word = self._app()
        rng = word.Selection.Range
        raw = rng.Text or ""
        if not raw:
            return None

        # La marca de parrafo final se excluye del texto, pero no se descarta:
        # `write` la deja intacta para no crear un parrafo de mas.
        if not raw.rstrip("\r\x07").strip():
            return None

        return Capture(text=raw.rstrip("\r\x07"), suffix="", meta={"app": "word"})

    def write(self, ctx, capture: Capture, text: str) -> None:
        word = self._app()
        rng = word.Selection.Range

        # Word siempre termina el documento con una marca de parrafo. Si esa
        # marca forma parte del rango y se reemplaza por texto que tambien
        # acaba en \r, Word inserta un parrafo adicional. La solution es
        # escribir sobre un rango que NO incluya la marca final.
        if (rng.Text or "").endswith("\r"):
            rng.SetRange(rng.Start, rng.End - 1)

        rng.Text = text
        log.debug("word: escritura aplicada")

    def release(self, capture: Capture) -> None:
        """Word se lee y escribe por COM: el portapapeles no interviene."""
        return
