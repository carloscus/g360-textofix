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
from pathlib import Path


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


def cargar_dotenv(ruta: Path | None = None) -> bool:
    """
    Lee un .env sencillo y lo pasa al entorno.

    A proposito no se usa python-dotenv: son seis lineas y asi el proyecto no
    gana una dependencia solo para leer la clave. Las variables ya presentes en
    el entorno tienen prioridad, que es lo esperable.
    """
    ruta = ruta or (Path.cwd() / ".env")
    if not ruta.exists():
        return False

    try:
        for linea in ruta.read_text(encoding="utf-8").splitlines():
            linea = linea.strip()
            if not linea or linea.startswith("#") or "=" not in linea:
                continue
            clave, _, valor = linea.partition("=")
            clave = clave.strip()
            valor = valor.strip().strip("'\"")
            if clave and clave not in os.environ:
                os.environ[clave] = valor
    except OSError:
        return False
    return True


@dataclass(frozen=True)
class Config:

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

    # --- Etapa 2 (Gemini) ---
    gemini_model: str = field(
        default_factory=lambda: os.environ.get("GEMINI_MODEL", "gemini-3.8-flash")
    )
    gemini_timeout_s: int = field(default_factory=lambda: _env_int("GEMINI_TIMEOUT_S", 8))

    @classmethod
    def from_env(cls) -> Config:
        return cls(
            sound=_env_bool("TEXTOFIX_SOUND", True),
            enabled=_env_bool("TEXTOFIX_ENABLED", True),
            verbose=_env_bool("TEXTOFIX_VERBOSE", False),
            clipboard_timeout_ms=_env_int("TEXTOFIX_CLIPBOARD_TIMEOUT_MS", 400),
        )
