"""
Registro de adaptadores.

El orden importa: los adaptadores especificos se consultan antes del generico,
porque COM es mas fiable que UIA en Office.
"""

from __future__ import annotations

from ..config import Config
from .base import Adapter, Capture
from .excel import ExcelAdapter
from .generic import GenericAdapter
from .word import WordAdapter


def build_adapters(cfg: Config) -> list[Adapter]:
    """Adaptadores en orden de prioridad."""
    return [
        WordAdapter(),
        ExcelAdapter(),
        GenericAdapter(
            clipboard_timeout_ms=cfg.clipboard_timeout_ms,
            paste_settle_ms=cfg.paste_settle_ms,
        ),
    ]


def pick_adapter(adapters: list[Adapter], ctx) -> Adapter | None:
    """Primer adaptador que sepa manejar la ventana en primer plano."""
    for adapter in adapters:
        try:
            if adapter.matches(ctx):
                return adapter
        except Exception:
            continue
    return None


__all__ = [
    "Adapter",
    "Capture",
    "ExcelAdapter",
    "GenericAdapter",
    "WordAdapter",
    "build_adapters",
    "pick_adapter",
]
