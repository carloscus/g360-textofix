"""
Correccion con Gemini (Etapa 2).

Reglas de diseno:

- El prompt es deliberadamente CONSERVADOR. Un corrector que reescribe es peor
  que uno que no corrige, porque el usuario tiene que revisar cada cambio.
- Cualquier fallo (red, cuota, respuesta rara) devuelve None y el llamador
  conserva el texto original. Nunca se escribe una respuesta sin validar: las
  guardas de `guards.py` son la ultima linea de defensa, no la primera.
- La clave se lee del almacén cifrado de Windows (o del entorno en
  desarrollo) y jamas se loguea.
"""

from __future__ import annotations

import logging
import os
import time

from .logsetup import LOGGER_NAME, describe

log = logging.getLogger(LOGGER_NAME)

MODELO_POR_DEFECTO = "gemini-3.8-flash"


def _clave_almacenada() -> str | None:
    """
    La clave del almacén cifrado de Windows, si hay.

    Si `perfil` no puede cargarse (instalacion rota, permisos), se devuelve
    None y se sigue buscando en el entorno: una carpeta de perfil ilegible no
    tiene que tumbar el corrector.
    """
    try:
        from .perfil import leer_clave_api

        return leer_clave_api()
    except Exception as exc:
        log.debug("no se pudo leer el almacén de la clave: %s", exc)
        return None


class CuotaAgotada(RuntimeError):
    """La API rechazo la peticion por cuota. No es un fallo del corrector."""


def _es_cuota(exc: Exception) -> bool:
    texto = str(exc)
    return "429" in texto or "RESOURCE_EXHAUSTED" in texto


def _espera_sugerida(exc: Exception) -> int | None:
    """La API indica cuanto esperar, en segundos."""
    import re

    encontrado = re.search(r'retryDelay["\']?\s*[:=]\s*["\']?(\d+)', str(exc))
    return int(encontrado.group(1)) if encontrado else None


def _mensaje_de_cuota(exc: Exception) -> str:
    """Explica el problema en castellano, sin el muro de JSON de la API."""
    if "FreeTier" in str(exc):
        return (
            "Se agoto la cuota GRATUITA de Gemini (5 peticiones por minuto).\n"
            "Activa la facturacion en Google AI Studio: ademas de quitar el "
            "limite, es lo que evita que tus textos se usen para entrenar el "
            "modelo o sean revisados por personas."
        )
    return "Se agoto la cuota de Gemini API. Revisa tu plan en Google AI Studio."


PROMPT = """\
Eres un corrector de ortografia y gramatica en espanol PERUANO, para texto \
de trabajo (correos, informes, mensajes a clientes).

Tu unico trabajo es devolver el texto corregido, conservando el significado, el \
vocabulario y el estilo original.

Reglas:
1. Corrige SOLO ortografia, tildes, mayusculas, puntuacion y gramatica.
2. NO reformules, NO resumas, NO anadas ni quites ideas.
3. NO inventes ni cambies nombres, fechas, cifras, codigos, unidades ni \
   simbolos de moneda.
4. NO traduzcas.
5. NO cambies el registro: si el texto es formal, queda formal; si es \
   informal, queda informal.
6. NO cambies el vocabulario por variantes regionales. El espanol peruano es \
   correcto tal cual: "computadora" no es "ordenador", "combustible" no es \
   "gasolina", "bus" no es "autobus", "celular" no es "movil". Si una palabra \
   no es un error de escritura, se deja como esta.
7. Respeta intactos: URLs, correos, rutas de archivo, codigos, SKU, etiquetas \
   como @menciones, hashtags, emoticonos, fechas (dd/mm/aaaa), montos con "S/" \
   y saltos de linea.
8. Si el texto ya esta correcto, devuelvelo tal cual, sin commentary ni nota.
9. Devuelve SOLO el texto corregido. Sin comillas, sin explicaciones, sin \
   "aqui tienes", sin listas y sin bloques de codigo.

Ejemplos:
- "Hola, gracias por su atencion" -> "Hola, gracias por su atencion."   (SI: punto)
- "Hola, gracias por su atencion" -> "Hola, gracias por su atencion. \
   Cordialmente, el area de ventas."  (NO: no inventes el cierre)
- "La reunion es el 12/05" -> "La reunion es el 13/05"  (NUNCA: no cambies \
   la fecha)
- "El monto es S/ 1,250.00" -> "El monto es S/ 1250,00"  (NUNCA: no toques \
   el formato de la moneda)
- "Adjuntamos la factura en formato PDF" -> "Adjuntamos la factura en formato \
   Word"  (NUNCA: no cambies el contenido)

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
        """
        La clave, en este orden.

        1. La dada explicitamente (para tests y para la bandeja).
        2. El almacén cifrado de Windows (DPAPI), que es lo que usa el .exe.
        3. El entorno o el .env, que es lo comodo en desarrollo.

        El orden importa: el almacen cifrado manda sobre .env, asi que quien
        cambio la clave desde la bandeja no sigue usando la vieja por tener un
        .env olvidado al lado.

        Se lee en cada llamada, sin cachear: es un archivo pequeno y se consulta
        una vez por correccion, antes de una llamada de red que la eclipsa. El
        cachearlo dejaria la instancia corriendo con la clave vieja despues de
        cambiarla desde la bandeja, que es un fallo silencioso y caro.
        """
        if self._api_key:
            return self._api_key
        return _clave_almacenada() or os.environ.get("GEMINI_API_KEY") or None

    def disponible(self) -> tuple[bool, str]:
        """Si se puede usar, y por que no si no."""
        if not self.api_key:
            return False, (
                "falta la clave de Gemini: se pide al arrancar o desde "
                "'Configurar clave API...' en la bandeja"
            )
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

        respuesta = self._pedir(cliente, config, texto)

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

    def _pedir(self, cliente, config, texto: str):
        """
        Llama al modelo, esperando si se topa con el limite de cuota.

        La cuota gratuita permite 5 peticiones por minuto. La de pago es mucho
        mayor, pero reintentar igual hace que la herramienta sirva en los dos
        casos sin cambiar el codigo.
        """
        espera = 0
        for intento in range(3):
            try:
                return cliente.models.generate_content(
                    model=self.modelo,
                    contents=PROMPT + texto,
                    config=config,
                )
            except Exception as exc:
                if not _es_cuota(exc) or intento == 2:
                    raise CuotaAgotada(_mensaje_de_cuota(exc)) from exc
                espera = _espera_sugerida(exc) or 15
                log.warning(
                    "cuota alcanzada: se reintenta en %ds (intento %d/2)", espera, intento + 1
                )
                time.sleep(espera)
        raise RuntimeError("no se llego a hacer la consulta")

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
