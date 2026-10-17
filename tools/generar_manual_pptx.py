"""
Genera el manual de usuario en PowerPoint.

Salida: docs/manual-g360-textofix.pptx

Para regenerating:
    uvx --from python-pptx python tools/generar_manual_pptx.py
"""

from __future__ import annotations

import sys
from pathlib import Path

from pptx import Presentation
from pptx.util import Inches, Pt, Emu
from pptx.dml.color import RGBColor

# Colores G360
VERDE = RGBColor(0x00, 0xD0, 0x84)
NEGRO = RGBColor(0x0B, 0x12, 0x20)
GRIS_CLARO = RGBColor(0xE9, 0xEC, 0xF2)
GRIS_OSCURO = RGBColor(0x2A, 0x2E, 0x39)
BLANCO = RGBColor(0xFF, 0xFF, 0xFF)


def _nuevo_pptx() -> Presentation:
    prs = Presentation()
    # 16:9
    prs.slide_width = Inches(13.333)
    prs.slide_height = Inches(7.5)
    return prs


def _slide_vacia(prs: Presentation):
    layout = prs.slide_layouts[6]  # blank
    return prs.slides.add_slide(layout)


def _fondo(slide, color: RGBColor) -> None:
    bg = slide.shapes.add_shape(
        1,  # rectangle
        Emu(0),
        Emu(0),
        prs.slide_width,
        prs.slide_height,
    )
    bg.fill.solid()
    bg.fill.fore_color.rgb = color
    bg.line.fill.background()
    bg.shadow.inherit = False


# No se accede a prs desde dentro de esta funcion; usar modulo global.
def _rect(slide, x, y, w, h, color: RGBColor, line_color: RGBColor | None = None):
    shape = slide.shapes.add_shape(1, x, y, w, h)
    shape.fill.solid()
    shape.fill.fore_color.rgb = color
    if line_color is None:
        shape.line.fill.background()
    else:
        shape.line.color.rgb = line_color
    shape.shadow.inherit = False
    return shape


def _texto(slide, x, y, w, h, texto, size=18, bold=False, color=NEGRO, alinear_left=True):
    box = slide.shapes.add_textbox(x, y, w, h)
    tf = box.text_frame
    tf.word_wrap = True
    p = tf.paragraphs[0]
    p.alignment = 1 if alinear_left else 2  # LEFT=1, CENTER=2
    run = p.add_run()
    run.text = texto
    run.font.size = Pt(size)
    run.font.bold = bold
    run.font.color.rgb = color
    return box


def _tito_cabecera(slide, titulo: str, sub: str = ""):
    """Tira verde superior + titulo."""
    _rect(slide, Emu(0), Emu(0), prs.slide_width, Inches(0.42), VERDE)
    _texto(
        slide,
        Inches(0.5),
        Inches(0.55),
        prs.slide_width - Inches(1),
        Inches(0.8),
        titulo,
        size=32,
        bold=True,
        color=NEGRO,
    )
    if sub:
        _texto(
            slide,
            Inches(0.5),
            Inches(1.15),
            prs.slide_width - Inches(1),
            Inches(0.5),
            sub,
            size=14,
            color=GRIS_OSCURO,
        )


def _pie(slide, n: int, total: int):
    _texto(
        slide,
        prs.slide_width - Inches(1.5),
        prs.slide_height - Inches(0.5),
        Inches(1),
        Inches(0.4),
        f"{n} / {total}",
        size=10,
        color=GRIS_OSCURO,
    )


TOTAL_SLIDES = 9


def slide_portada():
    s = _slide_vacia(prs)
    _fondo(s, NEGRO)
    # barra verde
    _rect(s, Emu(0), prs.slide_height - Inches(0.6), prs.slide_width, Inches(0.6), VERDE)

    # Logo G360 simplificado: 3 barras
    _rect(s, Inches(0.6), Inches(0.6), Inches(0.35), Inches(0.8), GRIS_CLARO)
    _rect(s, Inches(1.05), Inches(0.6), Inches(0.35), Inches(0.8), VERDE)
    _rect(s, Inches(1.5), Inches(0.6), Inches(0.35), Inches(0.8), GRIS_CLARO)

    _texto(
        s,
        Inches(0.8),
        Inches(2.6),
        Inches(11.5),
        Inches(1.2),
        "g360-textofix",
        size=60,
        bold=True,
        color=VERDE,
    )
    _texto(
        s,
        Inches(0.8),
        Inches(3.7),
        Inches(11.5),
        Inches(0.8),
        "Manual de usuario",
        size=28,
        color=BLANCO,
    )
    _texto(
        s,
        Inches(0.8),
        Inches(4.5),
        Inches(11.5),
        Inches(0.6),
        "Corrector de texto para Windows · atajo global · corrección con Gemini",
        size=16,
        color=GRIS_CLARO,
    )


