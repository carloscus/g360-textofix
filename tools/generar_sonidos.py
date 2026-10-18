"""
Genera los tres avisos sonoros del corrector.

Salida: assets/sonidos/{ok,sin-seleccion,error}.wav

Son WAV cortos sintetizados con la stdlib (wave + math), no el bip de onda
cuadrada del sistema: una placa suave con ataque rapido y caida exponencial,
que suena a interfaz actual. Se reproducen con PlaySound SND_ASYNC, asi que
no bloquean el ciclo de correccion (Beep si lo bloqueaba 70-220 ms).

Para regenerar:
    uv run python tools/generar_sonidos.py
"""

from __future__ import annotations

import math
import struct
import wave
from pathlib import Path

FREC = 44100  # Hz
RAIZ = Path(__file__).resolve().parents[1]
DESTINO = RAIZ / "assets" / "sonidos"


def _envolve(muestras: int, tau: float, ataque_ms: float = 4.0) -> list[float]:
    """Ataque lineal corto + caida exponencial (el 'plonk' de las interfaces)."""
    ataque = int(FREC * ataque_ms / 1000)
    env = []
    for i in range(muestras):
        if i < ataque:
            env.append(i / ataque)
        else:
            env.append(math.exp(-(i - ataque) / (FREC * tau)))
    return env


def _nota(freq: float, ms: float, amp: float = 0.45, arm: float = 0.3, tau: float = 0.09):
    """Una nota: seno fundamental + segundo armonico, con envolvente."""
    muestras = int(FREC * ms / 1000)
    env = _envolve(muestras, tau)
    seno = []
    for i in range(muestras):
        t = i / FREC
        v = math.sin(2 * math.pi * freq * t) + arm * math.sin(4 * math.pi * freq * t)
        seno.append(v * env[i] * amp)
    return seno


def _concat(*bloques: list[float], silencio_ms: float = 12.0) -> list[float]:
    hueco = [0.0] * int(FREC * silencio_ms / 1000)
    salida: list[float] = []
    for i, bloque in enumerate(bloques):
        if i:
            salida.extend(hueco)
        salida.extend(bloque)
    return salida


def _wav(nombre: str, muestras: list[float]) -> None:
    """Escribe PCM 16-bit mono, recortando por debajo de 1.0 por seguridad."""
    destino = DESTINO / nombre
    destino.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(destino), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(FREC)
        datos = bytearray()
        for v in muestras:
            v = max(-1.0, min(1.0, v))
            datos += struct.pack("<h", int(v * 32767))
        w.writeframes(bytes(datos))
    print(f"sonido: {destino} ({len(muestras) / FREC * 1000:.0f} ms)")


def principal() -> None:
    # ok: dos notas ascendentes (E5 -> A5), el "listo" de la app.
    _wav("ok.wav", _concat(_nota(659.25, 95, tau=0.07), _nota(880.0, 170, tau=0.10)))

    # sin seleccion: una sola nota media, mas corta y discreta (D5).
    _wav("sin-seleccion.wav", _nota(587.33, 130, amp=0.35, tau=0.08))

    # error: golpe grave y amortiguado (G3 -> F3), presente sin ser agresivo.
    _wav(
        "error.wav",
        _concat(
            _nota(196.0, 110, amp=0.40, arm=0.15, tau=0.06),
            _nota(174.61, 180, amp=0.40, arm=0.15, tau=0.12),
            silencio_ms=6,
        ),
    )


if __name__ == "__main__":
    principal()
