"""
Consola bajo demanda.

El .exe arranca SIN ventana: vive en la bandeja, en segundo plano. Pero en
tres momentos hace falta una consola de verdad:

- Llegar desde un terminal (cmd/PowerShell): la salida (--probar-api,
  --bateria, los logs) va a la terminal de origen via AttachConsole.
- Pedir una clave o un atajo desde la bandeja: se crea UNA consola propia,
  visible, con la X deshabilitada (cerrar la ventana mataria el proceso) y
  sin Ctrl+C letal; se libera con Enter al terminar.
- Falta la clave y no hay terminal: un popup de Windows avisa y ofrece
  abrir la consola para pegarla.

Tres estados posibles: terminal de origen (no es nuestra: no se toca),
consola propia (la creamos y la liberamos), o ninguna (la salida va a un
stream inerte, ver `logsetup.Nulo`).
"""

from __future__ import annotations

import ctypes
import sys

from .logsetup import Nulo, refrescar_streams

kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
user32 = ctypes.WinDLL("user32", use_last_error=True)

kernel32.AttachConsole.argtypes = [ctypes.c_uint32]
kernel32.AttachConsole.restype = ctypes.c_bool
kernel32.AllocConsole.restype = ctypes.c_bool
kernel32.FreeConsole.restype = ctypes.c_bool
kernel32.GetConsoleWindow.restype = ctypes.c_void_p
kernel32.GetStdHandle.argtypes = [ctypes.c_int32]
kernel32.GetStdHandle.restype = ctypes.c_void_p
kernel32.GetConsoleMode.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_uint32)]
kernel32.SetConsoleMode.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
kernel32.SetConsoleTitleW.argtypes = [ctypes.c_wchar_p]
user32.ShowWindow.argtypes = [ctypes.c_void_p, ctypes.c_int]
user32.SetForegroundWindow.argtypes = [ctypes.c_void_p]
user32.GetSystemMenu.argtypes = [ctypes.c_void_p, ctypes.c_bool]
user32.GetSystemMenu.restype = ctypes.c_void_p
user32.EnableMenuItem.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_uint]
user32.DrawMenuBar.argtypes = [ctypes.c_void_p]
user32.MessageBoxW.argtypes = [
    ctypes.c_void_p,
    ctypes.c_wchar_p,
    ctypes.c_wchar_p,
    ctypes.c_uint,
]
user32.MessageBoxW.restype = ctypes.c_int

ATTACH_PARENT_PROCESS = 0xFFFFFFFF
STD_INPUT_HANDLE = -10
ENABLE_PROCESSED_INPUT = 0x0001
SC_CLOSE = 0xF060
MF_BYCOMMAND = 0x0000
MF_GRAYED = 0x0001
SW_SHOW = 5
MB_YESNO = 0x04
MB_ICONINFORMATION = 0x40
IDYES = 6

_consola_propia = False
_streams: list = []


def hay_consola() -> bool:
    """Si el proceso tiene consola ahora mismo (propia o de origen)."""
    return bool(kernel32.GetConsoleWindow())


def sin_salida() -> bool:
    """
    Si no hay A DONDE imprimir: ni consola, ni pipe, ni nada util.

    Distingue dos situaciones que se ven igual por fuera pero no lo son:
    un terminal/pipe (la salida se ve ahi: NO hace falta popup) vs un arranque
    en segundo plano sin nadie mirando (la salida se perderia: popup).
    """
    import io

    stdout = sys.stdout
    if stdout is None or isinstance(stdout, Nulo):
        return True
    # Un pipe o la consola los envuelve Python en TextIOWrapper; cualquier
    # otra cosa (el NullWriter del modo windowed) descarta la salida.
    return not isinstance(stdout, io.TextIOBase)


def preparar() -> bool:
    """
    Al arrancar: engancha la terminal de origen, o deja streams inertes.

    Se llama ANTES de parsear argumentos: sin esto, --help y --version de un
    exe sin consola no tendrian donde imprimir.
    """
    if enganchar():
        return True
    _inertizar()
    refrescar_streams()
    return False


def enganchar() -> bool:
    """
    Usa la consola del proceso de origen (cmd/PowerShell).

    Si arranca por doble clic o desde el registro, no hay terminal padre:
    devuelve False y el proceso sigue mudo hasta que alguien pida consola.
    Un exe de desarrollo (python.exe) ya tiene consola: se devuelve True sin
    tocar nada.
    """
    if hay_consola():
        return True
    if not kernel32.AttachConsole(ATTACH_PARENT_PROCESS):
        return False
    _vincular_streams()
    return True