def slide_1_ques():
    s = _slide_vacia(prs)
    _fondo(s, BLANCO)
    _tito_cabecera(
        s, "¿Qué es?", "Un atajo global corrige el texto donde esté, sin cambiar de app."
    )

    bloques = [
        ("Seleccionás el texto", "en cualquier app: Word, Excel, correo, navegador, Flet."),
        ("Apretás Ctrl+Shift+E", "y el texto se corrige y se reemplaza donde estaba."),
        ("Preserva el formato", "no toca lo que el usuario no seleccionó."),
        ("Deshacer: Ctrl+Shift+Z", "Rehacer: Ctrl+Shift+R."),
    ]
    y = Inches(1.6)
    for i, (a, b) in enumerate(bloques):
        _rect(s, Inches(0.6), y, Inches(12.1), Inches(1.1), GRIS_CLARO)
        _rect(s, Inches(0.6), y, Inches(0.15), Inches(1.1), VERDE)
        _texto(
            s,
            Inches(0.95),
            y + Inches(0.12),
            Inches(11.5),
            Inches(0.4),
            f"{i + 1}.  {a}",
            size=20,
            bold=True,
            color=NEGRO,
        )
        _texto(
            s,
            Inches(0.95),
            y + Inches(0.55),
            Inches(11.5),
            Inches(0.4),
            b,
            size=15,
            color=GRIS_OSCURO,
        )
        y += Inches(1.25)
    _pie(s, 1, TOTAL_SLIDES)


def slide_2_atajos():
    s = _slide_vacia(prs)
    _fondo(s, BLANCO)
    _tito_cabecera(s, "Atajos por defecto", "Cambiables desde la bandeja. No necesitan reiniciar.")

    filas = [
        ("Corregir", "Ctrl + Shift + E"),
        ("Deshacer", "Ctrl + Shift + Z"),
        ("Rehacer", "Ctrl + Shift + R"),
    ]
    y = Inches(1.7)
    for accion, comb in filas:
        _rect(s, Inches(0.6), y, Inches(12.1), Inches(0.9), GRIS_CLARO)
        _texto(
            s,
            Inches(0.9),
            y + Inches(0.15),
            Inches(3.5),
            Inches(0.6),
            accion,
            size=20,
            bold=True,
            color=NEGRO,
        )
        _texto(
            s,
            Inches(5),
            y + Inches(0.15),
            Inches(7.5),
            Inches(0.6),
            comb,
            size=22,
            bold=True,
            color=VERDE,
        )
        y += Inches(1.05)

    _texto(
        s,
        Inches(0.6),
        y + Inches(0.2),
        Inches(12.1),
        Inches(0.5),
        "Formato: CTRL/ALT/SHIFT/WIN + letra, dígito, F1–F24, SPACE, ESC, ENTER, "
        "TAB, INSERT, DELETE, HOME, END, PGUP, PGDN.",
        size=14,
        color=GRIS_OSCURO,
    )
    _texto(
        s,
        Inches(0.6),
        y + Inches(0.7),
        Inches(12.1),
        Inches(0.5),
        "Dos acciones no pueden compartir el mismo atajo: Windows no lo acepta.",
        size=14,
        color=GRIS_OSCURO,
    )
    _pie(s, 2, TOTAL_SLIDES)


