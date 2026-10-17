"""
Perfil del usuario: configuracion y clave de API.

La clave NO se guarda en texto plano. Se cifra con DPAPI, la API de Windows
que cifra con la cuenta del usuario: no hay contraseña que recordar y el
archivo solo lo puede abrir esa persona en esa maquina.

La configuracion que no es secreta (atajos, iniciar con Windows) va en JSON a
la vista, porque no tiene nada que proteger y asi se puede editar a mano.
"""

from __future__ import annotations

import ctypes
import json
import logging
import os
from ctypes import wintypes
from pathlib import Path

from .logsetup import LOGGER_NAME

log = logging.getLogger(LOGGER_NAME)

# El perfil vive en %APPDATA%, no junto al programa: asi funciona aunque el
# .exe este en Archivos de Programa (donde no se puede escribir) y es distinto
# por usuario de Windows.
DIR_PERFIL = Path(os.environ.get("APPDATA", Path.home())) / "g360-textofix"

ARCHIVO_CONFIG = DIR_PERFIL / "config.json"
ARCHIVO_CLAVE = DIR_PERFIL / "clave.dat"

CONFIG_POR_DEFECTO = {
    "hotkey_corregir": "CTRL+SHIFT+E",
    "hotkey_deshacer": "CTRL+SHIFT+Z",
    "hotkey_rehacer": "CTRL+SHIFT+R",
    "iniciar_con_windows": False,
    "activo": True,
}


# --- DPAPI -------------------------------------------------------------------


class _BLOB(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_byte))]


def _blob(datos: bytes) -> tuple[_BLOB, object]:
    buffer = ctypes.create_string_buffer(datos, len(datos))
    blob = _BLOB(len(datos), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_byte)))
    return blob, buffer


def _de_blob(blob: _BLOB) -> bytes:
    return ctypes.string_at(blob.pbData, blob.cbData)


