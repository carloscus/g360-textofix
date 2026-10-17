"""
Proveedores de IA para el corrector.

Dos opciones:

- **Gemini** (`ai.py`): por la nube. Cada correccion gasta cuota y depende de
  la red. El default de este proyecto.
- **Ollama** (`ollama.py`, este modulo): un modelo local. El texto no sale de
  la maquina, no hay cuota y funciona offline. Necesita Ollama corriendo.

El contrato es el mismo: `ProveedorIA.corregir(texto) -> str | None`. Cualquier
proveedor que cumpla eso puede ser probado con la bateria (`--bateria`) y
usado en el ciclo del corrector.
"""

from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass

from .logsetup import LOGGER_NAME, describe

log = logging.getLogger(LOGGER_NAME)

# El modelo local mas liviano que entiende instrucciones en espanol y corrige
# ortografia. "liviano" es relativo: 3B en Q4 en CPU son unos 2-5 GB de RAM
# y 1-3 s por correccion. Mas chico (1B) pierde la instruccion del prompt.
OLLAMA_MODELO_POR_DEFECTO = "llama3.2:3b"
OLLAMA_URL_POR_DEFECTO = "http://127.0.0.1:11434"


@dataclass
class RespuestaProveedor:
    """Respuesta de un proveedor, sin depender del tipo concreto del modelo."""

    texto: str | None
    modelo: str
    segundos: float


class OllamaCorrupta(RuntimeError):
    """La maquina local no esta corriendo Ollama o no tiene el modelo."""


class ProveedorOllama:
    """
    Correccion con un modelo local via Ollama.

    Ventajas frente a Gemini:
      - La clave no existe. No hay cuota, no hay red, el texto no sale.
      - Sin modelo descargado: falla una vez y se detiene (no reintentos).
    Desventajas:
      - Necesita Ollama instalado y el modelo descargado.
      - Es lento en CPU: 1-3 s por correccion con 3B en Q4.
    """

    def __init__(
        self,
        modelo: str = OLLAMA_MODELO_POR_DEFECTO,
        url: str | None = None,
        timeout_s: int = 30,
    ):
        self.modelo = modelo
        self.url = (url or os.environ.get("OLLAMA_URL") or OLLAMA_URL_POR_DEFECTO).rstrip("/")
        self.timeout_s = timeout_s

    # --- Configuracion ------------------------------------------------------

    def disponible(self) -> tuple[bool, str]:
        """Si hay Ollama corriendo y el modelo descargado."""
        try:
            import httpx  # noqa: F401
        except ImportError:
            return False, "falta la dependencia: uv sync --extra ai"

        if not self._ollama_arriba():
            return False, (
                "Ollama no esta corriendo. Ejecutalo y asegurate de que el "
                "modelo este descargado: ollama pull llama3.2:3b"
            )
        return True, ""

    def _ollama_arriba(self) -> bool:
        import httpx

        try:
            return httpx.get(f"{self.url}/api/tags", timeout=2.0).status_code == 200
        except Exception:
            return False

    # --- Correccion ---------------------------------------------------------

    def corregir(self, texto: str) -> str | None:
        """Devuelve el texto corregido, o None si no se pudo."""
        listo, motivo = self.disponible()
        if not listo:
            raise OllamaCorrupta(motivo)

        import httpx

        from .ai import PROMPT  # mismo prompt conservador

        inicio = time.monotonic()
        respuesta = httpx.post(
            f"{self.url}/api/chat",
            json={
                "model": self.modelo,
                "messages": [
                    {"role": "system", "content": PROMPT},
                    {"role": "user", "content": texto},
                ],
                "stream": False,
                "options": {
                    "temperature": 0.1,
                    "top_p": 0.9,
                },
            },
            timeout=self.timeout_s,
        )
        respuesta.raise_for_status()
        cuerpo = respuesta.json()
        mensaje = (cuerpo.get("message") or {}).get("content", "").strip() or None

        transcurrido = time.monotonic() - inicio
        log.info(
            "ollama %s respondio en %.2fs (%s -> %s)",
            self.modelo,
            transcurrido,
            describe(texto),
            describe(mensaje),
        )
        return mensaje

    def probar(self, texto: str) -> dict:
        """Corrige sin escribir nada. Sirve para medir la calidad del prompt."""
        return {"original": texto, "corregido": self.corregir(texto)}
