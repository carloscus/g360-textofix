"""
Genera el icono de g360-textofix.
Chevron > verde sobre fondo oscuro.

SVG original: viewBox="0 0 20 20", polyline points="6 4 14 10 6 16"
"""

from __future__ import annotations
from pathlib import Path
from PIL import Image, ImageDraw

FONDO = (11, 18, 32, 255)
VERDE = (0, 208, 132, 255)
TAM = 256
S = TAM / 20.0  # 1 unidad SVG = 12.8 px


def dibujar() -> Image.Image:
    im = Image.new("RGBA", (TAM, TAM), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle([0, 0, TAM - 1, TAM - 1], radius=int(TAM * 0.2), fill=FONDO)

    # El SVG usa stroke-width=2 en un viewBox de 20 unidades.
    # Proporcion: 2/20 = 10% del tamano del canvas.
    # PERO: en un angulo de 106 grados, 10% hace que las dos lineas
    # se superpongan cerca de la punta. 6% es lo maximo que se puede
    # usar sin que se fusionen en un trapecio.
    grosor = int(0.06 * TAM)  # 15 px en 256

    # Puntos del SVG
    p1 = (int(6 * S), int(4 * S))  # (76, 51)
    p2 = (int(14 * S), int(10 * S))  # (179, 128)
    p3 = (int(6 * S), int(16 * S))  # (76, 204)

    # Dibujar como poligono ABIERTO (no cerrado) para que no se rellene
    puntos = [p1, p2, p3]
    d.line(puntos, fill=VERDE, width=grosor, joint="curve")

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
