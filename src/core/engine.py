"""
Motor: el ciclo completo de una correccion.

    elegir adaptador -> leer -> corregir -> validar -> escribir -> avisar

Invariante: si algo falla en cualquier paso, el texto original queda intacto y
se avisa con un tono de error. Nunca se escribe una respuesta sin validar.
"""

from __future__ import annotations

import contextlib
import logging
from dataclasses import dataclass

from . import feedback
from .adapters import Capture, build_adapters, pick_adapter
from .config import Config
from .guards import Verdict, validate
from .logsetup import LOGGER_NAME, describe
from .winapi import WindowContext, foreground_context, puede_inyectar

log = logging.getLogger(LOGGER_NAME)


@contextlib.contextmanager
def com_inicializado():
    """
    Prepara COM en el hilo actual para que UI Automation funcione.

    UI Automation es COM, y COM hay que inicializarlo POR HILO. El atajo
    dispara la correccion en un hilo de trabajo precisamente para no congelar
    el bucle de mensajes, asi que sin esto UIA falla con
    "CoInitialize has not been called" y el corrector se queda sin poder leer
    la seleccion.

    En el hilo principal no hace falta, pero inicializarlo ahi es inofensivo.
    """
    try:
        import uiautomation as auto
    except ImportError:  # pragma: no cover
        yield
        return

    try:
        with auto.UIAutomationInitializerInThread():
            # Warm-up: la primera vez que uiautomation toca COM en este hilo
            # dispara la advertencia "CoInitialize has not been called".
            # Si se hace AQUI dentro del contexto, la advertencia queda
            # contenida y los llamadores siguientes no la ven.
            try:
                auto.GetFocusedControl()
            except Exception:
                # Se espera que falle si no hay ninguna ventana: lo que
                # importa es que la inicializacion ya esta lista.
                pass
            yield
    except OSError as exc:  # pragma: no cover
        # Sin COM no hay UIA, pero el adaptador generico todavia puede
        # funcionar por portapapeles. Se sigue, no se aborta.
        log.debug("COM no disponible, se sigue por portapapeles: %s", exc)
        yield


@dataclass(frozen=True)
class Outcome:
    """Como termino un intento. `reason` va al log, no a ningun archivo."""

    ok: bool
    reason: str
    adapter: str = ""
    chars: int = 0


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


def correct(text: str, mode: str, transform: str, modelo: str | None = None) -> str | None:
    """
    Produce la version corregida del texto.

    En modo `mock` no hay IA: devuelve el texto igual (o entrecomillado con
    `wrap`), que es lo que permite validar la mecanica sin gastar API.

    En modo `ia` llama a Gemini. `modelo`, si se da, manda sobre el default.
    Si algo falla devuelve None y el llamador conserva el original: fallar
    es siempre preferible a escribir cualquier cosa.
    """
    if mode == "mock":
        return mock_correct(text, transform)

    if mode == "ia":
        global _local_en_ultimo_pedido
        from .proovedor import es_ollama, seleccion_proveedor

        prov = seleccion_proveedor()
        _local_en_ultimo_pedido = es_ollama(prov)

        # Si el usuario fijo un modelo por --modelo (o OLLAMA_MODEL), lo
        # aplica solo al proovedor Ollama. En Gemini, el modelo va por GEMINI_MODEL.
        if es_ollama(prov) and modelo:
            prov.modelo = modelo

        try:
            return prov.corregir(text)
        except Exception as exc:
            # La caida solo existe cuando el proovedor original es Ollama
            # y reviento. Si el original ya era nube, reintentar no sirve:
            # se propaga el fallo.
            if not es_ollama(prov):
                raise
            log.warning("Ollama fallo (%s): se cae a la nube", exc)
            return _nube(modelo).corregir(text)

    raise NotImplementedError(f"modo de correccion desconocido: {mode}")


# --- Ciclo -------------------------------------------------------------------


def run_once(
    cfg: Config,
    mode: str = "mock",
    transform: str = "roundtrip",
    al_corregir=None,
    modelo: str | None = None,
) -> Outcome:
    """
    Ejecuta una correccion sobre lo que este seleccionado en pantalla.

    `al_corregir(original, corregido, proceso)` se invoca solo si se llego a
    escribir. `modelo`, si se da, manda sobre el default de `correct()`.
    Los textos nunca se loguean, pero deshacer necesita el par en memoria:
    por eso viajan por el callback y no por el log.
    """
    with com_inicializado():
        return _ciclo(cfg, mode, transform, al_corregir, modelo)


