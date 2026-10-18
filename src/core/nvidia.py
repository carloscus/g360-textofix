"""
Correccion con un modelo de la nube via NVIDIA NIM.

NVIDIA NIM expone una API OpenAI-compatible: POST /v1/chat/completions.
Solo se usan modelos con endpoint gratuito que respondan de verdad: el
listado /v1/models trae 81, pero varios devuelven 404 al llamarlos.

Medicion del 18/10/2026 (5 casos de la bateria del proyecto, timeout 15s):

    nvidia/nemotron-3-super-120b-a12b       4/5 OK, mediana 0.97s, max 1.34s
    meta/llama-3.2-90b-vision-instruct      1/5 OK, 2-11s, colgados a 15s
    nvidia/nemotron-3.5-lightning-30b-a3b   responde 4s pero no corrige y
                                            se cuelga a ratos
    z-ai/glm-5.3-flash                      si responde, ~58s: inviable
    deepseek-ai/deepseek-v4.1-flash         no responde
    mistral-7b, gemma-3-4b, granite-3b,
    nemotron-51b                            listados pero 404

Por eso el nemotron-super va PRIMERO (el mas rapido y el mejor puntaje) y
el 90b queda como respaldo, con otra familia de modelo.

Sobre el texto: SI sale de la maquina (va a la nube). Si la privacidad es el
motivo, este proveedor no es para textos sensibles.
- La clave se lee de NIM_API_KEY (o del almacen cifrado) y jamas se loguea.
"""

from __future__ import annotations

import logging
import os
import time

from .logsetup import LOGGER_NAME, describe

log = logging.getLogger(LOGGER_NAME)

URL_POR_DEFECTO = "https://integrate.api.nvidia.com/v1/chat/completions"
MODELO_POR_DEFECTO = "nvidia/nemotron-3-super-120b-a12b"
# Respaldo: otra familia por si el primero no responde o anda mal. En la
# medicion el 90b responde en 2-11s cuando no se cuelga; su fama de "mejor
# calidad" no se reprodujo (1/5 en la bateria, y reescribio el formato de
# moneda S/ 4,500.00 -> S/ 4.500,00).
MODELOS_DE_REPALDO = ["meta/llama-3.2-90b-vision-instruct"]


class NIMCorrupta(RuntimeError):
    """La API de NVIDIA reviento (clave invalida, sin red, cuota)."""


