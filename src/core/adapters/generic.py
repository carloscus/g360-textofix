"""
Adaptador generico para el resto de aplicaciones (Bloc de notas, navegador,
correo, editores, consolas).

## Por que el portapapeles sigue siendo el camino de escritura

UI Automation tiene dos patrones y no sirven para lo mismo:

- `TextPattern.GetSelection()` si devuelve el texto REALMENTE resaltado. Es la
  unica forma de saber que selecciono el usuario.
- `ValuePattern` devuelve el valor COMPLETO del control. Sirve para un campo
  de formulario entero, pero no puede expresar "solo estos caracteres".

El Bloc de notas de Windows 11, por ejemplo, expone `ValuePattern` y NO
`TextPattern`. Leer con `ValuePattern` y reescribir con `SetValue()` borraria
todo lo que el usuario no habia seleccionado. Por eso aqui:

- Lectura: `TextPattern` si hay seleccion soportada; si no, portapapeles.
- Escritura: siempre portapapeles, porque el pegado respeta la seleccion.

Word y Excel si tienen adaptador propio por COM, donde la seleccion es exacta.

## Nota sobre el portapapeles

Se guarda lo que hubiera antes de pegar y se restaura despues, para no dejar
el texto corregido en el portapapeles del usuario.
"""

from __future__ import annotations

import logging
import time

import uiautomation as auto

from ..logsetup import LOGGER_NAME
from ..winapi import (
    clipboard_copy_from_app,
    clipboard_paste_into_app,
    clipboard_read,
    clipboard_soportado,
    clipboard_write,
    marcar_clipboard,
)
from .base import Capture

log = logging.getLogger(LOGGER_NAME)

# Ventanas donde nunca se debe inyectar entrada ni escribir.
_EXCLUIDOS = {
    "explorer.exe",
    "dwm.exe",
    "shellexperiencehost.exe",
    "startmenuexperiencehost.exe",
    "textinputhost.exe",
    "logonui.exe",
}


