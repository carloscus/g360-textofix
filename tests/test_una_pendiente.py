"""
Cola de UNA sola pulsacion pendiente del atajo y estado visible en bandeja.

Cubre la mejora de UX sobre la latencia real de OpenRouter:

- Una segunda pulsacion durante una correccion se ejecuta exactamente una
  vez al terminar la primera; cualquier pulsacion adicional se descarta.
- `deshacer`/`rehacer` son independientes de `corregir` en `_ocupado`.
- El item de estado de la bandeja muestra "Corrigiendo..." mientras
  `en_curso("corregir")` es True, y vuelve al resumen cuando False (en la
  misma instancia de Bandeja, tanto en exito como en fallo/excepcion).

Se ejecuta con pytest; no necesita RegisterHotKey ni red.
"""

from __future__ import annotations

import sys
import threading
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from core.bandeja import Bandeja
from core.hotkey import EscuchaAtajos


class _EstadoFalso:
    """Estado minimo para Bandeja sin ventana ni atajos reales."""

    def resumen(self) -> str:
        return "OpenRouter (Nemotron) 1.2s"


def _escucha_bloqueada():
    """
    EscuchaAtajos cuyo _al_presionar se bloquea hasta que se libere.

    Devuelve (escucha, bloqueo, liberar) donde:
    - `bloqueo` se pone en cuanto _al_presionar arranca y se libera para dejar
      continuar la ejecucion.
    - `liberar` se pone cuando _al_presionar termina (para sincronizar el test).
    """
    escucha = EscuchaAtajos(
        {
            "corregir": SimpleNamespace(),
            "deshacer": SimpleNamespace(),
            "rehacer": SimpleNamespace(),
        }
    )
    bloqueo = threading.Event()
    liberar = threading.Event()

    def _al_presionar(accion: str) -> None:
        bloqueo.wait()
        liberar.set()

    escucha._al_presionar = _al_presionar
    escucha._bloqueo = bloqueo
    return escucha, bloqueo, liberar


# --- Cola de una sola pulsacion pendiente -------------------------------------


def test_segunda_pulsacion_se_ejecuta_al_terminar():
    """4 disparos durante el bloqueo -> exactamente 2 ejecuciones totales."""
    escucha, bloqueo, liberar = _escucha_bloqueada()
    ejecuciones: list[str] = []

    def _al_presionar(accion: str) -> None:
        ejecuciones.append(accion)
        bloqueo.wait()
        liberar.set()

    escucha._al_presionar = _al_presionar

    for _ in range(4):
        escucha._disparar("corregir")

    # La primera ejecucion arranca y se bloquea.
    liberar.wait(timeout=5)
    # Liberar la primera; al terminar, arranca la encolada (segunda ejecucion).
    bloqueo.set()
    liberar.wait(timeout=5)
    # La segunda tambien queda bloqueada; liberarla para que termine.
    bloqueo.set()
    liberar.wait(timeout=5)

    assert len(ejecuciones) == 2, ejecuciones
    assert escucha._pulsacion_pendiente == set(), escucha._pulsacion_pendiente
    assert escucha._ocupado == set(), escucha._ocupado

    # Tras esperar un rato, no hay mas ejecuciones.
    time.sleep(0.3)
    assert len(ejecuciones) == 2, ejecuciones


def test_tercera_y_cuarta_se_descartan():
    """Implicito en el anterior: al terminar solo queda una ejecucion en cola."""
    escucha, bloqueo, liberar = _escucha_bloqueada()
    ejecuciones: list[str] = []

    def _al_presionar(accion: str) -> None:
        ejecuciones.append(accion)
        bloqueo.wait()
        liberar.set()

    escucha._al_presionar = _al_presionar

    for _ in range(4):
        escucha._disparar("corregir")

    liberar.wait(timeout=5)
    bloqueo.set()
    liberar.wait(timeout=5)
    bloqueo.set()
    liberar.wait(timeout=5)

    assert len(ejecuciones) == 2, ejecuciones
    assert escucha._pulsacion_pendiente == set()


def test_acciones_distintas_independientes():
    """con `corregir` bloqueado, `deshacer` corre y termina solo."""
    escucha, bloqueo, liberar = _escucha_bloqueada()
    ejecuciones: list[str] = []
    deshacer_terminado = threading.Event()

    def _al_presionar(accion: str) -> None:
        ejecuciones.append(accion)
        if accion == "deshacer":
            deshacer_terminado.set()
        else:
            bloqueo.wait()
        liberar.set()

    escucha._al_presionar = _al_presionar

    escucha._disparar("corregir")
    escucha._disparar("deshacer")

    # `deshacer` no esta bloqueado: termina por si solo.
    deshacer_terminado.wait(timeout=5)
    assert "deshacer" in ejecuciones, ejecuciones
    assert ejecuciones.count("deshacer") == 1, ejecuciones

    # Liberar `corregir` y dejar que termine.
    bloqueo.set()
    liberar.wait(timeout=5)
    time.sleep(0.3)

    assert escucha._ocupado == set(), escucha._ocupado
    assert escucha._pulsacion_pendiente == set(), escucha._pulsacion_pendiente


