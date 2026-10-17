"""
Genera el icono de g360-textofix.

Restriccion real: en la bandeja del sistema el icono mide 16 px de verdad. Un
logotipo detallado a ese tamano es una mancha, asi que hay dos disenos:

- 16, 20 y 24 px: version compacta, solo las tres barras, mas gruesas y anchas.
- 32 px en adelante: version completa, con el chevron.

    uv run --with pillow python tools/generar_icono.py
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

# Paleta de la identidad G360
FONDO = (11, 18, 32, 255)
GRIS = (156, 163, 175, 255)
VERDE = (0, 208, 132, 255)
CLARO = (226, 232, 240, 255)

TAM = 1024
G = TAM / 256.0  # todo se dibuja sobre una grilla de 256


def _barra(d, x0, y0, x1, y1, color) -> None:
    d.rounded_rectangle([x0, y0, x1, y1], radius=(x1 - x0) // 2, fill=color)


def dibujar(chevron: bool = True) -> Image.Image:
    """Icono sobre una grilla de 256.

    Sin chevron las barras tienen espacio para ser mas gruesas y seguir
    leyendose como tres, que es lo que importa a 16 px.
    """
    im = Image.new("RGBA", (TAM, TAM), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle([0, 0, TAM - 1, TAM - 1], radius=int(TAM * 0.22), fill=FONDO)

    if chevron:
        ancho, hueco, top, bot = 46, 10, 60, 196
        x = int(30 * G)
        for color in (GRIS, VERDE, GRIS):
            _barra(d, x, int(top * G), x + int(ancho * G), int(bot * G), color)
            x += int((ancho + hueco) * G)

        grosor = int(22 * G)
        x_izq, x_punta = int(196 * G), int(236 * G)
        y_arriba, y_medio, y_abajo = int(84 * G), int(128 * G), int(172 * G)
        d.line([(x_izq, y_arriba), (x_punta, y_medio)], fill=CLARO, width=grosor)
        d.line([(x_punta, y_medio), (x_izq, y_abajo)], fill=CLARO, width=grosor)
        radio = grosor // 2
        for cx, cy in ((x_izq, y_arriba), (x_punta, y_medio), (x_izq, y_abajo)):
            d.ellipse([cx - radio, cy - radio, cx + radio, cy + radio], fill=CLARO)
    else:
        ancho, hueco, top, bot = 62, 12, 52, 204
        x = int(26 * G)
        for color in (GRIS, VERDE, GRIS):
            _barra(d, x, int(top * G), x + int(ancho * G), int(bot * G), color)
            x += int((ancho + hueco) * G)

    return im


def _escribir_ico(ruta: Path, marcos: list) -> None:
    """
    Arma un .ico con una imagen distinta por medida.

    Pillow redimensiona una sola imagen para todas cuando se le pasa `sizes`,
    asi que el archivo se escribe a mano. Las entradas usan PNG, que Windows y
    pystray aceptan sin problema.
    """
    import io
    import struct

    blobs = []
    for tam, imagen in marcos:
        buffer = io.BytesIO()
        imagen.resize((tam, tam), Image.LANCZOS).save(buffer, format="PNG", optimize=True)
        blobs.append(buffer.getvalue())

    desplazamiento = 6 + 16 * len(blobs)
    entradas = []
    for (tam, _), blob in zip(marcos, blobs):
        entradas.append(
            struct.pack(
                "<BBBBHHII",
                tam & 0xFF,  # 0 significa 256
                tam & 0xFF,
                0,  # paleta
                0,  # reservado
                1,  # planos de color
                32,  # bits por pixel
                len(blob),
                desplazamiento,
            )
        )
        desplazamiento += len(blob)

    ruta.write_bytes(struct.pack("<HHH", 0, 1, len(blobs)) + b"".join(entradas) + b"".join(blobs))


def principal() -> None:
    raiz = Path(__file__).resolve().parents[1]
    destino = raiz / "assets" / "g360-textofix.ico"
    destino.parent.mkdir(parents=True, exist_ok=True)

    completo = dibujar(chevron=True)
    compacto = dibujar(chevron=False)

    marcos = [
        (16, compacto),
        (20, compacto),
        (24, compacto),
        (32, completo),
        (48, completo),
        (64, completo),
        (128, completo),
        (256, completo),
    ]

    _escribir_ico(destino, marcos)
    completo.resize((512, 512), Image.LANCZOS).save(destino.with_suffix(".png"))

    print(f"icono: {destino}")
    print("medidas: " + ", ".join(f"{t}px" + ("*" if c is compacto else "") for t, c in marcos))
    print("(* version compacta, sin chevron, para que se lea en la bandeja)")


if __name__ == "__main__":
    principal()
