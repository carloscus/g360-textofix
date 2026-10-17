"""
Configuracion del corrector.

Solo lee variables de entorno. La Etapa 1 no necesita ninguna: el corrector
arranca y funciona sin configuracion previa.

Los campos de la Etapa 2 (Gemini) estan declarados pero NO se consumen todavia:
se agregan cuando exista la facturacion. Ver README > Etapa 2.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field

# Modificadores y teclas de Windows (winuser.h)
MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_WIN = 0x0008
MOD_NOREPEAT = 0x4000

VK_E = 0x45
VK_ESCAPE = 0x1B


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "si", "sí", "on"}


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


@dataclass(frozen=True)
class Hotkey:
    """Atajo global. Por defecto Ctrl+Shift+E."""

    modifiers: int = MOD_CONTROL | MOD_SHIFT | MOD_NOREPEAT
    virtual_key: int = VK_E
    label: str = "Ctrl+Shift+E"


@dataclass(frozen=True)
class Config:
    hotkey: Hotkey = field(default_factory=Hotkey)

    # Espera a que la app destino responda al Ctrl+C sintetico.
    clipboard_timeout_ms: int = 400

    # Espera a que la aplicacion procese el pegado.
    paste_settle_ms: int = 60

    # Cuanto texto se considera una seleccion valida.
    min_chars: int = 1

    # Suena al corregir / fallar. Para pruebas se puede apagar.
    sound: bool = True

    # Activado/desactivado desde la bandeja (Etapa 3).
    enabled: bool = True

    # Verbose activa el detalle de adaptadores en consola.
    verbose: bool = False

    # --- Etapa 2 (Gemini). Declarados, todavia no consumidos. ---
    gemini_model: str = os.environ.get("GEMINI_MODEL", "gemini-3.8-flash")
    gemini_timeout_s: int = _env_int("GEMINI_TIMEOUT_S", 8)

    @classmethod
    def from_env(cls) -> Config:
        return cls(
            sound=_env_bool("TEXTOFIX_SOUND", True),
            enabled=_env_bool("TEXTOFIX_ENABLED", True),
            verbose=_env_bool("TEXTOFIX_VERBOSE", False),
            clipboard_timeout_ms=_env_int("TEXTOFIX_CLIPBOARD_TIMEOUT_MS", 400),
        )
