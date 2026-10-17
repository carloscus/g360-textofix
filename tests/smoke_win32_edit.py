"""
Prueba de humo determinista sobre un control EDIT de Win32.

Por que no basta con el Bloc de notas: para fijar una seleccion PARCIAL hay que
enviar teclas de navegacion, y las teclas sin modificador no llegan de forma
fiable a las aplicaciones modernas. En vez de pelear con eso, esta prueba crea un
control EDIT estandar (el mismo que usan miles de apps) y fija la seleccion por
mensaje EM_SETSEL, que es determinista.

La ventana vive en un hilo PROPIO con su propio bucle de mensajes. No es
decorativo: si compartiera el hilo con el codigo de prueba, las pulsaciones
sinteticas se quedarian en la cola sin despacharse mientras el hilo esta ocupado,
y la prueba fallaria siempre.

    uv run python tests/smoke_win32_edit.py
"""

from __future__ import annotations

import ctypes
import sys
import threading
import time
from ctypes import wintypes
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from core.config import Config
from core.engine import run_once
from core.logsetup import setup_logging

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

WS_OVERLAPPEDWINDOW = 0x00CF0000
WS_CHILD = 0x40000000
WS_VISIBLE = 0x10000000
ES_MULTILINE = 0x0004
ES_AUTOVSCROLL = 0x0040
WM_DESTROY = 0x0002
WM_SETTEXT = 0x000C
WM_GETTEXT = 0x000D
WM_GETTEXTLENGTH = 0x000E
EM_SETSEL = 0x00B1
EM_GETSEL = 0x00B0
SW_HIDE = 0
SW_SHOW = 5

TEXTO = "El cliente pidio tres cajas"

log = setup_logging(verbose=True)

WNDPROC = ctypes.WINFUNCTYPE(
    ctypes.c_longlong, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM
)


class WNDCLASS(ctypes.Structure):
    """ctypes.wintypes no incluye WNDCLASS; hay que declararla."""

    _fields_ = [
        ("style", ctypes.c_uint),
        ("lpfnWndProc", WNDPROC),
        ("cbClsExtra", ctypes.c_int),
        ("cbWndExtra", ctypes.c_int),
        ("hInstance", wintypes.HINSTANCE),
        ("hIcon", wintypes.HANDLE),
        ("hCursor", wintypes.HANDLE),
        ("hbrBackground", wintypes.HANDLE),
        ("lpszMenuName", wintypes.LPCWSTR),
        ("lpszClassName", wintypes.LPCWSTR),
    ]


# En 64 bits los handles no caben en un int: sin esto se truncan. Tambien
# WPARAM/LPARAM son de 64 bits y sin declararlos ctypes los recorta a 32.
user32.DefWindowProcW.restype = ctypes.c_longlong
user32.DefWindowProcW.argtypes = [
    wintypes.HWND,
    wintypes.UINT,
    wintypes.WPARAM,
    wintypes.LPARAM,
]
user32.SendMessageW.restype = ctypes.c_longlong
user32.SendMessageW.argtypes = [
    wintypes.HWND,
    wintypes.UINT,
    wintypes.WPARAM,
    wintypes.LPARAM,
]
user32.CreateWindowExW.restype = wintypes.HWND
user32.CreateWindowExW.argtypes = [
    wintypes.DWORD,
    wintypes.LPCWSTR,
    wintypes.LPCWSTR,
    wintypes.DWORD,
    ctypes.c_int,
    ctypes.c_int,
    ctypes.c_int,
    ctypes.c_int,
    wintypes.HWND,
    wintypes.HMENU,
    wintypes.HINSTANCE,
    wintypes.LPVOID,
]


def _texto(hwnd: int) -> str:
    largo = user32.SendMessageW(hwnd, WM_GETTEXTLENGTH, 0, 0)
    buffer = ctypes.create_unicode_buffer(largo + 1)
    user32.SendMessageW(
        hwnd, WM_GETTEXT, largo + 1, ctypes.cast(buffer, ctypes.c_void_p).value
    )
    return buffer.value


def _poner_texto(hwnd: int, texto: str) -> None:
    buffer = ctypes.create_unicode_buffer(texto)
    user32.SendMessageW(hwnd, WM_SETTEXT, 0, ctypes.cast(buffer, ctypes.c_void_p).value)


def _seleccion(hwnd: int) -> tuple[int, int]:
    """(inicio, fin) de la seleccion actual, leida con EM_GETSEL."""
    packed = user32.SendMessageW(hwnd, EM_GETSEL, 0, 0)
    return packed & 0xFFFF, (packed >> 16) & 0xFFFF


