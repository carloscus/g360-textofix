"""
Tests de los avisos sonoros (`core.feedback`).

Nunca suena de verdad: PlaySound/Beep se patean. Lo que se cubre es la
ruta de decision: mute, WAV encontrado, y la reserva con Beep si falta.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import winsound

import core.feedback as fb


def _patear_reproduccion(monkeypatch) -> tuple[list, list]:
    llamadas_sonido: list = []
    llamadas_beep: list = []
    monkeypatch.setattr(
        fb.winsound, "PlaySound", lambda ruta, flags: llamadas_sonido.append((ruta, flags))
    )
    monkeypatch.setattr(fb.winsound, "Beep", lambda freq, ms: llamadas_beep.append((freq, ms)))
    return llamadas_sonido, llamadas_beep


def test_los_tres_wav_existen():
    for nombre in ("ok", "sin-seleccion", "error"):
        ruta = fb.ruta_sonido(nombre)
        assert ruta is not None, f"falta assets/sonidos/{fb.SONIDOS[nombre]}"
        assert ruta.exists()


def test_ok_reproduce_el_wav_asincrono(monkeypatch):
    monkeypatch.setattr(fb, "_muted", False)
    sonido, _ = _patear_reproduccion(monkeypatch)

    fb.ok()

    assert len(sonido) == 1
    ruta, flags = sonido[0]
    assert ruta.endswith("ok.wav")
    assert flags & winsound.SND_ASYNC
    assert flags & winsound.SND_FILENAME
    assert flags & winsound.SND_NODEFAULT


def test_los_tres_avisos_usan_su_archivo(monkeypatch):
    monkeypatch.setattr(fb, "_muted", False)
    sonido, _ = _patear_reproduccion(monkeypatch)

    fb.ok()
    fb.no_selection()
    fb.error()

    usados = [Path(r).name for r, _ in sonido]
    assert usados == ["ok.wav", "sin-seleccion.wav", "error.wav"]


def test_mute_no_reproduce_nada(monkeypatch):
    monkeypatch.setattr(fb, "_muted", True)
    sonido, beep = _patear_reproduccion(monkeypatch)

    fb.ok()
    fb.no_selection()
    fb.error()

    assert sonido == []
    assert beep == []


def test_sin_wav_cae_al_beep_del_sistema(monkeypatch):
    monkeypatch.setattr(fb, "_muted", False)
    monkeypatch.setattr(fb, "ruta_sonido", lambda _nombre: None)
    _, beep = _patear_reproduccion(monkeypatch)

    fb.ok()

    assert beep == [fb._BEEPS["ok"]]
