"""
Avisos sonoros. Sin dependencias: `winsound` viene en la stdlib.

Se usan tonos distintos en vez de `MessageBeep` para poder diferenciar de un
golpe de oido: grave y corto = error, agudo = ok.
"""

from __future__ import annotations

import winsound

# (frecuencia Hz, duracion ms)
_TONE_OK = (1400, 70)
_TONE_NO_SELECTION = (600, 120)
_TONE_ERROR = (350, 220)

_muted = False


def set_muted(muted: bool) -> None:
    global _muted
    _muted = muted


def _play(tone: tuple[int, int]) -> None:
    if _muted:
        return
    freq, ms = tone
    try:
        winsound.Beep(freq, ms)
    except RuntimeError:
        # Sin altavoz (sesion remota / entorno virtual): no es fatal.
        pass


def ok() -> None:
    """La correccion se aplico."""
    _play(_TONE_OK)


def no_selection() -> None:
    """No habia texto seleccionado: no se modifico nada."""
    _play(_TONE_NO_SELECTION)


def error() -> None:
    """Fallo la correccion: el original quedo intacto."""
    _play(_TONE_ERROR)