class _Ventana:
    """Ventana con un EDIT, alojada en un hilo con su propio bucle de mensajes."""

    def __init__(self) -> None:
        self.hwnd = 0
        self.edit = 0
        self._listo = threading.Event()
        self._error: Exception | None = None
        self._hilo = threading.Thread(
            target=self._ciclo, name="smoke-win32", daemon=True
        )
        self._proc = None
        self._thread_id = 0

    # --- Hilo de la ventana --------------------------------------------------

    def _ciclo(self) -> None:
        try:
            self._crear()
            self._listo.set()
            self._bucle()
        except Exception as exc:  # pragma: no cover
            self._error = exc
            self._listo.set()

    def _crear(self) -> None:
        self._thread_id = kernel32.GetCurrentThreadId()
        hinstance = kernel32.GetModuleHandleW(None)

        @WNDPROC
        def wndproc(hwnd, msg, wparam, lparam):
            if msg == WM_DESTROY:
                user32.PostQuitMessage(0)
                return 0
            return user32.DefWindowProcW(hwnd, msg, wparam, lparam)

        self._proc = wndproc  # la referencia no debe morir

        clase = "TextofixSmokeEdit"
        wndclass = WNDCLASS()
        wndclass.lpfnWndProc = wndproc
        wndclass.hInstance = hinstance
        wndclass.lpszClassName = clase
        wndclass.hCursor = user32.LoadCursorW(None, ctypes.c_wchar_p(32512))
        wndclass.hbrBackground = 16  # COLOR_BTNFACE + 1
        user32.RegisterClassW(ctypes.byref(wndclass))

        self.hwnd = user32.CreateWindowExW(
            0,
            clase,
            "Prueba textofix",
            WS_OVERLAPPEDWINDOW | WS_VISIBLE,
            100,
            100,
            520,
            240,
            None,
            None,
            hinstance,
            None,
        )
        if not self.hwnd:
            raise RuntimeError("no se pudo crear la ventana")

        self.edit = user32.CreateWindowExW(
            0,
            "EDIT",
            "",
            WS_CHILD | WS_VISIBLE | ES_MULTILINE | ES_AUTOVSCROLL,
            0,
            0,
            520,
            200,
            self.hwnd,
            None,
            hinstance,
            None,
        )
        if not self.edit:
            raise RuntimeError("no se pudo crear el control EDIT")

        # SetFocus solo funciona dentro del hilo que creo el control: por eso
        # el EDIT debe nacer'se ya con el foco.
        user32.SetFocus(self.edit)

    def _bucle(self) -> None:
        msg = wintypes.MSG()
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))

    # --- API desde el hilo principal ----------------------------------------

    def abrir(self) -> None:
        self._hilo.start()
        if not self._listo.wait(10):
            raise RuntimeError("la ventana de prueba no arranco")
        if self._error:
            raise self._error

    def cerrar(self) -> None:
        if self.hwnd:
            user32.PostMessageW(self.hwnd, WM_DESTROY, 0, 0)
        self._hilo.join(timeout=3)


def _enfocar(ventana: _Ventana) -> None:
    """Pone la ventana de prueba delante de todo."""
    user32.ShowWindow(ventana.hwnd, SW_SHOW)
    user32.SetForegroundWindow(ventana.hwnd)
    time.sleep(0.5)

    actual = user32.GetForegroundWindow()
    if actual != ventana.hwnd:
        raise RuntimeError(
            f"la ventana de prueba no quedo en primer plano "
            f"(foreground={actual}, esperada={ventana.hwnd})"
        )


def _ocultar_consola() -> None:
    """
    Sin esto la consola de Python compite por el primer plano: ambas ventanas
    son del mismo proceso y el Ctrl+C sintetico se va a la consola.
    """
    consola = kernel32.GetConsoleWindow()
    if consola:
        user32.ShowWindow(consola, SW_HIDE)


def main() -> int:
    _ocultar_consola()
    ventana = _Ventana()
    ventana.abrir()

    fallos = 0
    try:
        cfg = Config.from_env()

        def caso(nombre: str, inicio: int, fin: int, esperado: str) -> None:
            nonlocal fallos
            log.info("=== %s ===", nombre)
            _poner_texto(ventana.edit, TEXTO)
            _enfocar(ventana)
            user32.SendMessageW(ventana.edit, EM_SETSEL, inicio, fin)

            inicio_real, fin_real = _seleccion(ventana.edit)
            log.info("seleccion fijada: [%d, %d)", inicio_real, fin_real)

            outcome = run_once(cfg, mode="mock", transform="wrap")
            log.info("resultado=%s adaptador=%s", outcome.reason, outcome.adapter)
            time.sleep(0.4)

            texto = _texto(ventana.edit)
            log.info("documento ahora: %r", texto)
            if texto != esperado:
                log.error("FALLO %s: se esperaba %r", nombre, esperado)
                fallos += 1
            else:
                log.info("OK %s", nombre)

        caso("seleccion completa", 0, -1, f"«{TEXTO}»")
        caso("seleccion parcial", 0, len("El cliente"), "«El cliente» pidio tres cajas")
        caso(
            "seleccion al final",
            len("El cliente pidio "),
            -1,
            "El cliente pidio «tres cajas»",
        )
        caso("sin seleccion", 3, 3, TEXTO)
    finally:
        ventana.cerrar()

    if fallos:
        log.error("=== %d prueba(s) fallaron ===", fallos)
        return 1
    log.info("=== todas las pruebas pasaron ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