# CryptProtectData vive en Crypt32.dll, no en Advapi32.
crypt32 = ctypes.WinDLL("Crypt32.dll", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32.dll", use_last_error=True)

CRYPTPROTECT_UI_FORBIDDEN = 0x01

crypt32.CryptProtectData.restype = wintypes.BOOL
crypt32.CryptProtectData.argtypes = [
    ctypes.POINTER(_BLOB),
    wintypes.LPCWSTR,
    ctypes.POINTER(_BLOB),
    ctypes.c_void_p,
    ctypes.c_void_p,
    wintypes.DWORD,
    ctypes.POINTER(_BLOB),
]
crypt32.CryptUnprotectData.restype = wintypes.BOOL
crypt32.CryptUnprotectData.argtypes = [
    ctypes.POINTER(_BLOB),
    ctypes.c_void_p,
    ctypes.POINTER(_BLOB),
    ctypes.c_void_p,
    ctypes.c_void_p,
    wintypes.DWORD,
    ctypes.POINTER(_BLOB),
]
kernel32.LocalFree.restype = ctypes.c_void_p
kernel32.LocalFree.argtypes = [ctypes.c_void_p]


def _cifrar(datos: bytes) -> bytes:
    entrada, buffer = _blob(datos)
    salida = _BLOB()
    if not crypt32.CryptProtectData(
        ctypes.byref(entrada),
        "g360-textofix",
        None,
        None,
        None,
        CRYPTPROTECT_UI_FORBIDDEN,
        ctypes.byref(salida),
    ):
        raise OSError(ctypes.get_last_error(), "no se pudo cifrar la clave")
    try:
        return _de_blob(salida)
    finally:
        kernel32.LocalFree(salida.pbData)
        del buffer


def _descifrar(datos: bytes) -> bytes:
    entrada, buffer = _blob(datos)
    salida = _BLOB()
    if not crypt32.CryptUnprotectData(
        ctypes.byref(entrada),
        None,
        None,
        None,
        None,
        CRYPTPROTECT_UI_FORBIDDEN,
        ctypes.byref(salida),
    ):
        raise OSError(ctypes.get_last_error(), "no se pudo descifrar la clave")
    try:
        return _de_blob(salida)
    finally:
        kernel32.LocalFree(salida.pbData)
        del buffer


# --- Clave de API ------------------------------------------------------------


def guardar_clave_api(clave: str) -> None:
    """Guarda la clave cifrada. Una clave vacia la borra."""
    DIR_PERFIL.mkdir(parents=True, exist_ok=True)
    if not clave.strip():
        borrar_clave_api()
        return
    ARCHIVO_CLAVE.write_bytes(_cifrar(clave.strip().encode("utf-8")))
    log.info("clave de API guardada (cifrada con DPAPI)")


def leer_clave_api() -> str | None:
    """Devuelve la clave guardada, o None si no hay o no se puede abrir."""
    if not ARCHIVO_CLAVE.exists():
        return None
    try:
        return _descifrar(ARCHIVO_CLAVE.read_bytes()).decode("utf-8").strip()
    except OSError as exc:
        # Ocurre si el archivo se copio de otra maquina o de otra cuenta: DPAPI
        # lo ata al usuario de Windows y no se puede abrir en otro.
        log.warning("hay una clave guardada pero no se puede descifrar: %s", exc)
        return None


def borrar_clave_api() -> None:
    ARCHIVO_CLAVE.unlink(missing_ok=True)


def hay_clave_api() -> bool:
    return ARCHIVO_CLAVE.exists()


# --- Configuracion (no secreta) ---------------------------------------------


def leer_config() -> dict:
    datos = dict(CONFIG_POR_DEFECTO)
    if ARCHIVO_CONFIG.exists():
        try:
            guardado = json.loads(ARCHIVO_CONFIG.read_text(encoding="utf-8"))
            if isinstance(guardado, dict):
                datos.update({k: v for k, v in guardado.items() if k in CONFIG_POR_DEFECTO})
        except (OSError, ValueError) as exc:
            log.warning("configuracion ilegible, se usan los valores por defecto: %s", exc)
    return datos


def guardar_config(config: dict) -> None:
    DIR_PERFIL.mkdir(parents=True, exist_ok=True)
    limpio = {k: config[k] for k in CONFIG_POR_DEFECTO if k in config}
    ARCHIVO_CONFIG.write_text(json.dumps(limpio, indent=2, ensure_ascii=False), encoding="utf-8")


# El nombre de la accion no es la llave del config: separamos las dos cosas para
# que el resto del codigo no tenga que saber como se llama el campo.
_LLAVE_ATAJO = {
    "corregir": "hotkey_corregir",
    "deshacer": "hotkey_deshacer",
    "rehacer": "hotkey_rehacer",
}


def guardar_atajo(accion: str, texto: str) -> None:
    """
    Persiste el atajo de una accion en el perfil.

    El texto se guarda tal cual, ya normalizado por el parser. Si la accion no
    tiene llave conocida se ignora en silencio: no hay nada que persistir.
    """
    llave = _LLAVE_ATAJO.get(accion)
    if llave is None:
        log.debug("accion %r sin llave de configuracion", accion)
        return
    config = leer_config()
    config[llave] = texto.upper()
    guardar_config(config)
    log.info("atajo de %s guardado en el perfil: %s", accion, texto.upper())


def ruta_perfil() -> Path:
    return DIR_PERFIL


# --- Inicio automatico --------------------------------------------------------
# Se usa HKCU y no el registro de maquina a proposito: que el corrector arranque
# solo para el usuario que lo instalo, no para todos los que usan el equipo.


def _clave_run() -> str:
    return r"Software\Microsoft\Windows\CurrentVersion\Run"


def ruta_ejecutable() -> Path:
    """El ejecutable tal como se lanzo, incluso si esta dentro de un .exe."""
    if getattr(__import__("sys"), "frozen", False):
        import sys

        return Path(sys.executable)
    return Path(__file__).resolve().parents[2] / "iniciar.bat"


def iniciar_con_windows() -> bool:
    """Programa el arranque automatico. True si quedo activado."""
    import winreg

    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _clave_run(), 0, winreg.KEY_SET_VALUE) as k:
        winreg.SetValueEx(k, "g360-textofix", 0, winreg.REG_SZ, f'"{ruta_ejecutable()}"')
    log.info("inicio automatico activado: %s", ruta_ejecutable())
    return True


def quitar_inicio_con_windows() -> bool:
    import winreg

    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _clave_run(), 0, winreg.KEY_SET_VALUE) as k:
        try:
            winreg.DeleteValue(k, "g360-textofix")
        except FileNotFoundError:
            pass
    log.info("inicio automatico quitado")
    return False


def tiene_inicio_con_windows() -> bool:
    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _clave_run()) as k:
            winreg.QueryValueEx(k, "g360-textofix")
        return True
    except (FileNotFoundError, OSError):
        return False
