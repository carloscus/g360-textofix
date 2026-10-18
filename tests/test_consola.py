"""
Tests de la consola bajo demanda (`core.consola`).

La logica de Win32 se prueba con fakes: en CI no hay terminal de origen
propia que enganchar ni consola que allocar sin ensuciar la sesion. Lo que
si se cubre es la maquina de estados: quien se crea, quien se libera, y
quien NUNCA se toca (la terminal de origen).
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from core import consola


class _Kernel32Falso:
    def __init__(self, consola_ahora=0, puede_attach=True, puede_alloc=True):
        self._consola = consola_ahora
        self._puede_attach = puede_attach
        self._puede_alloc = puede_alloc
        self.attach_llamado = 0
        self.alloc_llamado = 0
        self.free_llamado = 0
        self.titulo = None
        self.modo_set = None

    def GetConsoleWindow(self):
        return self._consola

    def AttachConsole(self, _tipo):
        self.attach_llamado += 1
        if self._puede_attach:
            self._consola = 0x55
            return True
        return False

    def AllocConsole(self):
        self.alloc_llamado += 1
        if self._puede_alloc:
            self._consola = 0x66
            return True
        return False

    def FreeConsole(self):
        self.free_llamado += 1
        self._consola = 0
        return True

    def SetConsoleTitleW(self, titulo):
        self.titulo = titulo

    def GetStdHandle(self, _cual):
        return 0x77

    def GetConsoleMode(self, _h, puntero):
        puntero._obj.value = 0b0111  # ENABLE_PROCESSED_INPUT activo
        return True

    def SetConsoleMode(self, _h, modo):
        self.modo_set = modo
        return True


class _User32Falso:
    def __init__(self, respuesta=6):
        self.respuesta = respuesta
        self.menus: list = []
        self.show: list = []
        self.mensajes: list = []

    def GetSystemMenu(self, _hwnd, _b):
        return 0x88

    def EnableMenuItem(self, _menu, id_item, flags):
        self.menus.append((id_item, flags))

    def DrawMenuBar(self, _hwnd):
        pass

    def ShowWindow(self, _hwnd, cmd):
        self.show.append(cmd)

    def SetForegroundWindow(self, _hwnd):
        pass

    def MessageBoxW(self, _owner, texto, titulo, estilo):
        self.mensajes.append((titulo, texto, estilo))
        return self.respuesta


def _estado_limpio(monkeypatch) -> None:
    """El modulo arranca como recien importado (sin consola propia)."""
    monkeypatch.setattr(consola, "_consola_propia", False)
    monkeypatch.setattr(consola, "_streams", [])


def _patear_helpers(monkeypatch) -> dict:
    """Espia los helpers de I/O reales (no abren CONOUT$ en los tests)."""
    llamados = {"vincular": 0, "inertizar": [], "preparar": 0}

    monkeypatch.setattr(
        consola,
        "_vincular_streams",
        lambda: llamados.__setitem__("vincular", llamados["vincular"] + 1),
    )
    monkeypatch.setattr(
        consola, "_inertizar", lambda forzar=False: llamados["inertizar"].append(forzar)
    )
    monkeypatch.setattr(
        consola,
        "_preparar_propia",
        lambda: llamados.__setitem__("preparar", llamados["preparar"] + 1),
    )
    return llamados


# --- Preparar / enganchar ----------------------------------------------------


def test_preparar_engancha_la_terminal_de_origen(monkeypatch):
    _estado_limpio(monkeypatch)
    llamados = _patear_helpers(monkeypatch)
    k32 = _Kernel32Falso(consola_ahora=0, puede_attach=True)
    monkeypatch.setattr(consola, "kernel32", k32)

    assert consola.preparar() is True
    assert k32.attach_llamado == 1
    assert llamados["vincular"] == 1
    assert llamados["inertizar"] == []  # nada de streams inertes


def test_preparar_sin_terminal_deja_streams_inertes(monkeypatch):
    _estado_limpio(monkeypatch)
    llamados = _patear_helpers(monkeypatch)
    k32 = _Kernel32Falso(consola_ahora=0, puede_attach=False)
    monkeypatch.setattr(consola, "kernel32", k32)

    assert consola.preparar() is False
    assert llamados["inertizar"] == [False]
    assert llamados["vincular"] == 0


def test_desarrollo_con_consola_no_se_toca(monkeypatch):
    """python.exe en un terminal ya tiene consola: no se adjunta ni se vincula."""
    _estado_limpio(monkeypatch)
    llamados = _patear_helpers(monkeypatch)
    k32 = _Kernel32Falso(consola_ahora=0x10)
    monkeypatch.setattr(consola, "kernel32", k32)

    assert consola.preparar() is True
    assert k32.attach_llamado == 0
    assert llamados["vincular"] == 0


# --- pedir_consola -----------------------------------------------------------


def test_pedir_crea_consola_propia_si_no_hay(monkeypatch):
    _estado_limpio(monkeypatch)
    llamados = _patear_helpers(monkeypatch)
    k32 = _Kernel32Falso(consola_ahora=0, puede_alloc=True)
    monkeypatch.setattr(consola, "kernel32", k32)

    assert consola.pedir_consola() is True
    assert k32.alloc_llamado == 1
    assert consola._consola_propia is True
    assert llamados["preparar"] == 1
    assert llamados["vincular"] == 1


def test_pedir_no_toca_una_consola_existente(monkeypatch):
    """La terminal de origen (o la heredada en desarrollo) no es nuestra."""
    _estado_limpio(monkeypatch)
    llamados = _patear_helpers(monkeypatch)
    k32 = _Kernel32Falso(consola_ahora=0x10)
    monkeypatch.setattr(consola, "kernel32", k32)

    assert consola.pedir_consola() is True
    assert k32.alloc_llamado == 0
    assert consola._consola_propia is False
    assert llamados["vincular"] == 0


def test_pedir_falla_si_no_se_puede_allocar(monkeypatch):
    _estado_limpio(monkeypatch)
    _patear_helpers(monkeypatch)
    k32 = _Kernel32Falso(consola_ahora=0, puede_alloc=False)
    monkeypatch.setattr(consola, "kernel32", k32)

    assert consola.pedir_consola() is False
    assert consola._consola_propia is False


# --- cerrar_consola_propia ---------------------------------------------------


class _ArchivoFalso:
    def __init__(self):
        self.cerrado = False

    def close(self):
        self.cerrado = True


def test_cerrar_libera_solo_la_consola_propia(monkeypatch, capsys):
    _estado_limpio(monkeypatch)
    llamados = _patear_helpers(monkeypatch)
    k32 = _Kernel32Falso()
    monkeypatch.setattr(consola, "kernel32", k32)
    monkeypatch.setattr(consola, "_consola_propia", True)
    archivo = _ArchivoFalso()
    monkeypatch.setattr(consola, "_streams", [archivo])
    monkeypatch.setattr("builtins.input", lambda *_: "")

    consola.cerrar_consola_propia()

    assert "Enter para cerrar" in capsys.readouterr().out
    assert k32.free_llamado == 1
    assert archivo.cerrado
    assert consola._consola_propia is False
    assert consola._streams == []
    assert llamados["inertizar"] == [True]  # fuerza stream inerte tras liberar


def test_cerrar_no_libera_la_terminal_de_origen(monkeypatch):
    _estado_limpio(monkeypatch)
    llamados = _patear_helpers(monkeypatch)
    k32 = _Kernel32Falso(consola_ahora=0x10)
    monkeypatch.setattr(consola, "kernel32", k32)

    consola.cerrar_consola_propia()  # propia == False

    assert k32.free_llamado == 0
    assert llamados["inertizar"] == []


# --- avisar ------------------------------------------------------------------


def test_avisar_con_popup_devuelve_si(monkeypatch):
    _estado_limpio(monkeypatch)
    monkeypatch.setattr(consola, "sin_salida", lambda: True)
    monkeypatch.setattr(consola, "kernel32", _Kernel32Falso(consola_ahora=0))
    u32 = _User32Falso(respuesta=6)
    monkeypatch.setattr(consola, "user32", u32)

    assert consola.avisar("titulo", "texto", ofrecer=True) is True
    titulo, texto, estilo = u32.mensajes[0]
    assert titulo == "titulo"
    assert texto == "texto"
    assert estilo & consola.MB_YESNO


def test_avisar_con_no_devuelve_false(monkeypatch):
    _estado_limpio(monkeypatch)
    monkeypatch.setattr(consola, "sin_salida", lambda: True)
    monkeypatch.setattr(consola, "kernel32", _Kernel32Falso(consola_ahora=0))
    monkeypatch.setattr(consola, "user32", _User32Falso(respuesta=7))

    assert consola.avisar("titulo", "texto") is False


def test_avisar_imprime_cuando_hay_donde(monkeypatch, capsys):
    """Con consola O con pipe no hay popup: se imprime y ya (no bloquea)."""
    _estado_limpio(monkeypatch)
    monkeypatch.setattr(consola, "sin_salida", lambda: False)
    u32 = _User32Falso()
    monkeypatch.setattr(consola, "user32", u32)

    assert consola.avisar("titulo", "texto aca") is False
    assert "texto aca" in capsys.readouterr().out
    assert u32.mensajes == []


def test_sin_salida_detecta_streams_muertos(monkeypatch):
    import io

    from core.logsetup import Nulo

    monkeypatch.setattr(sys, "stdout", None)
    assert consola.sin_salida() is True

    monkeypatch.setattr(sys, "stdout", Nulo())
    assert consola.sin_salida() is True

    # Pipe o consola real: Python lo envuelve en TextIOWrapper.
    monkeypatch.setattr(sys, "stdout", io.StringIO())
    assert consola.sin_salida() is False

    # El NullWriter del modo windowed: objeto de mentira, no stream.
    monkeypatch.setattr(sys, "stdout", object())
    assert consola.sin_salida() is True


# --- _preparar_propia: la parte que salva el proceso -------------------------


def test_consola_propia_deshabilita_la_x_y_el_ctrl_c(monkeypatch):
    _estado_limpio(monkeypatch)
    k32 = _Kernel32Falso(consola_ahora=0x66)
    u32 = _User32Falso()
    monkeypatch.setattr(consola, "kernel32", k32)
    monkeypatch.setattr(consola, "user32", u32)

    consola._preparar_propia()

    assert k32.titulo == "g360-textofix"
    assert (consola.SC_CLOSE, consola.MF_BYCOMMAND | consola.MF_GRAYED) in u32.menus
    assert consola.SW_SHOW in u32.show
    # Sin ENABLE_PROCESSED_INPUT: Ctrl+C no termina el proceso.
    assert k32.modo_set == 0b0110


# --- streams inertes ---------------------------------------------------------


def test_inertizar_forzado_deja_salidas_que_no_reventan(monkeypatch):
    from core.logsetup import Nulo

    monkeypatch.setattr(sys, "stdout", sys.stdout)
    monkeypatch.setattr(sys, "stderr", sys.stderr)

    consola._inertizar(forzar=True)

    assert isinstance(sys.stdout, Nulo)
    assert isinstance(sys.stderr, Nulo)
    # print no revienta con la salida inerte (el teardown restaura sys).
    print("esto no debe reventar")