class GenericAdapter:
    """UIA para leer la seleccion; portapapeles para escribir."""

    name = "generic"

    def __init__(self, clipboard_timeout_ms: int = 400, paste_settle_ms: int = 60):
        self.clipboard_timeout_ms = clipboard_timeout_ms
        self.paste_settle_ms = paste_settle_ms

    def matches(self, ctx) -> bool:
        return ctx.process.lower() not in _EXCLUIDOS

    # --- UIA (solo lectura) -------------------------------------------------

    def _focused(self):
        try:
            return auto.GetFocusedControl()
        except Exception as exc:
            # Fallo tipico: COM sin inicializar en este hilo. No se propaga
            # porque el portapapeles todavia puede funcionar, pero conviene
            # que se vea en vez de degradar en silencio.
            log.warning("UIA no disponible en este hilo: %s", exc)
            return None

    def _read_uia(self) -> Capture | None:
        """
        Lee la seleccion real via TextPattern.

        Devuelve None si el control no soporta seleccion por UIA: en ese caso
        no se sabe que selecciono el usuario y hay que ir al portapapeles.
        """
        ctrl = self._focused()
        if ctrl is None:
            return None

        pattern = ctrl.GetPattern(auto.PatternId.TextPattern)
        if pattern is None:
            log.debug("el control enfocado no expone TextPattern")
            return None

        try:
            if not pattern.SupportedTextSelection:
                log.debug("TextPattern sin soporte de seleccion")
                return None

            seleccion = pattern.GetSelection()
            # GetSelection devuelve una LISTA de TextRange (puede haber mas de
            # una seleccion). Y el rango no expone `.Text`: hay que pedirlo
            # con GetText(-1), que "-1" significa "hasta el final".
            rangos = seleccion if isinstance(seleccion, (list, tuple)) else [seleccion]

            partes = []
            for rango in rangos:
                if rango is None:
                    continue
                if hasattr(rango, "Text"):
                    partes.append(rango.Text or "")
                else:
                    partes.append(rango.GetText(-1) or "")
            text = "".join(partes)

            if text.strip():
                return Capture(text=text, meta={"via": "uia-text"})
        except Exception as exc:
            log.debug("uia TextPattern fallo: %s", exc)

        return None

    def _read_valor_entero(self, ctx) -> Capture | None:
        """
        Ultimo recurso: el VALOR COMPLETO del control.

        Se llega aqui solo cuando fallaron los dos caminos precisos, y hay
        frameworks donde es la unica opcion:

        - Flutter (Flet) dibuja el texto el mismo, no expone TextPattern y
          tampoco responde al Ctrl+C sintetico, asi que no hay forma de saber
          que selecciono el usuario.
        - Algunos controles de Chromium en paginas con frameworks pesados.

        El precio es que se corrige y se reescribe el campo ENTERO. No se pierde
        texto (todo el contenido se conserva y se corrige), pero si el usuario
        habia seleccionado solo una parte, esa intencion se ignora. Por eso va
        al final de la cadena y no antes del portapapeles: en el Bloc de notas,
        por ejemplo, el portapapeles si funciona y respeta la seleccion parcial.

        Y solo se usa si el control NO expone TextPattern Y la app nunca ha
        respondido a un Ctrl+C sintetico. Si expone TextPattern y dice que no
        hay nada seleccionado, es que el usuario no selecciono nada y hay que
        respetarlo; si la app ya demostro que copia, tambien sabemos que un
        fallo significa "no hay seleccion". Sin esas dos condiciones, apretar el
        atajo con solo el cursor reescribiria el documento entero.
        """
        ctrl = self._focused()
        if ctrl is None:
            return None

        if ctrl.GetPattern(auto.PatternId.TextPattern) is not None:
            # La app SABI decirnos la seleccion y dijo que no hay ninguna.
            return None

        if clipboard_soportado(ctx.process):
            # Ya sabemos que esta app copia con Ctrl+C: si no salio nada, es
            # que el usuario no tiene nada seleccionado.
            return None

        patron = ctrl.GetPattern(auto.PatternId.ValuePattern)
        if patron is None:
            return None

        try:
            if patron.IsReadOnly:
                return None

            valor = patron.Value or ""
            if not valor.strip():
                return None

            if "\n" in valor or "\r" in valor:
                # Campo de varias lineas: SetValue podria aplanarlo y perder
                # los saltos. No se arriesga.
                log.info("campo multilinea: se omite la correccion del campo entero")
                return None

            log.info(
                "sin seleccion detectable: se corrige el campo entero (%d caracteres)",
                len(valor),
            )
            return Capture(text=valor, meta={"via": "uia-value"})
        except Exception as exc:
            log.debug("uia ValuePattern fallo: %s", exc)
            return None

    # --- Ciclo --------------------------------------------------------------

    def read(self, ctx) -> Capture | None:
        capture = self._read_uia()
        if capture is not None:
            return capture

        log.debug("sin seleccion via UIA: se usa el portapapeles")
        previo = clipboard_read()
        text = clipboard_copy_from_app(self.clipboard_timeout_ms)
        # Si la app respondio con algo, queda registrada como "copia bien".
        # Sirve para no confundir despues "no hay seleccion" con "no entiende
        # Ctrl+C", que en Flutter/Flet son indistinguibles a simple vista.
        marcar_clipboard(ctx.process, bool(text))

        if not text or not text.strip():
            # Puede que el Ctrl+C haya copiado algo (por ejemplo solo espacios)
            # y por eso no haya nada utilizable. En ese caso el portapapeles
            # quedo modificado y `run_once` va a retornar antes de poder llamar
            # a release(), asi que se restaura aqui.
            if text is not None and previo is not None:
                clipboard_write(previo)

            # Ultimo recurso: controles donde no hay ninguna forma de saber la
            # seleccion (Flutter/Flet entre otros). Corrige el campo entero.
            return self._read_valor_entero(ctx)

        return Capture(text=text, meta={"via": "clipboard", "clipboard_previo": previo})

    def write(self, ctx, capture: Capture, text: str) -> None:
        if capture.meta.get("via") == "uia-value":
            # Campo entero: se escribe entero, que es lo que se leyo.
            ctrl = self._focused()
            if ctrl is None:
                raise RuntimeError("el control enfocado se perdio antes de escribir")
            patron = ctrl.GetPattern(auto.PatternId.ValuePattern)
            if patron is None or patron.IsReadOnly:
                raise RuntimeError("el control ya no acepta escritura")
            patron.SetValue(text)
            log.debug("escrito el campo completo via ValuePattern")
            return

        # Si la lectura fue por UIA, el portapapeles todavia es del usuario y
        # hay que acordarse de su valor ANTES de que el pegado lo pise.
        if capture.meta.get("clipboard_para_restaurar") is None:
            previo = capture.meta.get("clipboard_previo")
            if previo is None:
                previo = clipboard_read()
            capture.meta["clipboard_para_restaurar"] = previo

        # El pegado respeta la seleccion, que es justo lo que queremos.
        if not clipboard_paste_into_app(text):
            raise RuntimeError("no se pudo escribir en el portapapeles")
        time.sleep(self.paste_settle_ms / 1000.0)

    def release(self, capture: Capture) -> None:
        """
        Devuelve el portapapeles a lo que habia antes de que pasaramos por el.

        Importa igual que se haya escrito o no: leer la seleccion de muchas apps
        exige copiarla, y si despues la correccion se rechaza, el usuario se
        queda con su portapapeles cambiado sin haberlo pedido.
        """
        previo = capture.meta.get("clipboard_previo")
        if previo is None:
            previo = capture.meta.get("clipboard_para_restaurar")
        if previo is None:
            return
        clipboard_write(previo)
        log.debug("portapapeles restaurado")
