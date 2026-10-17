"""
Capa Win32 minima: ventana en primer plano, teclado sintetico y portapapeles.

Se apoya en pywin32 para portapapeles/ventanas y en SendInput (ctypes) para el
teclado.

Nota importante: SendInput esta sujeto a UIPI. Si la app destino corre como
administrador y este proceso no, el envio se bloquea en silencio;
`puede_inyectar()` lo detecta para poder avisar en vez de fallar sin explica.
"""

from __future__ import annotations

import ctypes
import logging
import time
from ctypes import wintypes
from dataclasses import dataclass

import win32api
import win32clipboard
import win32con
import win32security

from .logsetup import LOGGER_NAME

log = logging.getLogger(LOGGER_NAME)

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

VK_CONTROL = 0x11
VK_SHIFT = 0x10
VK_MENU = 0x12
VK_LWIN = 0x5B
VK_C = 0x43
VK_V = 0x56

# Los flags de modificador de RegisterHotKey (MOD_*) usan un espacio de
# numeros distinto al de las teclas reales (VK_*). Hay que traducir.
MOD_CONTROL = 0x0002
MOD_TO_VK = {0x0001: VK_MENU, 0x0002: VK_CONTROL, 0x0004: VK_SHIFT, 0x0008: VK_LWIN}

PROCESS_QUERY_LIMITED_INFORMATION = 0x1000

# En 64 bits, un HANDLE no cabe en un int. Sin esto, ctypes trunca el puntero
# y las llamadas fallan de forma intermitente.
kernel32.OpenProcess.restype = wintypes.HANDLE
kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
kernel32.QueryFullProcessImageNameW.restype = wintypes.BOOL
kernel32.QueryFullProcessImageNameW.argtypes = [
    wintypes.HANDLE,
    wintypes.DWORD,
    wintypes.LPWSTR,
    ctypes.POINTER(wintypes.DWORD),
]
kernel32.CloseHandle.restype = wintypes.BOOL
kernel32.CloseHandle.argtypes = [wintypes.HANDLE]

# --- SendInput ---------------------------------------------------------------
# La union INPUT debe contener las tres variantes aunque solo usemos teclado:
# MOUSEINPUT es la mas grande y de ella depende el tamano de la estructura.
# Si falta, sizeof(_INPUT) da 32 en vez de 40 y SendInput rechaza el cbSize,
# dejando las teclas sin enviar y sin avisar.

_INPUT_KEYBOARD = 1
_KEYEVENTF_KEYUP = 0x0002

ULONG_PTR = ctypes.POINTER(wintypes.ULONG)


class _MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", wintypes.LONG),
        ("dy", wintypes.LONG),
        ("mouseData", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ULONG_PTR),
    ]


class _KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", wintypes.WORD),
        ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ULONG_PTR),
    ]


class _HARDWAREINPUT(ctypes.Structure):
    _fields_ = [
        ("uMsg", wintypes.DWORD),
        ("wParamL", wintypes.WORD),
        ("wParamH", wintypes.WORD),
    ]


class _INPUTunion(ctypes.Union):
    _fields_ = [("mi", _MOUSEINPUT), ("ki", _KEYBDINPUT), ("hi", _HARDWAREINPUT)]


class _INPUT(ctypes.Structure):
    _fields_ = [("type", wintypes.DWORD), ("union", _INPUTunion)]


# Falla ruidosa si la estructura no mide lo que Windows espera.
_INPUT_SIZE = ctypes.sizeof(_INPUT)
_EXPECTED_INPUT_SIZE = 40 if ctypes.sizeof(ctypes.c_void_p) == 8 else 28
if _INPUT_SIZE != _EXPECTED_INPUT_SIZE:
    raise RuntimeError(
        f"struct INPUT mide {_INPUT_SIZE} bytes, se esperaba {_EXPECTED_INPUT_SIZE}"
    )


@dataclass(frozen=True)
class WindowContext:
    """Identifica la ventana que tiene el foco."""

    hwnd: int
    pid: int
    process: str

    @property
    def label(self) -> str:
        return f"{self.process}#{self.pid}"


def _process_name(pid: int) -> str:
    """Nombre del proceso via QueryFullProcessImageNameW."""
    try:
        handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if not handle:
            return "desconocido"
        try:
            size = wintypes.DWORD(260)
            buffer = ctypes.create_unicode_buffer(size.value)
            if kernel32.QueryFullProcessImageNameW(
                handle, 0, buffer, ctypes.byref(size)
            ):
                return buffer.value.rsplit("\\", 1)[-1]
            return "desconocido"
        finally:
            kernel32.CloseHandle(handle)
    except Exception:
        return "desconocido"


def foreground_context() -> WindowContext | None:
    """Ventana en primer plano y su proceso. `None` si no hay ninguna."""
    hwnd = user32.GetForegroundWindow()
    if not hwnd:
        return None

    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    return WindowContext(hwnd=hwnd, pid=pid.value, process=_process_name(pid.value))


# --- Teclado sintetico -------------------------------------------------------