def slide_3_bandeja():
    s = _slide_vacia(prs)
    _fondo(s, BLANCO)
    _tito_cabecera(s, "La bandeja del sistema", "El corrector vive en el icono, no en una ventana.")

    items = [
        ("Activo · Modo IA", "Estado actual; no es un botón."),
        ("Deshacer / Rehacer", "En gris si no hay nada para aplicar."),
        ("Cambiar atajo…", "Valida, registra en caliente y guarda en el perfil."),
        ("Configurar clave API…", "Pide la clave y la guarda cifrada con DPAPI."),
        ("Iniciar con Windows", "Registra en HKCU, solo para tu cuenta."),
        ("Salir", "Suelta los atajos y cierra la bandeja."),
    ]
    y = Inches(1.6)
    for nombre, desc in items:
        _rect(s, Inches(0.6), y, Inches(12.1), Inches(0.75), GRIS_CLARO)
        _rect(s, Inches(0.6), y, Inches(0.12), Inches(0.75), VERDE)
        _texto(
            s,
            Inches(0.9),
            y + Inches(0.06),
            Inches(4.5),
            Inches(0.5),
            nombre,
            size=16,
            bold=True,
            color=NEGRO,
        )
        _texto(
            s,
            Inches(5.5),
            y + Inches(0.06),
            Inches(7.1),
            Inches(0.5),
            desc,
            size=13,
            color=GRIS_OSCURO,
        )
        y += Inches(0.82)
    _pie(s, 3, TOTAL_SLIDES)


def slide_4_deshacer():
    s = _slide_vacia(prs)
    _fondo(s, BLANCO)
    _tito_cabecera(
        s, "Deshacer y rehacer", "Determinista en cualquier app; no depende del Ctrl+Z nativo."
    )

    reglas = [
        (
            "Una sola corrección",
            "Se guarda el par (original, corregido). No es historial: se pierde al cerrar y nunca toca disco.",
        ),
        (
            "Solo en la misma app",
            "Si corregiste en Flet y cambiaste a Word, Ctrl+Shift+Z suena y no escribe nada.",
        ),
        (
            "Se invalida si editaste",
            "Si el usuario tocó el texto después, el búfer se pone gris. Escribir sobre lo que el usuario puso sería peor que no deshacer.",
        ),
        (
            "Si la escritura falla, se revierte",
            "El búfer no cree que aplicó algo que no se escribió.",
        ),
    ]
    y = Inches(1.7)
    for nombre, desc in reglas:
        _rect(s, Inches(0.6), y, Inches(12.1), Inches(1.1), GRIS_CLARO)
        _rect(s, Inches(0.6), y, Inches(0.15), Inches(1.1), VERDE)
        _texto(
            s,
            Inches(0.95),
            y + Inches(0.12),
            Inches(11.5),
            Inches(0.4),
            nombre,
            size=18,
            bold=True,
            color=NEGRO,
        )
        _texto(
            s,
            Inches(0.95),
            y + Inches(0.5),
            Inches(11.5),
            Inches(0.5),
            desc,
            size=14,
            color=GRIS_OSCURO,
        )
        y += Inches(1.22)
    _pie(s, 4, TOTAL_SLIDES)


def slide_5_clave():
    s = _slide_vacia(prs)
    _fondo(s, BLANCO)
    _tito_cabecera(
        s,
        "La clave de Gemini",
        "Primera vez te la pide la consola, luego vive cifrada en tu perfil.",
    )

    _texto(
        s,
        Inches(0.6),
        Inches(1.7),
        Inches(12.1),
        Inches(0.5),
        "Orden en que se busca:",
        size=16,
        bold=True,
        color=NEGRO,
    )
    orden = [
        "El almacén cifrado de Windows (DPAPI) — %APPDATA%\\g360-textofix\\clave.dat",
        "El entorno GEMINI_API_KEY o el .env en la carpeta del proyecto",
    ]
    y = Inches(2.25)
    for i, texto in enumerate(orden, start=1):
        _rect(s, Inches(0.9), y, Inches(0.5), Inches(0.5), VERDE)
        _texto(
            s,
            Inches(0.95),
            y + Inches(0.05),
            Inches(0.4),
            Inches(0.4),
            str(i),
            size=16,
            bold=True,
            color=BLANCO,
        )
        _texto(
            s,
            Inches(1.6),
            y + Inches(0.05),
            Inches(11.1),
            Inches(0.45),
            texto,
            size=15,
            color=NEGRO,
        )
        y += Inches(0.6)

    _rect(s, Inches(0.6), y + Inches(0.15), Inches(12.1), Inches(0.85), GRIS_CLARO)
    _rect(s, Inches(0.6), y + Inches(0.15), Inches(0.15), Inches(0.85), VERDE)
    _texto(
        s,
        Inches(0.95),
        y + Inches(0.28),
        Inches(11.5),
        Inches(0.4),
        "DPAPI ata la clave a tu cuenta: copiar clave.dat a otra máquina no sirve de nada.",
        size=15,
        bold=True,
        color=NEGRO,
    )
    _texto(
        s,
        Inches(0.95),
        y + Inches(0.65),
        Inches(11.5),
        Inches(0.4),
        "Cambiarla desde la bandeja (Configurar clave API…) la hace efectiva al instante, sin reiniciar.",
        size=14,
        color=GRIS_OSCURO,
    )
    _pie(s, 5, TOTAL_SLIDES)