def test_fallo_no_deja_estado_colgado():
    """Lanza en la 1ra ejecucion con una pendiente; la 2da corre; todo vacio."""
    escucha = EscuchaAtajos(
        {
            "corregir": SimpleNamespace(),
            "deshacer": SimpleNamespace(),
            "rehacer": SimpleNamespace(),
        }
    )
    primera_listo = threading.Event()
    liberar = threading.Event()
    contador = {"n": 0}

    def _al_presionar(accion: str) -> None:
        contador["n"] += 1
        if contador["n"] == 1:
            primera_listo.set()
            liberar.wait(timeout=5)  # se queda bloqueado en la primera
            raise RuntimeError("fallo simulado")
        # Segunda ejecucion: termina bien.

    escucha._al_presionar = _al_presionar

    escucha._disparar("corregir")  # primera: lanza
    primera_listo.wait(timeout=5)
    escucha._disparar("corregir")  # segunda: encolada, corre al "terminar" la primera
    liberar.set()

    time.sleep(0.5)

    assert escucha._ocupado == set(), escucha._ocupado
    assert escucha._pulsacion_pendiente == set(), escucha._pulsacion_pendiente
    assert contador["n"] == 2, contador


# --- en_curso ----------------------------------------------------------------


def test_en_curso_refleja_ocupado():
    """Bloqueado: en_curso(corregir) True, en_curso(deshacer) False. Al terminar: False."""
    escucha, bloqueo, liberar = _escucha_bloqueada()

    escucha._disparar("corregir")
    liberar.wait(timeout=5)  # espera a que _al_presionar arranque y se bloquee
    assert escucha.en_curso("corregir") is True
    assert escucha.en_curso("deshacer") is False

    bloqueo.set()
    liberar.wait(timeout=5)  # espera a que termine la ejecucion
    time.sleep(0.2)
    assert escucha.en_curso("corregir") is False


# --- Item de estado de la bandeja -------------------------------------------


def test_item_estado_muestra_corrigiendo():
    """en_curso True -> item.text() contiene 'Corrigiendo'."""
    estado = _EstadoFalso()
    escucha_falsa = SimpleNamespace(en_curso=lambda a: True, faltantes=[])
    b = Bandeja(estado, {}, escucha=escucha_falsa)

    item = b._item_estado()
    texto = item.text
    assert "Corrigiendo" in texto, texto


def test_item_estado_vuelve_al_resumen():
    """Misma instancia, en_curso->False: texto == resumen, sin 'Corrigiendo'."""
    estado = _EstadoFalso()
    estado_actual = {"en_curso": True}

    def en_curso(accion: str) -> bool:
        return estado_actual["en_curso"]

    escucha_falsa = SimpleNamespace(en_curso=en_curso, faltantes=[])
    b = Bandeja(estado, {}, escucha=escucha_falsa)

    item = b._item_estado()
    texto_con = item.text
    assert "Corrigiendo" in texto_con, texto_con

    estado_actual["en_curso"] = False
    texto_sin = item.text
    assert texto_sin == estado.resumen(), texto_sin
    assert "Corrigiendo" not in texto_sin, texto_sin


def test_item_estado_faltantes_actualiza_texto_estado_dinamicamente():
    """Rama faltantes: texto_estado() se re-evalua en cada acceso al item."""
    estado = _EstadoFalso()
    estado_actual = {"en_curso": True}
    faltantes = [{"atajo": "CTRL+E", "es_conflicto_externo": True}]

    def en_curso(accion: str) -> bool:
        return estado_actual["en_curso"]

    escucha_falsa = SimpleNamespace(en_curso=en_curso, faltantes=faltantes)
    b = Bandeja(estado, {}, escucha=escucha_falsa)

    item = b._item_estado()

    # Con en_curso True, primer renglon es 'Corrigiendo...'.
    texto_con = item.text
    assert "Corrigiendo" in texto_con.split("\n")[0], texto_con
    assert "Atajos sin registrar" in texto_con, texto_con

    # Alternar en_curso sobre la MISMA instancia: el texto debe cambiar sin
    # reconstruir el menu.
    estado_actual["en_curso"] = False
    texto_sin = item.text
    assert texto_sin.split("\n")[0] == estado.resumen(), texto_sin
    assert "Corrigiendo" not in texto_sin.split("\n")[0], texto_sin
    assert "Atajos sin registrar" in texto_sin, texto_sin


def test_corrigiendo_convive_con_faltantes():
    """faltantes no vacios + en_curso True: primer renglon 'Corrigiendo', resto conserva 'Atajos sin registrar'."""
    estado = _EstadoFalso()
    escucha_falsa = SimpleNamespace(
        en_curso=lambda a: True,
        faltantes=[{"atajo": "CTRL+E", "es_conflicto_externo": True}],
    )
    b = Bandeja(estado, {}, escucha=escucha_falsa)

    item = b._item_estado()
    texto = item.text
    lineas = texto.split("\n")
    assert "Corrigiendo" in lineas[0], lineas
    assert any("Atajos sin registrar" in l for l in lineas[1:]), lineas


def test_flujo_completo_hotkey_mas_bandeja():
    """EscuchaAtajos real + Bandeja real: texto con 'Corrigiendo', luego vuelve al resumen y sets vacios."""
    escucha, bloqueo, liberar = _escucha_bloqueada()

    estado = _EstadoFalso()
    b = Bandeja(estado, {}, escucha=escucha)

    escucha._disparar("corregir")
    liberar.wait(timeout=5)  # _al_presiono arranco y se bloqueo

    # Mientras corre, el item de estado muestra 'Corrigiendo'.
    item = b._item_estado()
    texto_durante = item.text
    assert "Corrigiendo" in texto_durante, texto_durante
    assert escucha.en_curso("corregir") is True

    # Liberar y esperar a que termine.
    bloqueo.set()
    liberar.wait(timeout=5)
    time.sleep(0.2)

    assert escucha.en_curso("corregir") is False
    texto_despues = item.text
    assert texto_despues == estado.resumen(), texto_despues
    assert "Corrigiendo" not in texto_despues, texto_despues
    assert escucha._ocupado == set(), escucha._ocupado
    assert escucha._pulsacion_pendiente == set(), escucha._pulsacion_pendiente
