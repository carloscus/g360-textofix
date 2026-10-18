"""
Genera el icono de g360-textofix.
Marca G360 (3 puntos + chevron) sobre fondo oscuro.

Adaptacion cuadrada de logo-g360.svg (g360-ventas-pulse/static):
  <circle cx=20 cy=20 r=5 fill=gris />
  <circle cx=20 cy=40 r=5 fill=verde glow />
  <circle cx=20 cy=60 r=5 fill=gris />
  <path d="M45 20 L 65 40 L 45 60" stroke=verde stroke-width=6 glow />
El texto "G360 BY CCUSI" se omite: ilegible a tamano de bandeja (16 px).
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

FONDO = (11, 18, 32, 255)
VERDE = (0, 208, 132, 255)
GRIS = (148, 163, 184, 255)  # #94a3b8, mismo gris del logo
TAM = 256


def dibujar() -> Image.Image:
    im = Image.new("RGBA", (TAM, TAM), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle([0, 0, TAM - 1, TAM - 1], radius=int(TAM * 0.2), fill=FONDO)

    # Proporcion del logo: stroke-width 6 en viewBox 70 de alto = 8.6%.
    # En cuadrado con puntos a la izquierda hay mas aire que en el chevron
    # solo, pero 6% sigue siendo lo maximo sin que la punta se fusione.
    grosor = int(0.06 * TAM)  # 15 px en 256

    # Marca centrada: puntos en x=82, chevron de 126 a 178.
    radio = 12  # logo: r=5 vs stroke 6 -> radio ~ 0.83 * grosor
    puntos_y = [80, 128, 176]
    chevron = [(126, 80), (178, 128), (126, 176)]

    # Glow suave del elemento verde, como el filtro feGaussianBlur del SVG.
    glow = Image.new("RGBA", (TAM, TAM), (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow)
    gd.ellipse([82 - radio, puntos_y[1] - radio, 82 + radio, puntos_y[1] + radio], fill=VERDE)
    gd.line(chevron, fill=VERDE, width=grosor, joint="curve")
    glow = glow.filter(ImageFilter.GaussianBlur(6))
    im = Image.alpha_composite(im, glow)

    # Formas nítidas encima del glow.
    d = ImageDraw.Draw(im)
    for i, cy in enumerate(puntos_y):
        color = VERDE if i == 1 else GRIS
        d.ellipse([82 - radio, cy - radio, 82 + radio, cy + radio], fill=color)
    d.line(chevron, fill=VERDE, width=grosor, joint="curve")

    return im


def _ico(ruta: Path, im: Image.Image) -> None:
    import io
    import struct

    blobs = []
    for tam in [16, 20, 24, 32, 48, 64, 128, 256]:
        b = io.BytesIO()
        im.resize((tam, tam), Image.LANCZOS).save(b, format="PNG")
        blobs.append(b.getvalue())
    desp = 6 + 16 * len(blobs)
    entradas = []
    for tam, blob in zip([16, 20, 24, 32, 48, 64, 128, 256], blobs):
        entradas.append(
            struct.pack("<BBBBHHII", tam & 0xFF, tam & 0xFF, 0, 0, 1, 32, len(blob), desp)
        )
        desp += len(blob)
    ruta.write_bytes(struct.pack("<HHH", 0, 1, len(blobs)) + b"".join(entradas) + b"".join(blobs))


def principal(destino: Path | None = None) -> None:
    raiz = Path(__file__).resolve().parents[1]
    dest = destino or (raiz / "assets" / "g360-textofix.ico")
    dest.parent.mkdir(parents=True, exist_ok=True)
    im = dibujar()
    if dest.suffix.lower() == ".png":
        im.save(dest)
    else:
        _ico(dest, im)
        im.save(dest.with_suffix(".png"))
    print(f"icono: {dest}")


if __name__ == "__main__":
    import sys

    arg = Path(sys.argv[1]) if len(sys.argv) > 1 else None
    principal(arg)
