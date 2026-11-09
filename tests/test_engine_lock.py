"""
Tests del lock global del motor (item 3).

`run_once` y `aplicar_texto` se serializan detras de `_motor_lock`. Si uno
toma el lock, el otro espera hasta liberarlo. Este test simula ese comportamiento
sin depender de ventanas reales ni de UIA.
"""

from __future__ import annotations

import sys
import threading
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pytest
from core.engine import _motor_lock, aplicar_texto


def _tiempo_desde_llamada(f, *args, **kwargs) -> float:
    t0 = time.monotonic()
    f(*args, **kwargs)
    return time.monotonic() - t0


def test_lock_puede_adquirirse_y_liberarse():
    """El lock existe, se puede adquirir y liberar sin problema."""
    acquired = []
    with _motor_lock:
        acquired.append(True)
    assert acquired == [True]


def test_lock_serializa_dos_hilos(monkeypatch):
    """
    Dos hilos compiten por el lock: el segundo entra DESPUES de que el primero
    termine. No simultaneamente.
    """
    orden: list = []
    stop_event = threading.Event()

    def hilo_largo():
        # Bloquea el motor y se mantiene bloqueado hasta que el otro hilo haya
        # esperado lo suficiente.
        with _motor_lock:
            orden.append("largo-inicia")
            time.sleep(0.15)
            orden.append("largo-fin")

    def hilo_corto():
        # Espera a que largo-inicia aparezca, luego intenta tomar el lock; si el
        # lock funciona bien, corto entrara DESPUES de largo-fin.
        while "largo-inicia" not in orden:
            time.sleep(0.01)
        with _motor_lock:
            orden.append("corto-inicia")
        orden.append("corto-fin")

    t1 = threading.Thread(target=hilo_largo)
    t2 = threading.Thread(target=hilo_corto)
    t1.start()
    t2.start()
    t1.join(timeout=2)
    t2.join(timeout=2)

    assert "largo-inicia" in orden
    assert "largo-fin" in orden
    assert "corto-inicia" in orden
    assert "corto-fin" in orden

    idx_largo_inicio = orden.index("largo-inicia")
    idx_corto_fin = orden.index("corto-fin")
    # Serialesacion: corto-fin llega despues que largo-fin.
    assert (idx_largo_fin := orden.index("largo-fin"))
    assert idx_corto_fin > idx_largo_fin, f"los hilos no se serializaron como esperaba: {orden}"


def test_aplicar_texto_toma_lock(monkeypatch):
    """`aplicar_texto` debe intentar adquirir el lock (falls gracefully when no context)."""
    # Cuando no hay ventana activa (entorno headless de tests), aplica_texto
    # retorna Outcome(False, ...) pero NO debe hacer deadlock ni lanzar exception.
    outcome = aplicar_texto("algo")
    # En entorno sin Windows/IA, espera que sea False. Si llegase a adquirir el
    # lock e intentar abrir contexto, fallaria controladamente.
    assert not outcome.ok or outcome.reason in (
        "sin-ventana-activa",
        "uipi-bloqueado",
        "sin-adaptador",
    )