def _send(vk: int, up: bool) -> bool:
    """Envia una pulsacion de tecla. False si Windows la rechazo (UIPI)."""
    extra = ULONG_PTR()
    item = _INPUT(type=_INPUT_KEYBOARD)
    item.union.ki = _KEYBDINPUT(
        wVk=vk,
        wScan=0,
        dwFlags=_KEYEVENTF_KEYUP if up else 0,
        time=0,
        dwExtraInfo=extra,
    )
    enviados = user32.SendInput(1, ctypes.byref(item), _INPUT_SIZE)
    if enviados != 1:
        log.debug("SendInput rechazo la tecla vk=0x%X (up=%s)", vk, up)
        return False
    return True


def send_hotkey(virtual_key: int, modifiers: int) -> bool:
    """Pulsa una combinacion de modificadores + una tecla."""
    mods = [vk for mod, vk in MOD_TO_VK.items() if modifiers & mod]
    ok = True
    for mod in mods:
        ok = _send(mod, up=False) and ok
    ok = _send(virtual_key, up=False) and ok
    ok = _send(virtual_key, up=True) and ok
    for mod in reversed(mods):
        ok = _send(mod, up=True) and ok
    return ok


def send_ctrl(key_vk: int) -> None:
    """Atajo simple Ctrl+tecla."""
    send_hotkey(key_vk, MOD_CONTROL)


# --- Integridad (UIPI) -------------------------------------------------------


def _integrity_level(sid) -> int:
    """Extrae el IL (Mandatory Level RID) de un SID de integridad."""
    return int(win32security.ConvertSidToStringSid(sid).split("-")[-1])


def _current_integrity() -> int:
    token = win32security.OpenProcessToken(
        win32api.GetCurrentProcess(), win32con.TOKEN_QUERY
    )
    user = win32security.GetTokenInformation(token, win32security.TokenUser)[0]
    return _integrity_level(user[0])


def puede_inyectar(ctx: WindowContext) -> bool:
    """
    False si la app destino corre con mayor integridad que este proceso (UIPI).

    En ese caso SendInput no hace nada y el corrector fallaria en silencio.
    """
    try:
        handle = win32api.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, ctx.pid)
        token = win32security.OpenProcessToken(handle, win32con.TOKEN_QUERY)
        user = win32security.GetTokenInformation(token, win32security.TokenUser)[0]
        return _integrity_level(user[0]) <= _current_integrity()
    except Exception:
        return True  # si no se puede determinar, se intenta igual


# --- Portapapeles ------------------------------------------------------------


def clipboard_read() -> str | None:
    """Texto del portapapeles, o None si no hay o no es texto."""
    try:
        win32clipboard.OpenClipboard()
        try:
            if not win32clipboard.IsClipboardFormatAvailable(win32con.CF_UNICODETEXT):
                return None
            return win32clipboard.GetClipboardData(win32con.CF_UNICODETEXT)
        finally:
            win32clipboard.CloseClipboard()
    except Exception:
        return None


def clipboard_write(text: str) -> bool:
    """Escribe texto en el portapapeles. False si esta bloqueado por otra app."""
    try:
        win32clipboard.OpenClipboard()
        try:
            win32clipboard.EmptyClipboard()
            win32clipboard.SetClipboardData(win32con.CF_UNICODETEXT, text)
            return True
        finally:
            win32clipboard.CloseClipboard()
    except Exception:
        return False


user32.GetClipboardSequenceNumber.restype = wintypes.DWORD
user32.GetClipboardSequenceNumber.argtypes = []

# La funcion existe desde Windows 2000; en theory no falta, pero si faltara
# GetLastError != 0 seria la unica senal.
_SEQUENCE_DISPONIBLE = user32.GetClipboardSequenceNumber() != 0


def clipboard_sequence() -> int:
    """Contador que Windows incrementa en cada cambio del portapapeles."""
    return user32.GetClipboardSequenceNumber()


def clipboard_copy_from_app(timeout_ms: int) -> str | None:
    """
    Copia la seleccion de la app en primer plano via Ctrl+C sintetico.

    La deteccion se hace con el NUMERO DE SECUENCIA del portapapeles, no
    comparando el contenido: si el usuario copia dos veces el mismo texto, el
    contenido no cambia pero el portapapeles si, y comparar texto diria
    falsamente que no hay nada seleccionado.

    Devuelve None si el portapapeles no cambio dentro del plazo, es decir, si
    la app no soporta Ctrl+C o no hay nada seleccionado.
    """
    if _SEQUENCE_DISPONIBLE:
        antes = clipboard_sequence()
        send_ctrl(VK_C)
        limite = time.monotonic() + (timeout_ms / 1000.0)
        while time.monotonic() < limite:
            time.sleep(0.02)
            if clipboard_sequence() != antes:
                texto = clipboard_read()
                return texto if texto and texto.strip() else None
        return None

    # Reserva: comparar contenido es peor, pero mejor que nada.
    antes_texto = clipboard_read()
    send_ctrl(VK_C)
    limite = time.monotonic() + (timeout_ms / 1000.0)
    while time.monotonic() < limite:
        time.sleep(0.02)
        actual = clipboard_read()
        if actual is not None and actual != antes_texto:
            return actual
    return None


def clipboard_paste_into_app(text: str) -> bool:
    """Pega `text` en la app en primer plano via Ctrl+V."""
    if not clipboard_write(text):
        return False
    time.sleep(0.02)
    send_ctrl(VK_V)
    return True