def slide_6_apps():
    s = _slide_vacia(prs)
    _fondo(s, BLANCO)
    _tito_cabecera(s, "Apps verificadas", "No está todo: lo que no dice está sin probar.")

    tab = [
        ("Win32 EDIT, Bloc de notas", "Captura ✅ · Reemplazo ✅"),
        ("Word y Excel", "Captura ✅ · Reemplazo ✅ · Formulas y celdas protegidas no se tocan"),
        ("Chrome: textarea y contenteditable", "Captura ✅ · Reemplazo ✅"),
        (
            "Flet / Flutter (campos)",
            "Captura ✅ · Reemplazo ✅ · Sin Ctrl+C ni TextPattern: escribe a mano",
        ),
        (
            "Outlook (redactar)",
            "Captura ✅ · Reemplazo ✅ · No acepta Ctrl+V sintético: escribe a mano",
        ),
        ("Outlook (bandeja, solo lectura)", "Captura ✅ · Reemplazo ❌ · Intencional: es lectura"),
        (
            "ERP Centura (elevado)",
            "Detectado · No se corrige · La app corre como admin y UIPI lo bloquea",
        ),
    ]
    y = Inches(1.6)
    for app, detalle in tab:
        _rect(s, Inches(0.6), y, Inches(12.1), Inches(0.62), GRIS_CLARO)
        _texto(
            s,
            Inches(0.9),
            y + Inches(0.08),
            Inches(4.5),
            Inches(0.5),
            app,
            size=14,
            bold=True,
            color=NEGRO,
        )
        _texto(
            s,
            Inches(5.5),
            y + Inches(0.08),
            Inches(7.1),
            Inches(0.5),
            detalle,
            size=13,
            color=GRIS_OSCURO,
        )
        y += Inches(0.68)
    _pie(s, 6, TOTAL_SLIDES)


def slide_7_seguridad():
    s = _slide_vacia(prs)
    _fondo(s, BLANCO)
    _tito_cabecera(
        s, "Privacidad y garantías", "El principio: ante cualquier duda, no se escribe nada."
    )

    bloques = [
        (
            "No hay historial",
            "Ninguna corrección se guarda a disco. El búfer de deshacer vive en memoria y se pierde al cerrar.",
        ),
        (
            "Los logs no tienen texto",
            "Solo longitud y un hash. El texto corre por memoria y viaja por callback, no por el log.",
        ),
        (
            "El portapapeles se restaura",
            "Si la corrección falla, tu portapapeles queda como estaba.",
        ),
        (
            "La clave cifrada vive solo en tu cuenta",
            "DPAPI: copiar el archivo a otro equipo no descifra la clave.",
        ),
        (
            "Nada se entrena con tu texto",
            "En la cuota de pago, los términos de Gemini lo garantizan. En la gratuita, Google sí usa los textos para mejorar su modelo.",
        ),
    ]
    y = Inches(1.65)
    for nombre, desc in bloques:
        _rect(s, Inches(0.6), y, Inches(12.1), Inches(0.92), GRIS_CLARO)
        _rect(s, Inches(0.6), y, Inches(0.14), Inches(0.92), VERDE)
        _texto(
            s,
            Inches(0.9),
            y + Inches(0.09),
            Inches(11.7),
            Inches(0.35),
            nombre,
            size=15,
            bold=True,
            color=NEGRO,
        )
        _texto(
            s,
            Inches(0.9),
            y + Inches(0.42),
            Inches(11.7),
            Inches(0.5),
            desc,
            size=13,
            color=GRIS_OSCURO,
        )
        y += Inches(1.0)
    _pie(s, 7, TOTAL_SLIDES)


