"""
Contrato de los adaptadores de captura.

Cada aplicacion objetivo tiene su forma de exponer "lo que el usuario tiene
seleccionado". Word y Excel exponen COM y son mucho mas fiables que UIA, asi
que tienen adaptador propio. Todo lo demas usa UIA y, si no alcanza, el
portapapeles.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from ..winapi import WindowContext


@dataclass(frozen=True)
class Capture:
    """
    Texto leido de la seleccion.

    `suffix` son los caracteres de control que pertenecen a la seleccion pero no
    al texto (por ejemplo el salto de parrafo de Word). Si no se preservan al
    escribir, se borran del documento.
    """

    text: str
    suffix: str = ""
    meta: dict = field(default_factory=dict)


class Adapter(Protocol):
    name: str

    def matches(self, ctx: WindowContext) -> bool:
        """True si este adaptador sabe leer la ventana indicada."""
        ...

    def read(self, ctx: WindowContext) -> Capture | None:
        """Lee la seleccion, o None si no hay nada seleccionado."""
        ...

    def write(self, ctx: WindowContext, capture: Capture, text: str) -> None:
        """Reemplaza la seleccion original por `text`. Lanza si no puede."""
        ...

    def release(self, capture: Capture) -> None:
        """
        Restaura lo que el adaptador haya tenido que alterar.

        Se llama SIEMPRE, se haya escrito o no. El caso que importa: si la
        correccion se rechaza, el portapapeles del usuario tiene que quedar
        igual, no con el texto que se copio para poder leerlo.
        """
        ...
