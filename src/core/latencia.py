"""
Tracker de latencia por proveedor.

Mantiene un historial movil de las ultimas N respuestas por proveedor y
calcula el promedio. Se usa para:

- Mostrar latencia promedio en el resumen de la bandeja.
- Avisar visualmente cuando un proveedor esta lento (promedio > 8s).

No se persiste en disco: el historial vive solo mientras la app esta
corriendo.

Uso:

    tracker = LatencyTracker(window=5)
    tracker.registrar("nvidia", 1.2)
    tracker.registrar("gemini", 0.8)
    print(tracker.promedio("nvidia"))  # 1.2
"""

from __future__ import annotations

import threading
from collections import deque
from typing import Protocol

VENTANA_POR_DEFECTO = 5
UMBRAL_LENTO_S = 8.0


class Registro(Protocol):
    etiqueta: str
    segundos: float


class LatencyTracker:
    """Historial movil de latencias por proveedor."""

    def __init__(self, window: int = VENTANA_POR_DEFECTO) -> None:
        self._window = window
        self._historial: dict[str, deque[float]] = {}
        self._lock = threading.Lock()

    def registrar(self, proveedor: str, segundos: float) -> None:
        """Agrega una medicion al historial del proveedor."""
        with self._lock:
            if proveedor not in self._historial:
                self._historial[proveedor] = deque(maxlen=self._window)
            self._historial[proveedor].append(segundos)

    def promedio(self, proveedor: str) -> float | None:
        """
        Promedio movil de los ultimos N tiempos.

        None si no hay datos para ese proveedor.
        """
        with self._lock:
            historial = self._historial.get(proveedor)
        if not historial:
            return None
        return sum(historial) / len(historial)

    def es_lento(self, proveedor: str) -> bool:
        """True si el promedio movil supera el umbral de alerta."""
        prom = self.promedio(proveedor)
        return prom is not None and prom > UMBRAL_LENTO_S

    def ultimo_provedor(self) -> str | None:
        """El proveedor con mas datos registrados (el "actual" del usuario)."""
        with self._lock:
            if not self._historial:
                return None
            return max(self._historial, key=lambda k: len(self._historial[k]))

    def resumen(self, proveedor_actual: str) -> str:
        """
        Una linea de texto para mostrar en la bandeja.

        Ejemplos:
          "Activo · IA · NVIDIA 1.2s (lent@)"
          "Activo · IA · Gemini 3.4s"
        """
        prom = self.promedio(proveedor_actual)
        if prom is None:
            return ""
        lento = self.es_lento(proveedor_actual)
        etiqueta = " (lent@)" if lento else ""
        return f"{proveedor_actual} {prom:.1f}s{etiqueta}"


# Singleton: una sola instancia global para todos los Estados.
LATENCIA_TRACKER = LatencyTracker()