def slide_8_distribuir():
    s = _slide_vacia(prs)
    _fondo(s, BLANCO)
    _tito_cabecera(s, "Repartir el .exe", "Un archivo por usuario. Ningún secreto adentro.")

    pasos = [
        ("Empaquetar", "uv sync --extra pack y después uvx pyinstaller textofix.spec --noconfirm"),
        (
            "Repartir",
            "Pasás dist/g360-textofix.exe a quien lo necesite. No lleva la clave ni ningún secreto.",
        ),
        (
            "Primera vez",
            "La consola pide la clave, la guarda cifrada y en el próximo arranque ya no.",
        ),
        (
            "Cada usuario, su cuota",
            "La clave es personal. El .exe no hace uso de la cuota de otro.",
        ),
        (
            "Anti-virus",
            "Si se detecta como falso positivo, Nuitka produce un binario más discreto: uv run python -m nuitka --onefile src/main.py",
        ),
    ]
    y = Inches(1.65)
    for i, (a, b) in enumerate(pasos, start=1):
        _rect(s, Inches(0.6), y, Inches(12.1), Inches(0.95), GRIS_CLARO)
        _rect(s, Inches(0.6), y, Inches(0.42), Inches(0.95), VERDE)
        _texto(
            s,
            Inches(0.72),
            y + Inches(0.28),
            Inches(0.3),
            Inches(0.4),
            str(i),
            size=18,
            bold=True,
            color=BLANCO,
        )
        _texto(
            s,
            Inches(1.15),
            y + Inches(0.09),
            Inches(11.3),
            Inches(0.35),
            a,
            size=16,
            bold=True,
            color=NEGRO,
        )
        _texto(
            s,
            Inches(1.15),
            y + Inches(0.45),
            Inches(11.3),
            Inches(0.5),
            b,
            size=13,
            color=GRIS_OSCURO,
        )
        y += Inches(1.05)
    _pie(s, 8, TOTAL_SLIDES)


def slide_9_cuota():
    s = _slide_vacia(prs)
    _fondo(s, NEGRO)
    _tito_cabecera(
        s,
        "Cuota gratuita vs de pago",
        "Para uso personal alcanza la gratuita; para empresa, la de pago.",
    )

    _texto(
        s,
        Inches(0.6),
        Inches(1.7),
        Inches(12.1),
        Inches(0.5),
        "Gratuita",
        size=18,
        bold=True,
        color=VERDE,
    )
    _texto(
        s,
        Inches(0.6),
        Inches(2.15),
        Inches(12.1),
        Inches(1.4),
        "· ~5 pedidos por minuto, suficiente para uso personal.\n"
        "· --bateria necesita --pausa 13 para no agotar la cuota.\n"
        "· Google usa los textos para mejorar el modelo.",
        size=14,
        color=BLANCO,
    )

    _texto(
        s,
        Inches(0.6),
        Inches(3.9),
        Inches(12.1),
        Inches(0.5),
        "De pago",
        size=18,
        bold=True,
        color=VERDE,
    )
    _texto(
        s,
        Inches(0.6),
        Inches(4.35),
        Inches(12.1),
        Inches(1.4),
        "· Los términos de Gemini garantizan que no se entrena con tu texto.\n"
        "· Corrección sobre correo, documentos o datos de una empresa\n"
        "  exige esta opción, no por el límite, sino por los términos.",
        size=14,
        color=BLANCO,
    )

    _pie(s, 9, TOTAL_SLIDES)


def main():
    global prs
    prs = _nuevo_pptx()

    slide_portada()
    slide_1_ques()
    slide_2_atajos()
    slide_3_bandeja()
    slide_4_deshacer()
    slide_5_clave()
    slide_6_apps()
    slide_7_seguridad()
    slide_8_distribuir()
    slide_9_cuota()

    salida = Path(__file__).resolve().parents[1] / "docs" / "manual-g360-textofix.pptx"
    salida.parent.mkdir(parents=True, exist_ok=True)
    prs.save(str(salida))
    print(f"Listo: {salida}")
    print(f"Slides: {len(prs.slides._sldIdLst)}")


if __name__ == "__main__":
    sys.exit(main())
