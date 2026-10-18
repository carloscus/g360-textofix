"""
Verificacion de la API: una llamada minima que confirma clave, modelo y red.

Sirve para dos momentos:

- Al guardar una clave (bandeja o prompt de arranque): que se valide de una
  vez, no en la primera correccion con el usuario esperando.
- Con `--probar-api`: re-verificar cuando cambie la clave o el modelo
  (GEMINI_MODEL / NIM_MODEL).

No escribe nada en pantalla el modulo: devuelve resultados y decide el
llamador que hacer con ellos. El texto de prueba es "hola": corto a proposito,
porque el ping gasta tokens de la cuota.
"""

from __future__ import annotations

import time

TEXTO_DE_PRUEBA = "hola"

# Para el ping no hace falta la espera de correccion real: un proveedor que
# no responde en 15s no sirve para corregir en vivo de todas formas.
TIMEOUT_PING_S = 15


def probar_gemini(api_key: str | None = None) -> dict:
    """Verifica la clave de Gemini con una llamada real, sin esperas de cuota."""
    from .ai import CorrectorIA

    # reintentos=0: un 429 se reporta de una, no se duerme 120s en un ping.
    return _verificar("gemini", CorrectorIA(api_key=api_key, reintentos=0))


def probar_nvidia(api_key: str | None = None) -> dict:
    """Verifica la clave de NVIDIA NIM con una llamada real."""
    from .nvidia import ProveedorNIM

    return _verificar("nvidia", ProveedorNIM(api_key=api_key, timeout_s=TIMEOUT_PING_S))


def probar_todo() -> list[dict]:
    """Las dos nubes: la que no tenga clave sale como 'falta la clave'."""
    return [probar_nvidia(), probar_gemini()]


def _verificar(nombre: str, prov) -> dict:
    """
    Una llamada real al proveedor. Devuelve:
    {"etiqueta", "ok", "detalle", "segundos"}.

    `ok` solo si el proveedor respondio con texto. Un error de red, una
    clave rechazada (401) o un modelo retirado (404) salen en `detalle`
    traducidos a un motivo accionable.
    """
    listo, motivo = prov.disponible()
    if not listo:
        return {"etiqueta": nombre, "ok": False, "detalle": motivo, "segundos": 0.0}

    inicio = time.monotonic()
    try:
        salida = prov.corregir(TEXTO_DE_PRUEBA)
    except Exception as exc:
        return {
            "etiqueta": nombre,
            "ok": False,
            "detalle": _diagnostico(exc),
            "segundos": time.monotonic() - inicio,
        }

    segundos = time.monotonic() - inicio
    if not salida:
        return {
            "etiqueta": nombre,
            "ok": False,
            "detalle": "respondio sin texto (bloqueo del modelo?)",
            "segundos": segundos,
        }
    return {"etiqueta": nombre, "ok": True, "detalle": "clave y modelo OK", "segundos": segundos}


def _diagnostico(exc: Exception) -> str:
    """
    Traduce el error de la API a un motivo que se pueda actuar.

    Se mira tambien la causa: NIM envuelve el HTTPStatusError (que trae el
    401/404 real) en un NIMCorrupta generico, y el mensaje propio de
    CuotaAgotada ya dice "cuota" sin traer el 429.
    """
    texto = f"{exc} {exc.__cause__ or ''}"
    bajo = texto.lower()
    if "401" in texto or "API_KEY_INVALID" in texto or "UNAUTHENTICATED" in texto:
        return "clave rechazada (401): no sirve, vuelve a pegarla"
    if "404" in texto or "410" in texto or "NOT_FOUND" in texto:
        return "modelo inexistente o retirado (404): revisa GEMINI_MODEL / NIM_MODEL"
    if "429" in texto or "RESOURCE_EXHAUSTED" in texto or "cuota" in bajo:
        return "cuota agotada (429): la clave sirve, espera y reintenta"
    return f"{type(exc).__name__}: {texto[:120]}"


def linea(resultado: dict) -> str:
    """Una linea de reporte: [OK] nvidia: clave y modelo OK (1.2s)."""
    marca = "OK   " if resultado["ok"] else "FALLO"
    return (
        f"[{marca}] {resultado['etiqueta']}: {resultado['detalle']} ({resultado['segundos']:.1f}s)"
    )


def sin_clave(resultado: dict) -> bool:
    """Si el fallo es solo 'no hay clave' (no un error de la API)."""
    return not resultado["ok"] and "falta la clave" in resultado["detalle"]


def imprimir(resultado: dict) -> None:
    """Reporta a consola, con la marca de SIN CLAVE cuando solo falta la clave."""
    if sin_clave(resultado):
        print(f"[SIN CLAVE] {resultado['etiqueta']}: configurala desde la bandeja o en .env")
    else:
        print(linea(resultado))
