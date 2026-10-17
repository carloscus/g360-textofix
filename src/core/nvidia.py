"""
Correccion con un modelo de la nube via NVIDIA NIM.

NVIDIA NIM expone una API OpenAI-compatible: POST /v1/chat/completions.
Es un proveedor de nube por defecto: corre modelos grandes (llama, mistral,
nemotron) que entienden bien el prompt conservador del proyecto, y su
cupo es mas generoso que el free tier de Gemini.

- El texto SI sale de la maquina (va a la nube). Si la privacidad es el
  motivo, usar Ollama local.
- La clave se lee de NIM_API_KEY (o del almacen cifrado) y jamas se loguea.
"""

from __future__ import annotations

import logging
import os
import time

from .logsetup import LOGGER_NAME, describe

log = logging.getLogger(LOGGER_NAME)

URL_POR_DEFECTO = "https://integrate.api.nvidia.com/v1/chat/completions"
# El modelo de correccion: grande para que resuelva "como"/"cómo" e invente
# pocas palabras. El 90b corrige mejor que el 3b local.
MODELO_POR_DEFECTO = "meta/llama-3.2-90b-vision-instruct"


class NIMCorrupta(RuntimeError):
    """La API de NVIDIA reviento (clave invalida, sin red, cuota)."""


class ProveedorNIM:
    """Correccion con un modelo NVIDIA NIM, por la nube."""

    def __init__(
        self,
        modelo: str | None = None,
        url: str | None = None,
        api_key: str | None = None,
        timeout_s: int = 60,
    ):
        self.modelo = modelo or os.environ.get("NIM_MODEL") or MODELO_POR_DEFECTO
        self.url = url or os.environ.get("NIM_URL") or URL_POR_DEFECTO
        self._api_key = api_key
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
        respuesta = httpx.post(
            self.url,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": self.modelo,
                "messages": [
                    {"role": "system", "content": PROMPT},
                    {"role": "user", "content": texto},
                ],
                "max_tokens": 200,
                "temperature": 0.1,
                "top_p": 0.9,
            },
            timeout=self.timeout_s,
        )
        respuesta.raise_for_status()
        cuerpo = respuesta.json()
        mensaje = (cuerpo.get("choices") or [{}])[0].get("message", {}).get(
            "content", ""
        ).strip() or None

        transcurrido = time.monotonic() - inicio
        log.info(
            "nvidia %s respondio en %.2fs (%s -> %s)",
            self.modelo,
            transcurrido,
            describe(texto),
            describe(mensaje),
        )
        return mensaje

    def probar(self, texto: str) -> dict:
        """Corrige sin escribir nada. Sirve para medir la calidad del prompt."""
        return {"original": texto, "corregido": self.corregir(texto)}
