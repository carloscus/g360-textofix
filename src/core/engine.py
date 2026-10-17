"""
Motor: el ciclo completo de una correccion.

    elegir adaptador -> leer -> corregir -> validar -> escribir -> avisar

Invariante: si algo falla en cualquier paso, el texto original queda intacto y
se avisa con un tono de error. Nunca se escribe una respuesta sin validar.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from . import feedback
from .adapters import Capture, build_adapters, pick_adapter
from .config import Config
from .guards import Verdict, validate
from .logsetup import LOGGER_NAME, describe
from .winapi import WindowContext, foreground_context, puede_inyectar

log = logging.getLogger(LOGGER_NAME)


@dataclass(frozen=True)
class Outcome:
    """Como termino un intento. `reason` va al log, no a ningun archivo."""

    ok: bool
    reason: str
    adapter: str = ""
    chars: int = 0

    @property
    def should_write(self) -> bool:
        return self.ok and self.reason == "escrito"


# --- Corrector ---------------------------------------------------------------
# Etapa 1: no hay IA. El modo simulado devuelve el texto para comprobar que
# el ciclo capturar -> escribir funciona de punta a punta.


def mock_correct(text: str, transform: str) -> str:
    """
    Sustituto determinista para probar sin IA.

    - `roundtrip`: devuelve el texto igual. Si el documento queda igual, la
      lectura y la escritura funcionaron.
    - `wrap`: envuelve en comillas angulares. Se ve a simple vista donde se
      escribio, para confirmar la posicion.
    """
    if transform == "wrap":
        return f"«{text}»"
    return text


def correct(text: str, mode: str, transform: str) -> str:
    """Punto deextension para la Etapa 2 (Gemini)."""
    if mode == "mock":
        return mock_correct(text, transform)
    raise NotImplementedError("la correccion con IA llega en la Etapa 2; usar --mock en la Etapa 1")


# --- Ciclo -------------------------------------------------------------------


def run_once(cfg: Config, mode: str = "mock", transform: str = "roundtrip") -> Outcome:
    """Ejecuta una correccion sobre lo que este seleccionado en pantalla."""
    ctx = foreground_context()
    if ctx is None:
        feedback.error()
        return Outcome(False, "sin-ventana-activa")

    log.debug("ventana en primer plano: %s", ctx.label)

    if not puede_inyectar(ctx):
        # UIPI: la app corre como administrador y este proceso no. Ni UIA ni
        # el portapapeles van a funcionar, asi que se avisa en vez de fallar
        # en silencio.
        feedback.error()
        return Outcome(False, "uipi-bloqueado")

    adapters = build_adapters(cfg)
    adapter = pick_adapter(adapters, ctx)
    if adapter is None:
        feedback.error()
        return Outcome(False, "sin-adaptador")

    try:
        capture: Capture | None = adapter.read(ctx)
    except Exception as exc:
        log.warning("fallo leyendo con %s: %s", adapter.name, exc)
        feedback.error()
        return Outcome(False, "fallo-lectura", adapter=adapter.name)

    if capture is None or len(capture.text.strip()) < cfg.min_chars:
        log.info("sin seleccion en %s", ctx.label)
        feedback.no_selection()
        return Outcome(False, "sin-seleccion", adapter=adapter.name)

    original = capture.text
    log.debug("leido via %s: %s", adapter.name, describe(original))

    try:
        return _corregir_y_escribir(adapter, ctx, cfg, capture, mode, transform)
    finally:
        # Siempre, se haya escrito o no: deja el portapapeles como estaba.
        # Si la correccion se rechaza, el usuario no debe quedarse con su
        # portapapeles cambiado por nuestra cuenta.
        try:
            adapter.release(capture)
        except Exception as exc:
            log.debug("release fallo en %s: %s", adapter.name, exc)


def _corregir_y_escribir(adapter, ctx, cfg, capture, mode, transform) -> Outcome:
    """Corrige, valida y, si todo cuadra, reemplaza. Ver `run_once`."""
    original = capture.text
    try:
        candidate = correct(original, mode, transform)
    except NotImplementedError:
        feedback.error()
        return Outcome(False, "sin-modo-de-correccion", adapter=adapter.name)
    except Exception as exc:
        log.warning("fallo corrigiendo: %s", exc)
        feedback.error()
        return Outcome(False, "fallo-correccion", adapter=adapter.name)

    verdict: Verdict = validate(original, candidate)
    log.debug("validacion: %s", verdict.reason)

    if not verdict.ok:
        feedback.error()
        return Outcome(False, verdict.reason, adapter=adapter.name, chars=len(original))

    if not verdict.changed:
        # El texto ya estaba bien: no se toca nada.
        feedback.ok()
        return Outcome(True, "sin-cambios", adapter=adapter.name, chars=len(original))

    try:
        adapter.write(ctx, capture, candidate)
    except Exception as exc:
        log.warning("fallo escribiendo con %s: %s", adapter.name, exc)
        feedback.error()
        return Outcome(False, "fallo-escritura", adapter=adapter.name, chars=len(original))

    feedback.ok()
    log.info(
        "corregido en %s (%s -> %s)",
        adapter.name,
        describe(original),
        describe(candidate),
    )
    return Outcome(True, "escrito", adapter=adapter.name, chars=len(original))


def detect_context() -> WindowContext | None:
    """Solo diagnostico: informa que adapter usaria para la ventana actual."""
    ctx = foreground_context()
    if ctx is None:
        return None
    adapter = pick_adapter(build_adapters(Config.from_env()), ctx)
    log.info(
        "ventana=%s pid=%d adaptador=%s uipi=%s",
        ctx.process,
        ctx.pid,
        adapter.name if adapter else "ninguno",
        "ok" if puede_inyectar(ctx) else "BLOQUEADO",
    )
    return ctx
