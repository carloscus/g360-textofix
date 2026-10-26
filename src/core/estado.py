"""
Estado del corrector: activo/inactivo, modo, y deshacer/rehacer.

Es un modulo PURO, sin imports de Windows, para poder testear la logica de
deshacer sin montar interfaces.

Sobre el búfer:

- Guarda UN solo par (original, corregido). No es historial: se pierde al
  cerrar y nunca toca disco.
- Se invalida si el usuario edita el texto despues. Escribir el original sobre
  lo que el usuario acaba de escribir seria peor que no deshacer.
- Deshacer y rehacer exigen que la ventana activa siga siendo la misma donde
  se corrigio. Si el usuario cambio de aplicacion, se toca el tono de error y
  no se escribe nada.
"""

from __future__ import annotations

from dataclasses import dataclass

MOTIVOS = {
    "ok": "listo",
    "nada-que-deshacer": "no hay nada que deshacer",
    "nada-que-rehacer": "no hay nada que rehacer",
    "app-cambiada": "cambio de ventana: no se escribe nada",
    "texto-cambiado": "el texto cambio: deshacer ya no aplica",
    "nunca-corregido": "todavia no se corrigio nada",
}

# Variantes alternativas por atajo: la mejor correccion + 2 alternativas.
# Cada variante es una llamada de red aparte, pedida solo si el usuario
# insiste apretando el atajo sobre el texto ya corregido.
MAX_VARIANTES = 2


@dataclass(frozen=True)
class Correccion:
    """Una correccion aplicada, con lo necesario para revertirla o repetirla."""

    proceso: str  # proceso donde se corrigio
    original: str
    corregido: str
    escrito: str = ""  # lo que quedo realmente en pantalla
    valido: bool = True

    def __post_init__(self):
        if not self.escrito:
            object.__setattr__(self, "escrito", self.corregido)


@dataclass
class Estado:
    """Estado compartido del corrector. Un solo hilo lo lee; el worker lo escribe."""

    activo: bool = True
    modo: str = "mock"
    _correccion: Correccion | None = None
    _deshecho: bool = False
    # Variantes pedidas sobre la correccion vigente (ver puede_ciclar).
    _variantes: int = 0
    ultima_razon: str = ""

    # --- Correccion ---------------------------------------------------------

    def registrar_correccion(self, correccion: Correccion) -> None:
        """
        Guarda la ultima correccion como deshacible.

        Si la nueva correccion parte del texto que nosotros escribimos (es
        una variante del mismo pedido), se cuenta para limitar el ciclo;
        cualquier otra correccion arranca el conteo de cero.
        """
        encadenada = (
            self._correccion is not None
            and correccion.proceso == self._correccion.proceso
            and correccion.original == self._correccion.corregido
        )
        self._variantes = (self._variantes + 1) if encadenada else 0
        self._correccion = correccion
        self._deshecho = False
        self.ultima_razon = MOTIVOS["ok"]

    def comprobar_cambio(self, texto_actual: str | None) -> None:
        """
        Invalida el búfer si el texto ya no es el que dejamos.

        Es la red que evita que "Deshacer" pise lo que el usuario escribio
        despues de nuestra correccion.
        """
        if self._correccion is None or not self._correccion.valido:
            return
        if texto_actual is not None and texto_actual != self._correccion.escrito:
            self._correccion = None
            self._deshecho = False
            self.ultima_razon = MOTIVOS["texto-cambiado"]

    # --- Consulta -----------------------------------------------------------

    def puede_deshacer(self) -> bool:
        return self._correccion is not None and not self._deshecho

    def puede_rehacer(self) -> bool:
        return self._correccion is not None and self._deshecho

    def hay_correccion(self) -> bool:
        return self._correccion is not None

    # --- Latencia -----------------------------------------------------------

    def registrar_latencia(self, proveedor: str, segundos: float) -> None:
        """Agrega una medicion al tracker de latencia."""
        from .latencia import LATENCIA_TRACKER

        LATENCIA_TRACKER.registrar(proveedor, segundos)

    # --- Variantes (el mismo atajo, otra correccion) ------------------------

    def puede_ciclar(self, texto_actual: str) -> bool:
        """
        Si lo que hay en pantalla es exactamente lo que nosotros escribimos.

        Es el mismo criterio que protege a deshacer: si el usuario toco el
        texto, no se pide variante de nada (se corrije lo que hay).
        """
        return (
            self._correccion is not None
            and not self._deshecho
            and texto_actual == self._correccion.escrito
        )

    def variantes_agotadas(self) -> bool:
        """Si ya se dieron las MAX_VARIANTES alternativas de esta correccion."""
        return self._variantes >= MAX_VARIANTES

    def texto_original(self) -> str | None:
        """El original de la correccion vigente: la base para pedir variantes."""
        return self._correccion.original if self._correccion is not None else None

    # --- Deshacer / rehacer -------------------------------------------------

    def preparar_deshacer(self, proceso_actual: str) -> tuple[str | None, str]:
        """
        Decide que escribir al deshacer.

        Devuelve (texto, motivo). Texto None significa no hacer nada.
        """
        if self._correccion is None:
            return None, MOTIVOS["nunca-corregido"]
        if self._deshecho:
            return None, MOTIVOS["nada-que-deshacer"]
        if self._correccion.proceso != proceso_actual:
            return None, MOTIVOS["app-cambiada"]

        self._deshecho = True
        self._correccion = dataclass_replace_escrito(self._correccion, self._correccion.original)
        self.ultima_razon = MOTIVOS["ok"]
        return self._correccion.original, MOTIVOS["ok"]

    def preparar_rehacer(self, proceso_actual: str) -> tuple[str | None, str]:
        """Decide que escribir al rehacer. Simetrico a `preparar_deshacer`."""
        if self._correccion is None:
            return None, MOTIVOS["nunca-corregido"]
        if not self._deshecho:
            return None, MOTIVOS["nada-que-rehacer"]
        if self._correccion.proceso != proceso_actual:
            return None, MOTIVOS["app-cambiada"]

        self._deshecho = False
        self._correccion = dataclass_replace_escrito(self._correccion, self._correccion.corregido)
        self.ultima_razon = MOTIVOS["ok"]
        return self._correccion.corregido, MOTIVOS["ok"]

    def revertir_preparacion(self) -> None:
        """
        Deshace el cambio de estado hecho por preparar_deshacer/rehacer.

        Se llama si la escritura falla: si no, el búfer creeria que se aplico
        algo que no se escribio.
        """
        if self._correccion is None:
            return
        self._deshecho = not self._deshecho
        if self._deshecho:
            self._correccion = dataclass_replace_escrito(
                self._correccion, self._correccion.original
            )
        else:
            self._correccion = dataclass_replace_escrito(
                self._correccion, self._correccion.corregido
            )

    # --- Vista para la bandeja ----------------------------------------------

    def resumen(self) -> str:
        if not self.activo:
            return "Inactivo"
        modo = "IA" if self.modo == "ia" else "Demo"
        from .latencia import LATENCIA_TRACKER

        proveedor = LATENCIA_TRACKER.ultimo_provedor() or "—"
        extra = LATENCIA_TRACKER.resumen(proveedor)
        if extra:
            return f"Activo · Modo {modo} · {extra}"
        return f"Activo · Modo {modo} · {proveedor}"


def dataclass_replace_escrito(correccion: Correccion, texto: str) -> Correccion:
    return Correccion(
        proceso=correccion.proceso,
        original=correccion.original,
        corregido=correccion.corregido,
        escrito=texto,
        valido=correccion.valido,
    )