def _ciclo(
    cfg: Config, mode: str, transform: str, al_corregir, modelo: str | None = None
) -> Outcome:
    """El ciclo de la correccion. Ver `run_once`."""
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
        outcome = _corregir_y_escribir(
            adapter, ctx, cfg, capture, mode, transform, al_corregir, modelo
        )

        # HIBRIDO: si la correccion local fue RECHAZADA por las guardas
        # (se acorto, se "charlo", invento), se reintenta la misma accion
        # con el proveedor de nube, que es mas confiable con el prompt
        # conservador. El usuario no elige: si el local no confia, la
        # nube lo respalda en el mismo pedido.
        if (
            not outcome.ok
            and outcome.reason not in ("sin-seleccion", "sin-cambios", "fallo-lectura")
            and mode == "ia"
            and _usaba_local()
        ):
            log.info("la guarda rechazo la correccion local: se reintenta por la nube")
            outcome = _reintentar_por_nube(
                adapter, ctx, cfg, capture, mode, transform, al_corregir, modelo
            )

        return outcome
    finally:
        # Siempre, se haya escrito o no: deja el portapapeles como estaba.
        # Si la correccion se rechaza, el usuario no debe quedarse con su
        # portapapeles cambiado por nuestra cuenta.
        try:
            adapter.release(capture)
        except Exception as exc:
            log.debug("release fallo en %s: %s", adapter.name, exc)


def _corregir_y_escribir(
    adapter, ctx, cfg, capture, mode, transform, al_corregir, modelo: str | None = None
) -> Outcome:
    """Corrige, valida y, si todo cuadra, reemplaza. Ver `run_once`."""
    original = capture.text
    try:
        candidate = correct(original, mode, transform, modelo=modelo)
    except NotImplementedError:
        feedback.error()
        return Outcome(False, "sin-modo-de-correccion", adapter=adapter.name)
    except Exception as exc:
        # Falta la clave, se agoto la cuota, fallo la red: cualquier cosa.
        # El original se conserva intacto.
        log.warning("la correccion fallo: %s", exc)
        feedback.error()
        return Outcome(False, "fallo-correccion", adapter=adapter.name)

    if candidate is None:
        log.warning("la IA no devolvio texto")
        feedback.error()
        return Outcome(False, "sin-respuesta-ia", adapter=adapter.name)

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
    if al_corregir is not None:
        try:
            al_corregir(original, candidate, ctx.process.lower() if ctx else "")
        except Exception:
            log.exception("el seguimiento de la correccion fallo")
    return Outcome(True, "escrito", adapter=adapter.name, chars=len(original))


def _nube(modelo: str | None = None) -> object:
    """
    El proovedor de nube para la caida: NVIDIA NIM si tiene clave, si no
    Gemini. El `modelo` dado (por --modelo u OLLAMA_MODEL) no aplica a la
    nube: cada nube tiene sus propios nombres de modelo.
    """
    from .proovedor import seleccion_nube

    return seleccion_nube()


# --- Hibrido: local primero, nube como respaldo -----------------------------
#
# La correccion local (Ollama) es rapida y offline, pero un modelo chico a
# veces "charla" o acorta el texto, y las guardas lo rechazan. La respuesta
# no es dejar el texto intacto (correcto, pero incompleto): es reintentar
# por la nube, que es mas confiable con el prompt conservador. El usuario
# no elige: si el local no confia, la nube lo respalda en el mismo pedido.

_local_en_ultimo_pedido = False


def _usaba_local() -> bool:
    """Si el ultimo pedido de la correccion fue con el proveedor local."""
    return _local_en_ultimo_pedido