def pedir_consola() -> bool:
    """
    Asegura una consola usable para interactuar (pedir clave/atajo).

    Si ya hay (terminal de origen o la heredada en desarrollo) no hace nada.
    Si no hay, crea UNA consola propia visible y segura de usar. Devuelve si
    quedo donde escribir.
    """
    global _consola_propia
    if hay_consola():
        return True
    if not kernel32.AllocConsole():
        return False
    _consola_propia = True
    _preparar_propia()
    _vincular_streams()
    return True


def cerrar_consola_propia() -> None:
    """
    Libera la consola propia tras la interaccion, con una pausa para leer.

    La terminal de origen NUNCA se libera (no es nuestra). La X de la
    consola propia esta deshabilitada por `_preparar_propia` porque cerrar
    la ventana mataria el proceso: el camino de salida es Enter.
    """
    global _consola_propia
    if not _consola_propia:
        return
    try:
        print("\nEnter para cerrar esta consola (el corrector sigue activo).")
        input()
    except (EOFError, KeyboardInterrupt, OSError):
        pass
    _consola_propia = False
    for archivo in _streams:
        try:
            archivo.close()
        except OSError:
            pass
    _streams.clear()
    kernel32.FreeConsole()
    _inertizar(forzar=True)
    refrescar_streams()


def avisar(titulo: str, texto: str, ofrecer: bool = False) -> bool:
    """
    Popup de Windows. True si el usuario acepto (boton Si).

    Solo tiene sentido cuando la salida se perderia (sin consola ni pipe):
    si hay donde imprimir, se imprime ahi y se devuelve False (no hay
    boton que aceptar).
    """
    if not sin_salida():
        print(f"[{titulo}]\n{texto}")
        return False
    estilo = MB_ICONINFORMATION | (MB_YESNO if ofrecer else 0)
    return user32.MessageBoxW(None, texto, titulo, estilo) == IDYES


# --- Internos ----------------------------------------------------------------


def _preparar_propia() -> None:
    """
    La consola propia: visible, sin X letal, sin Ctrl+C letal.

    Dos trampas que se pagan caro si no se cubren:

    - Cerrar la ventana dispara CTRL_CLOSE_EVENT, que termina el proceso:
      la app moriria porque el usuario cerro "la consola de configuracion".
    - Ctrl+C en esa consola mataria el proceso igual; sin el modo
      procesado se comporta como cualquier otra tecla.
    """
    hwnd = kernel32.GetConsoleWindow()
    if not hwnd:
        return
    kernel32.SetConsoleTitleW("g360-textofix")
    menu = user32.GetSystemMenu(hwnd, False)
    if menu:
        user32.EnableMenuItem(menu, SC_CLOSE, MF_BYCOMMAND | MF_GRAYED)
        user32.DrawMenuBar(hwnd)
    user32.ShowWindow(hwnd, SW_SHOW)
    user32.SetForegroundWindow(hwnd)

    entrada = kernel32.GetStdHandle(STD_INPUT_HANDLE)
    modo = ctypes.c_uint32()
    if entrada and kernel32.GetConsoleMode(entrada, ctypes.byref(modo)):
        kernel32.SetConsoleMode(entrada, modo.value & ~ENABLE_PROCESSED_INPUT)


def _vincular_streams() -> None:
    """Apunta stdout/stderr/stdin y el handler de log a la consola nueva."""
    global _streams
    try:
        # cierran en `cerrar_consola_propia`, no en este bloque.
        salida = open("CONOUT$", "w", errors="replace")  # noqa: SIM115
        err = open("CONOUT$", "w", errors="replace")  # noqa: SIM115
        entrada = open("CONIN$", "r", errors="replace")  # noqa: SIM115
    except OSError:
        return
    _streams = [salida, err, entrada]
    sys.stdout = salida
    sys.stderr = err
    sys.stdin = entrada
    refrescar_streams()


def _inertizar(forzar: bool = False) -> None:
    """Salida inerte para cuando no hay consola (forzar tras liberar una)."""
    if forzar or sys.stdout is None:
        sys.stdout = Nulo()
    if forzar or sys.stderr is None:
        sys.stderr = Nulo()
