"""
Correccion con Gemini (Etapa 2).

Reglas de diseno:

- El prompt es deliberadamente CONSERVADOR. Un corrector que reescribe es peor
  que uno que no corrige, porque el usuario tiene que revisar cada cambio.
- Cualquier fallo (red, cuota, respuesta rara) devuelve None y el llamador
  conserva el texto original. Nunca se escribe una respuesta sin validar: las
  guardas de `guards.py` son la ultima linea de defensa, no la primera.
- La clave se lee del entorno y jamas se loguea.
"""

from __future__ import annotations

import logging
import os
import time

from .logsetup import LOGGER_NAME, describe

log = logging.getLogger(LOGGER_NAME)

MODELO_POR_DEFECTO = "gemini-3.8-flash"

PROMPT = """\
Eres un corrector de ortografia y gramatica en espanol. Tu unico trabajo es \
devolver el texto corregido, conservando el significado y el estilo original.

Reglas:
1. Corrige solo ortografia, tildes, mayusculas, puntuacion y gramatica.
2. NO reformules, NO resumas, NO anadas ni quites ideas.
3. NO inventes ni cambies nombres, fechas, cifras, codigos o unidades.
4. NO traduzcas.
5. NO cambies el estilo: si el texto es informal, queda informal.
6. Respeta intactos: URLs, correos, rutas de archivo, codigos,SKU, etiquetas \
como @menciones, hashtags, emoticonos y saltos de linea.
7. Si el texto ya esta correcto, devuelvelo tal cual, sin commentary ni nota.

Ejemplos de lo que NO hay que hacer:
- "Hola, gracias por su atencion" -> "Hola, gracias por su atencion."  (si)
- "Hola, gracias por su atencion" -> "Estimado usuario, gracias por su atencion."  (NO)
- "La reunion es el 12/05" -> "La reunion es el 13/05"  (NUNCA)
8. Devuelve SOLO el texto corregido. Sin comillas, sin explicaciones, sin \
"aqui tienes", sin listas, sin bloques de codigo.

Texto:
"""


class CorrectorIA:
    """Envoltura del cliente de Gemini con lo minimo que necesita el corrector."""

    def __init__(
        self,
        modelo: str = MODELO_POR_DEFECTO,
        timeout_s: int = 8,
        api_key: str | None = None,
    ):
        self.modelo = modelo
        self.timeout_s = timeout_s
        self._api_key = api_key
        self._cliente = None

    # --- Configuracion ------------------------------------------------------

    @property
    def api_key(self) -> str | None:
        return self._api_key or os.environ.get("GEMINI_API_KEY") or None

    def disponible(self) -> tuple[bool, str]:
        """Si se puede usar, y por que no si no."""
        if not self.api_key:
            return False, "falta GEMINI_API_KEY (ponela en .env)"
        try:
            import google.genai  # noqa: F401
        except ImportError:
            return False, "falta la dependencia: uv sync --extra ai"
        return True, ""

    def _obtener_cliente(self):
        if self._cliente is None:
            from google import genai

            self._cliente = genai.Client(api_key=self.api_key)
        return self._cliente

    # --- Correccion ---------------------------------------------------------

    def corregir(self, texto: str) -> str | None:
        """
        Devuelve el texto corregido, o None si no se pudo.

        None significa "no se sabe": el llamador conserva el original.
        """
        listo, motivo = self.disponible()
        if not listo:
            raise RuntimeError(motivo)

        from google.genai import types

        cliente = self._obtener_cliente()
        inicio = time.monotonic()

        config = types.GenerateContentConfig(
            temperature=0.1,
            top_p=0.9,
            # Para corregir no hace falta "pensar": baja la latencia y el costo.
            thinking_config=types.ThinkingConfig(thinking_level="low"),
        )

        respuesta = cliente.models.generate_content(
            model=self.modelo,
            contents=PROMPT + texto,
            config=config,
        )

        transcurrido = time.monotonic() - inicio
        candidato = self._texto_de(respuesta)
        log.info(
            "gemini %s respondio en %.2fs (%s -> %s)",
            self.modelo,
            transcurrido,
            describe(texto),
            describe(candidato),
        )
        return candidato

    @staticmethod
    def _texto_de(respuesta) -> str | None:
        """
        Saca el texto de la respuesta, o None si no hay nada util.

        `response.text` es None cuando el modelo se bloquea o no devuelve
        contenido; a veces hay que armarlo desde las partes.
        """
        texto = getattr(respuesta, "text", None)
        if texto:
            return texto
        try:
            partes = respuesta.candidates[0].content.parts or []
        except Exception:
            return None
        armado = "".join(p.text for p in partes if getattr(p, "text", None))
        return armado or None

    def probar(self, texto: str) -> dict:
        """Corrige sin escribir nada. Sirve para medir la calidad del prompt."""
        return {"original": texto, "corregido": self.corregir(texto)}