def _reintentar_por_nube(
    adapter, ctx, cfg, capture, mode, transform, al_corregir, modelo: str | None = None
) -> Outcome:
    """
    Vuelve a correr la correccion, forzando el proveedor de nube.

    El texto del control no se vuelve a leer: ya esta en `capture`. Solo se
    re-corrige y se re-valida. Si la nube tampoco confía, se deja el
    original: es mejor no escribir que escribir algo malo.
    """
    global _local_en_ultimo_pedido
    _local_en_ultimo_pedido = False

    from .guards import validate as _validate
    from .proovedor import seleccion_nube

    original = capture.text
    try:
        candidate = seleccion_nube().corregir(original)
    except Exception as exc:
        log.warning("la correccion por la nube fallo: %s", exc)
        feedback.error()
        return Outcome(False, "fallo-correccion-nube", adapter=adapter.name)

    if candidate is None:
        log.warning("la nube no devolvió texto")
        feedback.error()
        return Outcome(False, "sin-respuesta-nube", adapter=adapter.name)

    verdict = _validate(original, candidate)
    if not verdict.ok:
        # La nube tampoco confié: se deja el original. La guarda sigue
        # mandando, que es la ultima linea de defensa.
        log.warning("la nube tampoco confió (%s): se deja el original", verdict.reason)
        feedback.error()
        return Outcome(False, verdict.reason, adapter=adapter.name, chars=len(original))

    if not verdict.changed:
        feedback.ok()
        return Outcome(True, "sin-cambios", adapter=adapter.name, chars=len(original))

    try:
        adapter.write(ctx, capture, candidate)
    except Exception as exc:
        log.warning("fallo escribiendo (nube): %s", exc)
        feedback.error()
        return Outcome(False, "fallo-escritura", adapter=adapter.name, chars=len(original))

    feedback.ok()
    log.info(
        "corregido por la nube en %s (%s -> %s)",
        adapter.name,
        describe(original),
        describe(candidate),
    )
    if al_corregir is not None:
        try:
            al_corregir(original, candidate, ctx.process.lower() if ctx else "")
        except Exception:
            log.exception("el seguimiento de la correccion (nube) fallo")
    return Outcome(True, "escrito", adapter=adapter.name, chars=len(original))


def aplicar_texto(texto: str) -> Outcome:
    """
    Escribe `texto` en la seleccion actual, sin pasar por la IA.

    Es lo que usan deshacer y rehacer: no se trata de corregir, sino de
    devolver el texto a un estado anterior. Comparte el camino de lectura y
    escritura con la correccion, asi que respeta las mismas garantias: si no
    hay seleccion, no se escribe nada.
    """
    ctx = foreground_context()
    if ctx is None:
        feedback.error()
        return Outcome(False, "sin-ventana-activa")

    if not puede_inyectar(ctx):
        feedback.error()
        return Outcome(False, "uipi-bloqueado")

    adapter = pick_adapter(build_adapters(Config.from_env()), ctx)
    if adapter is None:
        feedback.error()
        return Outcome(False, "sin-adaptador")

    try:
        capture = adapter.read(ctx)
    except Exception as exc:
        log.warning("fallo leyendo con %s: %s", adapter.name, exc)
        feedback.error()
        return Outcome(False, "fallo-lectura", adapter=adapter.name)

    if capture is None or not capture.text.strip():
        feedback.no_selection()
        return Outcome(False, "sin-seleccion", adapter=adapter.name)

    try:
        adapter.write(ctx, capture, texto)
    except Exception as exc:
        log.warning("fallo escribiendo con %s: %s", adapter.name, exc)
        feedback.error()
        return Outcome(False, "fallo-escritura", adapter=adapter.name)
    finally:
        try:
            adapter.release(capture)
        except Exception as exc:
            log.debug("release fallo: %s", exc)

    feedback.ok()
    log.info("texto aplicado en %s (%s)", adapter.name, describe(texto))
    return Outcome(True, "escrito", adapter=adapter.name, chars=len(texto))


def texto_en_pantalla(ctx: WindowContext | None = None) -> str | None:
    """
    Lee el texto del control enfocado, para comprobar si el usuario lo cambio.

    Se usa para invalidar el bucle de deshacer: si el texto ya no es el que
    dejamos, deshacer escribiria encima de lo que el usuario puso despues.
    """
    ctx = ctx or foreground_context()
    if ctx is None:
        return None
    try:
        adapter = pick_adapter(build_adapters(Config.from_env()), ctx)
        if adapter is None:
            return None
        leer = getattr(adapter, "_texto_del_control", None)
        return leer() if callable(leer) else None
    except Exception:
        return None


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