class ProveedorNIM:
    """Correccion con un modelo NVIDIA NIM, por la nube."""

    def __init__(
        self,
        modelo: str | None = None,
        url: str | None = None,
        api_key: str | None = None,
        timeout_s: int = 15,
    ):
        self.modelo = modelo or os.environ.get("NIM_MODEL") or MODELO_POR_DEFECTO
        self.url = url or os.environ.get("NIM_URL") or URL_POR_DEFECTO
        self._api_key = api_key
        # 15s: en la medicion los buenos respondieron en <=11s (el super en
        # ~1s) y a 15s se corta cualquier modelo colgado. Peor caso de la
        # cadena (2 modelos): 30s, y despues el engine cae a Gemini. Con el
        # viejo timeout de 120s ese peor caso eran 4 minutos.
        self.timeout_s = timeout_s

    # --- Configuracion ------------------------------------------------------

    @property
    def api_key(self) -> str | None:
        """La clave, en este orden: la dada explicitamente, el entorno, o el almacen."""
        if self._api_key:
            return self._api_key
        clave_env = os.environ.get("NIM_API_KEY")
        if clave_env:
            return clave_env
        try:
            from .perfil import leer_clave_nim

            return leer_clave_nim()
        except Exception:
            return None

    def disponible(self) -> tuple[bool, str]:
        """Si se puede usar, y por que no si no."""
        if not self.api_key:
            return False, (
                "falta la clave de NVIDIA NIM: se pide al arrancar, o se pone "
                "NIM_API_KEY en .env / 'Configurar clave NIM...' en la bandeja"
            )
        try:
            import httpx  # noqa: F401
        except ImportError:
            return False, "falta la dependencia: uv sync --extra ai (trae httpx)"
        return True, ""

    # --- Correccion ---------------------------------------------------------

    def corregir(self, texto: str) -> str | None:
        """Devuelve el texto corregido, o None si no se pudo."""
        listo, motivo = self.disponible()
        if not listo:
            raise NIMCorrupta(motivo)

        import httpx

        from .ai import PROMPT  # mismo prompt conservador

        inicio = time.monotonic()
        mensaje = self._pedir(httpx, PROMPT, texto)

        transcurrido = time.monotonic() - inicio
        log.info(
            "nvidia respondio en %.2fs (%s -> %s)",
            transcurrido,
            describe(texto),
            describe(mensaje),
        )
        return mensaje

    def _pedir(self, httpx, prompt: str, texto: str) -> str | None:
        """
        Llama a la API y devuelve el texto de respuesta.

        Prueba la cadena de modelos en orden (el default, y los de
        respaldo). Un modelo saturado (timeout) o retirado (404/410) no
        aborta la correccion: se pasa al siguiente. Si la cadena entera
        falla, se levanta NIMCorrupta y el engine decide que hacer.

        Los modelos de razonamiento (Nemotron) gastan tokens pensando en
        `reasoning_content`, y con pocos tokens el `content` llega vacio.
        `thinking: False` lo evita; si el modelo no conoce el parametro,
        se reintenta sin el. Para corregir ortografia no hace falta pensar.
        """
        cadena = [self.modelo] + [m for m in MODELOS_DE_REPALDO if m != self.modelo]
        ultimo_error: Exception | None = None

        for modelo in cadena:
            try:
                mensaje = self._pedir_un_modelo(httpx, modelo, prompt, texto)
            except httpx.TimeoutException as exc:
                log.warning(
                    "nvidia %s no respondio en %ds: se prueba el respaldo",
                    modelo,
                    self.timeout_s,
                )
                ultimo_error = exc
                continue
            except httpx.HTTPStatusError as exc:
                log.warning(
                    "nvidia %s devolvio %s: se prueba el respaldo",
                    modelo,
                    exc.response.status_code,
                )
                ultimo_error = exc
                if exc.response.status_code in (401, 403):
                    # Clave mala: el respaldo usa la misma, no se gasta
                    # otra llamada en comprobarlo.
                    break
                continue

            if mensaje is not None:
                return mensaje
            # Respondio pero sin content (razono y se quedo sin tokens):
            # se prueba el siguiente modelo de la cadena.
            log.warning("nvidia %s devolvio content vacio", modelo)

        raise NIMCorrupta(
            f"ningun modelo de NIM respondio ({len(cadena)} probados): "
            f"ultimo error {type(ultimo_error).__name__ if ultimo_error else '-'}"
        ) from ultimo_error

    def _pedir_un_modelo(self, httpx, modelo: str, prompt: str, texto: str) -> str | None:
        """Una sola llamada a un modelo. Devuelve el texto, o None si no hay."""
        base = {
            "model": modelo,
            "messages": [
                {"role": "system", "content": prompt},
                {"role": "user", "content": texto},
            ],
            "max_tokens": 500,
            "temperature": 0.5,
            "top_p": 1.0,
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        def _contenido(resp) -> str | None:
            eleccion = (resp.json().get("choices") or [{}])[0]
            return (eleccion.get("message") or {}).get("content", "").strip() or None

        # Primero con thinking apagado: corrige igual y gasta la mitad.
        con_thinking = {**base, "chat_template_kwargs": {"thinking": False}}
        respuesta = httpx.post(self.url, headers=headers, json=con_thinking, timeout=self.timeout_s)
        if respuesta.status_code == 400:
            # El modelo no conoce el parametro: se reintenta basico.
            respuesta = httpx.post(self.url, headers=headers, json=base, timeout=self.timeout_s)
        respuesta.raise_for_status()
        mensaje = _contenido(respuesta)

        if mensaje is None:
            # El modelo razono y se quedo sin tokens para el contenido:
            # reintento basico con mas margen.
            log.warning("nvidia %s devolvio content vacio: se reintenta sin thinking", modelo)
            respuesta = httpx.post(self.url, headers=headers, json=base, timeout=self.timeout_s)
            mensaje = _contenido(respuesta)
        return mensaje

    def probar(self, texto: str) -> dict:
        """Corrige sin escribir nada. Sirve para medir la calidad del prompt."""
        return {"original": texto, "corregido": self.corregir(texto)}
