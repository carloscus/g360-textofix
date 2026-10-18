"""
Avisos sonoros. Sin dependencias: `winsound` viene en la stdlib.

Tres WAV cortos, sintetizados por `tools/generar_sonidos.py`, con envolvente
suave (ataque rapido y caida exponencial): no es el bip de onda cuadrada
del sistema, sino un sonido de interfaz actual. Se distinguen de un golpe
de oido: ok = dos notas ascendentes, sin seleccion = nota media corta,
error = golpe grave amortiguado.

Se reproducen CON PlaySound SND_ASYNC: no bloquean el ciclo de correccion
(winsound.Beep si lo bloqueaba 70-220 ms por correccion).

Reservas: si falta el WAV (build raro) se cae al Beep del sistema; si no
hay dispositivo de audio (sesion remota, entorno virtual), silencio.
"""

from __future__ import annotations

import sys
import winsound
from pathlib import Path

# nombre logico -> archivo
SONIDOS = {
    "ok": "ok.wav",
    "sin-seleccion": "sin-seleccion.wav",
    "error": "error.wav",
}

# Reserva si el WAV no existe: el tono viejo del sistema.
_BEEPS = {
    "ok": (1400, 70),
    "sin-seleccion": (600, 120),
    "error": (350, 220),
}

_muted = False


def set_muted(muted: bool) -> None:
    global _muted
    _muted = muted


def ruta_sonido(nombre: str) -> Path | None:
    """
    Busca el WAV, tanto en desarrollo como dentro del .exe.

    PyInstaller extrae los datos a una carpeta temporal y publica la ruta en
    sys._MEIPASS; sin eso el .exe no encontraria los sonidos.
    """
    base = getattr(sys, "_MEIPASS", None)
    candidatas = []
    if base:
        candidatas.append(Path(base) / "assets" / "sonidos" / SONIDOS[nombre])
    aqui = Path(__file__).resolve().parents[2] / "assets" / "sonidos" / SONIDOS[nombre]
    candidatas.append(aqui)

    for ruta in candidatas:
        if ruta.exists():
            return ruta
    return None


def _play(nombre: str) -> None:
    if _muted:
        return
    ruta = ruta_sonido(nombre)
    if ruta is not None:
        try:
            winsound.PlaySound(
                str(ruta),
                winsound.SND_FILENAME | winsound.SND_ASYNC | winsound.SND_NODEFAULT,
            )
            return
        except RuntimeError:
            # Sin dispositivo de audio: no es fatal.
            return
    try:
        winsound.Beep(*_BEEPS[nombre])
    except RuntimeError:
        pass


def ok() -> None:
    """La correccion se aplico."""
    _play("ok")


def no_selection() -> None:
    """No habia texto seleccionado: no se modifico nada."""
    _play("sin-seleccion")


def error() -> None:
    """Fallo la correccion: el original quedo intacto."""
    _play("error")
