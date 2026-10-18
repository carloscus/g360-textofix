"""
Genera el icono de g360-textofix.
Un chevron > verde sobre fondo oscuro.
"""

from __future__ import annotations
from pathlib import Path
from PIL import Image, ImageDraw

FONDO = (11, 18, 32, 255)
VERDE = (0, 208, 132, 255)
TAM = 256


def dibujar() -> Image.Image:
    im = Image.new("RGBA", (TAM, TAM), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle([0, 0, TAM - 1, TAM - 1], radius=int(TAM * 0.25), fill=FONDO)

    # Chevron mas grande y delgado
    grosor = 10

    # Coordenadas corregidas para que se vea la V
    # Punto izquierdo arriba
    x1, y1 = 60, 70
    # Punto derecho centro
    x2, y2 = 200, 128
    # Punto izquierdo abajo
    x3, y3 = 60, 186

    # Linea superior
    d.line([(x1, y1), (x2, y2)], fill=VERDE, width=grosor)
    # Linea inferior
    d.line([(x2, y2), (x3, y3)], fill=VERDE, width=grosor)

    return im


def _ico(ruta: Path, im: Image.Image) -> None:
    import io, struct

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


def principal():
    raiz = Path(__file__).resolve().parents[1]
    dest = raiz / "assets" / "g360-textofix.ico"
    dest.parent.mkdir(parents=True, exist_ok=True)
    im = dibujar()
    _ico(dest, im)
    im.save(dest.with_suffix(".png"))
    print(f"icono: {dest}")


if __name__ == "__main__":
    principal()
